# OpenAI ADE Kickoff — Workato / Otto Alpha Feedback


|             |                                                                  |
| ----------- | ---------------------------------------------------------------- |
| **Date**    | 2026-04-21                                                       |
| **Status**  | Final — run_020 complete                                         |
| **Model**   | gpt-realtime-alpha-dolphin-6                                     |
| **Runs**    | run_015, run_017, run_018 (invalid), run_019 (invalid — coverage mismatch), run_020 (final) |
| **Contact** | Aston Lee, [aston.lee@workato.com](mailto:aston.lee@workato.com) |


---

## Scenario Tested

**Otto voice meeting assistant** — a voice bot that joins Zoom meetings and answers questions from participants. The intended production architecture:

- Zoom SDK or Deepgram handles continuous STT and builds the meeting transcript
- When a participant says "Hey Otto", a **fresh OpenAI Realtime session opens** with the full transcript injected as context
- The model answers directly or calls `ask_otto` to delegate to the Otto backend
- The session closes after each answer

This is **E07 (production sim)**. The model is never passively listening to ambient meeting audio — it only hears the intended question per session.

- **E06 (always-streaming)**: Single long session processing all meeting audio continuously. Tested for comparison only; not the target architecture. Not viable on alpha (VAD forced on).

Also tested: text recall (E01), response latency (E03), tool call reliability (E04).

**Baseline**: gpt-realtime-1.5, runs 009–012 (same test suite, same audio fixtures).

---

## Eval Results

### E01 — Instant Context Recall (Text)

20 facts injected into a text session; model quizzed immediately.


| Provider                    | Recall | Hallucination | Notes        |
| --------------------------- | ------ | ------------- | ------------ |
| gpt-realtime-1.5 (baseline) | 100%   | 0%            | Runs 009–012 |
| alpha minimal               | 100%   | 0%            |              |
| alpha low                   | 100%   | 0%            |              |
| alpha medium                | 100%   | 0%            |              |
| alpha high                  | 100%   | 0%            |              |


**Result: no regression. Alpha matches 1.5 on text recall at all effort levels.**

---

### E03 — Response Latency (TTFB)

30 prompts across 3 complexity tiers.


| Effort                      | Avg       | P50       | P95    | Simple | Complex |
| --------------------------- | --------- | --------- | ------ | ------ | ------- |
| minimal                     | 909ms     | 1043ms    | 1742ms | 307ms  | 1167ms  |
| low                         | 929ms     | 1066ms    | 1782ms | 264ms  | 1361ms  |
| medium                      | **618ms** | 443ms     | 1665ms | 373ms  | 1080ms  |
| high                        | 827ms     | **306ms** | 2873ms | 286ms  | 1738ms  |
| gpt-realtime-1.5 (baseline) | 595ms     | —         | 1200ms | —      | —       |


**Observations:**

- `medium` has the lowest average TTFB (618ms) — counterintuitively faster than `low`/`minimal`
- `high` has the lowest P50 (306ms) but widest P95 (2873ms) — reasoning stabilizes simple responses but spikes on complex prompts
- Effort ordering is not monotonic on avg TTFB — consistent across run_015 and run_017

---

### E04 — Tool Call Reliability

8 should-call + 8 should-not-call scenarios.


| Effort                      | Accuracy | Precision | Recall | F1   |
| --------------------------- | -------- | --------- | ------ | ---- |
| minimal                     | 100%     | 100%      | 100%   | 100% |
| low                         | 100%     | 100%      | 100%   | 100% |
| medium                      | 100%     | 100%      | 100%   | 100% |
| high                        | 100%     | 100%      | 100%   | 100% |
| gpt-realtime-1.5 (baseline) | 100%     | 100%      | 100%   | 100% |


**Result: no regression. Perfect tool call routing at all effort levels.**

---

### E07 — Production Sim (Fresh Session per Question, Full Transcript Injected)

Meeting audio streamed through an STT session; each "Hey Otto" question opens a fresh voice session with the full transcript as context.

**Important — prior results are not a valid model quality comparison:**

The E07 benchmark uses the Realtime API as an STT engine to build the meeting transcript. Alpha rejects `input_audio_transcription` (server-side, confirmed run_020), which caused 3 seconds of wasted wait per audio line. Over 737 lines this added 36+ minutes of overhead, causing the STT session to hit the 60-min API cap at line 392 — covering only ~29 of 55 meeting minutes. Questions about minutes 30–55 were correctly answered as "not in transcript" because they genuinely weren't. gpt-realtime-1.5 is unaffected because `input_audio_transcription` works there.

**The 79% vs 58% recall gap was a transcript coverage artifact, not a model quality difference.** Both models were measured on different amounts of meeting content. This comparison is invalid.

run_020 fixed this by skipping the transcription wait when the server rejects `input_audio_transcription`. STT coverage improved from 53% → 84%, and recall jumped from 58% → 83%.

**Baseline (gpt-realtime-1.5, runs 009–012):** 79% recall on 60min meeting. STT session capped at ~53min but all 12 question sources fall within that window, so coverage was sufficient. Not directly comparable to alpha runs — different meeting duration, different STT behavior.

**Alpha runs:**

| Run     | Effort | Meeting | STT coverage    | Recall  | Halluc | Valid? |
| ------- | ------ | ------- | --------------- | ------- | ------ | ------ |
| run_019 | low    | 55min   | 29/55 min (53%) | 58%     | 8%     | No — coverage too low, questions from min 30–55 unanswered |
| run_019 | medium | 55min   | 29/55 min (53%) | 50%     | 0%     | No — same issue |
| run_020 | low    | 55min   | 46/55 min (84%) | **83%** | 17%    | Mostly valid — 2 questions (pm_11 min49, pm_12 min52) still outside coverage window due to VAD drain overhead |
| run_020 | medium | 55min   | 46/55 min (84%) | **83%** | 8%     | Same |
| run_021 | low    | 55min   | 27/55 min (54%) | 58%     | 17%    | No — API WebSocket drop at 38.8 min (transient, unrelated to code) |
| run_022 | low    | 55min   | 45/55 min (79%) | **83%** | 8%     | ✅ Valid — confirms run_020 result |

run_020 applied fix: skip transcription wait when server rejects `input_audio_transcription`. Coverage improved from 53% → 84%. run_022 independently confirms 83% recall at low effort.

**Why the STT session hits the 60-min cap:** E07 uses two separate Realtime API sessions. Session A (STT) runs for the entire meeting to build the transcript — this one hits the cap. Session B (each "Hey Otto" question) opens fresh per question and closes after ~10 seconds — these never approach the cap. **In production, Session A does not exist** — STT comes from Zoom SDK or Deepgram. The 60-min cap is a benchmark infrastructure limitation only, not a production concern.

Remaining gap: forced VAD drain (8s/trigger) still adds overhead to Session A. The 2 failing questions (pm_11 min49, pm_12 min52) are outside the coverage window as a result. Benchmark-only issue.


---

### E06 — Always-Streaming Audio

Architecture where one long session processes all meeting audio continuously.

**Result: not viable on alpha.** Alpha forces server VAD on (rejects `turn_detection: null`). Server VAD auto-commits audio buffer mid-stream and triggers unwanted responses, interfering with meeting audio ingestion. This was also broken on gpt-realtime-1.5 (consistent finding across all runs).

**Recommendation: do not use always-streaming architecture with alpha.**

---

## Top Strengths

**1. Tool call reliability is perfect across all effort levels (E04, run_017)**
All 4 effort levels scored 100% on should-call / should-not-call accuracy. For Otto's use case — a voice assistant that decides when to delegate to backend agents — this is the most important property. Zero false positives (unnecessary tool calls) and zero false negatives (missed delegations).

- Session IDs: run_017/e04_tool_call_reliability (openai-alpha[low|medium|high|minimal])

**2. Text recall matches gpt-realtime-1.5 at all effort levels (E01, runs 015 + 017)**
100% recall, 0% hallucination across all 4 effort levels on 20 injected facts. No prompt engineering needed — drop-in replacement for recall tasks.

- Session IDs: run_017/e01_instant_context_recall (all efforts)

**3. 100% recall on full meeting transcript — model quality confirmed (E08, run_023)**
E08 strips out the STT phase entirely: the full meeting transcript is loaded as text and injected directly into each fresh question session. With the correct context, the model scores 100% recall at both low and medium effort, with 0 false negatives on the 12 post-meeting questions. Hallucination rate: 8% (low), 17% (medium). Total run time: 6 minutes. This separates model quality from benchmark infrastructure — the model itself is not the limiting factor.

- Session IDs: run_023/e08_context_recall (openai-alpha[low], openai-alpha[medium])

**4. `medium` effort has the best average latency — counterintuitive but consistent**
`medium` (618ms avg TTFB) beats `low` (929ms) and `minimal` (909ms). Observed in both run_015 and run_017. Hypothesis: reasoning stabilizes the generation path, reducing variance on medium-complexity prompts. Worth validating in a production voice context.

- Session IDs: run_017/e03_response_latency

---

## P0 Improvements for Production

**1. Hard 60-minute session cap — not a production blocker for Hey Otto, but worth raising**
Alpha sessions close with `1001 (going away) Your session hit the maximum duration of 60 minutes.`

**Production impact: none for our architecture.** In the "Hey Otto" model, each question opens a fresh session (~10 seconds) and closes immediately. A 90-min meeting fires dozens of these — none approach the cap. The cap only matters for persistent long-running sessions.

**Benchmark impact: real.** Our E07 benchmark used a Realtime API session as an STT engine, streaming audio for 55 minutes. That session hits the cap. However, using the Realtime API for STT on alpha has no benefit: `input_audio_transcription` is rejected server-side (see P0 #3), so the session receives audio but returns nothing useful. In production, STT comes from Zoom SDK or Deepgram — not the Realtime API — so the cap is irrelevant there too.

We're raising this because it affects any customer who wants an always-on voice assistant or a persistent agent connection. For our use case it's a benchmark infrastructure issue we've already worked around (E08 drops the STT session entirely and runs in 6 min with 100% recall).

**Request:** Raise the alpha session cap to 120min, or provide a context-handoff mechanism for session continuation — primarily for customers whose architecture requires persistent connections.

- Session IDs: run_017/e07_production_sim (openai-alpha[low]_20260421T081622Z, openai-alpha[medium]_20260421T081620Z)

**2. `turn_detection: null` rejected + silent state bug in `session.updated`**

**What VAD is:** Server-side Voice Activity Detection — the API decides when a user has stopped talking and automatically triggers a model response.

**Why this wasn't a problem on gpt-realtime-1.5:** `turn_detection: null` was accepted. The client controlled when to commit audio and trigger a response:
```
client streams audio → client decides "user done" → client sends commit → client triggers response
```
Full client control. No surprise auto-responses.

**Why alpha is different:** Alpha rejects `turn_detection: null`. VAD is always server-controlled:
```
client streams audio → server decides "user done" → server auto-triggers response
```

For our **"Hey Otto" architecture** (short sessions, each only hears the intended question): minor inconvenience. VAD fires correctly because the session only hears one person asking one question. We implemented a `response.cancel` + drain workaround and it works.

For **always-on streaming** (E06 — one session hearing all meeting audio): fatal. The model auto-responds every time any participant pauses mid-sentence. Otto interrupts random meeting conversation. E06 is not viable on alpha for this reason.

**The state bug (more serious than the VAD rejection itself):** When `turn_detection: null` is rejected, `session.updated` omits the `turn_detection` field entirely instead of returning `"type": "server_vad"`. This means:

```python
td = session_updated.get("turn_detection")  # → None (field missing)
if td is None:
    vad_active = False  # ← WRONG — VAD is actually active
```

Client code reads "VAD is off" when it is in fact on. Every audio line streams into an active VAD session, auto-responses fire for every speaker pause, and the session fills with garbage responses the client isn't handling. This silently invalidated run_018 — the benchmark ran for 55 minutes producing wrong results before we identified and fixed the bug.

**Request:** When VAD is active after a rejected `turn_detection` override, return `"turn_detection": {"type": "server_vad"}` in `session.updated` so clients can reliably detect the actual VAD state.

- Session IDs: run_018/e07_production_sim (both efforts — invalid due to this bug)

**3. API cold-connect latency intermittently spikes to ~8 seconds**
When connecting fresh sessions (E07 fires one per question), the `session.update → error (unknown_parameter for turn_detection) → retry → session.updated` round-trip occasionally takes 8+ seconds. Normal connections complete in 250–600ms. The 8s cases appear to be API-side latency on the error response, not client-side. Observed consistently in run_018 post-meeting questions (all 12 had ~8300ms cold start).

**Request:** Investigate server-side latency on `unknown_parameter` errors — these seem to be queued differently than normal events.

- Session IDs: run_018/e07_production_sim (openai-alpha[low]_20260421T175505Z)

---

## Preamble Feedback

**Observation:** Preambles were not clearly observed in E01/E03 (text context, short responses, low/minimal effort). At `high` effort on complex E03 prompts, a noticeable delay before response suggests reasoning is happening but preamble audio was not always produced.

**Not yet tested:** E04 tool calling with `high` effort is the right scenario to observe preambles (model should say "checking your calendar" before tool dispatch). Needs a dedicated test run.

**Known issue from spec acknowledged:** Preamble audio cut off at end syllable was not reproducible in our test setup (text-context sessions). Will test with longer voice interactions.

**Questions for ADE session:**

- Is preamble behavior prompting documented anywhere? What's the recommended prompt pattern for tool call announcements ("checking your calendar", "looking that up")?
- Can preamble content be constrained to specific phrases (for brand consistency)?
- For meeting assistant use case: should the preamble be used as a meeting-context verbal acknowledgment ("I heard that, let me check the transcript")?

---

## Languages Feedback

Not tested in this benchmark run — all audio fixtures are English. Will test multilingual in next round.

**Planned:** Japanese and Spanish meeting transcripts. Otto has multilingual customers and this is a meaningful differentiator if the preamble/final_answer split handles language transitions correctly.

---

## Open Questions for Kickoff

### Blockers / P0

**1. Session cap — not blocking us, but affects persistent-connection architectures**
The "Hey Otto" question sessions are seconds long — unaffected by the 60-min cap. Our benchmark STT session hit the cap, but we've moved to E08 (text transcript injected directly) which eliminates that session entirely and runs in 6 min with 100% recall. In production, STT comes from Zoom SDK — no persistent Realtime connection needed.

Raising for customers who need always-on or persistent agent connections:
- Is a 120min cap or session-handoff mechanism on the roadmap before GA?
- What is the recommended reconnect/continuation pattern for long-running sessions today?

**2. `turn_detection: null` rejection — permanent or alpha-only?**
Alpha always runs server VAD. Our production architecture ("Hey Otto" trigger → fresh short session) can work around this, but always-streaming use cases cannot. The rejection also causes a silent state bug: `session.updated` omits `turn_detection` entirely after rejection, so clients can't detect VAD is active without special handling.
- Will `turn_detection: null` be supported before GA?
- Can `session.updated` return `turn_detection.type = "server_vad"` when VAD is active, even after a rejected override attempt?

**3. `input_audio_transcription` rejection — not blocking us, but a capability regression**
Alpha rejects `input_audio_transcription` server-side (confirmed run_020 — not a client code bug). This field requests a text copy of what the user said within a Realtime session.

**Production impact: none for our architecture.** For the "Hey Otto" use case, STT comes from Zoom SDK (which provides speaker-attributed transcription for free, with no session cap). Using the Realtime API as an STT engine on alpha has no benefit: the field is rejected, the 60-min cap kills long sessions, and VAD fires on ambient meeting audio. Zoom SDK or Deepgram is unambiguously the right tool for meeting STT. We've confirmed this with E08 — loading the transcript directly and asking questions via fresh Realtime sessions achieves 100% recall in 6 minutes.

**Why we're still raising it:** It's a regression from 1.5 and affects use cases where a developer doesn't have a separate STT pipeline and wants a single Realtime API to handle both input transcription and response generation.
- Is this permanent or will it be supported before GA?
- Is there an alternative field or event that provides input transcription on alpha?
- What is the intended STT architecture for developers who don't have Zoom SDK or Deepgram?

---

### Effort & Latency

**4. `medium` TTFB consistently faster than `low` — is this expected?**
Our E03 data (confirmed across run_015 and run_017): `medium` avg TTFB 618ms vs `low` 929ms vs `minimal` 909ms. Effort ordering is non-monotonic. This is counterintuitive and affects how we pick effort levels for different turn types.
- Is this a known property of the reasoning architecture, or a snapshot artifact?
- Does the reasoning overhead at `low` create more variance than `medium`'s more structured path?

**5. Per-turn effort override**
The spec mentions `response.create` can override effort per turn. We haven't tested this. For Otto the natural use is: `low` for conversational replies, `high` for complex tool dispatch.
- Confirmed: does `response.create` accept a `reasoning.effort` field that overrides the session default?
- Any latency cost to switching effort mid-session vs setting it at session start?

---

### Preambles

**6. Preamble prompting — how to control content and trigger rate**
We observed preambles inconsistently across runs. At `high` effort on complex prompts there's a delay before response, but explicit preamble audio wasn't always produced. We haven't tested preamble behavior with tool calls specifically (where "let me check that" would be most valuable).
- What prompt pattern reliably triggers preambles before tool dispatch?
- Can preamble content be constrained to specific phrases for brand consistency?
- Is there a way to disable preambles entirely if we don't want them?
- Is the preamble audio cutoff at end syllable (mentioned in spec) fixed before GA?

---

### Params we haven't tested / may have overlooked

**7. Audio input format**
We're sending PCM16 24kHz mono. We haven't tested other formats.
- What audio input formats does alpha accept? Is there a preferred format for quality vs bandwidth?
- Is there an `audio.input.format` field in the session config (analogous to `audio.output.format`)?

**8. `temperature` and `max_response_output_tokens`**
We haven't set these. On 1.5 they're standard.
- Are `temperature` and `max_response_output_tokens` supported on alpha? Do they affect reasoning behavior or only the output phase?

**9. `response.create` with `input` field for injecting context mid-session**
The Realtime API supports adding conversation items before triggering a response. We haven't tested injecting additional context (e.g. a fresh transcript snapshot) via `conversation.item.create` before `response.create`.
- Is this pattern supported on alpha? Any interaction with the reasoning phase?

**10. Cold-connect latency spike on `unknown_parameter` errors**
When alpha rejects `turn_detection`, the `unknown_parameter` error response intermittently takes ~8 seconds instead of the normal 250–600ms. This adds to every fresh session cold start in E07.
- Is this a known issue with error response queuing?
- Any way to pre-validate session config fields without incurring this latency?

