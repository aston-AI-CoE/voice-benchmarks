#!/usr/bin/env bash
#
# Voice Benchmarks — Full Test Suite
#
# Usage:
#   ./run_all.sh                          # interactive
#   nohup ./run_all.sh > /dev/null 2>&1 & # background (logs saved internally)
#
# Structure:
#   results/
#     run_002/
#       run.log              ← full log for this run
#       e01_instant_context_recall/
#         openai_*.json
#         grok_*.json
#       e02_context_window_cliff/
#         ...
#       e05_realtime_session_1hr/
#         ...
#       summary.txt          ← final comparison tables
#
set -euo pipefail

cd "$(dirname "$0")"

# --- Determine run name ---
# Auto-increment: find highest run_NNN and add 1
LAST=$(ls -d results/run_* 2>/dev/null | sort -V | tail -1 | grep -oP '\d+$' || echo "0")
RUN_NUM=$(printf "%03d" $((10#$LAST + 1)))
RUN_NAME="run_${RUN_NUM}"
RUN_DIR="results/${RUN_NAME}"

mkdir -p "$RUN_DIR"
LOG="${RUN_DIR}/run.log"

# Tee all output to both terminal and log file
exec > >(tee -a "$LOG") 2>&1

echo "=============================================="
echo "  Voice Benchmarks — ${RUN_NAME}"
echo "  $(date)"
echo "  Log: ${LOG}"
echo "=============================================="
echo ""

# --- Setup ---
if [ ! -f .env ]; then
    echo "ERROR: .env file not found. Copy .env.example and fill in API keys."
    exit 1
fi

echo "[setup] Installing dependencies..."
pip3 install -q -r requirements.txt
echo ""

# ==========================================================
# PHASE 1: DRY RUNS — validate before spending API credits
# ==========================================================
echo "=============================================="
echo "  PHASE 1: Dry Runs"
echo "=============================================="
echo ""

FAIL=0
for exp in 01 02 03 04 05 06; do
    echo -n "  E${exp} dry-run... "
    if python3 run_experiment.py -e "$exp" -p openai --dry-run --seconds-per-minute 5 > /dev/null 2>&1; then
        echo "OK"
    else
        echo "FAIL"
        FAIL=1
    fi
done
echo ""

if [ "$FAIL" -eq 1 ]; then
    echo "ERROR: Dry run failed. Fix issues before running."
    exit 1
fi

echo "All dry runs passed."
echo ""

# ==========================================================
# PHASE 2: Fast Experiments (E01-E04)
#   ~25 min total
# ==========================================================
echo "=============================================="
echo "  PHASE 2: Fast Experiments (E01-E04)"
echo "  Started: $(date)"
echo "=============================================="
echo ""

echo "--- E01: Instant Context Recall ---"
python3 run_experiment.py --run "$RUN_NAME" -e 01 -p openai
python3 run_experiment.py --run "$RUN_NAME" -e 01 -p grok
echo ""

echo "--- E02: Context Window Cliff ---"
python3 run_experiment.py --run "$RUN_NAME" -e 02 -p openai
python3 run_experiment.py --run "$RUN_NAME" -e 02 -p grok
echo ""

echo "--- E03: Response Latency ---"
python3 run_experiment.py --run "$RUN_NAME" -e 03 -p openai
python3 run_experiment.py --run "$RUN_NAME" -e 03 -p grok
echo ""

echo "--- E04: Tool Call Reliability ---"
python3 run_experiment.py --run "$RUN_NAME" -e 04 -p openai
python3 run_experiment.py --run "$RUN_NAME" -e 04 -p grok
echo ""

echo "  Phase 2 complete: $(date)"
echo ""

# ==========================================================
# PHASE 3: E05 Smoke Test (5-min pacing)
#   ~12 min total
# ==========================================================
echo "=============================================="
echo "  PHASE 3: E05 Smoke Test (5-min pacing)"
echo "  Started: $(date)"
echo "=============================================="
echo ""

python3 run_experiment.py --run "$RUN_NAME" -e 05 -p openai --seconds-per-minute 5
python3 run_experiment.py --run "$RUN_NAME" -e 05 -p grok --seconds-per-minute 5
echo ""

echo "  Smoke test complete: $(date)"
echo ""

# ==========================================================
# PHASE 4: Real 1-Hour Sessions
#   ~65 min per provider, ~130 min total
# ==========================================================
echo "=============================================="
echo "  PHASE 4: Real 1-Hour Sessions"
echo "  Started: $(date)"
echo "  ETA: ~2 hours from now"
echo "=============================================="
echo ""

echo "[OpenAI 1hr] Started: $(date)"
python3 run_experiment.py --run "$RUN_NAME" -e 05 -p openai --seconds-per-minute 60
echo "[OpenAI 1hr] Finished: $(date)"
echo ""

echo "[Grok 1hr] Started: $(date)"
python3 run_experiment.py --run "$RUN_NAME" -e 05 -p grok --seconds-per-minute 60
echo "[Grok 1hr] Finished: $(date)"
echo ""

# ==========================================================
# PHASE 5: E06 Audio Session (REAL voice pipeline)
#   Uses same meeting as E05 but streams actual audio
#   Audio fixtures must be generated once beforehand
# ==========================================================
echo "=============================================="
echo "  PHASE 5: E06 Audio Session"
echo "  Started: $(date)"
echo "=============================================="
echo ""

# Generate audio fixtures if they don't exist yet
if [ ! -f "audio_fixtures/realistic_meeting/manifest.json" ]; then
    echo "[E06] Generating audio fixtures (one-time, ~3 min)..."
    python3 generate_audio.py
fi

echo "[E06 smoke] Audio smoke test — 5 min pacing..."
python3 run_experiment.py --run "$RUN_NAME" -e 06 -p openai --seconds-per-minute 5
python3 run_experiment.py --run "$RUN_NAME" -e 06 -p grok --seconds-per-minute 5
echo ""

echo "[E06 OpenAI 1hr audio] Started: $(date)"
python3 run_experiment.py --run "$RUN_NAME" -e 06 -p openai --seconds-per-minute 60
echo "[E06 OpenAI 1hr audio] Finished: $(date)"
echo ""

echo "[E06 Grok 1hr audio] Started: $(date)"
python3 run_experiment.py --run "$RUN_NAME" -e 06 -p grok --seconds-per-minute 60
echo "[E06 Grok 1hr audio] Finished: $(date)"
echo ""

# ==========================================================
# PHASE 6: Summary
# ==========================================================
echo "=============================================="
echo "  Generating summary..."
echo "=============================================="
echo ""

SUMMARY="${RUN_DIR}/summary.txt"
{
    echo "Voice Benchmarks — ${RUN_NAME}"
    echo "Date: $(date)"
    echo ""
    echo "========== E01: Instant Context Recall =========="
    python3 compare_results.py -e 01 --run "$RUN_NAME" 2>/dev/null || echo "(no results)"
    echo ""
    echo "========== E05: Real-Time 1hr Session (text) =========="
    python3 compare_results.py -e 05 --run "$RUN_NAME" 2>/dev/null || echo "(no results)"
    echo ""
    echo "========== E06: Audio Session =========="
    python3 compare_results.py -e 06 --run "$RUN_NAME" 2>/dev/null || echo "(no results)"
} > "$SUMMARY" 2>&1

cat "$SUMMARY"

echo ""
echo "=============================================="
echo "  ALL DONE — ${RUN_NAME}"
echo "  $(date)"
echo "=============================================="
echo ""
echo "Results:  ${RUN_DIR}/"
echo "Log:      ${LOG}"
echo "Summary:  ${SUMMARY}"
echo ""
echo "Commands:"
echo "  python3 compare_results.py -e 01 --run ${RUN_NAME}"
echo "  python3 compare_results.py -e 05 --run ${RUN_NAME}"
echo "  python3 compare_results.py -e 06 --run ${RUN_NAME}"
