"""OpenAI Realtime API provider — gpt-realtime-2 alpha (reasoning model).

Differences from openai_realtime.py:
- No OpenAI-Beta header (alpha reasoning models reject it)
- reasoning.effort session parameter (minimal/low/medium/high)
- session.type must be "realtime"
- output_modalities replaces modalities; audio config is nested under audio.output
- phase-aware listener: separates commentary (preambles) from final_answer
- VAD-resilient audio sending: alpha defaults to server VAD; explicit commit is
  skipped if VAD already committed the buffer

Configure via env vars:
  OPENAI_REALTIME_MODEL   — defaults to gpt-realtime-alpha-dolphin-6
  OPENAI_REASONING_EFFORT — defaults to low (minimal/low/medium/high)
"""

from __future__ import annotations

import asyncio
import json
import os
import time

import websockets

from common.config import get_openai_api_key, setup_logging
from common.provider import Turn
from providers.openai_realtime import OpenAIRealtimeProvider

logger = setup_logging("providers.openai_alpha")

_DEFAULT_MODEL = "gpt-realtime-alpha-dolphin-6"
_VALID_EFFORTS = {"minimal", "low", "medium", "high"}

# Errors that should NOT unblock response waiters — they're transient audio
# buffer issues caused by server VAD auto-committing before our explicit commit.
_IGNORABLE_ERRORS = {
    "input_audio_buffer_commit_empty",
    "input_audio_buffer_committed",
    # VAD already triggered a response before our explicit response.create;
    # that response IS the one we want — just wait for it to complete.
    "conversation_already_has_active_response",
    # response.cancel when nothing is in-flight — alpha returns this code;
    # 1.5 returned "response_not_found" / "response_cancel_inactive".
    # In E07 (fresh session per question), no response is ever active before
    # send_audio() fires, so this fires on every question. Benign.
    "response_not_found",
    "response_cancel_inactive",
    "response_cancel_not_active",
}


def _get_reasoning_effort() -> str:
    effort = os.getenv("OPENAI_REASONING_EFFORT", "low")
    if effort not in _VALID_EFFORTS:
        raise ValueError(
            f"OPENAI_REASONING_EFFORT={effort!r} is invalid. "
            f"Must be one of: {', '.join(sorted(_VALID_EFFORTS))}"
        )
    return effort


class OpenAIRealtimeAlphaProvider(OpenAIRealtimeProvider):
    """Provider for gpt-realtime-2 alpha (reasoning model).

    Inherits all experiment logic from OpenAIRealtimeProvider; overrides
    connect(), audio methods, and _listen() for alpha API differences.
    """

    def __init__(self, model: str | None = None, reasoning_effort: str | None = None):
        super().__init__(model=model or os.getenv("OPENAI_REALTIME_MODEL", _DEFAULT_MODEL))
        self._reasoning_effort = reasoning_effort or _get_reasoning_effort()
        self._commentary_text = ""
        self._item_phases: dict[str, str] = {}  # item_id -> "commentary" | "final_answer"
        self._vad_active = True  # assume VAD on until session confirms otherwise
        self._transcription_supported: bool | None = None  # None = not yet known

    @property
    def name(self) -> str:
        return f"openai-alpha[{self._reasoning_effort}]"

    async def connect(
        self,
        instructions: str,
        tools: list[dict] | None = None,
    ) -> None:
        api_key = get_openai_api_key()
        url = f"wss://api.openai.com/v1/realtime?model={self._model}"
        # Alpha reasoning models do NOT accept the OpenAI-Beta header
        headers = {"Authorization": f"Bearer {api_key}"}

        logger.info(
            "Connecting to OpenAI Realtime alpha (%s, reasoning=%s)…",
            self._model,
            self._reasoning_effort,
        )
        self._ws = await websockets.connect(
            url,
            additional_headers=headers,
            max_size=16 * 1024 * 1024,
            ping_interval=20,
            ping_timeout=10,
        )
        self._metrics.started_at = time.time()

        session_config: dict = {
            "type": "session.update",
            "session": {
                "type": "realtime",
                "model": self._model,
                "instructions": instructions,
                "output_modalities": ["audio"],
                "audio": {
                    "output": {
                        "format": {"type": "audio/pcm", "rate": 24000},
                        "voice": "alloy",
                    },
                },
                # Attempt to disable server VAD. Alpha may reject this field;
                # if so, we fall back to VAD-resilient audio methods below.
                "turn_detection": {"type": "none"},
                "reasoning": {"effort": self._reasoning_effort},
                # Request input audio transcription. Alpha may reject this field;
                # if rejected we skip the transcription wait in send_audio_no_response.
                "input_audio_transcription": {"model": "whisper-1"},
            },
        }
        if tools:
            session_config["session"]["tools"] = tools
            session_config["session"]["tool_choice"] = "auto"

        await self._ws.send(json.dumps(session_config))

        while True:
            raw = await self._ws.recv()
            event = json.loads(raw)
            etype = event.get("type", "")

            if etype == "session.updated":
                confirmed_model = event.get("session", {}).get("model", "?")
                confirmed_effort = (
                    event.get("session", {}).get("reasoning", {}).get("effort", "?")
                )
                # Only update _vad_active if we haven't already set it via an
                # error path (e.g. turn_detection rejection already set it True).
                # session.updated after a failed turn_detection retry omits the
                # field entirely (td=None), which must NOT be read as VAD=off.
                if not self._vad_active:
                    td = event.get("session", {}).get("turn_detection")
                    if td is not None and not (isinstance(td, dict) and td.get("type") == "none"):
                        self._vad_active = True
                # Confirm whether input_audio_transcription was accepted.
                # Only set if still unknown (rejection path sets it to False already).
                if self._transcription_supported is None:
                    iat = event.get("session", {}).get("input_audio_transcription")
                    self._transcription_supported = iat is not None
                logger.info(
                    "Session confirmed — model=%s, reasoning=%s, VAD=%s, transcription=%s",
                    confirmed_model, confirmed_effort,
                    "active" if self._vad_active else "disabled",
                    "supported" if self._transcription_supported else "NOT supported (server rejected)",
                )
                break

            if etype == "error":
                err_code = event.get("error", {}).get("code", "")
                err_param = event.get("error", {}).get("param", "")
                if err_code == "unknown_parameter" and "turn_detection" in err_param:
                    logger.warning(
                        "Alpha rejected turn_detection — server VAD will be active."
                    )
                    self._vad_active = True
                    del session_config["session"]["turn_detection"]
                    await self._ws.send(json.dumps(session_config))
                    continue
                if err_code == "unknown_parameter" and "input_audio_transcription" in err_param:
                    # Server-side rejection confirmed — not a code bug.
                    logger.warning(
                        "Alpha rejected input_audio_transcription (server-side) — "
                        "transcription unavailable; E07 will use original text fallback."
                    )
                    self._transcription_supported = False
                    del session_config["session"]["input_audio_transcription"]
                    await self._ws.send(json.dumps(session_config))
                    continue
                raise RuntimeError(f"OpenAI alpha session error: {event}")

        self._listener_task = asyncio.create_task(self._listen())

    # -- Text / tool overrides (response.create with no modalities field) ------

    async def send_text(self, text: str) -> Turn:
        """Send text and trigger an audio-only response."""
        assert self._ws

        self._response_text = ""
        self._first_token_time = None
        self._current_tool_calls = []
        self._response_done.clear()

        t0 = time.monotonic()

        await self._ws.send(json.dumps({
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            },
        }))
        await self._ws.send(json.dumps({"type": "response.create"}))

        try:
            await asyncio.wait_for(self._response_done.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            logger.warning("Response timed out after 30s")

        t_done = time.monotonic()
        ttfb = (self._first_token_time - t0) * 1000 if self._first_token_time else None
        total_ms = (t_done - t0) * 1000

        turn = Turn(
            role="assistant",
            text=self._response_text,
            latency_ms=ttfb,
            full_response_ms=total_ms,
            tool_calls=list(self._current_tool_calls),
        )
        self._metrics.turns.append(turn)
        return turn

    async def handle_tool_call(self, call_id: str, output: str) -> None:
        """Return tool result and wait for audio-only follow-up response."""
        assert self._ws

        self._response_text = ""
        self._first_token_time = None
        self._current_tool_calls = []
        self._response_done.clear()

        await self._ws.send(json.dumps({
            "type": "conversation.item.create",
            "item": {
                "type": "function_call_output",
                "call_id": call_id,
                "output": output,
            },
        }))
        await self._ws.send(json.dumps({"type": "response.create"}))

        try:
            await asyncio.wait_for(self._response_done.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            logger.warning("Response timed out after 30s")

    # -- Audio overrides (VAD-resilient) ----------------------------------------

    async def _commit_audio(self) -> bool:
        """Commit the audio buffer. Returns True if buffer had content.

        With server VAD active, the buffer may already be empty because VAD
        auto-committed it. We send the commit anyway and let the listener
        swallow the resulting error — caller should proceed to wait for the
        VAD-triggered response regardless.
        """
        assert self._ws
        await self._ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
        return True  # optimistically assume content; errors handled in listener

    async def send_audio(self, pcm16_chunks: list[str], original_text: str) -> Turn:
        """Stream audio and collect the response (VAD-resilient).

        With VAD active: VAD auto-commits the buffer and auto-creates a
        response. We still send an explicit commit + response.create as a
        fallback for the case VAD didn't fire; the listener ignores the
        resulting empty-buffer / already-active-response errors.

        We cancel any in-flight VAD response from previous audio (e.g.
        trailing meeting audio in E06) before streaming the question.
        """
        assert self._ws

        # Cancel any lingering VAD response from preceding audio so it
        # doesn't race with the question response.
        await self._ws.send(json.dumps({"type": "response.cancel"}))
        await asyncio.sleep(0.1)

        self._response_text = ""
        self._audio_transcript = ""
        self._first_token_time = None
        self._current_tool_calls = []
        self._input_transcript = ""
        self._response_done.clear()

        t0 = time.monotonic()

        for chunk in pcm16_chunks:
            await self._ws.send(json.dumps({
                "type": "input_audio_buffer.append",
                "audio": chunk,
            }))
            await asyncio.sleep(0.1)

        # Explicit commit + response.create — errors are swallowed by listener
        # if VAD already handled them.
        await self._commit_audio()
        await self._ws.send(json.dumps({"type": "response.create"}))

        try:
            await asyncio.wait_for(self._response_done.wait(), timeout=60.0)
        except asyncio.TimeoutError:
            logger.warning("Audio response timed out after 60s")

        t_done = time.monotonic()
        ttfb = (self._first_token_time - t0) * 1000 if self._first_token_time else None
        total_ms = (t_done - t0) * 1000

        turn = Turn(
            role="assistant",
            text=self._response_text,
            latency_ms=ttfb,
            full_response_ms=total_ms,
            tool_calls=list(self._current_tool_calls),
            raw_events=[{
                "input_transcript": getattr(self, "_input_transcript", ""),
                "original_text": original_text,
            }],
        )
        self._metrics.turns.append(turn)
        return turn

    async def send_audio_no_response(self, pcm16_chunks: list[str]) -> None:
        """Stream audio for context accumulation only (no response expected).

        With VAD active, each audio segment may trigger an auto-response.
        We commit the buffer, then wait briefly for any auto-response to
        complete so the session stays clean before the next audio segment.
        """
        assert self._ws

        self._input_transcript = ""
        self._transcription_done.clear()
        # Arm _response_done so we can drain any VAD-triggered response
        self._response_done.clear()

        for chunk in pcm16_chunks:
            await self._ws.send(json.dumps({
                "type": "input_audio_buffer.append",
                "audio": chunk,
            }))
            await asyncio.sleep(0.1)

        await self._commit_audio()

        # Wait for transcription only if the server confirmed support during connect().
        # If rejected (server-side), skip entirely — original text fallback is used.
        if self._transcription_supported:
            try:
                await asyncio.wait_for(self._transcription_done.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                pass

        # If VAD triggered a response, drain it so it doesn't interfere with
        # subsequent calls. Short timeout — we don't want to block the meeting stream.
        if self._vad_active:
            try:
                await asyncio.wait_for(self._response_done.wait(), timeout=8.0)
            except asyncio.TimeoutError:
                pass  # no response came, that's fine

        self._metrics.items_injected += 1

    # -- Phase-aware listener ---------------------------------------------------

    async def _listen(self) -> None:
        """Background listener for gpt-realtime-2 alpha responses.

        Key differences from base class:
        - Tracks item phase (commentary vs final_answer); only final_answer
          content is used as the Turn result.
        - Ignorable errors (empty buffer, already-active response) are logged
          but do NOT unblock response waiters — this prevents cascading failures
          when VAD races with explicit commits.
        """
        assert self._ws
        self._audio_transcript = ""
        self._commentary_text = ""
        self._item_phases = {}

        try:
            async for raw in self._ws:
                event = json.loads(raw)
                etype = event.get("type", "")

                if etype == "response.output_item.added":
                    item = event.get("item", {})
                    item_id = item.get("id", "")
                    phase = item.get("phase", "final_answer")
                    if item_id:
                        self._item_phases[item_id] = phase
                    if phase == "commentary":
                        logger.debug("Preamble item started: %s", item_id)

                elif etype == "response.text.delta":
                    item_id = event.get("item_id", "")
                    phase = self._item_phases.get(item_id, "final_answer")
                    delta = event.get("delta", "")
                    if phase == "final_answer":
                        if self._first_token_time is None:
                            self._first_token_time = time.monotonic()
                        self._response_text += delta
                    else:
                        self._commentary_text += delta

                elif etype == "response.text.done":
                    item_id = event.get("item_id", "")
                    phase = self._item_phases.get(item_id, "final_answer")
                    if phase == "final_answer":
                        self._response_text = event.get("text", self._response_text)
                    else:
                        commentary = event.get("text", self._commentary_text)
                        logger.info("Preamble: %r", commentary)
                        self._commentary_text = commentary

                elif etype in (
                    "response.output_audio_transcript.delta",
                    "response.audio_transcript.delta",
                ):
                    item_id = event.get("item_id", "")
                    phase = self._item_phases.get(item_id, "final_answer")
                    if phase == "final_answer":
                        if self._first_token_time is None:
                            self._first_token_time = time.monotonic()
                        self._audio_transcript += event.get("delta", "")

                elif etype in (
                    "response.output_audio_transcript.done",
                    "response.audio_transcript.done",
                ):
                    item_id = event.get("item_id", "")
                    phase = self._item_phases.get(item_id, "final_answer")
                    if phase == "final_answer":
                        self._audio_transcript = event.get(
                            "transcript", self._audio_transcript
                        )

                elif etype in (
                    "conversation.item.input_audio_transcription.completed",
                    "conversation.item.input_audio_transcription.done",
                ):
                    self._input_transcript = event.get(
                        "transcript", event.get("text", "")
                    )
                    self._transcription_done.set()

                elif etype == "response.function_call_arguments.done":
                    self._current_tool_calls.append({
                        "name": event.get("name"),
                        "call_id": event.get("call_id"),
                        "arguments": event.get("arguments"),
                    })

                elif etype == "response.done":
                    if len(self._audio_transcript) > len(self._response_text):
                        self._response_text = self._audio_transcript
                    self._audio_transcript = ""
                    self._item_phases = {}

                    usage = event.get("response", {}).get("usage", {})
                    if usage:
                        self._metrics.total_input_tokens += usage.get("input_tokens", 0)
                        self._metrics.total_output_tokens += usage.get("output_tokens", 0)
                    self._response_done.set()

                elif etype == "error":
                    err_code = event.get("error", {}).get("code", "")
                    if err_code in _IGNORABLE_ERRORS:
                        # VAD race — buffer was auto-committed before our
                        # explicit commit, or a response was already in flight.
                        # Log at debug level and do NOT unblock waiters.
                        logger.debug("Ignored VAD race error: %s", err_code)
                    else:
                        logger.error("OpenAI alpha error: %s", event)
                        self._metrics.errors.append(event)
                        self._response_done.set()

        except websockets.ConnectionClosed as e:
            logger.warning("OpenAI alpha WebSocket closed: %s", e)
            self._metrics.connection_drops += 1
            self._response_done.set()
        except asyncio.CancelledError:
            pass
