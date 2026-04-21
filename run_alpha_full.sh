#!/usr/bin/env bash
#
# run_alpha_full.sh — gpt-realtime-alpha-dolphin-6 full overnight benchmark
#
# Runs all experiments across reasoning effort levels, validates E06 before
# committing to full-length runs, then generates a structured report.
#
# Usage:
#   nohup ./run_alpha_full.sh > /dev/null 2>&1 &
#   tail -f results/run_XXX/run.log
#
set -euo pipefail
cd "$(dirname "$0")"

MODEL="gpt-realtime-alpha-dolphin-6"

# ── Run name ─────────────────────────────────────────────────────────────────
LAST=$(ls -d results/run_* 2>/dev/null | sort -V | tail -1 | grep -oP '\d+$' || echo "0")
RUN_NUM=$(printf "%03d" $((10#$LAST + 1)))
RUN_NAME="run_${RUN_NUM}"
RUN_DIR="results/${RUN_NAME}"
mkdir -p "$RUN_DIR"
LOG="${RUN_DIR}/run.log"
exec > >(tee -a "$LOG") 2>&1

echo "=============================================="
echo "  Alpha Full Run — ${RUN_NAME}"
echo "  Model: ${MODEL}"
echo "  $(date)"
echo "=============================================="

[ -f .env ] || { echo "ERROR: .env not found"; exit 1; }
pip3 install -q -r requirements.txt
export OPENAI_REALTIME_MODEL="$MODEL"

# ── Audio fixtures ────────────────────────────────────────────────────────────
if [ -f "audio_fixtures/meeting_1hr/manifest.json" ] && [ -f "audio_fixtures/meeting_1hr_questions/manifest.json" ]; then
    echo "Audio fixtures: OK"
else
    echo "ERROR: Audio fixtures missing. Run:"
    echo "  cp -r /root/voice-benchmarks/audio_fixtures/meeting_1hr audio_fixtures/"
    echo "  cp -r /root/voice-benchmarks/audio_fixtures/meeting_1hr_questions audio_fixtures/"
    exit 1
fi

# ── Helper ────────────────────────────────────────────────────────────────────
run_exp() {
    local exp=$1 effort=$2 extra="${3:-}"
    local label="E${exp}_alpha_${effort}${extra:+_${extra//[^a-zA-Z0-9_]/_}}"
    local logfile="${RUN_DIR}/${label}.log"
    echo "[START] ${label} ($(date))"
    OPENAI_REASONING_EFFORT="$effort" \
        python3 run_experiment.py --run "$RUN_NAME" -e "$exp" -p openai-alpha $extra \
        > "$logfile" 2>&1
    local rc=$?
    [ $rc -eq 0 ] && echo "[DONE]  ${label} ($(date))" \
                   || echo "[FAIL]  ${label} exit=${rc} — see ${logfile}"
    return $rc
}

PIDS=()
FAILURES=0

# ── Phase 1: Fast text experiments — all 4 effort levels in parallel ──────────
echo ""
echo "=== Phase 1: Text experiments (E01 E02 E03 E04) ==="
for effort in minimal low medium high; do
    run_exp 01 "$effort" & PIDS+=($!)
    run_exp 03 "$effort" & PIDS+=($!)
    run_exp 04 "$effort" & PIDS+=($!)
done
run_exp 02 low & PIDS+=($!)

for pid in "${PIDS[@]}"; do wait "$pid" || ((FAILURES++)) || true; done
PIDS=()
echo "=== Phase 1 done (failures so far: ${FAILURES}) ==="

# ── Phase 2: E06 validation — 15min at low before committing to full runs ─────
echo ""
echo "=== Phase 2: E06 validation (15min, low) ==="
run_exp 06 low "--duration 15"
E06_VALID=$?

if [ $E06_VALID -ne 0 ]; then
    echo "WARN: E06 validation failed — skipping full E06 runs. E07 will continue."
fi

# ── Phase 3: E06 full + E07 full in parallel ──────────────────────────────────
echo ""
echo "=== Phase 3: E06 and E07 full runs ==="

# E07 at low + medium, 15min + 60min
for effort in low medium; do
    run_exp 07 "$effort" "--duration 15" & PIDS+=($!)
    run_exp 07 "$effort" "--duration 60" & PIDS+=($!)
done

# E06 full only if validation passed
if [ $E06_VALID -eq 0 ]; then
    for effort in low medium; do
        run_exp 06 "$effort" "--duration 60" & PIDS+=($!)
    done
else
    echo "Skipping E06 full runs (validation failed)"
fi

for pid in "${PIDS[@]}"; do wait "$pid" || ((FAILURES++)) || true; done
PIDS=()
echo "=== Phase 3 done ==="

# ── Report ────────────────────────────────────────────────────────────────────
echo ""
echo "=== Generating report ==="
python3 generate_alpha_report.py --run "$RUN_NAME" \
    > "${RUN_DIR}/alpha_report.md" 2>&1 \
    && echo "Report: ${RUN_DIR}/alpha_report.md" \
    || echo "WARN: report generation failed — check generate_alpha_report.py"

# ── Summary ───────────────────────────────────────────────────────────────────
SUMMARY="${RUN_DIR}/summary.txt"
{
    echo "Alpha Full Run — ${RUN_NAME}"
    echo "Model: ${MODEL}"
    echo "Date: $(date)"
    echo "Total failures: ${FAILURES}"
    echo ""
    for exp in 01 03 06 07; do
        echo "===== E${exp} ====="
        python3 compare_results.py -e "$exp" --run "$RUN_NAME" 2>/dev/null || echo "(no results)"
        echo ""
    done
} > "$SUMMARY" 2>&1
cat "$SUMMARY"

echo ""
echo "=============================================="
echo "  DONE — ${RUN_NAME}  failures=${FAILURES}"
echo "  $(date)"
echo "  Report:  ${RUN_DIR}/alpha_report.md"
echo "  Summary: ${SUMMARY}"
echo "  Logs:    ${RUN_DIR}/E*.log"
echo "=============================================="
