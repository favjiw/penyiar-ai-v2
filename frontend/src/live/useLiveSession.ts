import { useCallback, useEffect, useRef, useState } from 'react'
import type { OutputStatus, ShowSnapshot, ShowrunnerDecision, SupervisorEvent, TranscriptEntry, TurnEvent } from './types'

type Role = 'console' | 'prompter' | 'stage'
const RECONNECT_MS = 1500
const KEEP = 200

export interface LiveSession {
  connected: boolean
  snapshot: ShowSnapshot
  transcript: TranscriptEntry[]
  showrunner: ShowrunnerDecision[]
  supervisor: SupervisorEvent[]
  output: OutputStatus | null
  speaking: string | null
  alerts: { stage: string; message: string; turn: number }[]
  audioBlocked: boolean
  unlockAudio: () => void
}

/**
 * Sambungan /ws/session dengan sambung ulang otomatis (PRD §8). Bila klien ini
 * pemilik audio, giliran diputar di sini dan selesai-putarnya dilaporkan ke
 * server supaya Show Engine tahu kapan memutar giliran berikutnya.
 */
export function useLiveSession(role: Role): LiveSession {
  const [connected, setConnected] = useState(false)
  const [snapshot, setSnapshot] = useState<ShowSnapshot>({ state: 'idle' })
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([])
  const [showrunner, setShowrunner] = useState<ShowrunnerDecision[]>([])
  const [supervisor, setSupervisor] = useState<SupervisorEvent[]>([])
  const [output, setOutput] = useState<OutputStatus | null>(null)
  const [speaking, setSpeaking] = useState<string | null>(null)
  const [alerts, setAlerts] = useState<LiveSession['alerts']>([])
  const [audioBlocked, setAudioBlocked] = useState(false)

  const wsRef = useRef<WebSocket | null>(null)
  const ownerRef = useRef(false)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const pendingRef = useRef<TurnEvent | null>(null)
  const sessionRef = useRef<string | undefined>()

  const send = useCallback((action: string, data: Record<string, unknown> = {}) => {
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ action, data }))
  }, [])

  const stopAudio = useCallback(() => {
    const a = audioRef.current
    if (a) {
      a.onended = a.onerror = null
      a.pause()
    }
    pendingRef.current = null
  }, [])

  const play = useCallback(
    (turn: TurnEvent) => {
      stopAudio()
      if (!turn.audio_url) return
      const a = audioRef.current ?? (audioRef.current = new Audio())
      const report = (status: 'started' | 'ended' | 'error') => send('playback', { playback_id: turn.playback_id, status, persona: turn.persona })
      a.src = turn.audio_url
      a.onended = () => {
        setSpeaking(null)
        report('ended')
      }
      a.onerror = () => {
        setSpeaking(null)
        report('error')
      }
      a.play()
        .then(() => {
          setAudioBlocked(false)
          send('audio_state', { blocked: false })
          setSpeaking(turn.persona)
          report('started')
        })
        .catch((err: DOMException) => {
          if (err.name === 'NotAllowedError') {
            // Autoplay diblokir browser: tunggu operator mengklik halaman.
            pendingRef.current = turn
            setAudioBlocked(true)
            send('audio_state', { blocked: true })
          } else {
            report('error')
          }
        })
    },
    [send, stopAudio],
  )

  const unlockAudio = useCallback(() => {
    const pending = pendingRef.current
    if (pending) play(pending)
    else {
      // Gestur pengguna membuka izin autoplay untuk giliran berikutnya.
      const a = audioRef.current ?? (audioRef.current = new Audio())
      a.play().catch(() => undefined)
      setAudioBlocked(false)
      send('audio_state', { blocked: false })
    }
  }, [play, send])

  useEffect(() => {
    let closed = false
    let timer: number | undefined

    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      const ws = new WebSocket(`${proto}://${location.host}/ws/session?role=${role}`)
      wsRef.current = ws
      ws.onopen = () => setConnected(true)
      ws.onclose = () => {
        setConnected(false)
        if (!closed) timer = window.setTimeout(connect, RECONNECT_MS)
      }
      ws.onmessage = (ev) => {
        const { type, data } = JSON.parse(ev.data)
        switch (type) {
          case 'state': {
            const snap = data as ShowSnapshot
            setSnapshot(snap)
            if (snap.session_id !== sessionRef.current) {
              // Sesi baru, atau sambung ulang: ambil ulang riwayat dari snapshot.
              sessionRef.current = snap.session_id
              setShowrunner(snap.showrunner ? [snap.showrunner] : [])
              setSupervisor([])
              setAlerts([])
            }
            if (snap.transcript) setTranscript(snap.transcript)
            if (snap.state === 'ended') stopAudio()
            break
          }
          case 'turn': {
            const turn = data as TurnEvent
            setTranscript((t) => (t.some((x) => x.turn === turn.turn) ? t : [...t, turn].slice(-KEEP)))
            if (ownerRef.current) play(turn)
            else setSpeaking(turn.persona)
            break
          }
          case 'speaking':
            if (!ownerRef.current) setSpeaking(data.persona ?? null)
            break
          case 'topic_change':
            setSnapshot((s) => ({ ...s, topic: data, segment: data.id ? 'topic' : 'closing' }))
            break
          case 'showrunner':
            setShowrunner((l) => [...l, data].slice(-KEEP))
            break
          case 'supervisor':
            setSupervisor((l) => [...l, data].slice(-KEEP))
            break
          case 'alert':
            setAlerts((l) => [...l, data].slice(-20))
            break
          case 'output_status':
            ownerRef.current = data.is_audio_owner
            setOutput(data)
            if (!data.is_audio_owner) stopAudio()
            break
          case 'stop_audio':
            stopAudio()
            setSpeaking(null)
            break
        }
      }
    }
    connect()
    const ping = window.setInterval(() => send('ping'), 20000)
    return () => {
      closed = true
      window.clearTimeout(timer)
      window.clearInterval(ping)
      stopAudio()
      wsRef.current?.close()
    }
  }, [role, play, send, stopAudio])

  return { connected, snapshot, transcript, showrunner, supervisor, output, speaking, alerts, audioBlocked, unlockAudio }
}
