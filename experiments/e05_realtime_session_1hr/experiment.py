"""Experiment 05: Real-Time 1-Hour Session Simulation.

Maintains a live WebSocket session for up to 60 minutes, feeding a
realistic meeting transcript at real-world pacing. Tests:

1. Session stability — does the connection survive the full duration?
2. Context retention over real elapsed time
3. Response quality — can Otto answer natural questions during/after the meeting?
4. Latency drift — does TTFB creep up over the session?
5. Hallucination resistance — does Otto make things up?

Key design choices for validity:
- NO priming ("remember everything") — Otto is just sitting in a meeting
- Messy, realistic dialogue with tangents, interruptions, implicit references
- Questions are natural ("what was that thing about...") not quiz-style
- Supports external transcripts from real meetings (Whisper, Otter.ai, etc.)
"""

from __future__ import annotations

import asyncio
import dataclasses
import time

from common.config import setup_logging
from common.provider import RealtimeProvider
from common.scoring import (
    RecallScore,
    aggregate_scores,
    score_recall,
)
from common.audio import load_question_audio, pcm16_to_base64_chunks
from .realistic_meeting import (
    REALISTIC_SYSTEM_PROMPT,
    RealisticMeeting,
    generate_realistic_meeting,
    load_external_transcript,
)
from .meeting_1hr import generate_meeting_1hr

logger = setup_logging("experiment.05")

# How many seconds per simulated minute (controls pacing)
# 60 = real-time (1 hour), 30 = half-speed (30 min), 1 = fast (1 min total)
DEFAULT_SECONDS_PER_MINUTE = 60


async def run(
    provider: RealtimeProvider,
    *,
    dry_run: bool = False,
    skip_scoring: bool = False,
    seconds_per_minute: float = DEFAULT_SECONDS_PER_MINUTE,
    transcript_path: str | None = None,
    questions_path: str | None = None,
    duration_minutes: int = 0,
) -> dict:
    """Run the real-time session experiment.

    Args:
        provider: The realtime API provider to test.
        dry_run: Validate without API calls.
        skip_scoring: Skip LLM judge.
        seconds_per_minute: Pacing. 60=real-time, 30=half, 5=fast.
        transcript_path: Optional external transcript file.
        questions_path: Optional external questions file (JSON).
    """
    # Load meeting — default is the dense 1-hour version
    if transcript_path:
        meeting = load_external_transcript(transcript_path, questions_path)
    else:
        meeting = generate_meeting_1hr()

    if duration_minutes > 0:
        meeting.lines = [l for l in meeting.lines if l.minute <= duration_minutes]
        meeting.mid_meeting_questions = [
            q for q in meeting.mid_meeting_questions
            if q.trigger_after_minute <= duration_minutes
        ]

    if dry_run:
        return _dry_run_result(meeting, seconds_per_minute)

    # Load question audio — Mode A: meeting is text, questions are audio
    try:
        question_audio = load_question_audio("meeting_1hr")
        logger.info("Mode A: meeting=TEXT, questions=AUDIO (%d clips)", len(question_audio))
    except FileNotFoundError:
        logger.warning("Question audio not found — falling back to text questions")
        question_audio = {}

    total_words = sum(len(l.text.split()) for l in meeting.lines)
    est_audio_min = total_words / 150  # ~150 wpm speaking speed
    speed_mult = seconds_per_minute / 60
    est_duration = est_audio_min * speed_mult
    logger.info(
        "Starting experiment 05 (Mode A) with %s — %d lines, %d words, ~%.0f min of speech, "
        "speed=%.1fx → est %.0f real minutes",
        provider.name, len(meeting.lines), total_words, est_audio_min,
        speed_mult, est_duration,
    )

    # --- Connect (no priming, just join the meeting) ---
    await provider.connect(instructions=REALISTIC_SYSTEM_PROMPT)
    logger.info("Connected to %s", provider.name)

    session_start = time.monotonic()
    current_minute = 0
    lines_sent = 0
    connection_died_at: str | None = None
    mid_meeting_results = []
    post_meeting_results = []
    hallucination_results = []
    health_checks = []
    latency_over_time = []  # track TTFB at different points in the session

    # Pre-compute which mid-meeting questions fire at which minute
    pending_mid_questions = list(meeting.mid_meeting_questions)

    # --- Main meeting loop — natural pacing ---
    # Each line waits based on how long it would take to speak (~150 wpm).
    # seconds_per_minute acts as a speed multiplier:
    #   60 = real-time (~50 min meeting), 5 = fast test (~4 min)
    WORDS_PER_MINUTE = 150
    speed_factor = seconds_per_minute / 60  # 1.0 = real-time, <1 = fast
    last_health_check_min = -5

    try:
        for i, line in enumerate(meeting.lines):
            # Health check every 5 script-minutes
            if line.minute >= last_health_check_min + 5:
                connected = await provider.is_connected()
                elapsed = (time.monotonic() - session_start) / 60
                health_checks.append({
                    "minute": line.minute,
                    "elapsed_real_minutes": round(elapsed, 1),
                    "connected": connected,
                    "lines_sent": lines_sent,
                })
                logger.info(
                    "--- min %d | elapsed: %.1f real min | connected: %s | lines: %d/%d ---",
                    line.minute, elapsed, connected, lines_sent, len(meeting.lines),
                )
                last_health_check_min = line.minute

                if not connected:
                    connection_died_at = f"minute {line.minute} (elapsed {elapsed:.1f} real min)"
                    logger.error("CONNECTION LOST at %s!", connection_died_at)
                    break

            # Natural pacing: wait based on how long this line takes to speak
            word_count = len(line.text.split())
            speak_duration = (word_count / WORDS_PER_MINUTE) * 60  # seconds
            # Add a small natural pause between speakers (0.3-0.8s)
            pause = 0.5
            wait = (speak_duration + pause) * speed_factor
            if wait > 0:
                await asyncio.sleep(wait)

            # Send the line
            await provider.send_text_no_response(
                f"[{line.speaker}]: {line.text}"
            )
            lines_sent += 1

            # Check for mid-meeting questions — sent as AUDIO (Mode A: wake word)
            fired = []
            for mq in pending_mid_questions:
                if line.minute >= mq.trigger_after_minute:
                    await asyncio.sleep(1 * speed_factor)
                    q_idx = meeting.mid_meeting_questions.index(mq)
                    q_id = f"mid_{q_idx:02d}"
                    q_audio = question_audio.get(q_id)

                    if q_audio:
                        logger.info("  Hey Otto AUDIO (min %d): %s", line.minute, mq.question[:60])
                        q_chunks = pcm16_to_base64_chunks(q_audio["pcm16_bytes"])
                        turn = await provider.send_audio(q_chunks, mq.question)
                    else:
                        logger.info("  Hey Otto TEXT (min %d): %s", line.minute, mq.question[:60])
                        turn = await provider.send_text(mq.question)

                    mid_meeting_results.append({
                        "minute": line.minute,
                        "elapsed_real_seconds": time.monotonic() - session_start,
                        "question": mq.question,
                        "ground_truth": mq.ground_truth,
                        "response": turn.text,
                        "latency_ms": turn.latency_ms,
                        "full_response_ms": turn.full_response_ms,
                        "sent_as": "audio" if q_audio else "text",
                    })
                    latency_over_time.append({
                        "minute": line.minute,
                        "ttfb_ms": turn.latency_ms,
                        "type": "mid_meeting",
                    })
                    logger.info("  Response: %s", turn.text[:80])
                    fired.append(mq)
            for mq in fired:
                pending_mid_questions.remove(mq)

    except Exception as e:
        elapsed = (time.monotonic() - session_start) / 60
        connection_died_at = f"line {lines_sent} (exception: {type(e).__name__}: {e})"
        logger.error("Session failed at %.1f min: %s", elapsed, e)

    session_elapsed = time.monotonic() - session_start
    logger.info(
        "=== Meeting done. Lines: %d/%d | Elapsed: %.1f min | Died: %s ===",
        lines_sent, len(meeting.lines), session_elapsed / 60,
        connection_died_at or "no (survived)",
    )

    # --- Post-meeting phase (only if still connected) ---
    try:
        if await provider.is_connected() and meeting.post_meeting_questions:
            logger.info("Post-meeting questions (%d)…", len(meeting.post_meeting_questions))

            for q in meeting.post_meeting_questions:
                turn = await provider.send_text(q.question)
                post_meeting_results.append({
                    "question_id": q.question_id,
                    "question": q.question,
                    "ground_truth": q.ground_truth,
                    "category": q.category,
                    "difficulty": q.difficulty,
                    "source_minute": q.source_minute,
                    "response": turn.text,
                    "latency_ms": turn.latency_ms,
                    "full_response_ms": turn.full_response_ms,
                })
                latency_over_time.append({
                    "minute": "post",
                    "ttfb_ms": turn.latency_ms,
                    "type": "post_meeting",
                })
                logger.info(
                    "  [%s][%s] %s → %s",
                    q.question_id, q.category,
                    q.question[:40], turn.text[:80],
                )

        # Hallucination probes
        if await provider.is_connected() and meeting.hallucination_probes:
            logger.info("Hallucination probes (%d)…", len(meeting.hallucination_probes))
            for probe in meeting.hallucination_probes:
                turn = await provider.send_text(probe.question)
                hallucination_results.append({
                    "probe_id": probe.probe_id,
                    "question": probe.question,
                    "expected": "NOT_DISCUSSED",
                    "response": turn.text,
                    "latency_ms": turn.latency_ms,
                })
                logger.info("  [%s] %s → %s", probe.probe_id, probe.question[:40], turn.text[:80])

        if not await provider.is_connected():
            logger.warning("Skipping post-meeting phase — connection lost")

    except Exception as e:
        logger.error("Post-meeting phase failed: %s", e)

    metrics = await provider.get_session_metrics()
    try:
        await provider.disconnect()
    except Exception:
        pass

    # --- Score with LLM judge ---
    scores = []
    halluc_scores = []
    if not skip_scoring and post_meeting_results:
        logger.info("Scoring with LLM judge…")
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
            logger.info("  [%s] %s halluc=%s", s.fact_id, s.verdict.value, s.hallucinated)

    fact_categories = {q.question_id: q.category for q in meeting.post_meeting_questions}
    fact_minutes = {q.question_id: q.source_minute for q in meeting.post_meeting_questions}
    aggregate = aggregate_scores(scores, fact_categories, fact_minutes) if scores else None

    result = {
        "experiment": "e05_realtime_session_1hr",
        "provider": provider.name,
        "config": {
            "seconds_per_minute": seconds_per_minute,
            "meeting_title": meeting.title,
            "total_lines": len(meeting.lines),
            "num_mid_questions": len(meeting.mid_meeting_questions),
            "num_post_questions": len(meeting.post_meeting_questions),
            "num_hallucination_probes": len(meeting.hallucination_probes),
            "transcript_source": "external" if transcript_path else "built-in",
        },
        "session_survival": {
            "lines_sent": lines_sent,
            "lines_total": len(meeting.lines),
            "survived_full_meeting": connection_died_at is None,
            "connection_died_at": connection_died_at,
            "post_meeting_completed": len(post_meeting_results) > 0,
        },
        "timing": {
            "total_elapsed_seconds": session_elapsed,
            "total_elapsed_minutes": session_elapsed / 60,
            "target_minutes": meeting.duration_minutes,
            "pacing_ratio": seconds_per_minute / 60,
        },
        "health_checks": health_checks,
        "latency_over_time": latency_over_time,
        "mid_meeting_results": mid_meeting_results,
        "post_meeting_results": post_meeting_results,
        "hallucination_results": hallucination_results,
        "scores": [dataclasses.asdict(s) for s in scores] if scores else [],
        "hallucination_scores": [dataclasses.asdict(s) for s in halluc_scores] if halluc_scores else [],
        "aggregate": dataclasses.asdict(aggregate) if aggregate else None,
        "session_metrics": {
            "total_turns": len(metrics.turns),
            "items_injected": metrics.items_injected,
            "total_input_tokens": metrics.total_input_tokens,
            "total_output_tokens": metrics.total_output_tokens,
            "errors": metrics.errors,
            "connection_drops": metrics.connection_drops,
        },
    }

    if aggregate:
        logger.info(
            "=== RESULTS: accuracy=%.0f%% halluc=%.0f%% session=%.1f min survived=%s ===",
            aggregate.recall_accuracy * 100,
            aggregate.hallucination_rate * 100,
            session_elapsed / 60,
            connection_died_at is None,
        )

    return result


def _dry_run_result(meeting: RealisticMeeting, seconds_per_minute: float) -> dict:
    est_duration = meeting.duration_minutes * seconds_per_minute / 60
    total_words = sum(len(l.text.split()) for l in meeting.lines)
    est_tokens = int(total_words * 1.3)

    logger.info("DRY RUN: Real-time session")
    logger.info("  Title: %s", meeting.title)
    logger.info("  Lines: %d (~%d tokens)", len(meeting.lines), est_tokens)
    logger.info("  Mid-meeting questions: %d", len(meeting.mid_meeting_questions))
    logger.info("  Post-meeting questions: %d", len(meeting.post_meeting_questions))
    logger.info("  Hallucination probes: %d", len(meeting.hallucination_probes))
    logger.info("  Pacing: %.0fs/min → ~%.0f real minutes", seconds_per_minute, est_duration)

    # Print question categories
    categories = {}
    for q in meeting.post_meeting_questions:
        categories[q.category] = categories.get(q.category, 0) + 1
    logger.info("  Question types: %s", dict(categories))

    return {
        "experiment": "e05_realtime_session_1hr",
        "dry_run": True,
        "meeting_title": meeting.title,
        "total_lines": len(meeting.lines),
        "estimated_tokens": est_tokens,
        "estimated_real_minutes": est_duration,
        "seconds_per_minute": seconds_per_minute,
        "question_categories": categories,
    }
