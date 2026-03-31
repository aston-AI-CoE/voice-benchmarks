"""Experiment 01: Long Session Context Retention.

Simulates a 1-hour product meeting by injecting ~350 conversation turns
into a realtime session, then tests recall of 20 planted facts.
"""

from __future__ import annotations

import asyncio
import dataclasses
import time

from common.config import setup_logging
from common.provider import RealtimeProvider
from common.scoring import (
    AggregateScores,
    RecallScore,
    aggregate_scores,
    score_recall,
)
from .meeting_script import (
    generate_meeting_script,
    get_fact_categories,
    get_fact_minutes,
)
from .recall_questions import (
    CONSISTENCY_QUESTIONS,
    HALLUCINATION_PROBES,
    RECALL_QUESTIONS,
)

logger = setup_logging("experiment.01")

MEETING_ASSISTANT_PROMPT = """\
You are Otto, an AI meeting assistant. You are listening to a product team's \
weekly sync meeting. Your job is to:
1. Pay close attention to everything discussed — names, numbers, decisions, dates.
2. After the meeting, answer questions about what was discussed accurately.
3. If you are unsure or something was not discussed, say so honestly. \
Do NOT guess or make up information.
4. Keep your answers concise and conversational.

Important: When you don't know something or it wasn't mentioned in the meeting, \
clearly say "That wasn't discussed in the meeting" or "I don't recall that being \
mentioned." Never fabricate details.\
"""

# How long to wait between injected turns (seconds).
# Keeps us under rate limits while still being fast.
INJECTION_DELAY = 0.05
INJECTION_BATCH_PAUSE = 0.5  # Longer pause every N turns
INJECTION_BATCH_SIZE = 20


async def run(
    provider: RealtimeProvider,
    *,
    dry_run: bool = False,
    skip_scoring: bool = False,
) -> dict:
    """Run the long session context retention experiment.

    Args:
        provider: The realtime API provider to test.
        dry_run: If True, validate the script without making API calls.
        skip_scoring: If True, skip LLM judge scoring (returns raw responses only).

    Returns:
        Dict with experiment results suitable for JSON serialization.
    """
    script = generate_meeting_script()

    if dry_run:
        return _dry_run_result(script)

    logger.info(
        "Starting experiment 01 with provider=%s (%d turns, %d facts)",
        provider.name,
        len(script.turns),
        len(script.planted_facts),
    )

    # Phase 1: Connect
    await provider.connect(instructions=MEETING_ASSISTANT_PROMPT)
    logger.info("Connected to %s", provider.name)

    # Phase 2: Prime the assistant
    prime_turn = await provider.send_text(
        "I'm going to share a meeting transcript with you. Please listen carefully "
        "and remember all the details — names, numbers, decisions, dates, and "
        "preferences mentioned. I'll ask you questions about it afterwards. "
        "Just say 'ready' when you're set."
    )
    logger.info("Prime response: %s", prime_turn.text[:100])

    # Phase 3: Inject meeting transcript
    logger.info("Injecting %d meeting turns…", len(script.turns))
    t_inject_start = time.monotonic()

    for i, turn in enumerate(script.turns):
        text = f"[{turn.speaker}, minute {turn.minute}]: {turn.text}"
        await provider.send_text_no_response(text)

        # Small delay to avoid rate limits
        await asyncio.sleep(INJECTION_DELAY)
        if (i + 1) % INJECTION_BATCH_SIZE == 0:
            await asyncio.sleep(INJECTION_BATCH_PAUSE)
            logger.info("  Injected %d / %d turns", i + 1, len(script.turns))

    t_inject_end = time.monotonic()
    injection_time_s = t_inject_end - t_inject_start
    logger.info("Injection complete in %.1fs", injection_time_s)

    # Phase 4: Transition to recall
    transition_turn = await provider.send_text(
        "That's the end of the meeting recording. I'm now going to ask you "
        "specific questions about what was discussed. Please answer each one "
        "based only on what you heard in the meeting."
    )
    logger.info("Transition response: %s", transition_turn.text[:100])

    # Phase 5: Recall questions
    logger.info("Asking %d recall questions…", len(RECALL_QUESTIONS))
    recall_results: list[dict] = []

    for q in RECALL_QUESTIONS:
        turn = await provider.send_text(q.question)
        recall_results.append({
            "fact_id": q.fact_id,
            "question": q.question,
            "expected": q.expected_answer,
            "actual": turn.text,
            "latency_ms": turn.latency_ms,
            "full_response_ms": turn.full_response_ms,
            "distractors": q.distractors,
        })
        logger.info("  [%s] %s → %s", q.fact_id, q.question[:50], turn.text[:80])

    # Phase 6: Hallucination probes
    logger.info("Running %d hallucination probes…", len(HALLUCINATION_PROBES))
    hallucination_results: list[dict] = []

    for probe in HALLUCINATION_PROBES:
        turn = await provider.send_text(probe.question)
        hallucination_results.append({
            "probe_id": probe.probe_id,
            "question": probe.question,
            "expected": "NOT_DISCUSSED",
            "actual": turn.text,
            "latency_ms": turn.latency_ms,
            "full_response_ms": turn.full_response_ms,
            "description": probe.description,
        })
        logger.info("  [%s] %s → %s", probe.probe_id, probe.question[:50], turn.text[:80])

    # Phase 7: Consistency checks
    logger.info("Running %d consistency checks…", len(CONSISTENCY_QUESTIONS))
    consistency_results: list[dict] = []

    for q in CONSISTENCY_QUESTIONS:
        turn = await provider.send_text(q.question)
        consistency_results.append({
            "fact_id": q.fact_id,
            "question": q.question,
            "expected": q.expected_answer,
            "actual": turn.text,
            "latency_ms": turn.latency_ms,
            "full_response_ms": turn.full_response_ms,
        })
        logger.info("  [%s] consistency → %s", q.fact_id, turn.text[:80])

    # Phase 8: Collect metrics and disconnect
    metrics = await provider.get_session_metrics()
    await provider.disconnect()

    # Phase 9: Score with LLM judge
    scores: list[RecallScore] = []
    hallucination_scores: list[RecallScore] = []
    aggregate: AggregateScores | None = None

    if not skip_scoring:
        logger.info("Scoring recall responses with LLM judge…")
        for r in recall_results:
            s = await score_recall(
                fact_id=r["fact_id"],
                question=r["question"],
                expected=r["expected"],
                actual=r["actual"],
                distractors=r.get("distractors"),
            )
            scores.append(s)
            logger.info("  [%s] verdict=%s credit=%.1f", s.fact_id, s.verdict.value, s.partial_credit)

        logger.info("Scoring hallucination probes…")
        for r in hallucination_results:
            s = await score_recall(
                fact_id=r["probe_id"],
                question=r["question"],
                expected=r["expected"],
                actual=r["actual"],
            )
            hallucination_scores.append(s)
            logger.info("  [%s] verdict=%s hallucinated=%s", s.fact_id, s.verdict.value, s.hallucinated)

        aggregate = aggregate_scores(
            scores,
            fact_categories=get_fact_categories(),
            fact_minutes=get_fact_minutes(),
        )

    # Build final result
    result = {
        "experiment": "e01_instant_context_recall",
        "provider": provider.name,
        "config": {
            "meeting_script_version": script.version,
            "num_planted_facts": len(script.planted_facts),
            "num_turns": len(script.turns),
            "num_recall_questions": len(RECALL_QUESTIONS),
            "num_hallucination_probes": len(HALLUCINATION_PROBES),
            "num_consistency_checks": len(CONSISTENCY_QUESTIONS),
            "injection_delay": INJECTION_DELAY,
        },
        "timing": {
            "injection_time_s": round(injection_time_s, 1),
        },
        "recall_results": recall_results,
        "hallucination_results": hallucination_results,
        "consistency_results": consistency_results,
        "scores": [dataclasses.asdict(s) for s in scores] if scores else [],
        "hallucination_scores": [dataclasses.asdict(s) for s in hallucination_scores] if hallucination_scores else [],
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
            "=== RESULTS: recall=%.0f%% hallucination=%.0f%% honest_uncertainty=%.0f%% ===",
            aggregate.recall_accuracy * 100,
            aggregate.hallucination_rate * 100,
            aggregate.honest_uncertainty_rate * 100,
        )

    return result


def _dry_run_result(script) -> dict:
    """Validate the meeting script without making API calls."""
    logger.info("DRY RUN: validating meeting script…")
    logger.info("  Title: %s", script.title)
    logger.info("  Duration: %d minutes", script.duration_minutes)
    logger.info("  Speakers: %s", ", ".join(script.speakers))
    logger.info("  Total turns: %d", len(script.turns))
    logger.info("  Planted facts: %d", len(script.planted_facts))

    # Verify all facts appear in turns
    fact_ids_in_turns = {t.contains_fact for t in script.turns if t.contains_fact}
    fact_ids_expected = {f.fact_id for f in script.planted_facts}
    missing = fact_ids_expected - fact_ids_in_turns
    if missing:
        logger.error("  MISSING facts not in turns: %s", missing)
    else:
        logger.info("  All facts present in turns ✓")

    # Verify all facts have recall questions
    question_fact_ids = {q.fact_id for q in RECALL_QUESTIONS}
    missing_q = fact_ids_expected - question_fact_ids
    if missing_q:
        logger.error("  MISSING recall questions for: %s", missing_q)
    else:
        logger.info("  All facts have recall questions ✓")

    # Estimate token count (rough: ~1.3 tokens per word)
    total_words = sum(len(t.text.split()) for t in script.turns)
    est_tokens = int(total_words * 1.3)
    logger.info("  Estimated tokens: ~%d (%d words)", est_tokens, total_words)

    return {
        "experiment": "e01_instant_context_recall",
        "dry_run": True,
        "validation": {
            "total_turns": len(script.turns),
            "planted_facts": len(script.planted_facts),
            "all_facts_in_turns": len(missing) == 0,
            "all_facts_have_questions": len(missing_q) == 0,
            "estimated_tokens": est_tokens,
            "missing_facts": list(missing),
            "missing_questions": list(missing_q),
        },
    }
