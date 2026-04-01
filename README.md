# Voice Benchmarks — OpenAI Realtime vs Grok/xAI

Scientific benchmarks comparing realtime voice API providers for Otto's voice meeting assistant. 8 runs, 20 experiments per run, testing text recall, audio streaming, latency, tool calling, and production architecture.

## Key Findings (8 runs)

| | OpenAI | Grok |
|--|--------|------|
| **Text recall** | 95-100% | 88-100% |
| **Audio always-streaming (E06)** | 25% recall | 33% recall |
| **Production sim (E07)** | 92% recall at 60 min | Works for first 22 min, then context limit |
| **TTFB** | ~300-420ms | ~530-680ms |
| **Max session** | 60 min (hard cap) | 120 min (but context limit at ~3K words) |
| **Tool calling** | 100% | 100% |

**Recommendation:** OpenAI with production architecture (external STT → fresh voice session per question). See [run_008 report](results/run_008/run_008_report.md) for full analysis.

## Setup

```bash
cp .env.example .env
# Fill in: OPENAI_API_KEY, XAI_API_KEY, ANTHROPIC_API_KEY

pip3 install -r requirements.txt

# One-time: generate audio fixtures (~10 min)
python3 generate_audio.py --meeting meeting_1hr
python3 generate_question_audio.py
```

## Experiments

| ID | Name | What it tests |
|----|------|---------------|
| E01 | Instant Context Recall | Text injection, 20 planted facts, quiz-style |
| E02 | Context Window Cliff | Where recall degrades (100 → 20K tokens) |
| E03 | Response Latency | TTFB across 30 prompts (simple/medium/complex) |
| E04 | Tool Call Reliability | Should-call vs should-not-call accuracy |
| E06 | Always-Streaming Audio | One long session, all meeting audio streamed through it |
| E07 | Production Sim | STT transcribes meeting → fresh voice session per "Hey Otto" question |

## Usage

```bash
# Run all experiments in parallel (~65 min)
nohup ./run_all.sh > /dev/null 2>&1 &
tail -f results/run_*/run.log | tail -1

# Run individual experiments
python3 run_experiment.py -e 01 -p openai                          # text recall
python3 run_experiment.py -e 06 -p openai --duration 15            # 15 min audio session
python3 run_experiment.py -e 07 -p openai --duration 60            # production sim, 60 min
python3 run_experiment.py -e 07 -p grok --duration 15 --skip-scoring  # quick Grok test

# Smoke test (5 min, verifies everything works)
./smoke_test.sh

# Compare results
python3 compare_results.py -e 06 --run run_008
python3 compare_results.py -e 07 --run run_008
```

## Meeting Script

852 lines of natural dialogue (~60 min TTS audio), 4 speakers with different voices, realistic meeting dynamics (tangents, interruptions, filler). 16 mid-meeting "Hey Otto" questions sent as audio, 12 post-meeting questions, 4 hallucination probes.

```bash
# Audio fixtures (generated once, reused by all runs)
audio_fixtures/
  meeting_1hr/          # 852 PCM16 files (24kHz, mono, tts-1-hd)
  meeting_1hr_questions/ # 28 question audio clips
```

## Production Architecture (E07)

The architecture that actually works for a 1-hour meeting assistant:

```
Meeting audio → External STT (Deepgram) → Text transcript accumulates
                                                ↓
User says "Hey Otto" → Fresh OpenAI Realtime session
                     → Transcript injected as system prompt
                     → Question sent as audio
                     → Otto responds via voice
                     → Session closes (~10 sec total)
```

- No 60-min session cap (sessions are short-lived)
- No audio degradation (STT is external)
- No context loss (full transcript injected fresh each time)
- 92% recall, ~250ms cold start, ~4.5s question-to-answer

## Platform Limits Discovered

| Limit | OpenAI | Grok |
|-------|--------|------|
| Max session duration | 60 min | 120 min |
| Max system prompt (realtime) | 7,000+ words (no limit hit) | ~3,000 words |
| Audio inactivity timeout | None (with keepalive pings) | 15 min (needs `server_vad` + `input_audio_buffer`) |
| Audio comprehension quality | Good (10% WER at 15 min, degrades to 28% at 60 min) | Works with VAD enabled, but limited context |

## Architecture

```
voice-benchmarks/
├── common/
│   ├── provider.py          # Abstract RealtimeProvider ABC
│   ├── audio.py             # TTS generation, PCM16 encoding, WER
│   ├── scoring.py           # Claude LLM judge
│   ├── results.py           # JSON result storage per run
│   └── config.py            # Env loading
├── providers/
│   ├── openai_realtime.py   # OpenAI WebSocket (text+audio, Whisper STT)
│   └── grok_xai.py          # Grok WebSocket (server_vad, input_audio_buffer)
├── experiments/
│   ├── e01_instant_context_recall/
│   ├── e02_context_window_cliff/
│   ├── e03_response_latency/
│   ├── e04_tool_call_reliability/
│   ├── e05_realtime_session_1hr/   # Meeting scripts + realistic dialogue
│   ├── e06_audio_session/          # Always-streaming audio test
│   └── e07_production_sim/         # Production architecture (fresh sessions)
├── audio_fixtures/                 # Pre-generated PCM16 audio
├── results/                        # Per-run results + reports
│   ├── run_008/
│   │   ├── run.log
│   │   ├── summary.txt
│   │   ├── run_008_report.md
│   │   └── E*.log              # Per-experiment logs
│   └── ...
├── run_all.sh                   # Parallel test runner
├── smoke_test.sh                # Quick validation
├── generate_audio.py            # One-time TTS generation
├── generate_question_audio.py   # One-time question audio generation
├── run_experiment.py            # CLI entry point
└── compare_results.py           # Cross-provider comparison
```

## Run History

| Run | Key finding |
|-----|-------------|
| 001 | First run. OpenAI 100% text recall. Grok truncation bug discovered. |
| 002 | Grok truncation fixed. OpenAI survived 1hr text session. Grok died at 15 min. |
| 003 | Realistic meeting script. Hallucination rates higher with messy dialogue. |
| 004 | Grok text sessions survive (keepalive fix). Audio sessions still die. |
| 005 | Killed — Grok E06 hung due to missing response timeouts. |
| 006 | Full parallel run. Both providers bad at always-streaming audio (25-33%). OpenAI E07 gets 92%. |
| 007 | Skipped. |
| 008 | **Grok audio fix (VAD + input_audio_buffer).** Grok survives audio sessions. Works for first 22 min, then context limit. |
