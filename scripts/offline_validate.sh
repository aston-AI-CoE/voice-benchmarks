#!/usr/bin/env bash
#
# Credential-free validation for CI and local preflight checks.
#
# This intentionally does not run benchmark experiments, generate audio, open
# network connections, use microphones, or write benchmark results.
set -euo pipefail

cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1

echo "[offline] Checking shell script syntax"
while IFS= read -r script; do
    bash -n "$script"
done < <(git ls-files 'scripts/*.sh')

echo "[offline] Checking Python syntax and import registry"
python3 - <<'PY'
from __future__ import annotations

import ast
import importlib
import subprocess
import sys
from pathlib import Path

root = Path.cwd()
sys.path.insert(0, str(root))

tracked_python = subprocess.run(
    ["git", "ls-files", "*.py"],
    check=True,
    capture_output=True,
    text=True,
).stdout.splitlines()

for relative_path in tracked_python:
    path = root / relative_path
    ast.parse(path.read_text(encoding="utf-8"), filename=relative_path)

runner = importlib.import_module("run_experiment")

for experiment_id, module_path in sorted(runner.EXPERIMENTS.items()):
    module = importlib.import_module(module_path)
    run = getattr(module, "run", None)
    if not callable(run):
        raise RuntimeError(
            f"Experiment {experiment_id} module {module_path} has no callable run()"
        )

for provider_name, import_path in sorted(runner.PROVIDERS.items()):
    module_path, class_name = import_path.rsplit(":", 1)
    module = importlib.import_module(module_path)
    provider_class = getattr(module, class_name, None)
    if provider_class is None:
        raise RuntimeError(
            f"Provider {provider_name} target {import_path} could not be resolved"
        )

print(
    f"[offline] Parsed {len(tracked_python)} Python files, "
    f"validated {len(runner.EXPERIMENTS)} experiments and "
    f"{len(runner.PROVIDERS)} providers"
)
PY

echo "[offline] Validation complete"
