# Known Issues & Invalid Runs

## run_017 — E06 and E07 60min runs terminated by OpenAI API session limit

**Affected experiments:** E06 (always-streaming audio), E07 (production sim), 60min duration only  
**Affected provider:** `openai-alpha` (low and medium effort)  
**Status:** Known API constraint — no code fix possible; results are partially valid

### What happened

The alpha API enforces a hard 60-minute session limit. Both E07 60min runs and the E06 60min runs
received `ConnectionClosedOK: received 1001 (going away) Your session hit the maximum duration of 60 minutes.`
mid-run:

- E07[low] 60min: connection died at line 507/799 (63% through meeting)
- E07[medium] 60min: connection died at line 504/799 (63% through meeting)
- E06[low] 60min: connection died at line 507/799
- E06[medium] 60min: connection died at line 504/799

E06 60min results have `aggregate: null` because scoring runs post-session and the session terminated
before questions were asked. E07 60min results have partial scoring (questions asked up to the cap).

### Impact on results

E07 60min recall (67% low, 58% medium) reflects only the first ~63% of the meeting. Late-session
decay (40–60min → 1%) seen in the raw summary is an artifact: those questions are about content
played *after* the session was cut, so the model had no context. The 67% figure overstates recall
for a true 60min meeting.

### Valid results from run_017

| Experiment | Status | Notes |
|---|---|---|
| E01 | ✅ Valid | 100% recall all effort levels |
| E02 | ✅ Valid | Context cliff |
| E03 | ✅ Valid | Latency data, all effort levels |
| E04 | ✅ Valid | Tool calling |
| E06 (15min) | ✅ Valid | 17% recall, VAD interference confirmed |
| E06 (60min) | ⚠️ Incomplete | Session hit API 60min cap; aggregate=null, no scoring |
| E07 (15min) | ✅ Valid | 25% recall (limited meeting coverage expected) |
| E07 (60min) | ⚠️ Partial | Session cut at 63% of meeting; recall reflects first 37min only |

### Workaround

For a true 60min test, would need to either: (a) wait for OpenAI to raise the alpha session limit,
or (b) split the meeting into segments and stitch sessions (not representative of production use).

---



## run_015 — E06 and E07 results are invalid

**Affected experiments:** E06 (always-streaming audio), E07 (production sim)  
**Affected provider:** `openai-alpha` (all effort levels)  
**Status:** Fixed in provider code — re-run needed

### What happened

The alpha session schema rejects `turn_detection: null` with `unknown_parameter`.
Removing it left server VAD active by default. With VAD on:

1. Audio chunks are appended to the buffer
2. VAD detects end-of-speech → auto-commits the buffer → auto-creates a response
3. Our explicit `input_audio_buffer.commit` fires on an already-empty buffer → `input_audio_buffer_commit_empty` error
4. Our explicit `response.create` fires while a response is already active → `conversation_already_has_active_response` error
5. The old error handler called `_response_done.set()` on every error, unblocking response waiters with empty text
6. Errors accumulated → STT session crashed at ~26.9 min

### Observed symptoms

- E06: 269 errors, 0% recall, all `honest_uncertainty` (model said "I don't know")
- E07: 0% recall across all categories, session died at 26.9 min

### Fix applied (2026-04-21)

`providers/openai_realtime_alpha.py` changes:
1. `connect()` attempts `turn_detection: {"type": "none"}` — if alpha rejects it, logs a warning and retries without the field (VAD-resilient mode)
2. `send_audio()` and `send_audio_no_response()` still send explicit commit + response.create as fallback, but the listener now swallows `input_audio_buffer_commit_empty` and `conversation_already_has_active_response` errors without unblocking response waiters
3. `send_audio_no_response()` drains any VAD-triggered response with a short timeout (8s) to keep the session clean between meeting audio segments

### Valid results from run_015

| Experiment | Status | Notes |
|---|---|---|
| E01 | ✅ Valid | 100% recall all effort levels |
| E02 | ✅ Valid | Context cliff |
| E03 | ✅ Valid | Latency data clean (compare script had a bug, raw JSON is correct) |
| E04 | ✅ Valid | Tool calling |
| E06 | ❌ Invalid | VAD bug — discard all results |
| E07 | ❌ Invalid | VAD bug — discard all results |

---

## run_014 — Entire run invalid (killed mid-audio generation)

**Status:** Discard entirely  
**What happened:** run_014 was killed at audio line 303/852 because audio fixtures had not been fully copied over from `/root/voice-benchmarks/`. No experiment results were produced.
