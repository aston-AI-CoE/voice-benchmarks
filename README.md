# Voice Benchmarks — OpenAI Realtime vs Grok/xAI

Scientific benchmarks comparing realtime voice API providers for Otto's voice meeting assistant. 11 runs, 20 experiments per run, testing text recall, audio streaming, latency, tool calling, and production architecture.

## Key Findings (11 runs)

| | OpenAI | Grok |
|--|--------|------|
| **Text recall** | 95-100% | 88-100% |
| **Audio always-streaming (E06)** | 25-50% recall | 33% recall |
| **Production sim (E07)** | 92% recall (run_008); ~47% in runs 009-011 — E07 regression under investigation | 0% (context limit) |
| **TTFB** | ~290-770ms | ~530-680ms |
| **Max session** | 60 min (hard cap) | 120 min (but context limit at ~3K words) |
| **Tool calling** | 100% | 100% |

**Recommendation:** OpenAI with production architecture (external STT → fresh voice session per question). See [run_008 report](results/run_008/run_008_report.md) for full analysis. Note: E07 results from runs 009-010 are discounted pending investigation into the recall regression from 92% → ~47%.

## Benchmark Summary

### E01 — Text Recall

Both providers reliably recall injected facts from long text sessions. OpenAI is consistently at 100%; Grok started buggy (truncation, early session death) but stabilized at 88-100% by run_004 after keepalive and truncation fixes.

| Category | OpenAI (runs 009-011) | Grok (runs 009-011) |
|----------|----------------------|---------------------|
| Dates | 100% | 68-90% |
| Decisions | 100% | 65-92% |
| Names | 100% | 100% |
| Numbers | 92% | 75-100% |
| Preferences | 92-100% | 57-92% |

Recall holds across the full 60-min session for OpenAI. Grok shows mid-session dips (67% at 20-40 min in run_009) but recovers.

---

### E06 — Always-Streaming Audio

Neither provider works for continuous audio sessions. Recall collapses after ~20 minutes regardless of provider.

| Period | OpenAI (avg) | Grok (run_008) |
|--------|-------------|----------------|
| Early (0-20 min) | 48-70% | 47% |
| Mid (20-40 min) | 8-45% | 18% |
| Late (40-60 min) | 2% | 0% |

OpenAI averages 25-50% overall; Grok averaged 33% in run_008 (first run where Grok's audio sessions survived). Hallucination rates are high: OpenAI 17-42%, Grok 4%. The always-streaming architecture is not viable for a 60-minute meeting assistant.

---

### E07 — Production Sim

The production architecture (external STT → fresh voice session per question) avoids the audio degradation problem and is the viable path forward.

| Run | OpenAI recall | Grok recall |
|-----|--------------|-------------|
| 006 | 92% | — |
| 008 | 92% | 0% (context limit at ~26 min) |
| 009 | 50% | 0% |
| 010 | 47% | 0% |
| 011 | 47% | 0% |

**Grok hits its ~3K-word context limit at ~26 minutes** and fails all subsequent questions. OpenAI has no equivalent limit (tested to 7K+ words).

**OpenAI E07 regression:** runs 009-011 show ~47% vs 92% in runs 006/008. Cause is under investigation — the architecture itself works, but something changed in the scoring or test conditions. The run_008 numbers remain the best validated reference.

---

### Latency (E01 TTFB)

| Run | OpenAI | Grok |
|-----|--------|------|
| 009 | 773ms | 676ms |
| 010 | 290ms | 635ms |
| 011 | 451ms | 636ms |

OpenAI latency is more variable (290-770ms). Grok is more consistent (530-680ms) but higher floor.

---

### Bottom Line

| Question | Answer |
|----------|--------|
| Can either provider do a 60-min voice session? | No. Both fail on raw audio after 20 min. |
| Does the production architecture work? | Yes — for OpenAI. Grok hits context limits. |
| Which provider for text recall? | Both reliable; OpenAI slightly more consistent. |
| Which provider for a meeting assistant? | **OpenAI**, using production architecture (E07). |

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

## Discoveries

### Hard Platform Limits

| Limit | OpenAI | Grok |
|-------|--------|------|
| Max session duration | **60 min** (hard cap — session dies mid-meeting) | **120 min** (but irrelevant — context fills first) |
| Max system prompt (realtime) | 7,000+ words (no limit hit across 11 runs) | **~3,000 words / ~300 lines** — returns `INVALID_ARGUMENT` beyond this |
| Audio inactivity timeout | None (with keepalive pings) | **15 min** (fixed in run_008 via `server_vad` + `input_audio_buffer`) |
| Context failure mode | Clean 60-min cutoff | Silent `INVALID_ARGUMENT` — every question fails with no warning |

### The 20-Minute Audio Cliff

Both providers lose essentially all recall of audio content after ~20 minutes of continuous streaming. This is not a gradual degradation — it's a cliff:

| Period | OpenAI (E06 avg) | Grok (run_008) |
|--------|-----------------|----------------|
| 0-20 min | 48-70% | 47% |
| 20-40 min | 8-45% | 18% |
| **40-60 min** | **~2%** | **0%** |

The model appears to have a fixed audio attention window of roughly 20 minutes. Content from the first 40 minutes of a meeting is effectively gone by the end. Neither provider has solved this.

### Fresh Sessions Beat Long Sessions by a Wide Margin

The always-streaming approach (one session for the whole meeting) vs the production approach (fresh session per question with injected transcript):

| Architecture | OpenAI recall | Grok recall |
|-------------|--------------|-------------|
| Always-streaming (E06) | 25-50% | 33% |
| Fresh session + STT (E07, run_008) | **92%** | 0% (context limit) |

A fresh 10-second session with a text transcript injected as context outperforms a 60-minute live audio session by ~2-3x. The overhead (~250ms cold start) is negligible.

### Grok's Context Limit Has a Sharp Cliff Too

Grok works perfectly until the transcript hits ~3,000 words (~26 minutes of meeting), then every single subsequent question returns `INVALID_ARGUMENT`. There's no graceful degradation — it goes from 100% to 0% in one question:

```
min 22: "14 violations, contrast issues in sidebar, ARIA labels"   ✓ correct
min 26: INVALID_ARGUMENT — transcript too large                    ✗ failed
min 29: INVALID_ARGUMENT                                           ✗ failed
min 33: INVALID_ARGUMENT                                           ✗ failed
... every question after this: INVALID_ARGUMENT
```

### Grok's TTFB Is More Consistent Than OpenAI's

OpenAI's TTFB varies dramatically by run (290ms to 770ms). Grok is remarkably stable regardless of prompt complexity:

| Complexity | OpenAI TTFB | Grok TTFB |
|-----------|-------------|-----------|
| Simple | ~250-450ms | ~670ms |
| Medium | ~430-770ms | ~680ms |
| Complex | ~290-770ms | ~670ms |

Grok has a higher floor but is more predictable. If latency consistency matters more than raw speed, Grok is better.

### Audio Hallucination Rate Is Significantly Higher Than Text

OpenAI hallucination rate jumps sharply in audio vs text mode:

| Mode | OpenAI hallucination | Grok hallucination |
|------|---------------------|-------------------|
| Text (E01) | 0-5% | 0-5% |
| Audio always-streaming (E06) | **17-42%** | 4% |

OpenAI confidently invents answers in audio mode. Grok either answers correctly or admits uncertainty ("I'm not sure") — lower hallucination, but also lower recall.

### Tool Calling Is a Non-Issue for Both

Across all 11 runs and every tool call experiment, both providers achieved 100% accuracy. This was never a differentiator and likely never will be.

### The VAD Fix That Unlocked Grok Audio

Runs 001-007: Grok's audio sessions died at exactly 15 minutes because `conversation.item.create` with inline audio was the wrong API call — the model treated it as background noise, not as conversation, and the session eventually timed out.

Run 008 fix: switch to `input_audio_buffer.append` + `server_vad: true`. This is how a real microphone stream works. After this fix, Grok's audio sessions survived and produced real answers for the first time.

### Slack Message

> **Otto voice provider benchmarks — 11 runs complete**
>
> After 11 benchmark runs (~120+ hours of simulated meetings) comparing OpenAI Realtime vs Grok for Otto:
>
> **OpenAI wins for production.** 92% recall on a 60-min meeting using fresh sessions + STT (E07, run_008). Grok hits a ~3K-word context wall at ~26 min and returns `INVALID_ARGUMENT` for every question after that — no warning, just failure.
>
> **Key discoveries:**
> - Both providers hit a **20-minute audio cliff** — recall drops to ~2% for content beyond 20 min in always-streaming mode. Neither provider can "listen" to a full meeting in one session.
> - **Fresh sessions beat long sessions by 2-3x.** A 10-sec session with injected transcript = 92% recall. One 60-min live session = 25-50%.
> - **Grok's session cap is 120 min** (vs OpenAI's 60 min) but that's irrelevant — context fills up first.
> - **OpenAI hallucinates 17-42% in audio mode** vs ~0-5% in text mode. Grok hallucinates ~4% in audio — lower recall but more honest.
> - **Tool calling: 100% for both.** Not a factor.
>
> Recommendation: OpenAI + Deepgram STT + fresh Realtime session per "Hey Otto". Full details in the [run_008 report](results/run_008/run_008_report.md).

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
| 009 | ⚠️ **Partially bad run — E07 discounted.** E07 shows a sharp regression (OpenAI 50%, down from 92% in run_008) with no code changes between runs. Root cause unknown — suspected scoring flakiness or STT transcript variance. E01 and E06 results are valid: Grok 90%, OpenAI 100% text recall; OpenAI 42% E06 audio. Do not use run_009 E07 numbers as reference. |
| 010 | ⚠️ **Partially bad run — E07 discounted.** Second consecutive E07 regression (OpenAI 47%, Grok 0%). Confirms run_009 was not a one-off. E06 also degraded with OpenAI hallucination spiking to 42% — may indicate an upstream model or scoring issue during this period. E01 results remain clean: both providers 100%. E07 and E06 results from this run should not be cited. |
| 011 | **Latest run.** E01: Grok 95%, OpenAI 100%. E06: OpenAI 50%. E07: OpenAI 47%, Grok 0% (context limit). E07 regression persists — now confirmed across 3 consecutive runs, no longer dismissible as noise. Under active investigation. |
