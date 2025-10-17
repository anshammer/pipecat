"""Univox example: Pipecat-side VAD (Silero) + Deepgram STT.

Run with:
    python -m univox.examples.basic_vad_pipecat --transport webrtc
"""

import os

from dotenv import load_dotenv
from loguru import logger

from pipecat.frames.frames import (
    Frame,
    TranscriptionFrame,
    InterimTranscriptionFrame,
    ErrorFrame,
    OutputTransportMessageFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.transports.base_transport import BaseTransport, TransportParams

from univox.providers.deepgram import DeepgramProvider
from univox.service import UnivoxSTTService

load_dotenv(override=True)


class TranscriptionLogger(FrameProcessor):
    def __init__(self, transport: BaseTransport):
        super().__init__()
        self._transport = transport
        self._sent_vad_status = False

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, ErrorFrame):
            print(f"Error: {frame.error}")
        elif isinstance(frame, TranscriptionFrame):
            print(f"Transcription: {frame.text}")
            # Send VAD backend status on first transcript if not yet sent
            if not self._sent_vad_status:
                try:
                    from pipecat.processors.frameworks.rtvi import RTVIServerMessageFrame

                    vad = "unknown"
                    try:
                        analyzer = self._transport.input().vad_analyzer
                        if analyzer is not None:
                            cls = analyzer.__class__.__name__.lower()
                            if "silero" in cls:
                                vad = "silero"
                            elif "cobra" in cls:
                                vad = "cobra"
                            else:
                                vad = cls
                    except Exception:
                        pass
                    await self.push_frame(
                        RTVIServerMessageFrame(data={"univox": "status", "vad_backend": vad})
                    )
                    self._sent_vad_status = True
                except Exception as e:
                    logger.debug(f"Unable to push VAD status frame: {e}")
        elif isinstance(frame, InterimTranscriptionFrame):
            # Use RTVI observer path for interim transcripts (avoid duplicates)
            pass

        # Push all frames through
        await self.push_frame(frame, direction)


# VAD factory so we can plug different backends (silero, cobra)
def create_vad():
    backend = (os.getenv("VAD_BACKEND") or "silero").lower()
    if backend == "cobra":
        try:
            from univox.vad.cobra import CobraVADAnalyzer

            access_key = os.getenv("PICOVOICE_ACCESS_KEY") or ""
            logger.info("VAD backend: cobra")
            return CobraVADAnalyzer(access_key=access_key)
        except Exception as e:
            logger.warning(f"Falling back to Silero VAD (Cobra unavailable): {e}")
    # Lazy-import Silero only if needed, so we don't require onnxruntime
    # when using Cobra or other backends.
    try:
        from pipecat.audio.vad.silero import SileroVADAnalyzer  # type: ignore

        logger.info("VAD backend: silero")
        return SileroVADAnalyzer()
    except ModuleNotFoundError as e:
        logger.warning(
            "Silero VAD is not installed (onnxruntime missing). Install with: "
            "pip install 'pipecat-ai[silero]'"
        )
        return None


# We store functions so objects (e.g. VADAnalyzer) don't get
# instantiated until a transport is selected.
def _daily_params():
    # Import only when needed to avoid optional dependency errors
    from pipecat.transports.daily.transport import DailyParams  # type: ignore

    return DailyParams(audio_in_enabled=True, vad_analyzer=create_vad())


def _twilio_params():
    # Import only when needed to avoid optional dependency errors
    from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams  # type: ignore

    return FastAPIWebsocketParams(audio_in_enabled=True, vad_analyzer=create_vad())


transport_params = {
    "daily": _daily_params,
    "twilio": _twilio_params,
    "webrtc": lambda: TransportParams(audio_in_enabled=True, vad_analyzer=create_vad()),
}


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    logger.info("Starting Univox demo (Pipecat VAD + Deepgram STT)")

    provider = DeepgramProvider(api_key=os.getenv("DEEPGRAM_API_KEY"))
    stt = UnivoxSTTService(provider)

    # RTVI observer to drive the UI's chat panels
    from pipecat.processors.frameworks.rtvi import RTVIConfig, RTVIObserver, RTVIProcessor

    # Do NOT pass transport to RTVIProcessor, otherwise audio_in_stream_on_start
    # is disabled by default and you won't receive mic audio.
    rtvi = RTVIProcessor(config=RTVIConfig(config=[]))

    tl = TranscriptionLogger(transport)

    # Include transport.output() so RTVI messages reach the client UI
    pipeline = Pipeline([transport.input(), rtvi, stt, tl, transport.output()])

    task = PipelineTask(
        pipeline,
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
        observers=[RTVIObserver(rtvi)],
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        # Report which VAD backend is active to the UI via RTVI server-message
        import asyncio

        def detect_backend() -> str:
            backend_ = "unknown"
            try:
                vad_ = transport.input().vad_analyzer
                if vad_ is not None:
                    cls = vad_.__class__.__name__.lower()
                    if "silero" in cls:
                        backend_ = "silero"
                    elif "cobra" in cls:
                        backend_ = "cobra"
                    else:
                        backend_ = cls
            except Exception as e:
                logger.debug(f"Unable to determine VAD backend: {e}")
            return backend_

        async def delayed_announce():
            # Give the data channel time to open so messages are not discarded
            await asyncio.sleep(2.0)
            try:
                backend = detect_backend()
                # RTVI server-message (center panel aware UIs)
                await rtvi.send_server_message({"univox": "status", "vad_backend": backend})
                # App message fallback for minimal clients
                await transport.output().send_message(
                    OutputTransportMessageFrame(message={"type": "univox-status", "vad_backend": backend})
                )
            except Exception as e:
                logger.debug(f"Unable to send VAD backend status: {e}")

        asyncio.create_task(delayed_announce())

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)
    await runner.run(task)


async def bot(runner_args: RunnerArguments):
    """Main entry compatible with Pipecat Cloud runner."""
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
