"""Abstract provider interface for realtime voice API benchmarking."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Turn:
    """A single conversational turn with timing metrics."""

    role: str  # "user" or "assistant"
    text: str
    timestamp: float = field(default_factory=time.time)
    latency_ms: Optional[float] = None  # Time from send to first response token
    full_response_ms: Optional[float] = None  # Time to complete response
    tool_calls: list[dict] = field(default_factory=list)
    raw_events: list[dict] = field(default_factory=list)


@dataclass
class SessionMetrics:
    """Metrics collected over the lifetime of a session."""

    provider: str
    session_id: str
    started_at: float
    ended_at: float = 0.0
    turns: list[Turn] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    errors: list[dict] = field(default_factory=list)
    connection_drops: int = 0
    items_injected: int = 0  # conversation items injected via send_text_no_response


class RealtimeProvider(ABC):
    """Abstract interface for realtime voice API providers.

    Implementations connect via WebSocket and use text-mode injection
    for automated benchmarking (no audio required).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier, e.g. 'openai' or 'grok'."""
        ...

    @abstractmethod
    async def connect(
        self,
        instructions: str,
        tools: list[dict] | None = None,
    ) -> None:
        """Establish WebSocket connection and configure session.

        Args:
            instructions: System prompt for the session.
            tools: Optional tool definitions (JSON Schema function format).
        """
        ...

    @abstractmethod
    async def send_text(self, text: str) -> Turn:
        """Send a user text message and wait for the complete assistant response.

        Flow:
        1. Sends conversation.item.create with input_text content
        2. Sends response.create to trigger generation
        3. Collects all response events until response.done
        4. Measures latency (TTFB and total)

        Returns:
            Turn with assistant's response text and timing metrics.
        """
        ...

    @abstractmethod
    async def send_text_no_response(self, text: str) -> None:
        """Inject a conversation item without triggering a response.

        Used to build up conversation history (e.g., simulating meeting
        dialogue) without waiting for the model to respond to each turn.

        Sends conversation.item.create but does NOT send response.create.
        """
        ...

    @abstractmethod
    async def send_audio(self, pcm16_chunks: list[str], original_text: str) -> Turn:
        """Stream audio chunks and wait for the model's response.

        Simulates a user speaking:
        1. Sends input_audio_buffer.append for each PCM16 base64 chunk
        2. Sends input_audio_buffer.commit to finalize
        3. Sends response.create to trigger model response
        4. Waits for response.done
        5. Returns Turn with response text, latency, and transcription

        Args:
            pcm16_chunks: List of base64-encoded PCM16 audio chunks.
            original_text: The original text (for transcription accuracy comparison).

        Returns:
            Turn with assistant response and timing. The turn's raw_events
            will include the transcription of the input audio.
        """
        ...

    @abstractmethod
    async def send_audio_no_response(self, pcm16_chunks: list[str]) -> None:
        """Stream audio without triggering a model response.

        Like send_text_no_response but with audio — builds conversation
        history via audio input without waiting for a reply.
        """
        ...

    @abstractmethod
    async def handle_tool_call(self, call_id: str, output: str) -> None:
        """Return a tool call result to the API.

        Sends conversation.item.create with function_call_output,
        then sends response.create to let the model continue.
        """
        ...

    @abstractmethod
    async def get_session_metrics(self) -> SessionMetrics:
        """Return accumulated session metrics."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Cleanly close the WebSocket connection."""
        ...

    @abstractmethod
    async def is_connected(self) -> bool:
        """Check if the WebSocket connection is still alive."""
        ...
