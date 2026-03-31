"""Result storage, loading, and comparison utilities.

Results are organized by run:
    results/{run_name}/{experiment}/{provider}_{timestamp}.json
    results/{run_name}/run.log

If no run_name is set, falls back to: results/{experiment}/...
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from common.config import RESULTS_DIR, setup_logging

logger = setup_logging("results")

# Global run directory — set by the CLI runner
_run_dir: Path | None = None


def set_run_dir(run_name: str) -> Path:
    """Set the run directory for this session. Creates it if needed."""
    global _run_dir
    _run_dir = RESULTS_DIR / run_name
    _run_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Run directory: %s", _run_dir)
    return _run_dir


def get_run_dir() -> Path | None:
    return _run_dir


def save_result(result: dict) -> Path:
    """Save an experiment result to a JSON file.

    If a run dir is set: results/{run_name}/{experiment}/{provider}_{timestamp}.json
    Otherwise:           results/{experiment}/{provider}_{timestamp}.json
    """
    experiment = result.get("experiment", "unknown")
    provider = result.get("provider", "unknown")
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    base = _run_dir if _run_dir else RESULTS_DIR
    out_dir = base / experiment
    out_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{provider}_{ts}.json"
    filepath = out_dir / filename

    # Add run metadata
    result["run_id"] = f"{ts}_{provider}_{experiment}"
    result["run_name"] = _run_dir.name if _run_dir else None
    result["saved_at"] = datetime.now(timezone.utc).isoformat()

    with open(filepath, "w") as f:
        json.dump(result, f, indent=2, default=str)

    logger.info("Saved result to %s", filepath)
    return filepath


def load_results(experiment: str, run_name: str | None = None) -> list[dict]:
    """Load all results for a given experiment, optionally from a specific run."""
    if run_name:
        out_dir = RESULTS_DIR / run_name / experiment
    else:
        out_dir = RESULTS_DIR / experiment
    if not out_dir.exists():
        return []

    results = []
    for f in sorted(out_dir.glob("*.json")):
        with open(f) as fp:
            data = json.load(fp)
            data["_filepath"] = str(f)
            results.append(data)
    return results


def load_results_by_provider(
    experiment: str, run_name: str | None = None
) -> dict[str, list[dict]]:
    """Load results grouped by provider."""
    results = load_results(experiment, run_name)
    by_provider: dict[str, list[dict]] = {}
    for r in results:
        provider = r.get("provider", "unknown")
        by_provider.setdefault(provider, []).append(r)
    return by_provider


def latest_result(
    experiment: str, provider: str, run_name: str | None = None
) -> dict | None:
    """Get the most recent result for a given experiment and provider."""
    if run_name:
        out_dir = RESULTS_DIR / run_name / experiment
    else:
        out_dir = RESULTS_DIR / experiment
    if not out_dir.exists():
        return None

    files = sorted(out_dir.glob(f"{provider}_*.json"), reverse=True)
    if not files:
        return None

    with open(files[0]) as f:
        return json.load(f)
