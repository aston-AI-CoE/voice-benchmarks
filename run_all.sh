#!/usr/bin/env bash
#
# Voice Benchmarks — Full Test Suite (MAX PARALLEL)
#
# ALL experiments run in parallel. Each gets its own log.
# Total time ≈ longest single experiment (~65 min for E06/E07 60min)
#
set -euo pipefail
cd "$(dirname "$0")"

# --- Determine run name ---
LAST=$(ls -d results/run_* 2>/dev/null | sort -V | tail -1 | grep -oP '\d+$' || echo "0")
RUN_NUM=$(printf "%03d" $((10#$LAST + 1)))
RUN_NAME="run_${RUN_NUM}"
RUN_DIR="results/${RUN_NAME}"
mkdir -p "$RUN_DIR"
LOG="${RUN_DIR}/run.log"
exec > >(tee -a "$LOG") 2>&1

echo "=============================================="
echo "  Voice Benchmarks — ${RUN_NAME} (MAX PARALLEL)"
echo "  $(date)"
echo "  Log: ${LOG}"
echo "=============================================="
echo ""

if [ ! -f .env ]; then echo "ERROR: .env not found."; exit 1; fi
pip3 install -q -r requirements.txt

# --- Dry runs (fast, sequential) ---
echo "=== Dry Runs ==="
FAIL=0
for exp in 01 02 03 04 06 07; do
    echo -n "  E${exp}... "
    if python3 run_experiment.py -e "$exp" -p openai --dry-run --seconds-per-minute 5 > /dev/null 2>&1; then
        echo "OK"
    else
        echo "FAIL"; FAIL=1
    fi
done
if [ "$FAIL" -eq 1 ]; then exit 1; fi

# --- Audio check ---
[ -f "audio_fixtures/meeting_1hr/manifest.json" ] || { echo "ERROR: Run python3 generate_audio.py --meeting meeting_1hr"; exit 1; }
[ -f "audio_fixtures/meeting_1hr_questions/manifest.json" ] || { echo "ERROR: Run python3 generate_question_audio.py"; exit 1; }
echo "Audio: OK"
echo ""

# --- Helper: run one experiment and log to its own file ---
run_exp() {
    local exp=$1 provider=$2 extra="${3:-}"
    local label="E${exp}_${provider}${extra:+_${extra}}"
    local logfile="${RUN_DIR}/${label}.log"
    echo "[START] ${label} ($(date))"
    python3 run_experiment.py --run "$RUN_NAME" -e "$exp" -p "$provider" $extra > "$logfile" 2>&1
    local status=$?
    if [ $status -eq 0 ]; then
        echo "[DONE]  ${label} ($(date))"
    else
        echo "[FAIL]  ${label} ($(date)) — see ${logfile}"
    fi
    return $status
}

echo "=============================================="
echo "  Launching ALL experiments in parallel"
echo "  $(date)"
echo "=============================================="
echo ""

PIDS=()

# --- E01-E04: Fast experiments ---
run_exp 01 openai & PIDS+=($!)
run_exp 01 grok & PIDS+=($!)
run_exp 02 openai & PIDS+=($!)
run_exp 02 grok & PIDS+=($!)
run_exp 03 openai & PIDS+=($!)
run_exp 03 grok & PIDS+=($!)
run_exp 04 openai & PIDS+=($!)
run_exp 04 grok & PIDS+=($!)

# --- E06: Both providers (Grok last chance — now using input_audio_buffer + VAD) ---
run_exp 06 openai "--duration 15" & PIDS+=($!)
run_exp 06 openai "--duration 30" & PIDS+=($!)
run_exp 06 openai "--duration 60" & PIDS+=($!)
run_exp 06 grok "--duration 15" & PIDS+=($!)
run_exp 06 grok "--duration 30" & PIDS+=($!)
run_exp 06 grok "--duration 60" & PIDS+=($!)

# --- E07: Both providers ---
run_exp 07 openai "--duration 15" & PIDS+=($!)
run_exp 07 openai "--duration 30" & PIDS+=($!)
run_exp 07 openai "--duration 60" & PIDS+=($!)
run_exp 07 grok "--duration 15" & PIDS+=($!)
run_exp 07 grok "--duration 30" & PIDS+=($!)
run_exp 07 grok "--duration 60" & PIDS+=($!)

echo ""
echo "  ${#PIDS[@]} experiments launched. Waiting..."
echo ""

# --- Wait for all, track failures ---
FAILURES=0
for pid in "${PIDS[@]}"; do
    wait "$pid" || ((FAILURES++))
done

echo ""
echo "=============================================="
echo "  All experiments complete"
echo "  $(date)"
echo "  Failures: ${FAILURES}/${#PIDS[@]}"
echo "=============================================="
echo ""

# --- Summary ---
SUMMARY="${RUN_DIR}/summary.txt"
{
    echo "Voice Benchmarks — ${RUN_NAME}"
    echo "Date: $(date)"
    echo "Failures: ${FAILURES}/${#PIDS[@]}"
    echo ""
    echo "========== E01: Instant Context Recall =========="
    python3 compare_results.py -e 01 --run "$RUN_NAME" 2>/dev/null || echo "(no results)"
    echo ""
    echo "========== E06: Always-Streaming Audio (OpenAI) =========="
    python3 compare_results.py -e 06 --run "$RUN_NAME" 2>/dev/null || echo "(no results)"
    echo ""
    echo "========== E07: Production Sim =========="
    python3 compare_results.py -e 07 --run "$RUN_NAME" 2>/dev/null || echo "(no results)"
} > "$SUMMARY" 2>&1

cat "$SUMMARY"

echo ""
echo "=============================================="
echo "  ALL DONE — ${RUN_NAME}"
echo "  $(date)"
echo "=============================================="
echo "Results:  ${RUN_DIR}/"
echo "Log:      ${LOG}"
echo "Per-experiment logs: ${RUN_DIR}/E*.log"
echo "Summary:  ${SUMMARY}"
