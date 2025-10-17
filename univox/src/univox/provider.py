"""Provider-agnostic interface for Univox STT engines.

Defines a minimal async contract a streaming STT provider must implement
to interoperate with `UnivoxSTTService`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Protocol

from pipecat.transcriptions.language import Language


@dataclass
class TranscriptEvent:
    text: str
    is_final: bool
    language: Optional[Language] = None
    provider_payload: Any = None


class UnivoxCallbacks(Protocol):
    async def on_interim(self, evt: TranscriptEvent) -> None: ...
    async def on_final(self, evt: TranscriptEvent) -> None: ...
    async def on_error(self, error: str) -> None: ...
    async def on_speech_started(self) -> None: ...
    async def on_utterance_end(self) -> None: ...


class UnivoxProvider(Protocol):
    """Protocol for a streaming STT provider."""

    def set_callbacks(self, cb: UnivoxCallbacks) -> None: ...

    async def start(self, *, sample_rate: int) -> None: ...
    async def stop(self) -> None: ...
    async def cancel(self) -> None: ...

    async def send_audio(self, audio: bytes) -> None: ...
    async def finalize_utterance(self) -> None: ...

    async def set_language(self, language: Language) -> None: ...
    async def set_model(self, model: str) -> None: ...

