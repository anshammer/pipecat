# Univox UI (React + Vite)

Minimal React app to connect to the Pipecat WebRTC runner, open the mic, and show interim/final transcriptions.

## Prereqs

- Backend: run the Univox example server (port 7860):
  - `cd ../..` (repo root)
  - `cd univox`
  - `uv run python -m univox.examples.basic_vad_pipecat --transport webrtc`
- Node.js 18+

## Run the UI

```
cd univox/ui
npm install
npm run dev
# open http://localhost:5173
```

Optionally set the backend URL (defaults to http://localhost:7860):

```
BACKEND_URL=http://localhost:7860 npm run dev
```

## How it works

- Creates a WebRTC `RTCPeerConnection`
- Captures mic (`getUserMedia`) and adds the audio track
- Creates a DataChannel and POSTs the SDP offer to `POST /api/offer`
- Receives DataChannel messages and renders:
  - RTVI user transcription messages `{ label: 'rtvi-ai', type: 'user-transcription', data: { text, final } }`
  - Fallback app messages `{ type: 'message', role: 'assistant', content: ... }`

Interim text is shown in italic gray; final text in normal weight.

## Notes

- The UI sends a `ping` heartbeat over the DataChannel every second.
- Refreshing the UI disconnects the peer; click Start again to reconnect.
- For production, host this app behind your own domain and point `BACKEND_URL` to your Pipecat runner.

