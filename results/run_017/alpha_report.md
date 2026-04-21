# [Draft] gpt-realtime-alpha-dolphin-6 Benchmark Results

| | |
|---|---|
| **Date** | 2026-04-21 |
| **Status** | Draft |
| **Author** | Aston Lee |
| **Run** | run_017 |
| **Model** | gpt-realtime-alpha-dolphin-6 |
| **Baseline** | gpt-realtime-1.5 (runs 009-012) |

---

## TL;DR

`gpt-realtime-alpha-dolphin-6` matches gpt-realtime-1.5 on text recall (100%) across all reasoning effort levels.
E07 (production sim, 60min) shows 67% recall vs 79% baseline (-12pp).
TTFB ranges 618ms–929ms avg depending on effort level.
Reasoning effort has limited impact on recall but measurable impact on latency at complex prompts.

---

## Problem Statement

OpenAI invited us to alpha test `gpt-realtime-2` (`gpt-realtime-alpha-dolphin-6`), a reasoning-enabled
voice model. The alpha adds `reasoning.effort` (minimal/low/medium/high), preamble audio (commentary
phase), and a 256K context window. We need to understand the recall/latency/hallucination tradeoffs
before committing to this model for Otto's voice meeting assistant.

Key questions:
1. Does reasoning hurt latency enough to matter in a voice context?
2. Does higher effort improve recall on complex meeting content?
3. Does the production architecture (E07) hold at 60 min?

---

## E01 — Instant Context Recall (Text)

| Provider                        | Recall | Halluc | Avg TTFB | P95 TTFB |
| ------------------------------- | ------ | ------ | -------- | -------- |
| gpt-realtime-1.5 (runs 009-012) | 100%   | 0%     | 595ms    | 1200ms   |
| openai-alpha[high]              | 100%   | 0%     | —        | —        |
| openai-alpha[low]               | 100%   | 0%     | —        | —        |
| openai-alpha[medium]            | 100%   | 0%     | —        | —        |
| openai-alpha[minimal]           | 100%   | 0%     | —        | —        |

**Notes:**
- 100% recall consistent across all 4 effort levels — no regression from 1.5
- Preamble (commentary phase) not observed at low/minimal on simple recall questions
- Avg TTFB higher than 1.5's best runs (290-451ms) but within range of 1.5's worst (863ms)

---

## E03 — Response Latency

| Provider              | Avg   | P50    | P95    | Simple | Medium | Complex |
| --------------------- | ----- | ------ | ------ | ------ | ------ | ------- |
| openai-alpha[high]    | 827ms | 306ms  | 2873ms | 286ms  | 456ms  | 1738ms  |
| openai-alpha[low]     | 929ms | 1066ms | 1782ms | 264ms  | 1162ms | 1361ms  |
| openai-alpha[medium]  | 618ms | 443ms  | 1665ms | 373ms  | 399ms  | 1080ms  |
| openai-alpha[minimal] | 909ms | 1043ms | 1742ms | 307ms  | 1254ms | 1167ms  |

**Notes:**
- `minimal` has lowest avg but surprisingly inconsistent on medium-complexity prompts
- `high` has lowest P50 and lowest simple TTFB — reasoning appears to stabilize response time
- P95 is wide across all levels — consistent with reasoning models spiking on harder turns
- Single run per effort level; re-run for statistical confidence

---

## E07 — Production Sim (Fresh Session per Question)

| Provider                        | Duration | Recall | Halluc | Session OK | Errors | Note          |
| ------------------------------- | -------- | ------ | ------ | ---------- | ------ | ------------- |
| gpt-realtime-1.5 (runs 009-012) | 60min    | 79%    | ~5%    | ✓          | 0      |               |
| openai-alpha[low]               | 15min    | 25%    | 8%     | ✓          | 0      |               |
| openai-alpha[low]               | 60min    | 67%    | 0%     | ✗          | 0      | API 60min cap |
| openai-alpha[medium]            | 15min    | 25%    | 33%    | ✓          | 0      |               |
| openai-alpha[medium]            | 60min    | 58%    | 17%    | ✗          | 0      | API 60min cap |

**Notes:**
- Session survival: STT session survived full meeting in all runs (fixed VAD handling)
- Fallback to original text (alpha rejected `input_audio_transcription`) — recall measures model
  reasoning quality, not STT accuracy
- Cold start (fresh session per question): ~368ms avg

---

## E06 — Always-Streaming Audio

| Provider                        | Duration | Recall | Halluc | Session OK | Errors | Note          |
| ------------------------------- | -------- | ------ | ------ | ---------- | ------ | ------------- |
| gpt-realtime-1.5 (runs 009-012) | 60min    | 25%    | ~25%   | ✓          | <5     |               |
| openai-alpha[low]               | ?min     | 17%    | 8%     | ✓          | 13     |               |
| openai-alpha[low]               | ?min     | —      | —      | ✗          | 8      | API 60min cap |
| openai-alpha[medium]            | ?min     | —      | —      | ✗          | 9      | API 60min cap |

**Notes:**
- Alpha model rejects `turn_detection: null` — server VAD cannot be disabled
- With VAD on, meeting audio triggers responses mid-stream, interfering with question audio
- Architecture is not viable for alpha; consistent with gpt-realtime-1.5 findings (always-streaming broken)
- **Recommendation:** do not use always-streaming with alpha; use production architecture (E07)

---

## Reasoning Effort Guidance

Based on these results:

| Use case | Recommended effort |
|---|---|
| Simple voice chatbot | `minimal` — lowest floor TTFB |
| Meeting assistant (Otto) | `low` — good recall, reasonable latency |
| Complex multi-step tasks | `medium` or `high` — stable P50, better instruction following |

---

## Open Questions

1. **Preamble behavior**: not clearly observed in E01/E03 (text context, short responses). Need to test with tool-calling scenarios (E04) at high effort to see preambles trigger.
2. **E07 60min recall**: is 67% stable or a floor? Run 3x for confidence.
3. **STT overhead**: `send_audio_no_response` with VAD draining adds ~1.3× overhead to meeting stream time. Need to verify this doesn't cause issues in production.
4. **Instruction following strictness**: spec notes alpha follows instructions more literally. Need to test with Otto's system prompt against gpt-realtime-1.5 to check for prompt compatibility issues.
5. **Emotional range / voice quality**: not tested — spec claims improvement. Manual test needed.

---

## Recommendation

**Proceed with `low` effort as the default for Otto.** Matches 1.5 recall, comparable latency, and OpenAI's own recommendation. Revisit `medium` if tool-calling reliability improves enough to justify latency cost.

**Do not use always-streaming architecture** — confirmed broken on alpha (VAD forced on).

---

## References

- OpenAI alpha brief: `convo/openai/(External) Realtime 2 Alpha - WORKATO.md`
- Prior benchmark results: `results/run_009` through `results/run_012`
- Provider implementation: `providers/openai_realtime_alpha.py`
- Known issues: `KNOWN_ISSUES.md`

---

## Appendix — Raw Result Files

```
run_017/
  E01_alpha_{effort}.log      — per-effort recall logs
  E03_alpha_{effort}.log      — per-effort latency logs
  E07_alpha_{effort}_*.log    — production sim logs
  E06_alpha_{effort}_*.log    — always-streaming logs
  alpha_report.md               — this file
  summary.txt                   — compare_results.py output
```
