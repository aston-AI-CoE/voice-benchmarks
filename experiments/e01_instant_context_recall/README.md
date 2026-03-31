# Experiment 01: Long Session Context Retention

## Goal

Can a realtime voice API retain context from a 1-hour meeting and answer
questions accurately without hallucinating?

## Methodology

1. Connect with a meeting assistant system prompt
2. Inject ~90 turns of a product meeting with **20 planted facts** across:
   - Names (4): people, vendors, firms
   - Numbers (4): revenue targets, burn rate, rate limits, thresholds
   - Decisions (4): deprecations, migrations, tool choices
   - Preferences (4): design tools, themes, style guides
   - Dates (4): board meetings, pentests, launches, investor meetings
3. Ask **20 recall questions** (one per fact)
4. Run **5 hallucination probes** (questions about things NOT discussed)
5. Run **3 consistency checks** (same fact, different phrasing)
6. Score everything with an LLM judge

## Metrics

- **Recall Accuracy**: % of facts correctly recalled
- **Hallucination Rate**: % of responses with fabricated info
- **Honest Uncertainty**: % that correctly say "I don't know"
- **Recall by Category**: names vs numbers vs decisions vs dates
- **Recall Decay**: accuracy by minute (early facts vs late facts)
- **Latency**: avg and P95 for recall question responses
- **Consistency**: same answer when asked differently?

## Files

- `meeting_script.py` — Full meeting transcript with 20 planted facts
- `recall_questions.py` — Questions, expected answers, and distractor answers
- `experiment.py` — Main runner (inject → recall → score)
- `analyze.py` — Per-fact breakdown and cross-provider comparison
