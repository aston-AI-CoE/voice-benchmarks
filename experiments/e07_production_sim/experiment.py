"""Experiment 07: Production Architecture Simulation.

Simulates how Otto would ACTUALLY work in production:

1. Meeting audio streams through STT → text transcript accumulates
2. At each "Hey Otto" moment, a FRESH voice session opens
3. The accumulated transcript is injected as context (system prompt)
4. User's question is sent as AUDIO
5. Otto responds via voice
6. Session closes

This avoids the E06 problem of one session dying after 30-60 min.
Each question gets a clean session with full context.

Tests:
- STT quality on meeting audio (via the realtime API's Whisper)
- Context comprehension with growing transcript (15/30/60 min of context)
- Voice-to-voice latency per question
- Cold start time for new sessions
- Whether the model can handle a huge system prompt (full meeting transcript)
"""

from __future__ import annotations

import asyncio
import dataclasses
import time

from common.audio import (
    compute_transcription_accuracy,
    load_meeting_audio,
    load_question_audio,
    pcm16_to_base64_chunks,
)
from common.config import setup_logging
from common.provider import RealtimeProvider
from common.scoring import aggregate_scores, score_recall
from experiments.e05_realtime_session_1hr.meeting_1hr import generate_meeting_1hr
from experiments.e05_realtime_session_1hr.realistic_meeting import (
    REALISTIC_SYSTEM_PROMPT,
)

logger = setup_logging("experiment.07")


def _build_context_prompt(transcript_so_far: list[str]) -> str:
    """Build system prompt with accumulated meeting transcript."""
    transcript_text = "\n".join(transcript_so_far)
    return (
        "You are Otto, an AI meeting assistant. Below is the transcript of a meeting "
        "that has been happening. The user is going to ask you a question about the "
        "meeting. Answer based only on what's in the transcript. If something wasn't "
        "discussed, say so honestly. Keep your answers conversational and concise.\n\n"
        "=== MEETING TRANSCRIPT ===\n"
        f"{transcript_text}\n"
        "=== END TRANSCRIPT ==="
    )


async def run(
    provider_factory,
    *,
    dry_run: bool = False,
    skip_scoring: bool = False,
    seconds_per_minute: float = 60.0,
    duration_minutes: int = 0,
    max_lines: int = 0,
    **kwargs,
) -> dict:
    """Run the production architecture simulation.

    NOTE: provider_factory is a callable that returns a NEW provider instance.
    Unlike other experiments, E07 creates multiple sessions (one per question).
    """
    meeting = generate_meeting_1hr()

    if dry_run:
        return _dry_run_result(meeting, seconds_per_minute, duration_minutes)

    # Load audio
    audio_lines = load_meeting_audio("meeting_1hr")
    if duration_minutes > 0:
        audio_lines = [l for l in audio_lines if l["minute"] <= duration_minutes]
        meeting.mid_meeting_questions = [
            q for q in meeting.mid_meeting_questions
            if q.trigger_after_minute <= duration_minutes
        ]
    if max_lines > 0:
        audio_lines = audio_lines[:max_lines]

    try:
        question_audio = load_question_audio("meeting_1hr")
    except FileNotFoundError:
        question_audio = {}

    total_audio_ms = sum(a["duration_ms"] for a in audio_lines)
    logger.info(
        "Starting E07 (production sim) — %d lines, %.1f min audio, %d questions, "
        "questions via %s",
        len(audio_lines), total_audio_ms / 60000,
        len(meeting.mid_meeting_questions),
        "AUDIO" if question_audio else "text",
    )

    # === Phase 1: Stream meeting through STT, accumulate transcript ===
    # Use one session just for transcription (no responses needed)
    logger.info("Phase 1: Streaming meeting audio through STT...")
    stt_provider = provider_factory()
    await stt_provider.connect(instructions="You are listening to a meeting. Do not respond.")

    session_start = time.monotonic()
    transcript_lines: list[str] = []  # accumulated text transcript
    transcription_results = []
    mid_meeting_results = []
    health_checks = []
    last_health_min = -5
    lines_sent = 0
    connection_died_at: str | None = None

    pending_mid_questions = list(meeting.mid_meeting_questions)

    try:
        for i, audio_line in enumerate(audio_lines):
            minute = audio_line["minute"]

            # Health check
            if minute >= last_health_min + 5:
                connected = await stt_provider.is_connected()
                elapsed = (time.monotonic() - session_start) / 60
                health_checks.append({
                    "minute": minute,
                    "elapsed_real_minutes": round(elapsed, 1),
                    "connected": connected,
                    "lines_sent": lines_sent,
                    "phase": "stt",
                })
                logger.info(
                    "--- min %d | elapsed: %.1f min | connected: %s | lines: %d/%d | transcript: %d lines ---",
                    minute, elapsed, connected, lines_sent, len(audio_lines),
                    len(transcript_lines),
                )
                last_health_min = minute

                if not connected:
                    connection_died_at = f"STT session died at minute {minute}"
                    logger.error("STT CONNECTION LOST!")
                    break

            # Stream audio and get transcription
            pcm_chunks = pcm16_to_base64_chunks(audio_line["pcm16_bytes"])
            await stt_provider.send_audio_no_response(pcm_chunks)
            lines_sent += 1

            # Capture transcription
            input_transcript = getattr(stt_provider, "_input_transcript", "").strip()
            if input_transcript:
                transcript_lines.append(f"[{audio_line['speaker']}]: {input_transcript}")
                accuracy = compute_transcription_accuracy(
                    audio_line["text"], input_transcript
                )
                transcription_results.append({
                    "line_index": i,
                    "minute": minute,
                    "speaker": audio_line["speaker"],
                    "original": audio_line["text"],
                    "transcribed": input_transcript,
                    **accuracy,
                })
            else:
                # No transcription — use original text as fallback
                transcript_lines.append(f"[{audio_line['speaker']}]: {audio_line['text']}")

            # === Mid-meeting "Hey Otto" — open fresh session per question ===
            fired = []
            for idx, mq in enumerate(pending_mid_questions):
                if minute >= mq.trigger_after_minute:
                    logger.info("  Hey Otto! (min %d) Opening fresh session...", minute)
                    q_start = time.monotonic()

                    # Build context from transcript so far
                    context_prompt = _build_context_prompt(transcript_lines)

                    # Open a FRESH voice session for this question
                    q_provider = provider_factory()
                    await q_provider.connect(instructions=context_prompt)
                    cold_start_ms = (time.monotonic() - q_start) * 1000

                    # Send question as audio
                    q_id = f"mid_{idx:02d}"
                    q_audio = question_audio.get(q_id)
                    if q_audio:
                        logger.info("  Asking via AUDIO: %s", mq.question[:60])
                        q_chunks = pcm16_to_base64_chunks(q_audio["pcm16_bytes"])
                        turn = await q_provider.send_audio(q_chunks, mq.question)
                    else:
                        logger.info("  Asking via TEXT: %s", mq.question[:60])
                        turn = await q_provider.send_text(mq.question)

                    # Close the question session
                    await q_provider.disconnect()

                    mid_meeting_results.append({
                        "minute": minute,
                        "elapsed_real_seconds": time.monotonic() - session_start,
                        "question": mq.question,
                        "ground_truth": mq.ground_truth,
                        "response": turn.text,
                        "latency_ms": turn.latency_ms,
                        "cold_start_ms": round(cold_start_ms, 1),
                        "context_lines": len(transcript_lines),
                        "context_tokens_approx": sum(len(l.split()) for l in transcript_lines),
                        "sent_as": "audio" if q_audio else "text",
                    })
                    logger.info(
                        "  Response (cold_start=%dms, latency=%sms): %s",
                        cold_start_ms,
                        f"{turn.latency_ms:.0f}" if turn.latency_ms else "?",
                        turn.text[:80],
                    )
                    fired.append(mq)

            for mq in fired:
                pending_mid_questions.remove(mq)

    except Exception as e:
        elapsed = (time.monotonic() - session_start) / 60
        connection_died_at = f"line {lines_sent} ({type(e).__name__}: {e})"
        logger.error("Failed at %.1f min: %s", elapsed, e)

    # Close STT session
    stt_metrics = await stt_provider.get_session_metrics()
    try:
        await stt_provider.disconnect()
    except Exception:
        pass

    session_elapsed = time.monotonic() - session_start
    logger.info(
        "=== Meeting done. Lines: %d/%d | Transcript: %d lines | Elapsed: %.1f min ===",
        lines_sent, len(audio_lines), len(transcript_lines), session_elapsed / 60,
    )

    # === Phase 2: Post-meeting questions (each in fresh session) ===
    post_meeting_results = []
    hallucination_results = []
    full_context = _build_context_prompt(transcript_lines)

    if meeting.post_meeting_questions:
        logger.info("Phase 2: Post-meeting questions (%d, each fresh session)...",
                     len(meeting.post_meeting_questions))
        for q in meeting.post_meeting_questions:
            try:
                q_start = time.monotonic()
                q_provider = provider_factory()
                await q_provider.connect(instructions=full_context)
                cold_start_ms = (time.monotonic() - q_start) * 1000

                q_audio_clip = question_audio.get(q.question_id)
                if q_audio_clip:
                    q_chunks = pcm16_to_base64_chunks(q_audio_clip["pcm16_bytes"])
                    turn = await q_provider.send_audio(q_chunks, q.question)
                else:
                    turn = await q_provider.send_text(q.question)

                await q_provider.disconnect()

                post_meeting_results.append({
                    "question_id": q.question_id,
                    "question": q.question,
                    "ground_truth": q.ground_truth,
                    "category": q.category,
                    "difficulty": q.difficulty,
                    "response": turn.text,
                    "latency_ms": turn.latency_ms,
                    "cold_start_ms": round(cold_start_ms, 1),
                    "context_tokens_approx": sum(len(l.split()) for l in transcript_lines),
                    "sent_as": "audio" if q_audio_clip else "text",
                })
                logger.info("  [%s] cold=%dms → %s", q.question_id, cold_start_ms, turn.text[:70])
            except Exception as e:
                logger.error("  [%s] FAILED: %s", q.question_id, e)

    # Hallucination probes
    if meeting.hallucination_probes:
        logger.info("Hallucination probes (%d)...", len(meeting.hallucination_probes))
        for probe in meeting.hallucination_probes:
            try:
                q_provider = provider_factory()
                await q_provider.connect(instructions=full_context)
                turn = await q_provider.send_text(probe.question)
                await q_provider.disconnect()
                hallucination_results.append({
                    "probe_id": probe.probe_id,
                    "question": probe.question,
                    "expected": "NOT_DISCUSSED",
                    "response": turn.text,
                    "latency_ms": turn.latency_ms,
                })
                logger.info("  [%s] %s", probe.probe_id, turn.text[:70])
            except Exception as e:
                logger.error("  [%s] FAILED: %s", probe.probe_id, e)

    # === Score ===
    scores = []
    halluc_scores = []
    if not skip_scoring and post_meeting_results:
        logger.info("Scoring...")
        for r in post_meeting_results:
            s = await score_recall(
                fact_id=r["question_id"], question=r["question"],
                expected=r["ground_truth"], actual=r["response"],
            )
            scores.append(s)
            logger.info("  [%s] %s credit=%.1f", s.fact_id, s.verdict.value, s.partial_credit)

        for r in hallucination_results:
            s = await score_recall(
                fact_id=r["probe_id"], question=r["question"],
                expected=r["expected"], actual=r["response"],
            )
            halluc_scores.append(s)

    fact_categories = {q.question_id: q.category for q in meeting.post_meeting_questions}
    fact_minutes = {q.question_id: q.source_minute for q in meeting.post_meeting_questions}
    aggregate = aggregate_scores(scores, fact_categories, fact_minutes) if scores else None

    # Transcription summary
    wer_values = [t["wer"] for t in transcription_results]
    avg_wer = sum(wer_values) / len(wer_values) if wer_values else None

    result = {
        "experiment": "e07_production_sim",
        "provider": provider_factory().name,  # hacky but works
        "config": {
            "architecture": "production: STT session + fresh voice session per question",
            "meeting_lines": len(audio_lines),
            "mid_questions": len(meeting.mid_meeting_questions),
            "post_questions": len(meeting.post_meeting_questions),
            "questions_via": "audio" if question_audio else "text",
            "duration_minutes": duration_minutes or "full",
        },
        "session_survival": {
            "stt_lines_sent": lines_sent,
            "stt_lines_total": len(audio_lines),
            "stt_survived": connection_died_at is None,
            "connection_died_at": connection_died_at,
        },
        "timing": {
            "total_elapsed_seconds": session_elapsed,
            "total_elapsed_minutes": session_elapsed / 60,
        },
        "transcription": {
            "total_compared": len(transcription_results),
            "avg_wer": round(avg_wer, 3) if avg_wer is not None else None,
            "details": transcription_results[:20],  # first 20 for brevity
        },
        "health_checks": health_checks,
        "mid_meeting_results": mid_meeting_results,
        "post_meeting_results": post_meeting_results,
        "hallucination_results": hallucination_results,
        "scores": [dataclasses.asdict(s) for s in scores] if scores else [],
        "hallucination_scores": [dataclasses.asdict(s) for s in halluc_scores] if halluc_scores else [],
        "aggregate": dataclasses.asdict(aggregate) if aggregate else None,
        "stt_session_metrics": {
            "items_injected": stt_metrics.items_injected,
            "errors": stt_metrics.errors,
            "connection_drops": stt_metrics.connection_drops,
        },
    }

    if aggregate:
        logger.info(
            "=== RESULTS: accuracy=%.0f%% halluc=%.0f%% avg_wer=%.1f%% cold_start=%.0fms ===",
            aggregate.recall_accuracy * 100,
            aggregate.hallucination_rate * 100,
            (avg_wer or 0) * 100,
            sum(r.get("cold_start_ms", 0) for r in post_meeting_results) / max(len(post_meeting_results), 1),
        )

    return result


def _dry_run_result(meeting, seconds_per_minute, duration_minutes):
    lines = meeting.lines
    if duration_minutes > 0:
        lines = [l for l in lines if l.minute <= duration_minutes]
    words = sum(len(l.text.split()) for l in lines)

    logger.info("DRY RUN: Production simulation (E07)")
    logger.info("  Architecture: STT session + fresh voice session per question")
    logger.info("  Lines: %d (%d words)", len(lines), words)
    logger.info("  Duration: %s min", duration_minutes or "full")
    logger.info("  Mid-meeting questions: %d", len(meeting.mid_meeting_questions))
    logger.info("  Post-meeting questions: %d", len(meeting.post_meeting_questions))
    logger.info("  Each question opens a FRESH session with accumulated transcript as context")

    return {
        "experiment": "e07_production_sim",
        "dry_run": True,
        "lines": len(lines),
        "duration_minutes": duration_minutes or "full",
    }
