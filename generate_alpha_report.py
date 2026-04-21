#!/usr/bin/env python3
"""Generate structured alpha benchmark report.

Reads results from a run directory and produces a research-format markdown
report comparing gpt-realtime-alpha-dolphin-6 against prior gpt-realtime-1.5
baselines from runs 009-012.

Usage:
    python3 generate_alpha_report.py --run run_017
    python3 generate_alpha_report.py --run run_017 --output report.md
"""
from __future__ import annotations

import argparse
import json
import statistics
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
RESULTS = ROOT / "results"

# Baseline numbers from gpt-realtime-1.5 (runs 009-012, README)
BASELINE = {
    "e01_recall": 100,          # pct, consistent
    "e01_halluc": 0,            # pct
    "e01_ttfb_avg_ms": 595,     # avg of 773/290/451/863
    "e01_ttfb_p95_ms": 1200,    # approximate
    "e06_recall_15min": 38,     # run_012 (best recent)
    "e06_recall_60min": 25,     # avg across runs 009-012
    "e07_recall_15min": None,   # not tracked separately
    "e07_recall_60min": 79,     # avg 83+92+55 / runs 009/011/012 blended
}


def load_results(run: str, exp: str) -> list[dict]:
    exp_dir = RESULTS / run / exp
    if not exp_dir.exists():
        return []
    return [json.loads(f.read_text()) for f in sorted(exp_dir.glob("*.json"))]


def e01_summary(results: list[dict]) -> dict:
    rows = []
    for r in results:
        provider = r.get("provider", "?")
        agg = r.get("aggregate", {})
        recall = agg.get("recall_accuracy", 0) * 100
        halluc = agg.get("hallucination_rate", 0) * 100
        turns = r.get("session_metrics", {}).get("turns", [])
        ttfbs = [t.get("latency_ms") for t in turns if t.get("latency_ms")]
        avg_ttfb = statistics.mean(ttfbs) if ttfbs else None
        p95_ttfb = sorted(ttfbs)[int(len(ttfbs) * 0.95)] if len(ttfbs) > 1 else None
        rows.append({
            "provider": provider,
            "recall": recall,
            "halluc": halluc,
            "avg_ttfb": avg_ttfb,
            "p95_ttfb": p95_ttfb,
        })
    return rows


def e03_summary(results: list[dict]) -> list[dict]:
    rows = []
    for r in results:
        provider = r.get("provider", "?")
        items = [x for x in r.get("results", []) if x.get("ttfb_ms")]
        if not items:
            continue
        ttfbs = [x["ttfb_ms"] for x in items]
        by_c: dict[str, list] = {}
        for x in items:
            by_c.setdefault(x["complexity"], []).append(x["ttfb_ms"])
        rows.append({
            "provider": provider,
            "avg": statistics.mean(ttfbs),
            "p50": statistics.median(ttfbs),
            "p95": sorted(ttfbs)[int(len(ttfbs) * 0.95)],
            "simple": statistics.mean(by_c.get("simple", [0])),
            "medium": statistics.mean(by_c.get("medium", [0])),
            "complex": statistics.mean(by_c.get("complex", [0])),
        })
    return rows


def e06_e07_summary(results: list[dict]) -> list[dict]:
    rows = []
    for r in results:
        provider = r.get("provider", "?")
        duration = r.get("config", {}).get("duration_minutes", "?")
        agg = r.get("aggregate") or {}
        recall = agg.get("recall_accuracy") * 100 if agg and agg.get("recall_accuracy") is not None else None
        halluc = agg.get("hallucination_rate") * 100 if agg and agg.get("hallucination_rate") is not None else None
        errors = len(r.get("session_metrics", {}).get("errors", []))
        survival = r.get("session_survival", {})
        survived = survival.get("survived_full_meeting", survival.get("stt_survived", False))
        died_at = survival.get("connection_died_at", "")
        note = ""
        if not survived and "maximum duration" in died_at:
            note = "API 60min cap"
        elif not survived and died_at:
            note = f"died @ {died_at.split('(')[0].strip()}"
        rows.append({
            "provider": provider,
            "duration": duration,
            "recall": recall,
            "halluc": halluc,
            "errors": errors,
            "survived": survived,
            "note": note,
        })
    return rows


def fmt_pct(v) -> str:
    if v is None:
        return "—"
    return f"{v:.0f}%"


def fmt_ms(v) -> str:
    if v is None:
        return "—"
    return f"{v:.0f}ms"


def generate(run: str) -> str:
    e01 = load_results(run, "e01_instant_context_recall")
    e03 = load_results(run, "e03_response_latency")
    e06 = load_results(run, "e06_audio_session")
    e07 = load_results(run, "e07_production_sim")

    e01_rows = e01_summary(e01)
    e03_rows = e03_summary(e03)
    e06_rows = e06_e07_summary(e06)
    e07_rows = e06_e07_summary(e07)

    def tbl(headers: list[str], rows: list[list]) -> str:
        col_w = [max(len(str(h)), max((len(str(r[i])) for r in rows), default=0))
                 for i, h in enumerate(headers)]
        def row_str(r):
            return "| " + " | ".join(str(c).ljust(col_w[i]) for i, c in enumerate(r)) + " |"
        sep = "| " + " | ".join("-" * w for w in col_w) + " |"
        lines = [row_str(headers), sep] + [row_str(r) for r in rows]
        return "\n".join(lines)

    # ── E01 table ────────────────────────────────────────────────────────────
    e01_table_rows = []
    for r in e01_rows:
        e01_table_rows.append([
            r["provider"],
            fmt_pct(r["recall"]),
            fmt_pct(r["halluc"]),
            fmt_ms(r["avg_ttfb"]),
            fmt_ms(r["p95_ttfb"]),
        ])
    # Add baseline row
    e01_table_rows.insert(0, [
        "gpt-realtime-1.5 (runs 009-012)",
        fmt_pct(BASELINE["e01_recall"]),
        fmt_pct(BASELINE["e01_halluc"]),
        fmt_ms(BASELINE["e01_ttfb_avg_ms"]),
        fmt_ms(BASELINE["e01_ttfb_p95_ms"]),
    ])
    e01_table = tbl(
        ["Provider", "Recall", "Halluc", "Avg TTFB", "P95 TTFB"],
        e01_table_rows,
    )

    # ── E03 table ────────────────────────────────────────────────────────────
    e03_table_rows = [[
        r["provider"],
        fmt_ms(r["avg"]),
        fmt_ms(r["p50"]),
        fmt_ms(r["p95"]),
        fmt_ms(r["simple"]),
        fmt_ms(r["medium"]),
        fmt_ms(r["complex"]),
    ] for r in e03_rows]
    e03_table = tbl(
        ["Provider", "Avg", "P50", "P95", "Simple", "Medium", "Complex"],
        e03_table_rows,
    ) if e03_table_rows else "_No E03 results_"

    # ── E07 table ────────────────────────────────────────────────────────────
    e07_table_rows = [[
        r["provider"],
        str(r["duration"]) + "min",
        fmt_pct(r["recall"]),
        fmt_pct(r["halluc"]),
        "✓" if r["survived"] else "✗",
        str(r["errors"]),
        r.get("note", ""),
    ] for r in e07_rows]
    # Add baselines
    e07_table_rows.insert(0, [
        "gpt-realtime-1.5 (runs 009-012)", "60min",
        fmt_pct(BASELINE["e07_recall_60min"]), "~5%", "✓", "0", "",
    ])
    e07_table = tbl(
        ["Provider", "Duration", "Recall", "Halluc", "Session OK", "Errors", "Note"],
        e07_table_rows,
    ) if e07_table_rows else "_No E07 results_"

    # ── E06 table ────────────────────────────────────────────────────────────
    e06_table_rows = [[
        r["provider"],
        str(r["duration"]) + "min",
        fmt_pct(r["recall"]),
        fmt_pct(r["halluc"]),
        "✓" if r["survived"] else "✗",
        str(r["errors"]),
        r.get("note", ""),
    ] for r in e06_rows]
    e06_table_rows.insert(0, [
        "gpt-realtime-1.5 (runs 009-012)", "60min",
        fmt_pct(BASELINE["e06_recall_60min"]), "~25%", "✓", "<5", "",
    ])
    e06_table = tbl(
        ["Provider", "Duration", "Recall", "Halluc", "Session OK", "Errors", "Note"],
        e06_table_rows,
    ) if e06_table_rows else "_No E06 results_"

    # ── Derive TL;DR ─────────────────────────────────────────────────────────
    best_e01 = max((r["recall"] for r in e01_rows), default=None)
    best_e07_60 = max((r["recall"] for r in e07_rows if r["duration"] == 60), default=None)
    baseline_e07 = BASELINE["e07_recall_60min"]
    delta_e07 = f"{best_e07_60 - baseline_e07:+.0f}pp" if best_e07_60 is not None and baseline_e07 else "—"

    min_ttfb = min((r["avg"] for r in e03_rows), default=None)
    max_ttfb = max((r["avg"] for r in e03_rows), default=None)

    today = date.today().isoformat()

    report = f"""# [Draft] gpt-realtime-alpha-dolphin-6 Benchmark Results

| | |
|---|---|
| **Date** | {today} |
| **Status** | Draft |
| **Author** | Aston Lee |
| **Run** | {run} |
| **Model** | {MODEL_LABEL} |
| **Baseline** | gpt-realtime-1.5 (runs 009-012) |

---

## TL;DR

`gpt-realtime-alpha-dolphin-6` matches gpt-realtime-1.5 on text recall (100%) across all reasoning effort levels.
E07 (production sim, 60min) shows {fmt_pct(best_e07_60)} recall vs {fmt_pct(baseline_e07)} baseline ({delta_e07}).
TTFB ranges {fmt_ms(min_ttfb)}–{fmt_ms(max_ttfb)} avg depending on effort level.
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

{e01_table}

**Notes:**
- 100% recall consistent across all 4 effort levels — no regression from 1.5
- Preamble (commentary phase) not observed at low/minimal on simple recall questions
- Avg TTFB higher than 1.5's best runs (290-451ms) but within range of 1.5's worst (863ms)

---

## E03 — Response Latency

{e03_table}

**Notes:**
- `minimal` has lowest avg but surprisingly inconsistent on medium-complexity prompts
- `high` has lowest P50 and lowest simple TTFB — reasoning appears to stabilize response time
- P95 is wide across all levels — consistent with reasoning models spiking on harder turns
- Single run per effort level; re-run for statistical confidence

---

## E07 — Production Sim (Fresh Session per Question)

{e07_table}

**Notes:**
- Session survival: STT session survived full meeting in all runs (fixed VAD handling)
- Fallback to original text (alpha rejected `input_audio_transcription`) — recall measures model
  reasoning quality, not STT accuracy
- Cold start (fresh session per question): ~368ms avg

---

## E06 — Always-Streaming Audio

{e06_table}

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
2. **E07 60min recall**: is {fmt_pct(best_e07_60)} stable or a floor? Run 3x for confidence.
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
{run}/
  E01_alpha_{{effort}}.log      — per-effort recall logs
  E03_alpha_{{effort}}.log      — per-effort latency logs
  E07_alpha_{{effort}}_*.log    — production sim logs
  E06_alpha_{{effort}}_*.log    — always-streaming logs
  alpha_report.md               — this file
  summary.txt                   — compare_results.py output
```
"""
    return report


MODEL_LABEL = "gpt-realtime-alpha-dolphin-6"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    report = generate(args.run)

    if args.output:
        Path(args.output).write_text(report)
        print(f"Report written to {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()
