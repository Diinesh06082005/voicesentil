"""
Audio & Text Stream Buffer Manager for Real-Time Token Processing and Guardrail Interception.
Manages rolling token queue between LLM output generator and TTS audio synthesis stream.
"""

from typing import Dict, Any, Generator, AsyncGenerator, Iterable, AsyncIterable, List, Optional
from .guardrail import InFlightGuardrail, VoiceGuardrailEngine


class StreamBufferManager:
    """
    Manages rolling token queue between LLM generator and TTS synthesis stream.
    Evaluates every token using InFlightGuardrail.
    """

    def __init__(self, guardrail: Optional[InFlightGuardrail] = None, window_size: int = 3):
        if guardrail is None:
            guardrail = InFlightGuardrail()
        self.guardrail = guardrail
        self.window_size = window_size
        self.buffer: List[str] = []
        self.accumulated_text: str = ""

    def reset(self) -> None:
        """Resets the rolling buffer and accumulated text state."""
        self.buffer.clear()
        self.accumulated_text = ""

    async def process_stream_async(
        self,
        token_generator: AsyncIterable[str] | Iterable[str],
        customer_input: str = ""
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Asynchronously processes tokens from generator through rolling buffer and guardrail.

        Yields:
            dict with type 'AUDIO_TOKEN_FLUSH' or 'GUARDRAIL_INTERCEPTION'
        """
        self.reset()

        if hasattr(token_generator, "__aiter__"):
            async for token in token_generator:
                for event in self._handle_token(token, customer_input):
                    yield event
                    if event["type"] == "GUARDRAIL_INTERCEPTION":
                        return
        else:
            for token in token_generator:
                for event in self._handle_token(token, customer_input):
                    yield event
                    if event["type"] == "GUARDRAIL_INTERCEPTION":
                        return

        # Flush remaining safe tokens in buffer after stream ends
        while self.buffer:
            popped_token = self.buffer.pop(0)
            yield {
                "type": "AUDIO_TOKEN_FLUSH",
                "token": popped_token,
                "accumulated_text": self.accumulated_text,
                "latency_ms": 0.0
            }

    def process_stream_sync(
        self,
        token_generator: Iterable[str],
        customer_input: str = ""
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Synchronously processes tokens from generator through rolling buffer and guardrail.

        Yields:
            dict with type 'AUDIO_TOKEN_FLUSH' or 'GUARDRAIL_INTERCEPTION'
        """
        self.reset()

        for token in token_generator:
            events = self._handle_token(token, customer_input)
            for event in events:
                yield event
                if event["type"] == "GUARDRAIL_INTERCEPTION":
                    return

        # Flush remaining safe tokens in buffer after stream ends
        while self.buffer:
            popped_token = self.buffer.pop(0)
            yield {
                "type": "AUDIO_TOKEN_FLUSH",
                "token": popped_token,
                "accumulated_text": self.accumulated_text,
                "latency_ms": 0.0
            }

    def _handle_token(self, token: str, customer_input: str) -> List[Dict[str, Any]]:
        events = []

        # Evaluate token chunk with InFlightGuardrail
        inspection = self.guardrail.inspect_token_stream(
            current_chunk=token,
            accumulated_text=self.accumulated_text,
            customer_input=customer_input
        )

        if inspection["status"] == "VIOLATION":
            # Immediately truncate remaining tokens and return interception event
            events.append({
                "type": "GUARDRAIL_INTERCEPTION",
                "policy_id": inspection["policy_id"],
                "policy_name": inspection["policy_name"],
                "severity": inspection["severity"],
                "action": inspection["action"],
                "fallback_text": inspection["fallback_text"],
                "audio_payload": inspection["fallback_text"],
                "latency_ms": inspection["latency_ms"],
                "confidence_score": inspection["confidence_score"]
            })
            return events

        # If safe, append to rolling buffer
        self.buffer.append(token)
        self.accumulated_text = (f"{self.accumulated_text} {token}").strip()

        # When rolling buffer reaches/exceeds window_size, pop oldest token & flush for TTS
        if len(self.buffer) >= self.window_size:
            popped_token = self.buffer.pop(0)
            events.append({
                "type": "AUDIO_TOKEN_FLUSH",
                "token": popped_token,
                "accumulated_text": self.accumulated_text,
                "latency_ms": inspection["latency_ms"]
            })

        return events


class AudioStreamBuffer:
    """Legacy helper class maintained for backward compatibility."""
    def __init__(self, buffer_size_ms: int = 500, sample_rate: int = 16000):
        self.buffer_size_ms = buffer_size_ms
        self.sample_rate = sample_rate
        self.audio_chunks: List[bytes] = []
        self.text_chunks: List[str] = []

    def push_audio(self, chunk: bytes) -> None:
        self.audio_chunks.append(chunk)

    def push_text(self, text: str) -> None:
        self.text_chunks.append(text)

    def get_sliding_window_text(self, max_words: int = 50) -> str:
        full_text = " ".join(self.text_chunks)
        words = full_text.split()
        return " ".join(words[-max_words:])

    def clear(self) -> None:
        self.audio_chunks.clear()
        self.text_chunks.clear()
