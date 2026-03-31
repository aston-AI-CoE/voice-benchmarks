#!/usr/bin/env python3
"""Analysis script for experiment 01 results.

Loads results, prints detailed per-fact breakdown, and identifies
patterns in recall failure.

Usage:
    python -m experiments.01_long_session_context.analyze
    python -m experiments.01_long_session_context.analyze --provider openai
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from common.config import setup_logging
from common.results import load_results_by_provider, latest_result

logger = setup_logging("analyze.01")


def analyze_single_run(result: dict) -> None:
    """Print detailed analysis of a single experiment run."""
    provider = result.get("provider", "unknown")
    aggregate = result.get("aggregate")

    print(f"\n{'='*70}")
    print(f"  Provider: {provider.upper()}")
    print(f"  Run: {result.get('run_id', 'unknown')}")
    print(f"{'='*70}")

    if not aggregate:
        print("  [No scored results — run with scoring enabled]")
        return

    # Headline metrics
    print(f"\n  Recall Accuracy:       {aggregate['recall_accuracy']*100:.0f}%")
    print(f"  Hallucination Rate:    {aggregate['hallucination_rate']*100:.0f}%")
    print(f"  Honest Uncertainty:    {aggregate['honest_uncertainty_rate']*100:.0f}%")
    print(f"  Avg Partial Credit:    {aggregate['avg_partial_credit']*100:.0f}%")

    # Per-fact breakdown
    scores = result.get("scores", [])
    if scores:
        print(f"\n  {'Fact ID':<20} {'Verdict':<20} {'Credit':>7} {'Rationale'}")
        print(f"  {'-'*20} {'-'*20} {'-'*7} {'-'*40}")
        for s in scores:
            print(
                f"  {s['fact_id']:<20} {s['verdict']:<20} {s['partial_credit']:>6.0%} "
                f"{s['rationale'][:50]}"
            )

    # Hallucination probe results
    h_scores = result.get("hallucination_scores", [])
    if h_scores:
        print(f"\n  Hallucination Probes:")
        print(f"  {'Probe ID':<15} {'Verdict':<20} {'Hallucinated':>12}")
        print(f"  {'-'*15} {'-'*20} {'-'*12}")
        for s in h_scores:
            marker = "YES" if s["hallucinated"] else "no"
            print(f"  {s['fact_id']:<15} {s['verdict']:<20} {marker:>12}")

    # Category analysis
    by_cat = aggregate.get("by_category", {})
    if by_cat:
        print(f"\n  By Category:")
        for cat, score in sorted(by_cat.items()):
            bar = "#" * int(score * 20)
            print(f"    {cat:<12} {score*100:>5.0f}%  {bar}")

    # Time decay analysis
    by_min = aggregate.get("by_minute", {})
    if by_min:
        print(f"\n  Recall Decay (by minute planted):")
        for minute in sorted(by_min.keys(), key=int):
            score = by_min[minute]
            bar = "#" * int(score * 20)
            print(f"    min {minute:>3}  {score*100:>5.0f}%  {bar}")

    # Latency analysis
    recall_results = result.get("recall_results", [])
    latencies = [r["latency_ms"] for r in recall_results if r.get("latency_ms")]
    if latencies:
        avg_lat = sum(latencies) / len(latencies)
        p95_lat = sorted(latencies)[int(len(latencies) * 0.95)]
        print(f"\n  Latency: avg={avg_lat:.0f}ms  p95={p95_lat:.0f}ms")

    # Worst performers
    if scores:
        failures = [s for s in scores if s["partial_credit"] < 0.5]
        if failures:
            print(f"\n  Failed Recalls ({len(failures)}):")
            for s in failures:
                print(f"    - {s['fact_id']}: {s['rationale'][:70]}")

    # Session health
    metrics = result.get("session_metrics", {})
    print(f"\n  Session: {metrics.get('items_injected', 0)} items injected, "
          f"{metrics.get('connection_drops', 0)} drops, "
          f"{len(metrics.get('errors', []))} errors")


def main():
    parser = argparse.ArgumentParser(description="Analyze experiment 01 results")
    parser.add_argument("--provider", "-p", help="Filter to specific provider")
    args = parser.parse_args()

    by_provider = load_results_by_provider("e01_instant_context_recall")
    if not by_provider:
        print("No results found for experiment 01. Run the experiment first.")
        sys.exit(1)

    if args.provider:
        if args.provider not in by_provider:
            print(f"No results for provider '{args.provider}'")
            sys.exit(1)
        by_provider = {args.provider: by_provider[args.provider]}

    for provider, runs in by_provider.items():
        print(f"\n{'#'*70}")
        print(f"  {provider.upper()} — {len(runs)} run(s)")
        print(f"{'#'*70}")
        for run in runs:
            analyze_single_run(run)

    # Cross-provider summary if multiple providers
    if len(by_provider) > 1:
        print(f"\n{'='*70}")
        print("  CROSS-PROVIDER SUMMARY")
        print(f"{'='*70}")
        for provider, runs in by_provider.items():
            aggs = [r.get("aggregate") for r in runs if r.get("aggregate")]
            if aggs:
                avg_recall = sum(a["recall_accuracy"] for a in aggs) / len(aggs)
                avg_halluc = sum(a["hallucination_rate"] for a in aggs) / len(aggs)
                print(f"  {provider:>8}: recall={avg_recall*100:.0f}%  hallucination={avg_halluc*100:.0f}%")


if __name__ == "__main__":
    main()
