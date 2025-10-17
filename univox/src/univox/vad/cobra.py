"""Picovoice Cobra VAD analyzer compatible with Pipecat.

This module provides a `CobraVADAnalyzer` that plugs into Pipecat's
`VADAnalyzer` interface so you can swap VAD backends without changing
the rest of your pipeline.

Usage:

    from univox.vad.cobra import CobraVADAnalyzer
    analyzer = CobraVADAnalyzer(access_key=os.getenv("PICOVOICE_ACCESS_KEY"))
    params = TransportParams(audio_in_enabled=True, vad_analyzer=analyzer)

Dependencies:
    pip install pvcobra

Notes:
    - Cobra operates at 16 kHz mono. Ensure your transport provides 16 kHz
      input (Pipecat's SmallWebRTC transport resamples to 16 kHz internally).
    - `voice_confidence()` returns a float in [0, 1].
"""

from __future__ import annotations

from typing import Optional

import numpy as np
from loguru import logger

from pipecat.audio.vad.vad_analyzer import VADAnalyzer, VADParams


class CobraVADAnalyzer(VADAnalyzer):
    """VAD analyzer based on Picovoice Cobra.

    Wraps the `pvcobra` runtime and exposes the Pipecat `VADAnalyzer` API.
    """

    def __init__(
        self,
        *,
        access_key: str,
        sample_rate: Optional[int] = None,
        params: Optional[VADParams] = None,
    ):
        super().__init__(sample_rate=sample_rate, params=params)

        try:
            import pvcobra  # type: ignore
        except ModuleNotFoundError as e:  # pragma: no cover
            logger.error(f"Exception: {e}")
            logger.error(
                "To use Cobra VAD install pvcobra (or the extra): `pip install pvcobra` "
                "or `pip install univox[cobra]`"
            )
            raise

        if not access_key:
            raise ValueError("CobraVADAnalyzer requires a Picovoice access key")

        # Initialize Cobra runtime
        self._cobra = pvcobra.create(access_key=access_key)
        self._cobra_frame_length = self._cobra.frame_length  # samples per frame
        self._cobra_sample_rate = getattr(self._cobra, "sample_rate", 16000)

        logger.debug(
            f"Loaded Cobra VAD (sample_rate={self._cobra_sample_rate}, frame_length={self._cobra_frame_length})"
        )

    def __del__(self):  # best-effort resource cleanup
        try:
            if hasattr(self, "_cobra") and self._cobra is not None:
                self._cobra.delete()
        except Exception:
            pass

    # VADAnalyzer
    def set_sample_rate(self, sample_rate: int):
        # Cobra expects 16 kHz mono
        if sample_rate != 16000:
            raise ValueError(
                f"Cobra VAD requires 16000 Hz sample rate (received: {sample_rate})"
            )
        super().set_sample_rate(sample_rate)

    def num_frames_required(self) -> int:
        # Number of PCM samples Cobra expects per process() call
        return int(self._cobra_frame_length)

    def voice_confidence(self, buffer) -> float:
        try:
            # Convert bytes -> int16 numpy array of length = frame_length
            pcm = np.frombuffer(buffer, dtype=np.int16)
            # Cobra expects a Python list of ints (or numpy array works in practice)
            prob = float(self._cobra.process(pcm))
            # Ensure [0, 1]
            if prob < 0.0:
                prob = 0.0
            elif prob > 1.0:
                prob = 1.0
            return prob
        except Exception as e:
            logger.error(f"Error analyzing audio with Cobra VAD: {e}")
            return 0.0

