# Run 002 Report

**Date:** 2026-03-31
**Experiments:** E01-E05 (text-based, no audio)
**Providers:** OpenAI Realtime (`gpt-4o-realtime-preview-2025-06-03`), Grok/xAI (`grok-2-rt-audio`)
**Both providers tested with `modalities: ["text", "audio"]` for fair comparison**

---

## Headline Results

| | OpenAI | Grok |
|--|--------|------|
| **1-hour session survived?** | Yes (57 min) | No — died at 15 min |
| **Recall after full session** | 100% | N/A (dead) |
| **Instant recall (E01)** | 100% | 90% |
| **Avg TTFB** | ~350ms | ~700ms |
| **Hallucination rate** | 0-8% | 0-17% |

---

## E01: Instant Context Recall

126 meeting turns injected instantly (~2,249 tokens), 20 planted facts across 5 categories.

| Category | OpenAI | Grok |
|----------|--------|------|
| Names | 100% | 100% |
| Numbers | 92% | 75% |
| Decisions | 100% | 100% |
| Preferences | 100% | 68% |
| Dates | 100% | 68% |

**Grok's weakness:** dates and preferences. Numbers partially affected. Names and decisions solid.

---

## E02: Context Window Cliff

Injected filler up to 20K tokens, tested anchor fact recall at milestones.

**OpenAI:** Remembered anchor through 10K tokens. Lost it at 20K. Recent facts (5K-20K) recalled fine.

**Grok:** Codename recalled through 20K but budget number inconsistent. Recent facts mostly recalled.

---

## E03: Response Latency (fair — both using text+audio)

| Complexity | OpenAI TTFB | Grok TTFB |
|-----------|-------------|-----------|
| Simple | ~250ms | ~680ms |
| Medium | ~450ms | ~680ms |
| Complex | ~430ms | ~670ms |

OpenAI is ~2x faster. Grok's TTFB is remarkably consistent regardless of complexity.

---

## E04: Tool Call Reliability

**Both providers scored 100%.** 8/8 should-call correct, 8/8 should-not-call correct, zero errors, zero false positives. The race condition bug from run 001 (where `handle_tool_call` didn't wait for `response.done`) is fixed. Tool calling works reliably on both realtime APIs.

Note: run 001 showed 12% recall — that was caused by our test code bug, not the providers.

---

## E05: Real-Time 1-Hour Session (the key test)

### OpenAI — 57 real minutes, SURVIVED

- 167/167 meeting lines sent
- All 3 mid-meeting questions answered correctly
- 100% post-meeting recall accuracy
- 8% hallucination (on ambiguous/inference questions)
- Latency drift: 300ms (mid-meeting) → 550ms (post-meeting) — slight increase, no cliff

Mid-meeting answers (during the live session):
- min 15: "search latency is now around 140ms at p95" ✓
- min 30: "Mateo Ruiz, currently at Datadog, 8 years Go" ✓
- min 45: "cloud bill was $63K for February, up from $51K" ✓

### Grok — DIED AT 15 MINUTES

- 45/167 lines sent, then: `Conversation timed out due to inactivity`
- WebSocket pings (every 20s) were NOT enough — Grok requires actual audio/conversation activity
- Close code 1001 "going away" — server-initiated disconnect
- No recall phase possible

### Grok 5-min smoke test (worked fine)

When pacing is fast (5s/min), Grok survives and performs well:
- 92% recall, all mid-meeting questions correct
- Interesting: Grok scored better on action items (70% vs 45%) and inference (80% vs 76%)
- Suggests Grok may be better at synthesis but can't maintain long sessions

---

## Key Findings

1. **OpenAI is the only viable option for 1-hour meeting sessions.** Grok dies at 15 min from idle timeout even with WebSocket keepalive pings.

2. **No context degradation observed in OpenAI** over 57 minutes — 100% recall, no quality drop. Latency increased ~80% (300→550ms) but stayed well under 1s.

3. **Grok is 2x slower** (~700ms vs ~350ms TTFB) when both do the same work.

4. **Hallucination is higher with realistic questions** (8-17%) than with quiz-style questions (0%). The messy, ambiguous nature of real meetings makes this harder.

5. **Tool calling works perfectly** on both realtime APIs (100% accuracy). Run 001's poor results were caused by a bug in our test code.

6. **Grok may be better at inference/synthesis** in short sessions — worth investigating in a different context where long session survival isn't needed.

---

## What Run 002 Does NOT Test

- Real audio pipeline (speech-to-text accuracy, voice quality) — added in E06 for run 003
- Multiple concurrent sessions
- Network instability / reconnection
- Real user interaction patterns (interruptions, "um"s, background noise)

---

## Action Items for Run 003

- [ ] E06 audio session testing (TTS → stream → STT → compare)
- [ ] Investigate Grok keepalive — try sending periodic silent audio instead of just pings
- [ ] Run 3x per provider for statistical significance on E05
