"""Experiment 03: Latency Benchmarking.

Measures TTFB and total response time across varied prompt types.
Also tracks whether latency degrades as the session grows.

NOTE on fairness: Grok's provider requests modalities=["text","audio"] to avoid
truncation. This means Grok is also generating audio, adding latency that OpenAI
(text-only) doesn't have. The latency comparison between providers should be
interpreted with this caveat. For pure text-generation speed, both would need
text-only mode, but Grok truncates in that mode.
"""

from __future__ import annotations

import asyncio
import statistics

from common.config import setup_logging
from common.provider import RealtimeProvider

logger = setup_logging("experiment.03")

ASSISTANT_PROMPT = """\
You are Otto, a helpful AI assistant. Answer questions concisely and naturally. \
Keep responses brief — one to three sentences.\
"""

# 30 varied prompts across complexity levels
PROMPTS = [
    # Simple (factual, short answers expected)
    ("simple", "What's 17 times 23?"),
    ("simple", "What's the capital of Portugal?"),
    ("simple", "How many days are in February during a leap year?"),
    ("simple", "What does HTML stand for?"),
    ("simple", "What color do you get when you mix red and blue?"),
    ("simple", "Name three planets in our solar system."),
    ("simple", "What's the boiling point of water in Celsius?"),
    ("simple", "Who wrote Romeo and Juliet?"),
    ("simple", "What's the square root of 144?"),
    ("simple", "How many continents are there?"),
    # Medium (requires some reasoning or explanation)
    ("medium", "Explain the difference between TCP and UDP in one sentence."),
    ("medium", "What's the main advantage of using a hash table over an array?"),
    ("medium", "Why do we use HTTPS instead of HTTP?"),
    ("medium", "Briefly explain what a mutex is used for."),
    ("medium", "What's the difference between a stack and a queue?"),
    ("medium", "Why is it important to sanitize user input?"),
    ("medium", "Explain what a REST API is in simple terms."),
    ("medium", "What's the purpose of a load balancer?"),
    ("medium", "Why would you use an index on a database table?"),
    ("medium", "What's the difference between authentication and authorization?"),
    # Complex (creative, multi-step, or longer responses)
    ("complex", "Write a haiku about debugging code."),
    ("complex", "Give me a metaphor for explaining microservices to a non-technical person."),
    ("complex", "What are three things to consider when designing an API rate limiter?"),
    ("complex", "Describe the CAP theorem and give a practical example."),
    ("complex", "Suggest three ways to reduce latency in a web application."),
    ("complex", "Explain the observer pattern with a real-world analogy."),
    ("complex", "What's a good strategy for database migration with zero downtime?"),
    ("complex", "Compare eventual consistency and strong consistency with examples."),
    ("complex", "Describe a scenario where a memory leak is hard to detect."),
    ("complex", "How would you design a simple notification system?"),
]


async def run(
    provider: RealtimeProvider,
    *,
    dry_run: bool = False,
    skip_scoring: bool = False,
) -> dict:
    """Run latency benchmarks."""
    if dry_run:
        return {
            "experiment": "e03_response_latency",
            "dry_run": True,
            "num_prompts": len(PROMPTS),
            "complexity_breakdown": {
                "simple": sum(1 for c, _ in PROMPTS if c == "simple"),
                "medium": sum(1 for c, _ in PROMPTS if c == "medium"),
                "complex": sum(1 for c, _ in PROMPTS if c == "complex"),
            },
        }

    logger.info("Starting experiment 03 (latency) with %s (%d prompts)", provider.name, len(PROMPTS))

    await provider.connect(instructions=ASSISTANT_PROMPT)

    results = []
    for i, (complexity, prompt) in enumerate(PROMPTS):
        turn = await provider.send_text(prompt)
        results.append({
            "index": i,
            "complexity": complexity,
            "prompt": prompt,
            "response_length": len(turn.text),
            "ttfb_ms": turn.latency_ms,
            "total_ms": turn.full_response_ms,
        })
        logger.info(
            "  [%d/%d] %s: ttfb=%s total=%s",
            i + 1, len(PROMPTS), complexity,
            f"{turn.latency_ms:.0f}ms" if turn.latency_ms else "?",
            f"{turn.full_response_ms:.0f}ms" if turn.full_response_ms else "?",
        )

    metrics = await provider.get_session_metrics()
    await provider.disconnect()

    # Compute aggregates
    all_ttfb = [r["ttfb_ms"] for r in results if r["ttfb_ms"] is not None]
    all_total = [r["total_ms"] for r in results if r["total_ms"] is not None]

    by_complexity: dict[str, dict] = {}
    for complexity in ("simple", "medium", "complex"):
        ttfbs = [r["ttfb_ms"] for r in results if r["complexity"] == complexity and r["ttfb_ms"] is not None]
        totals = [r["total_ms"] for r in results if r["complexity"] == complexity and r["total_ms"] is not None]
        by_complexity[complexity] = {
            "avg_ttfb_ms": statistics.mean(ttfbs) if ttfbs else None,
            "avg_total_ms": statistics.mean(totals) if totals else None,
            "p95_ttfb_ms": sorted(ttfbs)[int(len(ttfbs) * 0.95)] if ttfbs else None,
            "p95_total_ms": sorted(totals)[int(len(totals) * 0.95)] if totals else None,
        }

    return {
        "experiment": "e03_response_latency",
        "provider": provider.name,
        "config": {"num_prompts": len(PROMPTS)},
        "results": results,
        "aggregate": {
            "avg_ttfb_ms": statistics.mean(all_ttfb) if all_ttfb else None,
            "avg_total_ms": statistics.mean(all_total) if all_total else None,
            "p95_ttfb_ms": sorted(all_ttfb)[int(len(all_ttfb) * 0.95)] if all_ttfb else None,
            "p95_total_ms": sorted(all_total)[int(len(all_total) * 0.95)] if all_total else None,
            "by_complexity": by_complexity,
        },
        "session_metrics": {
            "total_input_tokens": metrics.total_input_tokens,
            "total_output_tokens": metrics.total_output_tokens,
            "errors": metrics.errors,
            "connection_drops": metrics.connection_drops,
        },
    }
