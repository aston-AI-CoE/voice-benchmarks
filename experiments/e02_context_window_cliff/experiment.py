"""Experiment 02: Context Window Stress Test.

Incrementally grows conversation length and tests recall at each milestone
to find the "memory cliff" where context retention degrades.
"""

from __future__ import annotations

import asyncio
import dataclasses
import time

from common.config import setup_logging
from common.provider import RealtimeProvider
from common.scoring import RecallScore, score_recall
from .fact_generator import generate_filler_block, generate_unique_fact, AnchorFact

logger = setup_logging("experiment.02")

ASSISTANT_PROMPT = """\
You are Otto, an AI assistant participating in a conversation. Pay close \
attention to all facts, names, numbers, and details mentioned. You will be \
periodically quizzed on details from earlier in the conversation. Answer \
accurately based on what was discussed. If you're unsure, say so.\
"""

# Token milestones to test at (approximate)
MILESTONES = [100, 500, 1_000, 2_000, 5_000, 10_000, 20_000]

INJECTION_DELAY = 0.05


async def run(
    provider: RealtimeProvider,
    *,
    dry_run: bool = False,
    skip_scoring: bool = False,
) -> dict:
    """Run the context window stress test."""
    if dry_run:
        return _dry_run_result()

    logger.info("Starting experiment 02 (context window stress) with %s", provider.name)

    await provider.connect(instructions=ASSISTANT_PROMPT)

    # Plant the anchor fact at the very beginning
    anchor = AnchorFact(
        codename="Sapphire Falcon",
        budget="$2,847,300",
        location="Building 7, third floor",
    )
    anchor_turn = await provider.send_text(
        f"Before we start, remember these key details: "
        f"The project codename is '{anchor.codename}', "
        f"the total budget is exactly {anchor.budget}, "
        f"and the war room is in {anchor.location}. Got it?"
    )
    logger.info("Anchor planted. Response: %s", anchor_turn.text[:80])

    milestone_results = []
    planted_facts: list[dict] = []
    current_tokens = 0

    for target in MILESTONES:
        tokens_needed = target - current_tokens
        if tokens_needed <= 0:
            continue

        # Generate and inject filler conversation
        filler_turns = generate_filler_block(tokens_needed)
        for text in filler_turns:
            await provider.send_text_no_response(text)
            await asyncio.sleep(INJECTION_DELAY)

        current_tokens = target
        logger.info("Reached ~%d tokens", current_tokens)

        # Test anchor recall
        anchor_turn = await provider.send_text(
            "Quick check: what's the project codename and the total budget I mentioned at the start?"
        )

        codename_recalled = anchor.codename.lower() in anchor_turn.text.lower()
        budget_recalled = "2,847,300" in anchor_turn.text or "2847300" in anchor_turn.text

        # Plant a new fact at this milestone
        new_fact = generate_unique_fact(milestone=target)
        fact_turn = await provider.send_text(
            f"New update: {new_fact['statement']} Remember that."
        )
        planted_facts.append({**new_fact, "milestone": target})

        milestone_result = {
            "milestone_tokens": target,
            "anchor_codename_recalled": codename_recalled,
            "anchor_budget_recalled": budget_recalled,
            "anchor_response": anchor_turn.text,
            "anchor_latency_ms": anchor_turn.latency_ms,
            "new_fact": new_fact,
        }
        milestone_results.append(milestone_result)
        logger.info(
            "  Milestone %d: codename=%s budget=%s",
            target, codename_recalled, budget_recalled,
        )

    # Final recall: test ALL planted facts
    logger.info("Final recall phase: testing %d planted facts…", len(planted_facts))
    final_recall = []
    for fact in planted_facts:
        turn = await provider.send_text(fact["question"])
        recalled = fact["key_term"].lower() in turn.text.lower()
        final_recall.append({
            "milestone": fact["milestone"],
            "question": fact["question"],
            "expected_key_term": fact["key_term"],
            "response": turn.text,
            "recalled": recalled,
            "latency_ms": turn.latency_ms,
        })
        logger.info("  Fact@%d: recalled=%s", fact["milestone"], recalled)

    # Final anchor check
    final_anchor = await provider.send_text(
        "One last time — project codename, budget, and war room location?"
    )

    metrics = await provider.get_session_metrics()
    await provider.disconnect()

    return {
        "experiment": "e02_context_window_cliff",
        "provider": provider.name,
        "config": {
            "milestones": MILESTONES,
            "anchor": dataclasses.asdict(anchor),
        },
        "milestone_results": milestone_results,
        "final_recall": final_recall,
        "final_anchor": {
            "response": final_anchor.text,
            "codename_recalled": anchor.codename.lower() in final_anchor.text.lower(),
            "budget_recalled": "2,847,300" in final_anchor.text or "2847300" in final_anchor.text,
            "location_recalled": "building 7" in final_anchor.text.lower(),
        },
        "session_metrics": {
            "items_injected": metrics.items_injected,
            "total_input_tokens": metrics.total_input_tokens,
            "total_output_tokens": metrics.total_output_tokens,
            "errors": metrics.errors,
            "connection_drops": metrics.connection_drops,
        },
    }


def _dry_run_result() -> dict:
    logger.info("DRY RUN: Context window stress test")
    logger.info("  Milestones: %s", MILESTONES)
    logger.info("  Total filler tokens needed: ~%d", MILESTONES[-1])
    return {
        "experiment": "e02_context_window_cliff",
        "dry_run": True,
        "milestones": MILESTONES,
    }
