#!/usr/bin/env python3
"""CLI entry point for running voice benchmarks.

Usage:
    python3 run_experiment.py --run run_002 -e 01 -p openai
    python3 run_experiment.py --run run_002 -e 01 -p all
    python3 run_experiment.py --run run_002 -e 05 -p openai --seconds-per-minute 5
    python3 run_experiment.py -e 01 -p openai --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from common.config import setup_logging
from common.results import save_result, set_run_dir

logger = setup_logging("runner")

PROVIDERS = {
    "openai": "providers.openai_realtime:OpenAIRealtimeProvider",
    "grok": "providers.grok_xai:GrokRealtimeProvider",
}

EXPERIMENTS = {
    "01": "experiments.e01_instant_context_recall.experiment",
    "02": "experiments.e02_context_window_cliff.experiment",
    "03": "experiments.e03_response_latency.experiment",
    "04": "experiments.e04_tool_call_reliability.experiment",
    "05": "experiments.e05_realtime_session_1hr.experiment",
    "06": "experiments.e06_audio_session.experiment",
    "07": "experiments.e07_production_sim.experiment",
}


def get_provider(name: str):
    """Dynamically import and instantiate a provider."""
    module_path, class_name = PROVIDERS[name].rsplit(":", 1)
    module = __import__(module_path, fromlist=[class_name])
    cls = getattr(module, class_name)
    return cls()


def get_provider_factory(name: str):
    """Return a callable that creates new provider instances."""
    module_path, class_name = PROVIDERS[name].rsplit(":", 1)
    module = __import__(module_path, fromlist=[class_name])
    cls = getattr(module, class_name)
    return cls


def get_experiment_module(experiment_id: str):
    """Dynamically import an experiment module."""
    module_path = EXPERIMENTS[experiment_id]
    return __import__(module_path, fromlist=["run"])


async def run_single(
    experiment_id: str,
    provider_name: str,
    *,
    dry_run: bool = False,
    skip_scoring: bool = False,
    seconds_per_minute: float = 60.0,
    transcript_path: str | None = None,
    questions_path: str | None = None,
    max_lines: int = 0,
    duration_minutes: int = 0,
) -> dict:
    """Run a single experiment with a single provider."""
    logger.info(
        "=== Running experiment %s with provider %s ===",
        experiment_id,
        provider_name,
    )

    experiment = get_experiment_module(experiment_id)

    # E07 takes a provider factory (creates multiple sessions), others take an instance
    if experiment_id == "07":
        if dry_run:
            provider_or_factory = None
        else:
            provider_or_factory = get_provider_factory(provider_name)
    else:
        if dry_run:
            provider_or_factory = None
        else:
            provider_or_factory = get_provider(provider_name)

    # Build kwargs
    kwargs: dict = {"dry_run": dry_run, "skip_scoring": skip_scoring}
    if experiment_id in ("05", "06", "07"):
        kwargs["seconds_per_minute"] = seconds_per_minute
        if transcript_path:
            kwargs["transcript_path"] = transcript_path
        if questions_path:
            kwargs["questions_path"] = questions_path
    if experiment_id in ("06", "07"):
        kwargs["max_lines"] = max_lines
    if experiment_id in ("05", "06", "07") and duration_minutes > 0:
        kwargs["duration_minutes"] = duration_minutes

    result = await experiment.run(provider_or_factory, **kwargs)

    if not dry_run:
        filepath = save_result(result)
        logger.info("Result saved to %s", filepath)

    return result


async def main():
    parser = argparse.ArgumentParser(description="Voice Benchmark Runner")
    parser.add_argument(
        "--run",
        type=str,
        default=None,
        help="Run name (e.g. run_002). Results saved under results/{run}/. "
             "Required for real runs.",
    )
    parser.add_argument(
        "--experiment",
        "-e",
        required=True,
        choices=list(EXPERIMENTS.keys()) + ["all"],
        help="Experiment to run (01-05, or all)",
    )
    parser.add_argument(
        "--provider",
        "-p",
        required=True,
        choices=list(PROVIDERS.keys()) + ["all"],
        help="Provider to test (openai, grok, or all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate experiment script without making API calls",
    )
    parser.add_argument(
        "--skip-scoring",
        action="store_true",
        help="Skip LLM judge scoring (return raw responses only)",
    )
    parser.add_argument(
        "--runs",
        "-n",
        type=int,
        default=1,
        help="Number of runs per provider (default: 1, recommended: 3)",
    )
    parser.add_argument(
        "--seconds-per-minute",
        type=float,
        default=60.0,
        help="Pacing for e05 real-time experiment. 60=real-time (1hr), "
             "30=half-speed (30min), 5=fast-test (5min). Default: 60",
    )
    parser.add_argument(
        "--transcript",
        type=str,
        default=None,
        help="Path to external meeting transcript file (for e05). "
             "Supports .txt (Speaker: text) or .json format.",
    )
    parser.add_argument(
        "--questions",
        type=str,
        default=None,
        help="Path to external questions JSON file (for e05).",
    )
    parser.add_argument(
        "--max-lines",
        type=int,
        default=0,
        help="Limit audio lines for E06 smoke tests. 0=all (default). Try 10 for quick tests.",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=0,
        help="Limit meeting to first N minutes. 0=full meeting (default). "
             "Try 15, 30, or 60 for duration-specific tests.",
    )

    args = parser.parse_args()

    # Set up run directory
    if args.run and not args.dry_run:
        set_run_dir(args.run)

    experiments = list(EXPERIMENTS.keys()) if args.experiment == "all" else [args.experiment]
    providers = list(PROVIDERS.keys()) if args.provider == "all" else [args.provider]

    for exp_id in experiments:
        for prov_name in providers:
            for run_num in range(1, args.runs + 1):
                if args.runs > 1:
                    logger.info("--- Run %d/%d ---", run_num, args.runs)
                try:
                    await run_single(
                        exp_id,
                        prov_name,
                        dry_run=args.dry_run,
                        skip_scoring=args.skip_scoring,
                        seconds_per_minute=args.seconds_per_minute,
                        transcript_path=args.transcript,
                        questions_path=args.questions,
                        max_lines=args.max_lines,
                        duration_minutes=args.duration,
                    )
                except Exception:
                    logger.exception(
                        "Error running experiment %s with %s (run %d)",
                        exp_id,
                        prov_name,
                        run_num,
                    )


if __name__ == "__main__":
    asyncio.run(main())
