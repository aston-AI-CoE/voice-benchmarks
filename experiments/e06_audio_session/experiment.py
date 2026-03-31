"""Experiment 06: Audio Session — Real Voice Pipeline Test.

Unlike E01-E05 which inject text, this experiment streams actual audio
through the WebSocket to test the FULL voice pipeline:

1. TTS generates audio from meeting lines (pre-generated, cached)
2. Audio is streamed as PCM16 base64 chunks at real-time speed
3. The API transcribes the audio (Whisper / built-in STT)
4. We compare transcription against original text (WER)
5. The model responds with audio + text
6. We measure end-to-end audio latency

What this tests that text-only doesn't:
- Speech-to-text accuracy (does Whisper/STT degrade over time?)
- Audio-to-audio latency (real mouth-to-ear delay)
- Voice quality of responses over a long session
- VAD behavior with real audio input
- Full pipeline reliability (TTS → stream → STT → LLM → TTS → response)

Supports two modes:
- Built-in meeting (uses E05's realistic_meeting script, TTS-generated)
- External audio files (pre-recorded .wav or .pcm files)
"""

from __future__ import annotations

import asyncio
import dataclasses
import time
from pathlib import Path

from common.audio import (
    compute_transcription_accuracy,
    load_meeting_audio,
    load_question_audio,
    pcm16_to_base64_chunks,
)
from common.config import setup_logging
from common.provider import RealtimeProvider
from common.scoring import RecallScore, aggregate_scores, score_recall
from experiments.e05_realtime_session_1hr.realistic_meeting import (
    REALISTIC_SYSTEM_PROMPT,
)
from experiments.e05_realtime_session_1hr.meeting_1hr import generate_meeting_1hr

logger = setup_logging("experiment.06")

DEFAULT_SECONDS_PER_MINUTE = 60


async def run(
    provider: RealtimeProvider,
    *,
    dry_run: bool = False,
    skip_scoring: bool = False,
    seconds_per_minute: float = DEFAULT_SECONDS_PER_MINUTE,
    max_lines: int = 0,
    duration_minutes: int = 0,
    **kwargs,
) -> dict:
    """Run the audio session experiment.

    Args:
        max_lines: Limit audio lines to send. 0 = all lines (default).
                   Use 10-20 for quick smoke tests.
    """
    meeting = generate_meeting_1hr()

    if dry_run:
        return _dry_run_result(meeting, seconds_per_minute, max_lines)

    # Phase 1: Load pre-generated audio from fixed fixtures
    audio_lines = load_meeting_audio("meeting_1hr")
    if duration_minutes > 0:
        audio_lines = [l for l in audio_lines if l["minute"] <= duration_minutes]
        logger.info("LIMITED to first %d minutes (%d lines)", duration_minutes, len(audio_lines))
    if max_lines > 0:
        audio_lines = audio_lines[:max_lines]
        logger.info("LIMITED to first %d lines (smoke test mode)", max_lines)
    total_audio_ms = sum(a["duration_ms"] for a in audio_lines)

    # Load question audio (mid-meeting + post-meeting)
    try:
        question_audio = load_question_audio("meeting_1hr")
        logger.info("Loaded %d question audio clips", len(question_audio))
    except FileNotFoundError:
        logger.warning("Question audio not found — falling back to text questions")
        question_audio = {}

    logger.info(
        "Starting E06 (audio session) with %s — %d lines, %.1f min of audio, "
        "questions via %s",
        provider.name, len(audio_lines), total_audio_ms / 60000,
        "AUDIO" if question_audio else "text",
    )

    # Phase 2: Connect — same prompt as E05, no priming
    await provider.connect(instructions=REALISTIC_SYSTEM_PROMPT)
    logger.info("Connected to %s", provider.name)

    session_start = time.monotonic()
    lines_sent = 0
    connection_died_at: str | None = None
    transcription_results = []
    mid_meeting_results = []
    post_meeting_results = []
    hallucination_results = []
    health_checks = []
    current_minute = 0

    pending_mid_questions = list(meeting.mid_meeting_questions)

    # Phase 3: Stream audio meeting — natural pacing
    # Each line plays at real audio speed (no artificial gaps).
    # The meeting takes as long as the audio itself (~50 min for 649 lines).
    last_health_check_min = -5  # force first check immediately

    try:
        for i, audio_line in enumerate(audio_lines):
            minute = audio_line["minute"]
            audio_duration_s = audio_line["duration_ms"] / 1000

            # Health check every 5 script-minutes
            if minute >= last_health_check_min + 5:
                connected = await provider.is_connected()
                elapsed = (time.monotonic() - session_start) / 60
                health_checks.append({
                    "minute": minute,
                    "elapsed_real_minutes": round(elapsed, 1),
                    "connected": connected,
                    "lines_sent": lines_sent,
                })
                logger.info(
                    "--- min %d | elapsed: %.1f real min | connected: %s | lines: %d/%d ---",
                    minute, elapsed, connected, lines_sent, len(audio_lines),
                )
                last_health_check_min = minute

                if not connected:
                    connection_died_at = f"minute {minute} (elapsed {elapsed:.1f} real min)"
                    logger.error("CONNECTION LOST at %s!", connection_died_at)
                    break

            # Stream the audio (send_audio_no_response waits for transcription)
            pcm_chunks = pcm16_to_base64_chunks(audio_line["pcm16_bytes"])

            # Stream audio — send_audio_no_response now waits for
            # the transcription event before returning
            await provider.send_audio_no_response(pcm_chunks)
            lines_sent += 1

            # Read the transcription (populated by the provider after waiting)
            input_transcript = getattr(provider, "_input_transcript", "").strip()
            if input_transcript:
                accuracy = compute_transcription_accuracy(
                    audio_line["text"], input_transcript
                )
                transcription_results.append({
                    "line_index": i,
                    "minute": minute,
                    "speaker": audio_line["speaker"],
                    "original": audio_line["text"],
                    "transcribed": input_transcript,
                    "audio_duration_ms": audio_line["duration_ms"],
                    **accuracy,
                })
                if i % 20 == 0:
                    logger.info(
                        "  Transcription WER: %.1f%% [%s]: %s → %s",
                        accuracy["wer"] * 100,
                        audio_line["speaker"],
                        audio_line["text"][:40],
                        input_transcript[:40],
                    )

            # Mid-meeting questions — sent as AUDIO if available, text as fallback
            fired = []
            for idx, mq in enumerate(pending_mid_questions):
                if minute >= mq.trigger_after_minute:
                    await asyncio.sleep(1)  # natural pause
                    q_id = f"mid_{idx:02d}"
                    q_audio = question_audio.get(q_id)

                    if q_audio:
                        # Send question as audio (realistic — user speaks to Otto)
                        logger.info("  Mid-meeting Q AUDIO (min %d): %s", minute, mq.question[:60])
                        q_chunks = pcm16_to_base64_chunks(q_audio["pcm16_bytes"])
                        turn = await provider.send_audio(q_chunks, mq.question)
                    else:
                        # Fallback to text
                        logger.info("  Mid-meeting Q TEXT (min %d): %s", minute, mq.question[:60])
                        turn = await provider.send_text(mq.question)

                    mid_meeting_results.append({
                        "minute": minute,
                        "elapsed_real_seconds": time.monotonic() - session_start,
                        "question": mq.question,
                        "ground_truth": mq.ground_truth,
                        "response": turn.text,
                        "latency_ms": turn.latency_ms,
                        "sent_as": "audio" if q_audio else "text",
                    })
                    logger.info("  Response: %s", turn.text[:80])
                    fired.append(mq)
            for mq in fired:
                pending_mid_questions.remove(mq)

    except Exception as e:
        elapsed = (time.monotonic() - session_start) / 60
        connection_died_at = f"line {lines_sent} ({type(e).__name__}: {e})"
        logger.error("Session failed at %.1f min: %s", elapsed, e)

    session_elapsed = time.monotonic() - session_start
    logger.info(
        "=== Audio meeting done. Lines: %d/%d | Elapsed: %.1f min | Died: %s ===",
        lines_sent, len(audio_lines), session_elapsed / 60,
        connection_died_at or "no (survived)",
    )

    # Phase 4: Post-meeting questions — audio if available, text fallback
    try:
        if await provider.is_connected() and meeting.post_meeting_questions:
            logger.info("Post-meeting questions (%d, via %s)…",
                        len(meeting.post_meeting_questions),
                        "AUDIO" if question_audio else "text")
            for q in meeting.post_meeting_questions:
                q_audio = question_audio.get(q.question_id)

                if q_audio:
                    q_chunks = pcm16_to_base64_chunks(q_audio["pcm16_bytes"])
                    turn = await provider.send_audio(q_chunks, q.question)
                else:
                    turn = await provider.send_text(q.question)

                post_meeting_results.append({
                    "question_id": q.question_id,
                    "question": q.question,
                    "ground_truth": q.ground_truth,
                    "category": q.category,
                    "difficulty": q.difficulty,
                    "response": turn.text,
                    "latency_ms": turn.latency_ms,
                    "sent_as": "audio" if q_audio else "text",
                })
                logger.info("  [%s] %s → %s", q.question_id, q.question[:40], turn.text[:80])

        if await provider.is_connected() and meeting.hallucination_probes:
            for probe in meeting.hallucination_probes:
                turn = await provider.send_text(probe.question)
                hallucination_results.append({
                    "probe_id": probe.probe_id,
                    "question": probe.question,
                    "expected": "NOT_DISCUSSED",
                    "response": turn.text,
                    "latency_ms": turn.latency_ms,
                })
    except Exception as e:
        logger.error("Post-meeting phase failed: %s", e)

    metrics = await provider.get_session_metrics()
    try:
        await provider.disconnect()
    except Exception:
        pass

    # Phase 5: Score
    scores = []
    halluc_scores = []
    if not skip_scoring and post_meeting_results:
        logger.info("Scoring…")
        for r in post_meeting_results:
            s = await score_recall(
                fact_id=r["question_id"],
                question=r["question"],
                expected=r["ground_truth"],
                actual=r["response"],
            )
            scores.append(s)
            logger.info("  [%s] %s credit=%.1f", s.fact_id, s.verdict.value, s.partial_credit)

        for r in hallucination_results:
            s = await score_recall(
                fact_id=r["probe_id"],
                question=r["question"],
                expected=r["expected"],
                actual=r["response"],
            )
            halluc_scores.append(s)

    fact_categories = {q.question_id: q.category for q in meeting.post_meeting_questions}
    fact_minutes = {q.question_id: q.source_minute for q in meeting.post_meeting_questions}
    aggregate = aggregate_scores(scores, fact_categories, fact_minutes) if scores else None

    # Transcription summary
    wer_values = [t["wer"] for t in transcription_results]
    avg_wer = sum(wer_values) / len(wer_values) if wer_values else None

    result = {
        "experiment": "e06_audio_session",
        "provider": provider.name,
        "config": {
            "seconds_per_minute": seconds_per_minute,
            "meeting_title": meeting.title,
            "total_lines": len(meeting.lines),
            "total_audio_duration_ms": total_audio_ms,
            "mode": "audio",
        },
        "session_survival": {
            "lines_sent": lines_sent,
            "lines_total": len(audio_lines),
            "survived_full_meeting": connection_died_at is None,
            "connection_died_at": connection_died_at,
        },
        "timing": {
            "total_elapsed_seconds": session_elapsed,
            "total_elapsed_minutes": session_elapsed / 60,
        },
        "transcription": {
            "total_compared": len(transcription_results),
            "avg_wer": round(avg_wer, 3) if avg_wer is not None else None,
            "details": transcription_results,
        },
        "health_checks": health_checks,
        "mid_meeting_results": mid_meeting_results,
        "post_meeting_results": post_meeting_results,
        "hallucination_results": hallucination_results,
        "scores": [dataclasses.asdict(s) for s in scores] if scores else [],
        "hallucination_scores": [dataclasses.asdict(s) for s in halluc_scores] if halluc_scores else [],
        "aggregate": dataclasses.asdict(aggregate) if aggregate else None,
        "session_metrics": {
            "total_turns": len(metrics.turns),
            "items_injected": metrics.items_injected,
            "errors": metrics.errors,
            "connection_drops": metrics.connection_drops,
        },
    }

    if aggregate:
        logger.info(
            "=== RESULTS: accuracy=%.0f%% avg_wer=%.1f%% session=%.1f min ===",
            aggregate.recall_accuracy * 100,
            (avg_wer or 0) * 100,
            session_elapsed / 60,
        )

    return result


def _dry_run_result(meeting, seconds_per_minute: float, max_lines: int = 0) -> dict:
    est_duration = meeting.duration_minutes * seconds_per_minute / 60
    total_words = sum(len(l.text.split()) for l in meeting.lines)

    # Check if audio fixtures exist
    from common.audio import get_fixture_dir
    fixture_dir = get_fixture_dir("realistic_meeting")
    has_fixtures = (fixture_dir / "manifest.json").exists()

    logger.info("DRY RUN: Audio session")
    logger.info("  Lines: %d (%d words)", len(meeting.lines), total_words)
    logger.info("  Post-meeting questions: %d", len(meeting.post_meeting_questions))
    logger.info("  Pacing: %.0fs/min → ~%.0f real minutes", seconds_per_minute, est_duration)
    logger.info("  Audio fixtures: %s", "READY" if has_fixtures else "NOT GENERATED")
    if not has_fixtures:
        logger.info("  → Run first: python3 generate_audio.py")

    return {
        "experiment": "e06_audio_session",
        "dry_run": True,
        "total_lines": len(meeting.lines),
        "total_words": total_words,
        "estimated_real_minutes": est_duration,
        "audio_fixtures_ready": has_fixtures,
    }
