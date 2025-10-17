import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { connectWebRTC, type PeerBundle } from './webrtc'
import type { RTVIMessage, TranscriptionItem } from './types'

function useTranscripts() {
  const [items, setItems] = useState<TranscriptionItem[]>([])

  const upsert = useCallback((t: Omit<TranscriptionItem, 'id'> & { id?: string }) => {
    setItems(prev => {
      const id = t.id ?? `t-${prev.length + 1}`
      // If interim, replace or append a single interim line at end
      if (!t.final) {
        const last = prev[prev.length - 1]
        if (last && !last.final) {
          const next = prev.slice(0, -1)
          next.push({ id: last.id, text: t.text, final: false, ts: t.ts })
          return next
        }
        return [...prev, { id, text: t.text, final: false, ts: t.ts }]
      }
      // Final: append as new final
      return [...prev, { id, text: t.text, final: true, ts: t.ts }]
    })
  }, [])

  const clear = useCallback(() => setItems([]), [])
  return { items, upsert, clear }
}

export default function App() {
  const [connecting, setConnecting] = useState(false)
  const [connected, setConnected] = useState(false)
  const [status, setStatus] = useState<string>('Idle')
  const [vad, setVad] = useState<string>('unknown')
  const peerRef = useRef<PeerBundle | null>(null)
  const { items, upsert, clear } = useTranscripts()

  const backendUrl = useMemo(() => (import.meta.env.VITE_BACKEND_URL as string) || 'http://localhost:7860', [])

  const handleMessage = useCallback((msg: any) => {
    // Handle RTVI "user-transcription" first
    const m = msg as RTVIMessage
    try { console.debug('[Univox UI] received', m) } catch {}
    if (m && (m.label === 'rtvi-ai' || m.type === 'user-transcription')) {
      if (m.type === 'server-message' && m.data) {
        if (typeof m.data.vad_backend === 'string') {
          setVad(m.data.vad_backend)
        }
      }
      if (m.type === 'user-transcription' && m.data) {
        const { text, final, timestamp } = m.data
        if (typeof text === 'string') upsert({ text, final: !!final, ts: timestamp })
        return
      }
    }
    // Ignore generic app-message transcripts to avoid duplicates;
    // rely on RTVI 'user-transcription' messages instead.
    // Fallback: univox-status message
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
      <div className="left">
        <h3>Univox</h3>
        <div className="controls">
          <button className="primary" onClick={start} disabled={connecting || connected}>Start Mic</button>
          <button onClick={stop} disabled={!connected}>Stop</button>
        </div>
        <div className="status">{status}</div>
        <div className="status">VAD: {vad}</div>
        <div style={{marginTop: 16}}>
          <button onClick={clear}>Clear Transcript</button>
        </div>
      </div>
      <div className="main">
        <h3>Live Transcription</h3>
        <div className="transcript">
          {items.length === 0 && <div className="line">Waiting for messages...</div>}
          {items.map(it => (
            <div key={it.id} className={"line " + (it.final ? '' : 'interim')}>{it.text}</div>
          ))}
        </div>
      </div>
    </div>
  )
}
