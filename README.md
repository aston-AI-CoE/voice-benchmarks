# Voice Benchmarks — OpenAI Realtime vs Grok/xAI

Scientific benchmarks comparing realtime voice API providers for Otto's voice service.

## Setup

```bash
cp .env.example .env
# Fill in API keys: OPENAI_API_KEY, XAI_API_KEY, ANTHROPIC_API_KEY

pip install -r requirements.txt
```

## Experiments

| ID | Name | What it tests | Duration |
|----|------|---------------|----------|
| 01 | **Instant Context Recall** | Inject meeting turns instantly, quiz on 20 planted facts. Tests context window, NOT real session duration. | ~30s |
| 02 | **Context Window Cliff** | Find where recall degrades (anchor fact tested at 100-20K token milestones) | ~2min |
| 03 | **Response Latency** | TTFB and total response time across 30 varied prompts | ~2min |
| 04 | **Tool Call Reliability** | True/false positive rates for tool invocation | ~1min |
| 05 | **Realtime Session 1hr** | Actual 60-minute live session with paced dialogue, pulse checks, and recall. Tests session stability, quality degradation over time, and naturalness. | 5min-60min (configurable) |

## Usage

```bash
# Dry run — validate scripts without API calls
python3 run_experiment.py -e 01 -p openai --dry-run

# Run experiment 01 (instant context recall) with OpenAI
python3 run_experiment.py -e 01 -p openai

# Run with Grok
python3 run_experiment.py -e 01 -p grok

# Run both providers
python3 run_experiment.py -e 01 -p all

# Multiple runs for statistical significance
python3 run_experiment.py -e 01 -p all -n 3

# Skip LLM judge scoring (faster, raw responses only)
python3 run_experiment.py -e 01 -p openai --skip-scoring

# Real 1-hour session (actual 60 min)
python3 run_experiment.py -e 05 -p openai --seconds-per-minute 60

# Real 1-hour session at half speed (30 min)
python3 run_experiment.py -e 05 -p openai --seconds-per-minute 30

# Real 1-hour session fast test (5 min)
python3 run_experiment.py -e 05 -p openai --seconds-per-minute 5

# Run all experiments
python3 run_experiment.py -e all -p all
```

## Compare Results

```bash
python3 compare_results.py -e 01          # markdown table
python3 compare_results.py -e 01 -f json  # JSON output
```

## Detailed Analysis

```bash
python3 -m experiments.e01_instant_context_recall.analyze
python3 -m experiments.e01_instant_context_recall.analyze -p openai
```

## First Run Results (2026-03-30)

Experiment 01 (Instant Context Recall) — 126 turns, 20 facts, ~2,249 tokens:

| Metric               | OpenAI | Grok  |
|----------------------|--------|-------|
| Recall Accuracy      | 100%   | 70%*  |
| Hallucination Rate   | 0%     | 0%    |
| Avg Latency (TTFB)   | 241ms  | 514ms |

*Grok had a response truncation issue in text-only mode — it knows the answers but
responses were cut off mid-sentence. Fixed by requesting text+audio modalities.

**Key finding:** This test only proves context window recall on small input (~2K tokens).
It does NOT test real session duration. That's what experiment 05 is for.

See [results/e01_instant_context_recall/RUN_REPORT.md](results/e01_instant_context_recall/RUN_REPORT.md) for full analysis.

## Architecture

```
voice-benchmarks/
├── common/
│   ├── provider.py       # Abstract RealtimeProvider ABC
│   ├── scoring.py        # Claude LLM judge
│   ├── results.py        # JSON result storage
│   └── config.py         # Env loading
├── providers/
│   ├── openai_realtime.py  # OpenAI WebSocket (text-only)
│   └── grok_xai.py         # Grok WebSocket (text+audio, ignore audio)
├── experiments/
│   ├── e01_instant_context_recall/   # Fast context recall test
│   ├── e02_context_window_cliff/     # Memory cliff detection
│   ├── e03_response_latency/         # TTFB benchmarks
│   ├── e04_tool_call_reliability/    # Tool call accuracy
│   └── e05_realtime_session_1hr/     # REAL 1-hour paced session
├── results/              # JSON output per run + run reports
├── run_experiment.py     # CLI entry point
└── compare_results.py    # Cross-provider comparison
```
