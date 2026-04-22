"""Experiment 08: Context Recall (fast variant of E07).

Same question sessions as E07 — fresh voice session per question, full
transcript injected as context — but skips the STT streaming phase entirely.
The transcript is loaded from the ground-truth text fixtures instead of being
built by streaming audio through the Realtime API.

Why: E07 spends ~45 min streaming 737 audio lines through a Realtime STT
session just to build the transcript. The actual recall test (asking questions)
takes ~5 min. E08 isolates that part, cutting total run time from ~55 min to
~5-10 min.

Use E08 for: fast iteration on model quality, code changes, prompt changes.
Use E07 for: validating the full production pipeline (STT + recall end-to-end).
"""

from __future__ import annotations

import asyncio
import dataclasses
import time

from common.audio import load_meeting_audio, load_question_audio, pcm16_to_base64_chunks
from common.config import setup_logging
from common.scoring import aggregate_scores, score_recall
from experiments.e05_realtime_session_1hr.meeting_1hr import generate_meeting_1hr

logger = setup_logging("experiment.08")


def _build_context_prompt(transcript_lines: list[str]) -> str:
    transcript_text = "\n".join(transcript_lines)
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
    duration_minutes: int = 0,
    **kwargs,
) -> dict:
    """Run context recall test — fresh session per question, text transcript injected."""
    meeting = generate_meeting_1hr()

    if dry_run:
        return _dry_run_result(meeting, duration_minutes)

    # Load audio lines — used only for their .text and .minute fields (no STT)
    audio_lines = load_meeting_audio("meeting_1hr")
    if duration_minutes > 0:
        audio_lines = [l for l in audio_lines if l["minute"] <= duration_minutes]
        meeting.mid_meeting_questions = [
            q for q in meeting.mid_meeting_questions
            if q.trigger_after_minute <= duration_minutes
        ]

    try:
        question_audio = load_question_audio("meeting_1hr")
    except FileNotFoundError:
        question_audio = {}

    logger.info(
        "Starting E08 (context recall) — %d transcript lines, %d mid questions, "
        "%d post questions, questions via %s",
        len(audio_lines),
        len(meeting.mid_meeting_questions),
        len(meeting.post_meeting_questions),
        "AUDIO" if question_audio else "text",
    )

    # Build transcript grouped by minute — no API calls, just text
    transcript_by_minute: dict[int, list[str]] = {}
    for line in audio_lines:
        minute = line["minute"]
        transcript_by_minute.setdefault(minute, []).append(
            f"[{line['speaker']}]: {line['text']}"
        )

    def transcript_up_to(minute: int) -> list[str]:
        lines = []
        for m in sorted(transcript_by_minute):
            if m <= minute:
                lines.extend(transcript_by_minute[m])
        return lines

    full_transcript = transcript_up_to(max(transcript_by_minute) if transcript_by_minute else 0)

    run_start = time.monotonic()
    mid_meeting_results = []
    post_meeting_results = []
    hallucination_results = []

    # === Mid-meeting questions (transcript up to that minute) ===
    if meeting.mid_meeting_questions:
        logger.info("Mid-meeting questions (%d)...", len(meeting.mid_meeting_questions))
        for i, mq in enumerate(meeting.mid_meeting_questions):
            try:
                transcript_so_far = transcript_up_to(mq.trigger_after_minute)
                context_prompt = _build_context_prompt(transcript_so_far)

                q_start = time.monotonic()
                q_provider = provider_factory()
                await q_provider.connect(instructions=context_prompt)
                cold_start_ms = (time.monotonic() - q_start) * 1000

                q_id = f"mid_{i:02d}"
                q_audio = question_audio.get(q_id)
                if q_audio:
                    logger.info("  [%s] AUDIO: %s", q_id, mq.question[:60])
                    q_chunks = pcm16_to_base64_chunks(q_audio["pcm16_bytes"])
                    turn = await q_provider.send_audio(q_chunks, mq.question)
                else:
                    logger.info("  [%s] TEXT: %s", q_id, mq.question[:60])
                    turn = await q_provider.send_text(mq.question)

                await q_provider.disconnect()

                mid_meeting_results.append({
                    "minute": mq.trigger_after_minute,
                    "question": mq.question,
                    "ground_truth": mq.ground_truth,
                    "response": turn.text,
                    "latency_ms": turn.latency_ms,
                    "cold_start_ms": round(cold_start_ms, 1),
                    "context_lines": len(transcript_so_far),
                    "sent_as": "audio" if q_audio else "text",
                })
                logger.info(
                    "  [%s] cold=%dms lat=%sms → %s",
                    q_id, cold_start_ms,
                    f"{turn.latency_ms:.0f}" if turn.latency_ms else "?",
                    turn.text[:70],
                )
            except Exception as e:
                logger.error("  [mid_%02d] FAILED: %s", i, e)

    # === Post-meeting questions (full transcript) ===
    full_context = _build_context_prompt(full_transcript)

    if meeting.post_meeting_questions:
        logger.info("Post-meeting questions (%d)...", len(meeting.post_meeting_questions))
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
                    "context_lines": len(full_transcript),
                    "sent_as": "audio" if q_audio_clip else "text",
                })
                logger.info(
                    "  [%s] cold=%dms → %s", q.question_id, cold_start_ms, turn.text[:70]
                )
            except Exception as e:
                logger.error("  [%s] FAILED: %s", q.question_id, e)

    # === Hallucination probes ===
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

    elapsed = time.monotonic() - run_start

    result = {
        "experiment": "e08_context_recall",
        "provider": provider_factory().name,
        "config": {
            "architecture": "text transcript injected directly — no STT session",
            "transcript_lines": len(full_transcript),
            "mid_questions": len(meeting.mid_meeting_questions),
            "post_questions": len(meeting.post_meeting_questions),
            "questions_via": "audio" if question_audio else "text",
            "duration_minutes": duration_minutes or "full",
        },
        "timing": {
            "total_elapsed_seconds": elapsed,
            "total_elapsed_minutes": elapsed / 60,
        },
        "mid_meeting_results": mid_meeting_results,
        "post_meeting_results": post_meeting_results,
        "hallucination_results": hallucination_results,
        "scores": [dataclasses.asdict(s) for s in scores] if scores else [],
        "hallucination_scores": [dataclasses.asdict(s) for s in halluc_scores] if halluc_scores else [],
        "aggregate": dataclasses.asdict(aggregate) if aggregate else None,
    }

    if aggregate:
        logger.info(
            "=== RESULTS: accuracy=%.0f%% halluc=%.0f%% cold_start=%.0fms elapsed=%.1fmin ===",
            aggregate.recall_accuracy * 100,
            aggregate.hallucination_rate * 100,
            sum(r.get("cold_start_ms", 0) for r in post_meeting_results) / max(len(post_meeting_results), 1),
            elapsed / 60,
        )

    return result


def _dry_run_result(meeting, duration_minutes):
    logger.info("DRY RUN: Context recall (E08)")
    logger.info("  Architecture: text transcript injected — no STT session")
    logger.info("  Mid-meeting questions: %d", len(meeting.mid_meeting_questions))
    logger.info("  Post-meeting questions: %d", len(meeting.post_meeting_questions))
    logger.info("  Duration: %s min", duration_minutes or "full")
    return {
        "experiment": "e08_context_recall",
        "dry_run": True,
        "duration_minutes": duration_minutes or "full",
    }
