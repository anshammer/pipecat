"""Deepgram provider for Univox.

Minimal wrapper around Deepgram's websocket streaming client that adheres to
the `UnivoxProvider` protocol. Provider-side VAD should be disabled; rely on
Pipecat-side VAD/segmentation.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from loguru import logger

from pipecat.transcriptions.language import Language

from univox.provider import TranscriptEvent, UnivoxCallbacks, UnivoxProvider

try:
    from deepgram import (  # type: ignore
        AsyncListenWebSocketClient,
        DeepgramClient,
        DeepgramClientOptions,
        ErrorResponse,
        LiveOptions,
        LiveResultResponse,
        LiveTranscriptionEvents,
    )
except ModuleNotFoundError as e:  # pragma: no cover - optional dependency
    logger.error(f"Exception: {e}")
    logger.error(
        "Install Deepgram extras to use this provider: 'pip install pipecat-ai[deepgram]'"
    )
    raise


class DeepgramProvider(UnivoxProvider):
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "",
        live_options: Optional[LiveOptions] = None,
        addons: Optional[Dict[str, Any]] = None,
    ):
        # Default options: provider VAD off, interim on.
        default_options = LiveOptions(
            encoding="linear16",
            language=Language.EN,
            model="nova-3-general",
            channels=1,
            interim_results=True,
            smart_format=True,
            punctuate=True,
            profanity_filter=True,
            vad_events=False,
        )

        merged = default_options.to_dict()
        if live_options:
            default_model = default_options.model
            merged.update(live_options.to_dict())
            # SDK quirk: model may be "None" string
            if merged.get("model") == "None":
                merged["model"] = default_model

        # Normalize language if enum
        if isinstance(merged.get("language"), Language):
            merged["language"] = merged["language"].value

        self._settings = merged
        self._addons = addons

        self._client = DeepgramClient(
            api_key,
            config=DeepgramClientOptions(
                url=base_url,
                options={"keepalive": "true"},
            ),
        )

        self._connection: Optional[AsyncListenWebSocketClient] = None
        self._callbacks: Optional[UnivoxCallbacks] = None
        self._sample_rate: int = 0

    # UnivoxProvider

    def set_callbacks(self, cb: UnivoxCallbacks) -> None:
        self._callbacks = cb

    async def start(self, *, sample_rate: int) -> None:
        self._sample_rate = sample_rate
        self._settings["sample_rate"] = self._sample_rate
        await self._connect()

    async def stop(self) -> None:
        await self._disconnect()

    async def cancel(self) -> None:
        await self._disconnect()

    async def send_audio(self, audio: bytes) -> None:
        if self._connection is None or not getattr(self._connection, "is_connected", False):
            return
        await self._connection.send(audio)

    async def finalize_utterance(self) -> None:
        if self._connection is None:
            return
        await self._connection.finalize()

    async def set_language(self, language: Language) -> None:
        self._settings["language"] = language.value if isinstance(language, Language) else language
        await self._reconnect()

    async def set_model(self, model: str) -> None:
        self._settings["model"] = model
        await self._reconnect()

    # Internals

    async def _connect(self) -> None:
        logger.debug("[Univox.Deepgram] Connecting")
        self._connection = self._client.listen.asyncwebsocket.v("1")

        # Event wiring
        self._connection.on(
            LiveTranscriptionEvents(LiveTranscriptionEvents.Transcript), self._on_message
        )
        self._connection.on(
            LiveTranscriptionEvents(LiveTranscriptionEvents.Error), self._on_error
        )

        started = await self._connection.start(options=self._settings, addons=self._addons)
        if not started:
            logger.error("[Univox.Deepgram] Unable to connect")
            if self._callbacks:
                await self._callbacks.on_error(
                    "Deepgram connection failed. Check API key and network."
                )
        else:
            logger.info("[Univox.Deepgram] Connected")

    async def _disconnect(self) -> None:
        if self._connection and self._connection.is_connected:
            logger.debug("[Univox.Deepgram] Disconnecting")
            await self._connection.finish()
        self._connection = None

    async def _reconnect(self) -> None:
        await self._disconnect()
        await self._connect()

    # Event handlers

    async def _on_error(self, *args, **kwargs):
        if self._callbacks:
            error: ErrorResponse = kwargs.get("error")
            await self._callbacks.on_error(str(error))

    async def _on_message(self, *args, **kwargs):
        if not self._callbacks:
            return
        result: LiveResultResponse = kwargs["result"]
        if len(result.channel.alternatives) == 0:
            return
        is_final = result.is_final
        transcript = result.channel.alternatives[0].transcript
        language = None
        if result.channel.alternatives[0].languages:
            try:
                language = Language(result.channel.alternatives[0].languages[0])
            except Exception:
                language = None
        if transcript:
            logger.debug(
                f"[Univox.Deepgram] recv transcript final={is_final} lang={language} text={transcript!r}"
            )
            evt = TranscriptEvent(
                text=transcript,
                is_final=is_final,
                language=language,
                provider_payload=result,
            )
            if is_final:
                await self._callbacks.on_final(evt)
            else:
                await self._callbacks.on_interim(evt)
