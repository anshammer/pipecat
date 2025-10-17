# Univox

Provider-backed STT engine for Pipecat with pipeline-side VAD.

This package demonstrates building an STT service that relies on Pipecat's VAD
(e.g., Silero) for speech segmentation, while using a provider (Deepgram) for
recognition. It keeps turn-taking and segmentation inside the Pipecat pipeline.

## Installation

Using pip:

```bash
pip install pipecat-ai "pipecat-ai[deepgram,silero]"
# When publishing to PyPI, this becomes:
# pip install "univox[all]"
```

Using uv:

```bash
uv add pipecat-ai "pipecat-ai[deepgram,silero]"
```

## Example

Run a basic demo with Pipecat VAD + Deepgram STT:

```bash
export DEEPGRAM_API_KEY=...  # your key
uv run python -m univox.examples.basic_vad_pipecat --transport webrtc
```

You can also use `--transport daily` or `--transport twilio`, assuming your
environment and credentials are configured for those transports.

## Notes

- VAD is handled by Pipecat via `SileroVADAnalyzer`.
- Provider-side VAD is disabled by default (Deepgram `vad_events=False`).
- Tested with Pipecat v0.0.86+.

