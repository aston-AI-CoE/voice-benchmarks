# gpt-realtime-alpha-dolphin-6 — Capabilities, Limitations & Otto Use Case Impact


|            |                                                         |
| ---------- | ------------------------------------------------------- |
| **Date**   | 2026-04-21                                              |
| **Model**  | gpt-realtime-alpha-dolphin-6 (gpt-realtime-2 alpha)     |
| **Source** | OpenAI alpha brief + Workato benchmark runs 015/017/019 |


---

## Capabilities (what's better than 1.5)


| Capability                           | What it means                                                            | Impact on Otto                                                                                                      |
| ------------------------------------ | ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------- |
| **Reasoning**                        | Model thinks before answering instead of reacting immediately            | Better instruction following, more reliable tool dispatch — directly improves `ask_otto` routing accuracy           |
| **Tool calling**                     | 100% accuracy across all effort levels (our E04 benchmark) vs 1.5's 100% | No regression; meets bar for Zoom bot's `ask_otto` dispatch                                                         |
| **Text recall**                      | 100% across all efforts (our E01 benchmark)                              | No regression on core meeting memory task                                                                           |
| **256K context window**              | ~4× larger than 1.5                                                      | Full meeting transcript fits without truncation; relevant for injecting long meetings into E07-style fresh sessions |
| **Instruction following strictness** | Follows instructions more literally                                      | Prompts need to be precise — looser prompts that worked on 1.5 may behave differently (see Limitations)             |
| **Multilingual**                     | Material gains per OpenAI evals (GPQA audio: 70–76% vs 1.5's 54%)        | Relevant for Otto's international customers; not yet tested by us                                                   |
| **Emotional range**                  | Better voice steerability (whisper, emphatic, etc.)                      | Useful for Zoom bot personality tuning; not yet tested                                                              |
| **Preambles**                        | Model speaks a brief thinking phrase before answering ("one moment...")  | Fills dead air during `ask_otto` tool calls — makes the bot feel responsive even when Otto is slow                  |
| **Per-turn effort override**         | `response.create` can override effort level per turn                     | Can use `low` for conversational replies and `high` for complex tool dispatch in the same session                   |


---

## Limitations (what's worse or missing vs 1.5)


| Limitation                                    | What it means                                                               | Impact on Otto                                                                                                                                                                                       |
| --------------------------------------------- | --------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **VAD always on**                             | Server voice detection cannot be disabled (`turn_detection: null` rejected) | VAD = the server deciding when a user "stopped talking" and auto-triggering a response. With 1.5, `turn_detection: null` was accepted, so the client controlled when to commit audio and trigger a response. Alpha rejects this, so the server auto-fires responses on any detected speech. For passive always-on meeting streaming (E06), this is fatal — the model responds to random participant speech and crosstalk. For the intended "Hey Otto" architecture (E07), the impact is lower: each question session is short-lived and only hears the intended question audio. Workaround: `response.cancel` + drain before sending the question. **Side effect:** `response.cancel` fires before any audio is sent (session is fresh), so the server returns `response_cancel_not_active`. This is benign — the session proceeds normally. Fixed in benchmark code by adding `response_cancel_not_active` to the ignorable-errors set. Better fix (not yet applied): gate the cancel on a `_response_active` flag set by `response.created` events, eliminating the spurious cancel entirely. |
| **Hard 60-min session cap**                   | Session closes automatically at 60 minutes                                  | Zoom bot for a 90-min meeting will be disconnected mid-session. E07 production sim can't be cleanly tested past 55min. Requires session reconnect logic.                                             |
| **Higher latency floor**                      | Avg TTFB 618–929ms vs 1.5's 595ms avg (our E03)                             | Marginally slower for simple voice replies; acceptable. P95 spikes wider (up to 2873ms at `high` effort) for complex prompts.                                                                        |
| **Strict instruction following can surprise** | "Order ID" ≠ "confirmation code" to the model                               | Otto's system prompt may need rewording — terms that were interchangeable on 1.5 may break on alpha. Needs a prompt audit before switching.                                                          |
| **Preambles add a phase to handle**           | Responses come in two parts: `commentary` then `final_answer`               | Zoom bot needs to play both audio phases correctly and add silence padding between them (OpenAI's known issue before GA). Ignored = cutoff audio.                                                    |
| **No input audio transcription**              | `input_audio_transcription` field is rejected server-side (confirmed run_020 — not a client code bug). This field requests a text copy of what the user said. **Audio to the model still works normally** — the model hears and responds to voice. Only the text feedback transcript is unavailable. | E07 STT session can't use the Realtime API as a transcription engine — must use Zoom SDK or Deepgram instead. In benchmark code: skipping the transcription wait when server rejects this field (was burning 3s per audio line = 36+ min overhead on a 55-min run, causing the STT session to hit the 60-min cap at minute 29). |
| `**medium` faster than `low`**                | Counterintuitive — `medium` avg TTFB (618ms) beats `low` (929ms)            | Effort selection is not straightforward. Don't assume lower effort = lower latency. Our data: `medium` for best avg, `high` for best P50.                                                            |


---

## Our Use Cases & What's Affected

### Use Case 1: Zoom Voice Meeting Bot (feature/zoom-voice-to-voice-demo)

The intended architecture: Zoom SDK (or Deepgram) handles continuous STT and builds the meeting transcript. When a participant says "Hey Otto", a **fresh voice session opens** with the full transcript injected as context. The question is sent to the model, which either answers directly or calls `ask_otto` to delegate to the Otto backend. The session then closes. The model is never passively listening to the meeting — it only hears the intended question.

This is E07 architecture, not E06. E06 (always-streaming one session for the whole meeting) is not viable and not the target production design.


| Aspect                                    | Status         | Notes                                                                                                                                  |
| ----------------------------------------- | -------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| "Hey Otto" trigger → fresh session        | ✅ Works        | Each question opens a short-lived session; model only hears the question, not ambient meeting audio                                    |
| Answering simple conversational questions | ✅ Works        | Low/medium effort, fast enough for voice                                                                                               |
| Delegating to `ask_otto`                  | ✅ Works well   | 100% tool call accuracy (E04); preambles can say "let me check that" while Otto runs                                                   |
| VAD forced on (alpha only)                | ⚠️ Minor       | Since sessions are short and only hear the question, VAD misfires are rare. Workaround (`response.cancel` + drain) already implemented. gpt-realtime-1.5 accepted `turn_detection: null` so this workaround was not needed there. |
| Long meetings (60+ min)                   | ❌ Blocked      | The *question* session is short (fine). The *STT session* building the transcript also uses the Realtime API in our test setup and hits the 60-min cap. In production, STT comes from Zoom SDK or Deepgram — not the Realtime API — so this cap does not apply. |
| Preamble audio playback                   | ⚠️ Needs work  | Two-phase responses not currently handled in `realtime_session.py` — only `final_answer` audio is played                               |
| System prompt compatibility               | ⚠️ Needs audit | Current prompt is loose ("deep knowledge, complex reasoning") — alpha's strict instruction following may change routing behavior       |


### Use Case 2: E07 Production Sim (benchmark — fresh session per question)

Each "Hey Otto" question opens a fresh voice session with the full meeting transcript injected.


| Aspect                              | Status      | Notes                                                                                                                                 |
| ----------------------------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| Recall at 55min (clean)             | ✅ **83%**  | run_020 — with transcription-wait fix applied. Beats 1.5 baseline (79%).                                                             |
| Recall vs 1.5 baseline (79%)        | ✅ Exceeds  | Alpha low=83%, medium=83% vs 1.5's 79%. Prior 58% figure (run_019) was a benchmark infrastructure bug, not a model quality issue.    |
| Tool calling in production sessions | ✅ 100%     | E04 confirms                                                                                                                          |
| Session setup overhead              | ⚠️ Slower  | VAD rejection adds 250–8000ms per connection (API latency varies); intermittent 8s spikes on `unknown_parameter` error response       |


---

## Bottom Line for ADE Kickoff

**Proceed with alpha for Otto.** Recall exceeds 1.5 (83% vs 79%) on a clean 55-min production sim. Tool calling is 100% across all effort levels. The reasoning upgrade improves the two things that matter most: knowing when to delegate and what to ask.

**Two items before production:**

1. **Prompt audit** — alpha's strict instruction following means the current Zoom bot system prompt needs testing before switching models
2. **Preamble handling** — two-phase audio not yet handled in `realtime_session.py`; cosmetic but affects voice experience

**60-min session cap**: not a blocker for the "Hey Otto" architecture (question sessions are seconds long). Is a blocker if any part of the pipeline needs a persistent long-running session. Raised as P0 with OpenAI.

