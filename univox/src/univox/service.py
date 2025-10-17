"""Generic Univox STT service for Pipecat.

Accepts any `UnivoxProvider` and exposes a Pipecat `STTService` implementation
that streams audio to the provider and pushes interim/final transcription frames
to the pipeline. Segmentation is expected to be handled by Pipecat VAD.
"""

from __future__ import annotations

from typing import Any, AsyncGenerator, Optional

from loguru import logger

from pipecat.frames.frames import (
    ErrorFrame,
    Frame,
    InterimTranscriptionFrame,
    StartFrame,
    TranscriptionFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.stt_service import STTService
from pipecat.transcriptions.language import Language
from pipecat.utils.time import time_now_iso8601
from pipecat.utils.tracing.service_decorators import traced_stt

from univox.provider import TranscriptEvent, UnivoxCallbacks, UnivoxProvider


class _ServiceCallbacks(UnivoxCallbacks):
    def __init__(self, service: "UnivoxSTTService"):
        self._s = service

    async def on_interim(self, evt: TranscriptEvent) -> None:
        await self._s._handle_interim(evt)

    async def on_final(self, evt: TranscriptEvent) -> None:
        await self._s._handle_final(evt)

    async def on_error(self, error: str) -> None:
        await self._s.push_error(ErrorFrame(error))

    async def on_speech_started(self) -> None:
        # Optionally start metrics here if desired
        pass

    async def on_utterance_end(self) -> None:
        # Optionally stop metrics here if desired
        pass


class UnivoxSTTService(STTService):
    """Pipecat STT service that delegates to a UnivoxProvider.

    Notes:
        - Provider VAD should be disabled; rely on Pipecat VAD events.
        - Sends audio frames to provider; transcripts arrive via callbacks.
    """

    def __init__(self, provider: UnivoxProvider, **kwargs):
        super().__init__(**kwargs)
        self._provider = provider
        self._provider.set_callbacks(_ServiceCallbacks(self))

    def can_generate_metrics(self) -> bool:
        return True

    async def set_model(self, model: str):
        await super().set_model(model)
        logger.info(f"[Univox] Switching STT model to: [{model}]")
        await self._provider.set_model(model)

    async def set_language(self, language: Language):
        logger.info(f"[Univox] Switching STT language to: [{language}]")
        await self._provider.set_language(language)

    async def start(self, frame: StartFrame):
        await super().start(frame)
        await self._provider.start(sample_rate=self.sample_rate)

    async def stop(self, frame: Frame):
        await super().stop(frame)
        await self._provider.stop()

    async def cancel(self, frame: Frame):
        await super().cancel(frame)
        await self._provider.cancel()

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame, None]:
        await self._provider.send_audio(audio)
        yield None

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, UserStartedSpeakingFrame):
            # Metrics could start here when provider VAD is off
            pass
        elif isinstance(frame, UserStoppedSpeakingFrame):
            # Finalize turn on VAD stop
            try:
                await self._provider.finalize_utterance()
            except Exception as e:
                await self.push_error(ErrorFrame(f"Univox finalize error: {e}"))

    # Callback handlers

    async def _handle_interim(self, evt: TranscriptEvent) -> None:
        await self.push_frame(
            InterimTranscriptionFrame(
                evt.text,
                self._user_id,
                time_now_iso8601(),
                evt.language,
                result=evt.provider_payload,
            )
        )

    @traced_stt
    async def _handle_transcription(
        self, transcript: str, is_final: bool, language: Optional[Language] = None
    ):
        pass

    async def _handle_final(self, evt: TranscriptEvent) -> None:
        await self.push_frame(
            TranscriptionFrame(
                evt.text,
                self._user_id,
                time_now_iso8601(),
                evt.language,
                result=evt.provider_payload,
            )
        )
        await self._handle_transcription(evt.text, True, evt.language)
