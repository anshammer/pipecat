"""Univox Deepgram-backed STT service.

Uses Pipecat's streaming Deepgram client with provider VAD disabled by default,
so segmentation happens via Pipecat-side VAD (e.g., Silero).
"""

from typing import Optional

from loguru import logger

try:
    from deepgram import LiveOptions  # type: ignore
except ModuleNotFoundError as e:  # pragma: no cover - optional dependency
    logger.error(f"Exception: {e}")
    logger.error(
        "In order to use Univox with Deepgram, install extras: 'pip install univox[deepgram]'"
    )
    raise

from pipecat.services.deepgram.stt import DeepgramSTTService


class UnivoxSTTService(DeepgramSTTService):
    """Deepgram STT with Pipecat-side VAD by default.

    Notes:
        - Defaults `vad_events=False` to rely on Pipecat's VAD (e.g., Silero).
        - You can still pass a custom `LiveOptions` to override defaults.
    """

    def __init__(
        self,
        *,
        api_key: str,
        live_options: Optional[LiveOptions] = None,
        **kwargs,
    ):
        # Default to provider VAD disabled; let Pipecat drive segmentation
        if live_options is None:
            live_options = LiveOptions(interim_results=True, vad_events=False)

        super().__init__(api_key=api_key, live_options=live_options, **kwargs)

