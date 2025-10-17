export type ConnectOptions = {
  backendUrl?: string // default http://localhost:7860
  onMessage?: (msg: any) => void
  onConnected?: () => void
  onDisconnected?: () => void
}

export type PeerBundle = {
  pc: RTCPeerConnection
  dc: RTCDataChannel
  stream: MediaStream
  stop: () => Promise<void>
}

export async function connectWebRTC(opts: ConnectOptions = {}): Promise<PeerBundle> {
  const backend = opts.backendUrl || 'http://localhost:7860'

  const pc = new RTCPeerConnection({
    iceServers: []
  })

  // Data channel for control + messages
  const dc = pc.createDataChannel('app')
  dc.onopen = () => {
    opts.onConnected?.()
    // Heartbeat ping to keep connection marked as active
    const timer = setInterval(() => {
      if (dc.readyState === 'open') dc.send(`ping ${Date.now()}`)
    }, 1000)
    // Cleanup timer when closed
    dc.onclose = () => clearInterval(timer)
  }
  dc.onmessage = (ev) => {
    try {
      const obj = JSON.parse(ev.data)
      opts.onMessage?.(obj)
    } catch {
      // non-JSON ping/pong etc.
    }
  }

  pc.onconnectionstatechange = () => {
    if (pc.connectionState === 'disconnected' || pc.connectionState === 'failed' || pc.connectionState === 'closed') {
      opts.onDisconnected?.()
    }
  }

  // Capture mic
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })
  for (const track of stream.getAudioTracks()) pc.addTrack(track, stream)

  // Create offer
  const offer = await pc.createOffer({ offerToReceiveAudio: true, offerToReceiveVideo: false })
  await pc.setLocalDescription(offer)

  // Send to backend
  const res = await fetch(`${backend}/api/offer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sdp: offer.sdp, type: offer.type })
  })
  if (!res.ok) throw new Error(`Offer failed: ${res.status}`)
  const answer = await res.json()
  await pc.setRemoteDescription(answer)

  async function stop() {
    try { dc.close() } catch {}
    try { pc.close() } catch {}
    stream.getTracks().forEach(t => t.stop())
  }

  return { pc, dc, stream, stop }
}

