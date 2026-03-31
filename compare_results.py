#!/usr/bin/env python3
"""Cross-provider comparison report generator.

Usage:
    python compare_results.py --experiment 01
    python compare_results.py --experiment 01 --format markdown
    python compare_results.py --experiment 01 --format json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from common.config import setup_logging
from common.results import load_results_by_provider

logger = setup_logging("compare")


def _avg(values: list[float | None]) -> float | None:
    clean = [v for v in values if v is not None]
    return sum(clean) / len(clean) if clean else None


def _pct(value: float | None) -> str:
    return f"{value * 100:.0f}%" if value is not None else "N/A"


def _ms(value: float | None) -> str:
    return f"{value:.0f}ms" if value is not None else "N/A"


def compare_experiment_01(by_provider: dict[str, list[dict]]) -> dict:
    """Compare long session context results across providers."""
    comparison: dict[str, dict] = {}

    for provider, runs in by_provider.items():
        aggregates = [r.get("aggregate") for r in runs if r.get("aggregate")]
        if not aggregates:
            comparison[provider] = {"error": "No scored results found"}
            continue

        recall_accuracies = [a["recall_accuracy"] for a in aggregates]
        hallucination_rates = [a["hallucination_rate"] for a in aggregates]
        uncertainty_rates = [a["honest_uncertainty_rate"] for a in aggregates]
        avg_credits = [a["avg_partial_credit"] for a in aggregates]

        # Latency from recall results
        all_latencies = []
        for r in runs:
            for rr in r.get("recall_results", []):
                if rr.get("latency_ms") is not None:
                    all_latencies.append(rr["latency_ms"])

        # By category (average across runs)
        cat_scores: dict[str, list[float]] = {}
        for a in aggregates:
            for cat, score in a.get("by_category", {}).items():
                cat_scores.setdefault(cat, []).append(score)

        # By minute (average across runs)
        minute_scores: dict[str, list[float]] = {}
        for a in aggregates:
            for minute, score in a.get("by_minute", {}).items():
                minute_scores.setdefault(str(minute), []).append(score)

        # Connection stability
        all_drops = sum(
            r.get("session_metrics", {}).get("connection_drops", 0) for r in runs
        )
        all_errors = sum(
            len(r.get("session_metrics", {}).get("errors", [])) for r in runs
        )

        comparison[provider] = {
            "num_runs": len(runs),
            "recall_accuracy": _avg(recall_accuracies),
            "hallucination_rate": _avg(hallucination_rates),
            "honest_uncertainty_rate": _avg(uncertainty_rates),
            "avg_partial_credit": _avg(avg_credits),
            "avg_latency_ms": _avg(all_latencies),
            "p95_latency_ms": sorted(all_latencies)[int(len(all_latencies) * 0.95)] if all_latencies else None,
            "by_category": {k: _avg(v) for k, v in cat_scores.items()},
            "by_minute": {k: _avg(v) for k, v in minute_scores.items()},
            "connection_drops": all_drops,
            "total_errors": all_errors,
        }

    return comparison


def format_markdown(comparison: dict[str, dict]) -> str:
    """Format comparison as a markdown table."""
    providers = list(comparison.keys())
    if not providers:
        return "No results to compare."

    lines = []
    lines.append("# Voice Benchmark Comparison — Experiment 01: Long Session Context\n")

    # Main metrics table
    header = "| Metric | " + " | ".join(p.upper() for p in providers) + " |"
    separator = "|" + "---|" * (len(providers) + 1)
    lines.extend([header, separator])

    metrics = [
        ("Runs", "num_runs", str),
        ("Recall Accuracy", "recall_accuracy", _pct),
        ("Hallucination Rate", "hallucination_rate", _pct),
        ("Honest Uncertainty", "honest_uncertainty_rate", _pct),
        ("Avg Partial Credit", "avg_partial_credit", _pct),
        ("Avg Latency", "avg_latency_ms", _ms),
        ("P95 Latency", "p95_latency_ms", _ms),
        ("Connection Drops", "connection_drops", str),
        ("Errors", "total_errors", str),
    ]

    for label, key, fmt in metrics:
        values = []
        for p in providers:
            v = comparison[p].get(key)
            values.append(fmt(v) if v is not None else "N/A")
        lines.append(f"| **{label}** | " + " | ".join(values) + " |")

    # Category breakdown
    lines.append("\n## Recall by Category\n")
    categories = set()
    for p in providers:
        categories.update(comparison[p].get("by_category", {}).keys())
    categories = sorted(categories)

    if categories:
        header = "| Category | " + " | ".join(p.upper() for p in providers) + " |"
        lines.extend([header, separator])
        for cat in categories:
            values = []
            for p in providers:
                v = comparison[p].get("by_category", {}).get(cat)
                values.append(_pct(v))
            lines.append(f"| {cat} | " + " | ".join(values) + " |")

    # Minute breakdown (group into early/mid/late)
    lines.append("\n## Recall by Time Period\n")
    header = "| Period | " + " | ".join(p.upper() for p in providers) + " |"
    lines.extend([header, separator])

    for period, minute_range in [("Early (0-20min)", range(0, 21)), ("Mid (20-40min)", range(20, 41)), ("Late (40-60min)", range(40, 61))]:
        values = []
        for p in providers:
            by_min = comparison[p].get("by_minute", {})
            period_scores = [v for k, v in by_min.items() if int(k) in minute_range and v is not None]
            values.append(_pct(_avg(period_scores)))
        lines.append(f"| {period} | " + " | ".join(values) + " |")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Compare voice benchmark results")
    parser.add_argument(
        "--experiment",
        "-e",
        required=True,
        help="Experiment ID (e.g. 01_long_session_context)",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format",
    )
    parser.add_argument(
        "--run",
        type=str,
        default=None,
        help="Run name to compare (e.g. run_002). If omitted, uses results/ root.",
    )

    args = parser.parse_args()

    # Normalize experiment ID
    exp_map = {
        "01": "e01_instant_context_recall",
        "02": "e02_context_window_cliff",
        "03": "e03_response_latency",
        "04": "e04_tool_call_reliability",
        "05": "e05_realtime_session_1hr",
        "06": "e06_audio_session",
        "07": "e07_production_sim",
    }
    experiment = exp_map.get(args.experiment, args.experiment)

    by_provider = load_results_by_provider(experiment, run_name=args.run)
    if not by_provider:
        print(f"No results found for experiment '{experiment}'")
        sys.exit(1)

    comparison = compare_experiment_01(by_provider)

    if args.format == "json":
        print(json.dumps(comparison, indent=2, default=str))
    else:
        print(format_markdown(comparison))


if __name__ == "__main__":
    main()
