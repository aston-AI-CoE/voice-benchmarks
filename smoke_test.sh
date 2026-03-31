#!/usr/bin/env bash
#
# Quick smoke test — verify fixes before committing to a full run
# Tests E05 + E06 at 5-min pacing only (~25 min total)
#
# Usage:
#   ./smoke_test.sh
#
set -euo pipefail
cd "$(dirname "$0")"

RUN_NAME="smoke_$(date +%Y%m%dT%H%M%S)"
RUN_DIR="results/${RUN_NAME}"
mkdir -p "$RUN_DIR"
LOG="${RUN_DIR}/run.log"
exec > >(tee -a "$LOG") 2>&1

echo "=============================================="
echo "  Smoke Test — ${RUN_NAME}"
echo "  $(date)"
echo "=============================================="
echo ""

# Generate audio fixtures if needed
if [ ! -f "audio_fixtures/realistic_meeting/manifest.json" ]; then
    echo "[1] Generating audio fixtures..."
    python3 generate_audio.py
    echo ""
fi

# E05 text session — fastest pacing, just verify no crashes
echo "[2] E05 text session (speed test)..."
python3 run_experiment.py --run "$RUN_NAME" -e 05 -p openai --seconds-per-minute 1 --skip-scoring
python3 run_experiment.py --run "$RUN_NAME" -e 05 -p grok --seconds-per-minute 1 --skip-scoring
echo ""

# E06 audio session — 10 lines only for quick validation
echo "[3] E06 audio session (10 lines)..."
python3 run_experiment.py --run "$RUN_NAME" -e 06 -p openai --max-lines 10 --skip-scoring
python3 run_experiment.py --run "$RUN_NAME" -e 06 -p grok --max-lines 10 --skip-scoring
echo ""

# Quick results check
echo "=============================================="
echo "  Results Summary"
echo "=============================================="
echo ""
python3 -c "
import json, glob
PAD = ' ' * 30
for f in sorted(glob.glob('results/${RUN_NAME}/**/*.json', recursive=True)):
    with open(f) as fp:
        d = json.load(fp)
    p = d.get('provider','?')
    exp = d.get('experiment','?')
    surv = d.get('session_survival',{})
    trans = d.get('transcription',{})
    mid = d.get('mid_meeting_results',[])
    post = d.get('post_meeting_results',[])

    survived = surv.get('survived_full_meeting', '?')
    ls = str(surv.get('lines_sent','?')) + '/' + str(surv.get('lines_total','?'))
    died = surv.get('connection_died_at')

    print(exp + ' | ' + p + ' | survived=' + str(survived) + ' | lines=' + ls)
    if died:
        print(PAD + '  DIED: ' + str(died))

    if trans.get('total_compared'):
        print(PAD + '  transcriptions=' + str(trans['total_compared']) + ' avg_wer=' + str(trans.get('avg_wer')))

    for m in mid:
        resp = (m.get('response','') or '')[:60]
        print(PAD + '  mid min ' + str(m['minute']) + ': ' + resp)

    if post:
        answered = sum(1 for r in post if (r.get('response','') or '').strip())
        print(PAD + '  post-meeting: ' + str(answered) + '/' + str(len(post)) + ' answered')
    print()
"

echo "=============================================="
echo "  Smoke Test Done — $(date)"
echo "  Log: ${LOG}"
echo "=============================================="
