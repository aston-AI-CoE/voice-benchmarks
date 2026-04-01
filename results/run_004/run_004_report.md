# Run 004 Report

**Date:** 2026-03-31
**Meeting script:** meeting_1hr (649 lines, 7,559 words, ~50 min of audio)
**Providers:** OpenAI Realtime, Grok/xAI
**Both using `modalities: ["text", "audio"]`, `tts-1-hd` audio fixtures, natural pacing**

---

## Headline Results

| | OpenAI | Grok |
|--|--------|------|
| **E05 text 1hr survived?** | Yes (56 min) | Yes (56 min) |
| **E05 text recall** | 100% | 92% |
| **E06 audio 1hr survived?** | No (died at 39 min) | No (died at 15 min) |
| **E06 audio recall** | 64% (from smoke test) | N/A (died before questions) |
| **Hallucination rate** | 25-33% (text), 18% (audio) | 0-8% (text), N/A (audio) |

---

## E01: Instant Context Recall

| | OpenAI | Grok |
|--|--------|------|
| Recall | 100% | 95% |
| Hallucination | 0% | 5% |
| Avg TTFB | 274ms | 629ms |

Consistent with previous runs. OpenAI faster and more accurate on simple recall.

---

## E05: Real-Time 1-Hour Text Session

### Session survival: BOTH SURVIVED

Grok's silent audio keepalive fix worked — first time Grok survived a full 1-hour
session. Both providers ran all 649 lines at real-time pacing (~56 min).

### Recall accuracy

| Category | OpenAI | Grok |
|----------|--------|------|
| Action items | 70% | 70% |
| Ambiguous | 92% | 85% |
| Decisions | 88% | 83% |
| Details | 92% | 91% |
| Inference | 100% | 82% |

### Mid-meeting "Hey Otto" responses

Both providers answered 6/6 mid-meeting questions. Key observations:

- **Min 12 (search latency):** Both correct — 600ms to 140ms
- **Min 22 (accessibility):** Both correct — 14 violations
- **Min 30 (backend candidate):** BOTH GOT THIS WRONG in the 1hr run. OpenAI said
  "Tomas Kovac" (wrong person — that's the autocomplete dev). Grok said "I don't have
  details yet." The correct answer is Mateo Ruiz from Datadog.
- **Min 38 (cloud bill):** Both correct — $63K
- **Min 48 (logging tools):** OpenAI said "David didn't mention logging tools" (WRONG —
  he compared Mezmo vs Datadog). Grok correctly said "Redis vs Memcached" for caching
  (confused the question but closer).
- **Min 55 (Redis upgrade):** Both correct — Saturday maintenance window

### Hallucination: OpenAI hallucinates MORE than Grok

This is surprising. OpenAI: 25-33% hallucination. Grok: 0-8%.

OpenAI confidently fabricates specific wrong details (names, tools) while Grok tends to
either get it right or say it doesn't know. For a meeting assistant, Grok's behavior
is actually safer — better to say "I'm not sure" than confidently give wrong info.

---

## E06: Audio Session — The Reality Check

### Grok: Dead on arrival

Grok dies at exactly line 91 (~15 min) in BOTH smoke and 1hr runs. Same error:
`Conversation timed out due to inactivity`. The silent audio keepalive that works
for text sessions does NOT work for audio sessions. The `conversation.item.create`
with inline audio approach may not count as "activity" for Grok's session manager.

**Grok cannot do audio-based sessions longer than ~15 minutes.** This is a hard
platform limitation.

### OpenAI: Survives smoke test, dies in 1hr

- **Smoke test (5s/min):** Survived 649 lines, 57 min. 64% recall, 10.3% WER.
- **1hr real-time:** Died at line 455 (~39 min). WER degraded to 35%.

The audio pipeline adds significant overhead. Streaming 649 PCM16 clips at real-time
speed eventually overwhelms the WebSocket connection.

### Audio vs Text: The comprehension gap

| Metric | OpenAI Text (E05) | OpenAI Audio (E06) |
|--------|-------------------|--------------------|
| Recall | 100% | 64% |
| Hallucination | 25-33% | 18% |
| Session survived? | Yes (56 min) | No (39 min) |

**36% recall loss going from text to audio.** This is the cost of the STT pipeline.
The model loses information when it has to transcribe audio vs receiving clean text.

OpenAI also hallucinated wrong names from audio — "Tom Bradley" instead of Mateo Ruiz,
"Graylog and ELK stack" instead of Mezmo and Datadog. The STT introduces errors that
cascade into wrong comprehension.

### Transcription quality (WER) degrades over time

- Smoke test (fast pacing): 10.3% WER — good
- 1hr run before death: 35% WER — bad

Whisper's transcription accuracy degrades as the session gets longer. This could be
due to context window pressure on the transcription model, or accumulating audio
buffer issues.

---

## What E05 vs E06 Tells Us

**E05 (text) does NOT represent real-world performance.** In production, Otto hears
audio through a microphone, not clean injected text. The real pipeline is:

```
Microphone → STT (Whisper) → Text in context → LLM → TTS → Speaker
```

E05 skips the STT step. E06 includes it. The 36% recall gap between them proves
the STT step is a major source of information loss.

**E05 is still useful** — it isolates the LLM's raw context retention from the audio
pipeline. When E05=100% but E06=64%, we know the model CAN remember but the audio
pipeline is losing information before it reaches the model.

---

## Cross-Run Consistency (E05 text, 1hr sessions)

| Run | OpenAI Recall | OpenAI Survived | Grok Recall | Grok Survived |
|-----|---------------|-----------------|-------------|---------------|
| 002 | 100% | Yes (57 min) | N/A | No (15 min) |
| 003 | 92% | Yes (57 min) | N/A | No (15 min) |
| 004 | 100% | Yes (56 min) | 92% | Yes (56 min) |

Run 004 is the first run where Grok survived the full session (keepalive fix).

---

## Key Findings

1. **Both providers can now hold a 1-hour TEXT session** — Grok's keepalive fix works.

2. **Neither provider reliably holds a 1-hour AUDIO session** — OpenAI died at 39 min,
   Grok at 15 min. Audio sessions are harder to maintain.

3. **Audio comprehension is 36% worse than text** (OpenAI 64% vs 100%). The STT
   pipeline loses significant information.

4. **OpenAI hallucinates more than Grok** (25-33% vs 0-8%) on realistic messy meetings.
   Grok is more conservative — says "I don't know" instead of fabricating.

5. **Transcription quality degrades** over long audio sessions (10% → 35% WER).

6. **For production meeting assistant use:** The audio pipeline is the bottleneck, not
   the LLM. Improving STT accuracy (or using an external transcription service like
   Deepgram/AssemblyAI instead of built-in Whisper) could close the gap.

---

## Recommendation

For Otto as a 1-hour meeting assistant:

- **Text mode (live transcription → text injection):** Both providers work. OpenAI has
  better recall but worse hallucination. Grok is more conservative and safer.
- **Native audio mode:** Not production-ready for 1-hour sessions on either provider.
  Sessions die, transcription degrades, comprehension drops.
- **Best approach:** Use an external STT service (Deepgram, AssemblyAI) for transcription,
  then inject the text into the realtime session. This gives you the reliability of E05
  with real audio input. The realtime API handles the voice output only.
