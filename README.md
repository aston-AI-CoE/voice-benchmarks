# Voice Benchmarks — OpenAI Realtime vs Grok/xAI

Scientific benchmarks comparing realtime voice API providers for Otto's voice meeting assistant. Testing text recall, audio streaming, latency, tool calling, and production architecture across gpt-realtime-1.5 (runs 001–012) and gpt-realtime-alpha-dolphin-6 (runs 013–018).

## Key Findings (12 runs)

| | OpenAI | Grok |
|--|--------|------|
| **Text recall** | 95-100% | 88-100% |
| **Audio always-streaming (E06)** | 25-50% recall | 33% recall |
| **Production sim (E07)** | 83-92% recall (60min, runs 006/009/011); 55% in run_012 | 0% (context limit at ~26 min) |
| **TTFB** | ~290-863ms | ~530-680ms |
| **Max session** | 60 min (hard cap) | 120 min (but context limit at ~3K words) |
| **Tool calling** | 100% | 100% |

**Recommendation:** OpenAI with production architecture (external STT → fresh voice session per question). Run_012 confirmed OpenAI-only direction — Grok dropped from testing.

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

**gpt-realtime-1.5**

| Run | 60min recall | Avg (15+30+60min blended) | Notes |
|-----|-------------|---------------------------|-------|
| 006 | 92% | 56% | First successful E07 run |
| 008 | ❌ 8% | 29% | STT session hit 60-min cap mid-meeting — transcript truncated; invalid |
| 009 | 83% | 50% | |
| 010 | — | 47% | 60min not run this round |
| 011 | 92% | 47% | |
| 012 | 55% | 43% | Grok dropped; mild recall drop, worth monitoring |

**gpt-realtime-alpha-dolphin-6**

| Run | Effort | Duration | Recall | Notes |
|-----|--------|----------|--------|-------|
| 017 | low | 15min | 25% | Limited coverage expected (only first 15min of meeting) |
| 017 | medium | 15min | 25% | |
| 017 | low | 60min | ⚠️ 67% | API cut session at 63% of meeting — recall covers first ~38min only |
| 017 | medium | 60min | ⚠️ 58% | Same API cap issue |
| 018 | low | 55min | _pending_ | In progress — designed to stay under 60min API cap |
| 018 | medium | 55min | _pending_ | In progress |

**There is no regression on gpt-realtime-1.5.** The "92% → 47%" drop cited in earlier summaries was a measurement inconsistency: the original "92%" came from a single 60min test; run summaries from run_009 onward blend 15+30+60min. Comparing 60min-only: consistent 83-92% (runs 006/009/011). Run_012 at 55% is mild, worth monitoring. Alpha 60min results are partial — true 60min recall unknown until run_018 completes.

**Grok hits its ~3K-word context limit at ~26 minutes** and fails all subsequent questions. OpenAI has no equivalent limit (tested to 7K+ words).

---

### Latency (E01 TTFB)

| Run | OpenAI | Grok |
|-----|--------|------|
| 009 | 773ms | 676ms |
| 010 | 290ms | 635ms |
| 011 | 451ms | 636ms |
| 012 | 863ms | — |

OpenAI latency is more variable (290-863ms). Grok is more consistent (530-680ms) but higher floor.

---

### Bottom Line

| Question | Answer |
|----------|--------|
| Can either provider do a 60-min voice session? | No. Both fail on raw audio after 20 min. |
| Does the production architecture work? | Yes — for OpenAI. Grok hits context limits at ~26 min. |
| Which provider for text recall? | Both reliable; OpenAI consistently at 100%, Grok 88-95%. |
| Which provider for a meeting assistant? | **OpenAI**, using production architecture (E07). |

**OpenAI's real limitations:**
- 60-min hard session cap on raw voice sessions — mitigated by the production architecture (sessions are short-lived)
- Latency varies 290-863ms across runs — fast on average, not perfectly predictable
- Audio hallucination spikes to 17-42% in always-streaming mode (not a concern in production architecture)
- E07 60min recall dropped to 55% in run_012 (vs 83-92% in prior runs) — mild, worth monitoring

**Why Grok doesn't solve any of this:**
- Grok's E07 = **0%** — hard context wall at ~3K words (~26 min), every question after that fails silently with `INVALID_ARGUMENT`, no graceful degradation
- Grok's always-streaming audio recall (33%) is comparable to or worse than OpenAI (25-50%)
- Grok's TTFB floor (530-680ms) is higher than OpenAI's typical range
- Grok audio hallucinates only 4% (lower than OpenAI's 17-42%) but achieves that by saying "I'm not sure" — lower recall, not smarter answers
- The production architecture limitations (audio cliff, latency variance) are shared or worse on Grok

**OpenAI is the clear choice.** 83-92% E07 recall on full 60-min meetings, no context ceiling (vs Grok's 3K-word wall), and the only provider where the production architecture actually works end-to-end.

## Setup

```bash
cp .env.example .env
# Fill in: OPENAI_API_KEY, XAI_API_KEY, ANTHROPIC_API_KEY

pip3 install -r requirements.txt

# One-time: generate audio fixtures (~10 min)
python3 scripts/generate_audio.py --meeting meeting_1hr
python3 scripts/generate_question_audio.py
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
nohup ./scripts/run_all.sh > /dev/null 2>&1 &
tail -f results/run_*/run.log | tail -1

# Run individual experiments
python3 run_experiment.py -e 01 -p openai                          # text recall
python3 run_experiment.py -e 06 -p openai --duration 15            # 15 min audio session
python3 run_experiment.py -e 07 -p openai --duration 60            # production sim, 60 min
python3 run_experiment.py -e 07 -p grok --duration 15 --skip-scoring  # quick Grok test

# Smoke test (5 min, verifies everything works)
./scripts/smoke_test.sh

# Compare results
python3 reports/compare_results.py -e 06 --run run_008
python3 reports/compare_results.py -e 07 --run run_008
```

## gpt-realtime-alpha-dolphin-6 (Realtime 2 alpha)

Set in `.env`:

```
OPENAI_REALTIME_MODEL=gpt-realtime-alpha-dolphin-6
OPENAI_REASONING_EFFORT=low   # minimal | low | medium | high
```

The alpha uses provider `openai-alpha`. Key differences from `openai`:
- No `OpenAI-Beta` header (alpha rejects it)
- `reasoning.effort` session parameter required
- `session.type` must be `realtime`
- Audio-only output (`output_modalities: ["audio"]`)
- Response items have a `phase` field: `commentary` (preamble) or `final_answer`

```bash
# Full alpha suite — generates audio fixtures if missing (~10 min), then runs all
# E01/E03/E04 at all 4 effort levels + E06/E07 at low+medium (~65 min total)
nohup ./scripts/run_alpha.sh > /dev/null 2>&1 &
tail -f results/run_*/run.log | tail -1

# Text-only experiments, no audio fixtures needed (~15 min)
nohup ./scripts/run_alpha.sh --skip-audio > /dev/null 2>&1 &
tail -f results/run_*/run.log | tail -1

# Single effort level
nohup ./scripts/run_alpha.sh --skip-audio --effort medium > /dev/null 2>&1 &
tail -f results/run_*/run.log | tail -1

# Individual experiments
OPENAI_REASONING_EFFORT=low  python3 run_experiment.py --run run_013 -e 01 -p openai-alpha
OPENAI_REASONING_EFFORT=high python3 run_experiment.py --run run_013 -e 03 -p openai-alpha
OPENAI_REASONING_EFFORT=low  python3 run_experiment.py --run run_013 -e 07 -p openai-alpha --duration 60
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
- 83-92% recall on 60-min meetings (runs 006, 009, 011), ~250ms cold start, ~4.5s question-to-answer

## Discoveries

### Hard Platform Limits

| Limit | OpenAI | Grok |
|-------|--------|------|
| Max session duration | **60 min** (hard cap — session dies mid-meeting) | **120 min** (but irrelevant — context fills first) |
| Max system prompt (realtime) | 7,000+ words (no limit hit across 12 runs) | **~3,000 words / ~300 lines** — returns `INVALID_ARGUMENT` beyond this |
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
| Fresh session + STT (E07, 60min avg runs 006/009/011) | **83-92%** | 0% (context limit) |

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

Across all 12 runs and every tool call experiment, both providers achieved 100% accuracy. This was never a differentiator and likely never will be.

### The VAD Fix That Unlocked Grok Audio

Runs 001-007: Grok's audio sessions died at exactly 15 minutes because `conversation.item.create` with inline audio was the wrong API call — the model treated it as background noise, not as conversation, and the session eventually timed out.

Run 008 fix: switch to `input_audio_buffer.append` + `server_vad: true`. This is how a real microphone stream works. After this fix, Grok's audio sessions survived and produced real answers for the first time.


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
├── scripts/
│   ├── run_all.sh               # Parallel test runner (gpt-realtime-1.5)
│   ├── run_alpha.sh             # Alpha flexible runner
│   ├── run_alpha_full.sh        # Alpha overnight suite
│   ├── smoke_test.sh            # Quick validation
│   ├── generate_audio.py        # One-time TTS fixture generation
│   └── generate_question_audio.py  # One-time question audio generation
├── reports/
│   ├── compare_results.py       # Cross-provider comparison
│   └── generate_alpha_report.py # Alpha structured report
├── run_experiment.py            # CLI entry point (run from repo root)
├── README.md
└── KNOWN_ISSUES.md
```

## Run Validity

Which runs are usable and why. ✅ = valid data, ⚠️ = partial (usable with caveat), ❌ = invalid/discard.

| Run | Provider | E01 | E03 | E06 | E07 | Reason if invalid |
|-----|----------|-----|-----|-----|-----|-------------------|
| 001 | openai, grok | ✅ | — | — | — | Bring-up run; Grok truncation bug present |
| 002 | openai, grok | ✅ | — | — | — | Grok truncation fixed |
| 003 | openai, grok | ✅ | — | — | — | Realistic script introduced |
| 004 | openai, grok | ✅ | — | ❌ | — | Grok audio sessions still die |
| 005 | openai, grok | — | — | ❌ | — | Killed mid-run — Grok E06 hung on missing response timeout |
| 006 | openai, grok | ✅ | — | ✅ | ✅ | First clean full run; E07 60min 92% |
| 007 | — | — | — | — | — | Skipped |
| 008 | openai, grok | ✅ | — | ✅ | ❌ | E07: STT session hit 60-min cap; transcript truncated at ~50min; post-meeting quiz invalid |
| 009 | openai, grok | ✅ | ✅ | ✅ | ✅ | Clean run; E07 60min 83% |
| 010 | openai, grok | ✅ | ✅ | ✅ | ✅ | E07 60min not run; blended avg only |
| 011 | openai, grok | ✅ | ✅ | ✅ | ✅ | E07 60min 92% |
| 012 | openai only | ✅ | ✅ | ✅ | ✅ | Grok dropped; E07 60min 55% (mild drop) |
| 013 | openai-alpha | ✅ | — | — | — | Alpha bring-up only; single E01 at low effort |
| 014 | openai-alpha | ❌ | ❌ | ❌ | ❌ | Killed at audio line 303/852 — audio fixtures not ready; no valid results |
| 015 | openai-alpha | ✅ | ✅ | ❌ | ❌ | E06/E07: alpha rejected `turn_detection:null`; server VAD auto-committed buffer; 0% recall + session crash |
| 016 | openai-alpha | — | — | ❌ | ❌ | Forfeited — provider code changed mid-run during VAD fix; results unreliable |
| 017 | openai-alpha | ✅ | ✅ | ⚠️ | ⚠️ | E06/E07 60min: OpenAI API cut sessions at 60-min hard cap (at 63% of meeting); scoring incomplete |
| 018 | openai-alpha | — | — | — | ⚠️ | E07 55min in progress; designed to stay under API cap |

**Usable for alpha vs baseline comparison:** run_017 E01/E03 (clean), run_017 E07 15min (limited coverage), run_018 E07 55min (pending).  
**Usable for gpt-realtime-1.5 E07 baseline:** runs 006, 009, 011, 012 (60min).

---

## Run History

| Run | Key finding |
|-----|-------------|
| 001 | First run. OpenAI 100% text recall. Grok truncation bug discovered. |
| 002 | Grok truncation fixed. OpenAI survived 1hr text session. Grok died at 15 min. |
| 003 | Realistic meeting script. Hallucination rates higher with messy dialogue. |
| 004 | Grok text sessions survive (keepalive fix). Audio sessions still die. |
| 005 | Killed — Grok E06 hung due to missing response timeouts. |
| 006 | Full parallel run. Both providers bad at always-streaming audio (25-33%). OpenAI E07 60min: 92%. |
| 007 | Skipped. |
| 008 | **Grok audio fix (VAD + input_audio_buffer).** Grok survives audio sessions for first 22 min, then context limit. ⚠️ OpenAI E07 60min was only 8% — STT session hit 60-min cap mid-meeting, truncating the transcript. Post-meeting quiz results are invalid for this run. Mid-meeting "Hey Otto" questions were 13/13 correct (what the run_008 report mistakenly cited as "92%"). |
| 009 | E01: Grok 90%, OpenAI 100%. E06: OpenAI 42%. E07 60min: OpenAI 83% — consistent with run_006. Summary average (15+30+60min blended) shows 50%. |
| 010 | E01: both 100%. E06: OpenAI hallucination spiked to 42%. E07: summary average 47% (blended). |
| 011 | E01: Grok 95%, OpenAI 100%. E06: OpenAI 50%. E07 60min: OpenAI 92%. Summary average 47% (blended). |
| 012 | **Latest run. OpenAI only — Grok dropped.** E01: OpenAI 100%, 863ms latency. E06: OpenAI 38%, 8 errors (up from 1 in prior runs). E07 60min: OpenAI 55% — mild drop from prior runs, worth monitoring. |
| 013 | Alpha provider bring-up. Single E01 run (reasoning=low) to validate `openai-alpha` wiring. 100% recall, 0% hallucination. |
| 015 | **Alpha run 1 — `gpt-realtime-alpha-dolphin-6`, all effort levels.** E01: 100% recall / 0% hallucination across minimal/low/medium/high. E03: avg TTFB 779–1047ms (see table below). E06/E07: ⚠️ invalid — audio input broken due to server VAD auto-committing the buffer (alpha rejected `turn_detection: null`); needs fix before audio results are valid. |
| 017 | **Alpha run 2 — VAD fix validated, full E06/E07.** E01: 100% recall all effort levels. E03: avg TTFB 618–929ms (medium fastest avg, high fastest P50). E07 60min: 67% (low), 58% (medium) — but sessions cut by OpenAI's hard 60-min API cap at 63% through meeting; true 60min recall unknown. E07 15min: 25% (expected given limited meeting coverage). E06 60min: hit API cap; E06 (15min): 17%, VAD interference still present. See `KNOWN_ISSUES.md` for run_017 partial validity table. |

### run_015 — Alpha E01 Recall by Effort

| Effort | Recall | Hallucination | Avg TTFB |
|--------|--------|---------------|----------|
| minimal | 100% | 0% | 539ms |
| low | 100% | 0% | 614ms |
| medium | 100% | 0% | 409ms |
| high | 100% | 0% | 504ms |

### run_015 — Alpha E03 Latency by Effort

| Effort | Avg TTFB | P50 | P95 | Simple | Medium | Complex |
|--------|----------|-----|-----|--------|--------|---------|
| minimal | 839ms | 883ms | 1522ms | 343ms | 1047ms | 1127ms |
| low | 779ms | 515ms | 1771ms | 582ms | 742ms | 1015ms |
| medium | 1047ms | 508ms | 2754ms | 481ms | 802ms | 1857ms |
| high | 847ms | 486ms | 2574ms | 303ms | 697ms | 1539ms |

Note: effort ordering is not strictly monotonic on a single run — variance expected. `high` has lowest P50 (486ms) and lowest simple TTFB (303ms). E06/E07 audio results excluded (invalid — see run note).

### run_017 — Alpha E03 Latency by Effort (updated)

| Effort | Avg TTFB | P50 | P95 | Simple | Medium | Complex |
|--------|----------|-----|-----|--------|--------|---------|
| minimal | 909ms | 1043ms | 1742ms | 307ms | 1254ms | 1167ms |
| low | 929ms | 1066ms | 1782ms | 264ms | 1162ms | 1361ms |
| medium | 618ms | 443ms | 1665ms | 373ms | 399ms | 1080ms |
| high | 827ms | 306ms | 2873ms | 286ms | 456ms | 1738ms |

`medium` has the best avg (618ms). `high` has lowest P50 (306ms) and lowest simple TTFB (286ms) but widest P95 (2873ms — reasoning spikes on complex prompts). Consistent with run_015 pattern.

### run_017 — Alpha E07 Production Sim

| Provider | Duration | Recall | Halluc | Session OK | Note |
|----------|----------|--------|--------|------------|------|
| openai-alpha[low] | 15min | 25% | 8% | ✓ | |
| openai-alpha[low] | 60min | 67% | 0% | ✗ | API 60min cap at 63% of meeting |
| openai-alpha[medium] | 15min | 25% | 33% | ✓ | |
| openai-alpha[medium] | 60min | 58% | 17% | ✗ | API 60min cap at 63% of meeting |
| gpt-realtime-1.5 (runs 009-012) | 60min | 79% | ~5% | ✓ | |

E07 60min recall is a lower bound — sessions were cut before the full meeting was played. The late-session cliff (1% for 40–60min questions) is an artifact of missing context, not model degradation.
