# Zoom Voice Gateway — Architecture, Mental Model & Required Changes

| | |
|---|---|
| **Date** | 2026-04-21 |
| **Branch** | feature/zoom-voice-to-voice-demo |
| **Status** | Architecture changes required before shipping |

**READ THIS BEFORE TOUCHING ANY CODE IN THIS SERVICE.**

---

## Mental Model

Otto is a meeting assistant. People are in a Zoom call. At any point a participant says **"Hey Otto"** to ask a question. Otto answers — either directly or by delegating to the Otto AI agent. That's it.

**Otto is NOT a passive listener that responds whenever it wants. It wakes up on demand.**

---

## Correct Architecture (E07 — fresh session per question)

```
Zoom SDK raw audio (always flowing)
    │
    ├─► Zoom live transcription (or Deepgram) → running text transcript
    │
    └─► Wake word detector
            │
            on "Hey Otto":
            ├── snapshot current transcript
            ├── open FRESH RealtimeVoiceSession(transcript=snapshot)
            ├── send question audio
            ├── model answers OR calls ask_otto(question, transcript)
            └── close session → transcript continues accumulating
```

**One persistent session for the whole meeting = wrong.** That is E06:
- VAD fires on every participant's speech — Otto responds to random conversation
- Sessions hit the 60-min API cap mid-meeting
- Model has no structured transcript — just a raw audio buffer
- `ask_otto` gets a bare question with no meeting context so Otto can't recall anything

---

## What ask_otto needs

Questions like "Hey Otto, what did we decide about Meridian?" require the meeting transcript. If `ask_otto` only receives `{"message": q}`, Otto has no way to answer. It must receive `{"message": q, "context": transcript}`.

---

## What the current code (feature/zoom-voice-to-voice-demo) gets wrong

| Requirement | Current state |
|---|---|
| Wake word gate | `input_enabled = True` always — all audio flows to Realtime |
| Fresh session per question | One persistent session for entire meeting |
| Transcript accumulation | No transcript pipeline |
| Transcript injection | `SYSTEM_INSTRUCTIONS` has no transcript |
| ask_otto context | `{"message": q}` only |
| VAD | `semantic_vad` fires on all participant speech |

---

## Required Changes

### `state.py`

```python
class BotState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.output_muted: bool = False
        self.input_enabled: bool = False       # False by default — only True during a Hey Otto session
        self._transcript: list[str] = []
        self._drain_output: Callable[[], None] | None = None

    def append_transcript(self, speaker: str, text: str) -> None:
        with self._lock:
            self._transcript.append(f"[{speaker}]: {text}")

    def get_transcript_snapshot(self) -> list[str]:
        with self._lock:
            return list(self._transcript)
```

### `realtime_session.py`

Accept transcript at construction. Inject into system prompt. Close after each answer.

```python
class RealtimeVoiceSession:
    def __init__(self, settings, state, on_output_pcm16_24k, transcript=None, on_speech_started=None):
        self._transcript = transcript or []
        # ... rest unchanged

def _send_session_update(self) -> None:
    transcript_text = "\n".join(self._transcript) if self._transcript else "(no transcript yet)"
    instructions = (
        "You are Otto, an AI meeting assistant in a live Zoom call. "
        "A participant just said 'Hey Otto' to ask you a question. "
        "Answer based on the meeting transcript below if relevant. "
        "For questions requiring Otto's tools or integrations, call ask_otto. "
        "Keep answers conversational and brief.\n\n"
        "=== MEETING TRANSCRIPT ===\n"
        f"{transcript_text}\n"
        "=== END TRANSCRIPT ==="
    )

# Close after response.done
elif et == "response.done":
    self._maybe_handle_function_calls(event)
    self._state.set_input_enabled(False)
    threading.Timer(1.0, self.close).start()
```

If using gpt-realtime-alpha-dolphin-6: add a silence pad between `commentary` and `final_answer` audio phases (known OpenAI issue pre-GA).

### `otto_tool.py`

```python
def ask_otto(question, settings, transcript=None):
    payload = {"message": question.strip()}
    if transcript:
        payload["context"] = "\n".join(transcript)
    # ... rest unchanged
```

In `realtime_session.py`: `ask_otto(question, self._settings, transcript=self._transcript)`

### `sdk_runner.py`

Wire Zoom live transcription and wake word detection:

```python
# In _on_join:
self.transcription_ctrl = self.meeting_service.GetMeetingLiveTranscriptionController()
self.transcription_event = zoom.MeetingLiveTranscriptionEventCallbacks(
    onLiveTranscriptionMsgReceivedCallback=self._on_transcript,
)
self.transcription_ctrl.SetEvent(self.transcription_event)
self.transcription_ctrl.RequestToStartLiveTranscription()

# New callbacks:
def _on_transcript(self, user_id, text, is_final):
    speaker = self._get_participant_name(user_id)
    if is_final:
        self._state.append_transcript(speaker, text)
        if "hey otto" in text.lower() and not self._state.input_enabled:
            self._trigger_hey_otto()

def _trigger_hey_otto(self):
    transcript_snapshot = self._state.get_transcript_snapshot()
    self._state.set_input_enabled(True)
    session = RealtimeVoiceSession(
        self._settings, self._state, self.push_pcm16_24k_from_model,
        transcript=transcript_snapshot, on_speech_started=self._on_speech_started,
    )
    session.connect_background()
    if not session.wait_ready(30):
        self._state.set_input_enabled(False)
        return
    self.session = session
```

If Zoom live transcription is unavailable, use Deepgram on the mixed audio channel. Do NOT use the OpenAI Realtime API for STT — it rejects `input_audio_transcription` (server-side, confirmed).

### `runner.py`

Remove the persistent `RealtimeVoiceSession` instantiation at startup. Sessions are created by `_trigger_hey_otto` on demand.

---

## What to keep unchanged

- Audio capture pipeline (`_on_mixed_audio`, resampling) — correct, keep it
- Virtual mic output pipeline — correct, keep it
- `join_http_server.py`, Zoom SDK auth/join/leave — keep as-is
- `otto_tool.py` HTTP structure — only add `context` to payload

---

## Ship criteria

1. Bot joins meeting, no one speaks → Otto says nothing
2. "Hey Otto, what's on the agenda?" → Otto answers from transcript
3. "Hey Otto, what did Alice decide about Meridian?" → Otto answers from transcript or delegates to ask_otto with transcript context
4. 5 questions in one meeting → each opens and closes a fresh session, meeting stays connected
5. 90-minute meeting → bot stays alive (60-min cap irrelevant for short question sessions)
