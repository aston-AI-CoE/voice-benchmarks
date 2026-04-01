"""OpenAI Realtime API provider — direct WebSocket, text-only mode."""

from __future__ import annotations

import asyncio
import json
import time
import uuid

import websockets

from common.config import get_openai_api_key, get_openai_model, setup_logging
from common.provider import RealtimeProvider, SessionMetrics, Turn

logger = setup_logging("providers.openai")


class OpenAIRealtimeProvider(RealtimeProvider):
    """Connects to OpenAI Realtime via direct WebSocket (no WebRTC needed).

    Uses text-only modality for benchmarking — same context window behaviour
    as audio mode but skips TTS generation for speed.
    """

    def __init__(self, model: str | None = None):
        self._model = model or get_openai_model()
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._session_id = str(uuid.uuid4())
        self._metrics = SessionMetrics(
            provider="openai",
            session_id=self._session_id,
            started_at=0.0,
        )
        self._response_text = ""
        self._response_done = asyncio.Event()
        self._transcription_done = asyncio.Event()
        self._first_token_time: float | None = None
        self._current_tool_calls: list[dict] = []
        self._input_transcript = ""
        self._listener_task: asyncio.Task | None = None

    # -- ABC properties / methods ------------------------------------------

    @property
    def name(self) -> str:
        return "openai"

    async def connect(
        self,
        instructions: str,
        tools: list[dict] | None = None,
    ) -> None:
        api_key = get_openai_api_key()
        url = f"wss://api.openai.com/v1/realtime?model={self._model}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "OpenAI-Beta": "realtime=v1",
        }

        logger.info("Connecting to OpenAI Realtime (%s)…", self._model)
        self._ws = await websockets.connect(
            url,
            additional_headers=headers,
            max_size=16 * 1024 * 1024,
            ping_interval=20,   # send WebSocket ping every 20s to prevent idle timeout
            ping_timeout=10,
        )
        self._metrics.started_at = time.time()

        # Configure session — text+audio for fair comparison with Grok
        # (Grok requires audio modality to avoid truncation, so we match)
        session_config: dict = {
            "type": "session.update",
            "session": {
                "instructions": instructions,
                "modalities": ["text", "audio"],
                "voice": "alloy",
                "turn_detection": None,  # disable VAD — we control turns
                "input_audio_transcription": {"model": "whisper-1"},
            },
        }
        if tools:
            session_config["session"]["tools"] = tools
            session_config["session"]["tool_choice"] = "auto"

        await self._ws.send(json.dumps(session_config))

        # Wait for session.updated confirmation
        while True:
            raw = await self._ws.recv()
            event = json.loads(raw)
            if event.get("type") == "session.updated":
                logger.info("Session configured (id=%s)", self._session_id)
                break
            if event.get("type") == "error":
                raise RuntimeError(f"OpenAI session error: {event}")

        # Start background listener
        self._listener_task = asyncio.create_task(self._listen())

    async def send_text(self, text: str) -> Turn:
        assert self._ws, "Not connected"

        # Reset state
        self._response_text = ""
        self._first_token_time = None
        self._current_tool_calls = []
        self._response_done.clear()

        t0 = time.monotonic()

        # Inject user message
        await self._ws.send(json.dumps({
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            },
        }))

        # Trigger response generation (text only)
        await self._ws.send(json.dumps({
            "type": "response.create",
            "response": {"modalities": ["text", "audio"]},
        }))

        # Wait for response.done
        try:
            await asyncio.wait_for(self._response_done.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            logger.warning("Response timed out after 30s")

        t_done = time.monotonic()
        ttfb = (
            (self._first_token_time - t0) * 1000
            if self._first_token_time
            else None
        )
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

    async def send_text_no_response(self, text: str) -> None:
        assert self._ws, "Not connected"
        await self._ws.send(json.dumps({
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            },
        }))
        self._metrics.items_injected += 1

    async def send_audio(self, pcm16_chunks: list[str], original_text: str) -> Turn:
        assert self._ws, "Not connected"
        import asyncio as _asyncio

        self._response_text = ""
        self._audio_transcript = ""
        self._first_token_time = None
        self._current_tool_calls = []
        self._input_transcript = ""
        self._response_done.clear()

        t0 = time.monotonic()

        # Stream audio chunks
        for chunk in pcm16_chunks:
            await self._ws.send(json.dumps({
                "type": "input_audio_buffer.append",
                "audio": chunk,
            }))
            # Pace at roughly real-time (100ms per chunk)
            await _asyncio.sleep(0.1)

        # Commit the audio buffer
        await self._ws.send(json.dumps({
            "type": "input_audio_buffer.commit",
        }))

        # Trigger response
        await self._ws.send(json.dumps({
            "type": "response.create",
            "response": {"modalities": ["text", "audio"]},
        }))

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
            raw_events=[{
                "input_transcript": getattr(self, "_input_transcript", ""),
                "original_text": original_text,
            }],
        )
        self._metrics.turns.append(turn)
        return turn

    async def send_audio_no_response(self, pcm16_chunks: list[str]) -> None:
        assert self._ws, "Not connected"

        # Reset transcription state
        self._input_transcript = ""
        self._transcription_done.clear()

        for chunk in pcm16_chunks:
            await self._ws.send(json.dumps({
                "type": "input_audio_buffer.append",
                "audio": chunk,
            }))
            await asyncio.sleep(0.1)

        await self._ws.send(json.dumps({
            "type": "input_audio_buffer.commit",
        }))

        # Wait for the API to transcribe (with timeout)
        try:
            await asyncio.wait_for(self._transcription_done.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.debug("Transcription timeout — API may not have transcription enabled")

        self._metrics.items_injected += 1

    async def handle_tool_call(self, call_id: str, output: str) -> None:
        """Return tool result and wait for the model's follow-up response to complete."""
        assert self._ws, "Not connected"

        # Reset response state so we can wait for the follow-up
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
        await self._ws.send(json.dumps({
            "type": "response.create",
            "response": {"modalities": ["text", "audio"]},
        }))

        # Wait for the model to finish responding to the tool result
        try:
            await asyncio.wait_for(self._response_done.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            logger.warning("Response timed out after 30s")

    async def get_session_metrics(self) -> SessionMetrics:
        self._metrics.ended_at = time.time()
        return self._metrics

    async def disconnect(self) -> None:
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        if self._ws:
            await self._ws.close()
            self._ws = None
        self._metrics.ended_at = time.time()
        logger.info("Disconnected from OpenAI Realtime")

    async def is_connected(self) -> bool:
        if self._ws is None:
            return False
        try:
            from websockets.protocol import State
            return self._ws.state is State.OPEN
        except (ImportError, AttributeError):
            return getattr(self._ws, "open", False)

    # -- Internal listener -------------------------------------------------

    async def _listen(self) -> None:
        """Background task that processes all incoming WebSocket events.

        Handles both text and audio transcript events since we request
        modalities=["text","audio"] for fair comparison with Grok.
        """
        assert self._ws
        self._audio_transcript = ""
        try:
            async for raw in self._ws:
                event = json.loads(raw)
                etype = event.get("type", "")

                # Text stream events
                if etype == "response.text.delta":
                    if self._first_token_time is None:
                        self._first_token_time = time.monotonic()
                    self._response_text += event.get("delta", "")

                elif etype == "response.text.done":
                    self._response_text = event.get("text", self._response_text)

                # Audio transcript events
                elif etype in (
                    "response.output_audio_transcript.delta",
                    "response.audio_transcript.delta",
                ):
                    if self._first_token_time is None:
                        self._first_token_time = time.monotonic()
                    self._audio_transcript += event.get("delta", "")

                elif etype in (
                    "response.output_audio_transcript.done",
                    "response.audio_transcript.done",
                ):
                    self._audio_transcript = event.get(
                        "transcript", self._audio_transcript
                    )

                # Input audio transcription (what the user said)
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
                    # Prefer whichever transcript is more complete
                    if len(self._audio_transcript) > len(self._response_text):
                        self._response_text = self._audio_transcript
                    self._audio_transcript = ""

                    # Check for usage stats if available
                    usage = event.get("response", {}).get("usage", {})
                    if usage:
                        self._metrics.total_input_tokens += usage.get(
                            "input_tokens", 0
                        )
                        self._metrics.total_output_tokens += usage.get(
                            "output_tokens", 0
                        )
                    self._response_done.set()

                elif etype == "error":
                    logger.error("OpenAI error: %s", event)
                    self._metrics.errors.append(event)
                    self._response_done.set()  # unblock any waiters

        except websockets.ConnectionClosed as e:
            logger.warning("OpenAI WebSocket closed: %s", e)
            self._metrics.connection_drops += 1
            self._response_done.set()
        except asyncio.CancelledError:
            pass
