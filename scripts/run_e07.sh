#!/usr/bin/env bash
#
# run_e07.sh — E07 production sim (Hey Otto, fresh session per question)
#
# Runs E07 at low + medium effort in parallel against gpt-realtime-alpha-dolphin-6.
# This is the only benchmark we run going forward — E07 is the production architecture.
#
# Usage:
#   ./scripts/run_e07.sh                   # low + medium, 55 min
#   ./scripts/run_e07.sh --duration 15     # quick smoke test
#   ./scripts/run_e07.sh --effort low      # single effort level
#
set -euo pipefail
cd "$(dirname "$0")/.."

MODEL="gpt-realtime-alpha-dolphin-6"
DURATION=55
EFFORTS=(low medium)

for arg in "$@"; do
    case "$arg" in
        --duration=*) DURATION="${arg#--duration=}" ;;
        --duration)   shift; DURATION="$1" ;;
        --effort=*)   EFFORTS=("${arg#--effort=}") ;;
        --effort)     shift; EFFORTS=("$1") ;;
    esac
done

# --- Run name ---
LAST=$(ls -d results/run_* 2>/dev/null | sort -V | tail -1 | grep -oP '\d+$' || echo "0")
RUN_NUM=$(printf "%03d" $((10#$LAST + 1)))
RUN_NAME="run_${RUN_NUM}"
RUN_DIR="results/${RUN_NAME}"
mkdir -p "$RUN_DIR"

echo "=============================================="
echo "  E07 Production Sim — ${RUN_NAME}"
echo "  Model:    ${MODEL}"
echo "  Efforts:  ${EFFORTS[*]}"
echo "  Duration: ${DURATION} min"
echo "  $(date)"
echo "=============================================="

[ -f .env ] || { echo "ERROR: .env not found"; exit 1; }
pip3 install -q -r requirements.txt
export OPENAI_REALTIME_MODEL="$MODEL"

# --- Audio fixtures ---
if [ ! -f "audio_fixtures/meeting_1hr/manifest.json" ] || [ ! -f "audio_fixtures/meeting_1hr_questions/manifest.json" ]; then
    echo "ERROR: Audio fixtures missing. Run:"
    echo "  python3 scripts/generate_audio.py --meeting meeting_1hr"
    echo "  python3 scripts/generate_question_audio.py"
    exit 1
fi
echo "Audio fixtures: OK"
echo ""

# --- Run E07 at each effort level in parallel ---
PIDS=()
for effort in "${EFFORTS[@]}"; do
    logfile="${RUN_DIR}/E07_alpha_${effort}.log"
    echo "[START] E07 ${effort} effort ($(date)) → ${logfile}"
    OPENAI_REASONING_EFFORT="$effort" \
        python3 run_experiment.py --run "$RUN_NAME" -e 07 -p openai-alpha --duration "$DURATION" \
        > "$logfile" 2>&1 &
    PIDS+=($!)
done

echo "  ${#PIDS[@]} run(s) in parallel. Waiting..."
echo ""

FAILURES=0
for pid in "${PIDS[@]}"; do
    wait "$pid" || ((FAILURES++)) || true
done

echo ""
echo "=============================================="
echo "  Runs complete — failures: ${FAILURES}/${#PIDS[@]}"
echo "  $(date)"
echo "=============================================="
echo ""

# --- Results summary ---
for effort in "${EFFORTS[@]}"; do
    logfile="${RUN_DIR}/E07_alpha_${effort}.log"
    echo "=== E07 ${effort} ==="
    if [ -f "$logfile" ]; then
        grep -E "RESULTS:|lines:|ERROR" "$logfile" | tail -10
    else
        echo "  (no log)"
    fi
    echo ""
done

echo "Logs:  ${RUN_DIR}/E07_alpha_*.log"
echo "Run:   ${RUN_NAME}"
