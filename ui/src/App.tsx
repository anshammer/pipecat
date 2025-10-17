import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { connectWebRTC, type PeerBundle } from './webrtc'
import type { RTVIMessage, TranscriptItem } from './types'

function useTranscripts() {
  const [items, setItems] = useState<TranscriptItem[]>([])

  const upsert = useCallback((t: { text: string; final: boolean; ts?: string }) => {
    setItems((prev) => {
      if (!t.final) {
        const last = prev[prev.length - 1]
        if (last && !last.final) {
          return [...prev.slice(0, -1), { ...last, text: t.text, ts: t.ts }]
        }
        return [...prev, { id: `interim-${prev.length}`, text: t.text, final: false, ts: t.ts }]
      }
      return [...prev, { id: `final-${prev.length}`, text: t.text, final: true, ts: t.ts }]
    })
  }, [])

  const clear = useCallback(() => setItems([]), [])
  return { items, upsert, clear }
}

export default function App() {
  const [connecting, setConnecting] = useState(false)
  const [connected, setConnected] = useState(false)
  const [status, setStatus] = useState('Idle')
  const [vad, setVad] = useState('unknown')
  const peerRef = useRef<PeerBundle | null>(null)
  const { items, upsert, clear } = useTranscripts()

  const backendUrl = useMemo(() => (import.meta.env.VITE_BACKEND_URL as string) || 'http://localhost:7860', [])

  const handleMessage = useCallback((msg: any) => {
    const m = msg as RTVIMessage
    console.debug('[Univox UI] received', m)
    if (m && (m.label === 'rtvi-ai' || m.type === 'user-transcription')) {
      if (m.type === 'user-transcription' && m.data) {
        const { text, final, timestamp } = m.data
        if (typeof text === 'string') upsert({ text, final: !!final, ts: timestamp })
        return
      }
      if (m.type === 'server-message' && m.data && typeof m.data.vad_backend === 'string') {
        setVad(m.data.vad_backend)
      }
    }
    if (m && m.type === 'univox-status' && typeof (m as any).vad_backend === 'string') {
      setVad((m as any).vad_backend)
    }
  }, [upsert])

  const start = useCallback(async () => {
    if (connecting || connected) return
    setConnecting(true)
    setStatus('Connecting...')
    try {
      const peer = await connectWebRTC({
        backendUrl,
        onMessage: handleMessage,
        onConnected: () => setConnected(true),
        onDisconnected: () => setConnected(false)
      })
      peerRef.current = peer
      setStatus('Connected. Speak into your mic...')
    } catch (e: any) {
      console.error(e)
      setStatus(`Error: ${e?.message || e}`)
    } finally {
      setConnecting(false)
    }
  }, [backendUrl, connecting, connected, handleMessage])

  const stop = useCallback(async () => {
    setStatus('Disconnecting...')
    try { await peerRef.current?.stop() } catch {}
    peerRef.current = null
    setConnected(false)
    setStatus('Idle')
  }, [])

  useEffect(() => {
    return () => { peerRef.current?.stop() }
  }, [])

  return (
    <div className="container">
      <div className="sidebar">
        <h3>Univox</h3>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="primary" onClick={start} disabled={connecting || connected}>Start Mic</button>
          <button onClick={stop} disabled={!connected}>Stop</button>
        </div>
        <div style={{ marginTop: 8, fontSize: 12, color: '#555' }}>{status}</div>
        <div style={{ marginTop: 4, fontSize: 12, color: '#555' }}>VAD: {vad}</div>
        <div style={{ marginTop: 16 }}>
          <button onClick={clear}>Clear Transcript</button>
        </div>
      </div>
      <div className="main">
        <h3>Live Transcription</h3>
        <div className="transcript">
          {items.length === 0 && <div className="line">Waiting for messages...</div>}
          {items.map(item => (
            <div key={item.id} className={`line ${item.final ? '' : 'interim'}`}>{item.text}</div>
          ))}
        </div>
      </div>
    </div>
  )
}
