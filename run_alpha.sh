#!/usr/bin/env bash
#
# Voice Benchmarks — gpt-realtime-alpha-dolphin-6 full suite
#
# Runs all experiments across reasoning effort levels.
# E01/E03/E04: all 4 effort levels in parallel
# E02:         low effort only
# E06/E07:     low + medium (require audio fixtures)
#
# Usage:
#   ./run_alpha.sh                      # full suite
#   ./run_alpha.sh --skip-audio         # skip E06/E07 (no audio fixtures needed)
#   ./run_alpha.sh --effort low         # single effort level, all experiments
#
set -euo pipefail
cd "$(dirname "$0")"

MODEL="gpt-realtime-alpha-dolphin-6"
SKIP_AUDIO=0
SINGLE_EFFORT=""

for arg in "$@"; do
    case "$arg" in
        --skip-audio) SKIP_AUDIO=1 ;;
        --effort) shift; SINGLE_EFFORT="$1" ;;
        --effort=*) SINGLE_EFFORT="${arg#--effort=}" ;;
    esac
done

# --- Run name ---
LAST=$(ls -d results/run_* 2>/dev/null | sort -V | tail -1 | grep -oP '\d+$' || echo "0")
RUN_NUM=$(printf "%03d" $((10#$LAST + 1)))
RUN_NAME="run_${RUN_NUM}"
RUN_DIR="results/${RUN_NAME}"
mkdir -p "$RUN_DIR"
LOG="${RUN_DIR}/run.log"
exec > >(tee -a "$LOG") 2>&1

echo "=============================================="
echo "  Alpha Benchmarks — ${RUN_NAME}"
echo "  Model: ${MODEL}"
echo "  $(date)"
echo "  Log: ${LOG}"
echo "=============================================="
echo ""

[ -f .env ] || { echo "ERROR: .env not found."; exit 1; }
pip3 install -q -r requirements.txt
export OPENAI_REALTIME_MODEL="$MODEL"

# --- Audio fixtures check ---
HAS_AUDIO=0
if [ -f "audio_fixtures/meeting_1hr/manifest.json" ] && [ -f "audio_fixtures/meeting_1hr_questions/manifest.json" ]; then
    HAS_AUDIO=1
    echo "Audio fixtures: OK"
else
    echo "Audio fixtures: MISSING"
    if [ "$SKIP_AUDIO" -eq 0 ]; then
        echo "  Generating now (~10 min)..."
        python3 generate_audio.py --meeting meeting_1hr
        python3 generate_question_audio.py
        HAS_AUDIO=1
        echo "  Audio fixtures: generated"
    else
        echo "  Skipping E06/E07 (--skip-audio)"
    fi
fi
echo ""

# --- Dry-run validation ---
echo "=== Dry-run validation ==="
FAIL=0
for exp in 01 02 03 04; do
    echo -n "  E${exp}... "
    if OPENAI_REASONING_EFFORT=low python3 run_experiment.py -e "$exp" -p openai-alpha --dry-run > /dev/null 2>&1; then
        echo "OK"
    else
        echo "FAIL"; FAIL=1
    fi
done
if [ "$HAS_AUDIO" -eq 1 ]; then
    for exp in 06 07; do
        echo -n "  E${exp}... "
        if OPENAI_REASONING_EFFORT=low python3 run_experiment.py -e "$exp" -p openai-alpha --dry-run --seconds-per-minute 5 > /dev/null 2>&1; then
            echo "OK"
        else
            echo "FAIL"; FAIL=1
        fi
    done
fi
[ "$FAIL" -eq 0 ] || { echo "Dry-run failures — aborting."; exit 1; }
echo ""

# --- Effort levels to test ---
if [ -n "$SINGLE_EFFORT" ]; then
    EFFORTS=("$SINGLE_EFFORT")
else
    EFFORTS=(minimal low medium high)
fi

# --- Helper ---
run_exp() {
    local exp=$1 effort=$2 extra="${3:-}"
    local label="E${exp}_alpha_${effort}${extra:+_${extra//--/}}"
    local logfile="${RUN_DIR}/${label}.log"
    echo "[START] ${label} ($(date))"
    OPENAI_REASONING_EFFORT="$effort" \
        python3 run_experiment.py --run "$RUN_NAME" -e "$exp" -p openai-alpha $extra \
        > "$logfile" 2>&1
    local status=$?
    [ $status -eq 0 ] && echo "[DONE]  ${label} ($(date))" \
                       || echo "[FAIL]  ${label} ($(date)) — see ${logfile}"
    return $status
}

echo "=============================================="
echo "  Launching experiments"
echo "  Effort levels: ${EFFORTS[*]}"
echo "  $(date)"
echo "=============================================="
echo ""

PIDS=()

# E01, E03, E04: all effort levels (fast, run in parallel)
for effort in "${EFFORTS[@]}"; do
    run_exp 01 "$effort" & PIDS+=($!)
    run_exp 03 "$effort" & PIDS+=($!)
    run_exp 04 "$effort" & PIDS+=($!)
done

# E02: low only (slow context cliff test, single run sufficient)
run_exp 02 low & PIDS+=($!)

# E06/E07: low + medium (long audio tests)
if [ "$HAS_AUDIO" -eq 1 ]; then
    for effort in low medium; do
        # Skip if running single effort that's not low or medium
        if [ -n "$SINGLE_EFFORT" ] && [ "$SINGLE_EFFORT" != "$effort" ]; then
            continue
        fi
        run_exp 06 "$effort" "--duration 15" & PIDS+=($!)
        run_exp 06 "$effort" "--duration 60" & PIDS+=($!)
        run_exp 07 "$effort" "--duration 15" & PIDS+=($!)
        run_exp 07 "$effort" "--duration 60" & PIDS+=($!)
    done
fi

echo ""
echo "  ${#PIDS[@]} experiments launched. Waiting..."
echo ""

FAILURES=0
for pid in "${PIDS[@]}"; do
    wait "$pid" || ((FAILURES++)) || true
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
    echo "Alpha Benchmarks — ${RUN_NAME}"
    echo "Model: ${MODEL}"
    echo "Date: $(date)"
    echo "Efforts tested: ${EFFORTS[*]}"
    echo "Failures: ${FAILURES}/${#PIDS[@]}"
    echo ""
    echo "========== E01: Instant Context Recall =========="
    python3 compare_results.py -e 01 --run "$RUN_NAME" 2>/dev/null || echo "(no results)"
    echo ""
    echo "========== E03: Response Latency =========="
    python3 compare_results.py -e 03 --run "$RUN_NAME" 2>/dev/null || echo "(no results)"
    echo ""
    if [ "$HAS_AUDIO" -eq 1 ]; then
        echo "========== E06: Always-Streaming Audio =========="
        python3 compare_results.py -e 06 --run "$RUN_NAME" 2>/dev/null || echo "(no results)"
        echo ""
        echo "========== E07: Production Sim =========="
        python3 compare_results.py -e 07 --run "$RUN_NAME" 2>/dev/null || echo "(no results)"
    fi
} > "$SUMMARY" 2>&1

cat "$SUMMARY"

echo ""
echo "=============================================="
echo "  ALL DONE — ${RUN_NAME}"
echo "  $(date)"
echo "=============================================="
echo "Results:  ${RUN_DIR}/"
echo "Summary:  ${SUMMARY}"
echo "Per-experiment logs: ${RUN_DIR}/E*.log"
