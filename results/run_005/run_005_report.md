# Run 005 Report (Partial — killed due to Grok hang)

**Date:** 2026-03-31
**Status:** Killed during E06 Grok 15min — Grok hung after 900s inactivity timeout
**Meeting script:** meeting_1hr (852 lines, ~53 min audio, tts-1-hd)

---

## What Completed

| Experiment | OpenAI | Grok |
|-----------|--------|------|
| E01 Instant Recall | 100% recall | 90% recall |
| E02 Context Cliff | Remembers to 10K tokens | Remembers to 10K tokens |
| E03 Latency | ~310ms TTFB | ~535ms TTFB |
| E04 Tool Calls | 100% accuracy | 100% accuracy |
| E06 15min audio | 25% recall, 9.6% WER | **HUNG — empty responses, then 900s timeout** |
| E06 30/60min | Not reached | Not reached |
| E07 all | Not reached | Not reached |

---

## The Grok Audio Problem (Consistent Across ALL Runs)

**Grok's realtime API has a hard 900-second (15 min) inactivity timeout for audio sessions.** This has happened in every single run:

- Run 001: Died at 15.1 min
- Run 002: Died at 15.1 min
- Run 003: Died at 15.1 min
- Run 004: Died at 15.2 min (twice)
- Run 005: Timed out at 15 min, then hung

Additionally, even before dying, Grok doesn't comprehend the audio content. Responses are:
- "I'm listening in on the meeting. Let me know if you need anything."
- "Got it, team. I'm Otto, here and listening if you need me."
- Empty strings

**Grok's `conversation.item.create` with inline audio does not work for meeting comprehension.** The model treats the audio as background noise, not as conversation to understand.

---

## E06 OpenAI 15min — Worked Well

- Session survived all 207 lines
- 9.6% average WER (good transcription)
- All 4 mid-meeting questions answered correctly via audio
- Post-meeting: 25% recall (but this is for 15 min context with 12 questions spanning full 60 min — the 7 "not discussed" answers are correct)

---

## Root Cause of Hang

When Grok times out, the `send_audio` or `send_text` call in E06/E07 hangs waiting for `response.done` that never comes. The error event fires but the response event doesn't, so the experiment blocks forever.

**Fix needed:** Add a timeout to all `response.done` waits. If no response after 30s, treat it as a failure and continue.

---

## Recommendations for Run 006

1. Skip Grok E06 entirely — it fundamentally doesn't work for audio sessions
2. Add response timeouts to prevent hangs
3. Focus Grok testing on E07 (production sim with fresh sessions)
