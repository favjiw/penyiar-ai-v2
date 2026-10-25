import { useCallback, useEffect, useRef, useState } from 'react'
import type { OutputStatus, ShowSnapshot, ShowrunnerDecision, SupervisorEvent, TranscriptEntry, TurnEvent } from './types'

type Role = 'console' | 'prompter' | 'stage'
const RECONNECT_MS = 1500
const RECONNECT_MAX_MS = 10000
const KEEP = 200

export interface LiveSession {
  connected: boolean
  snapshot: ShowSnapshot
  transcript: TranscriptEntry[]
  showrunner: ShowrunnerDecision[]
  supervisor: SupervisorEvent[]
  output: OutputStatus | null
  speaking: string | null
  /** Video lip-sync (T2) untuk audio yang sedang diputar; `clock` = posisi audio (detik) untuk sinkron. */
  lipsync: LipSync | null
  alerts: { stage: string; message: string; turn: number }[]
  sttPartial: string
  audioBlocked: boolean
  unlockAudio: () => void
  send: (action: string, data?: Record<string, unknown>) => void
}

export interface LipSync {
  persona: string
  url: string
  key: string
  clock: () => number
}

/** Satu hal yang diputar berurutan: filler, atau giliran AI yang bisa terdiri dari beberapa bagian kalimat. */
interface PlayItem {
  id: string
  persona: string
  urls: (string | null | undefined)[] // undefined = bagian belum tiba; null = TTS bagian itu gagal (dilewati)
  videos?: (string | null | undefined)[] // video lip-sync per bagian (T2), bila ada
  total: number
  idx: number
  report: boolean // giliran dilaporkan ke server; filler tidak
  started: boolean
}

/**
 * Sambungan /ws/session dengan sambung ulang otomatis (PRD §8). Bila klien ini
 * pemilik audio, audio diputar di sini lewat antrean (filler → giliran → bagian
 * kalimat berikutnya) dan selesai-putar tiap giliran dilaporkan ke server supaya
 * Show Engine tahu kapan lanjut.
 */
export function useLiveSession(role: Role): LiveSession {
  const [connected, setConnected] = useState(false)
  const [snapshot, setSnapshot] = useState<ShowSnapshot>({ state: 'idle' })
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([])
  const [showrunner, setShowrunner] = useState<ShowrunnerDecision[]>([])
  const [supervisor, setSupervisor] = useState<SupervisorEvent[]>([])
  const [output, setOutput] = useState<OutputStatus | null>(null)
  const [speaking, setSpeaking] = useState<string | null>(null)
  const [lipsync, setLipsync] = useState<LipSync | null>(null)
  const [alerts, setAlerts] = useState<LiveSession['alerts']>([])
  const [sttPartial, setSttPartial] = useState('')
  const [audioBlocked, setAudioBlocked] = useState(false)

  const wsRef = useRef<WebSocket | null>(null)
  const ownerRef = useRef(false)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const queueRef = useRef<PlayItem[]>([])
  const playingRef = useRef(false)
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
    queueRef.current = []
    playingRef.current = false
    setLipsync(null)
  }, [])

  /** Putar bagian berikutnya dari item terdepan antrean; berhenti menunggu bila bagiannya belum tiba. */
  const pump = useCallback(() => {
    if (playingRef.current) return
    const item = queueRef.current[0]
    if (!item) return
    const report = (status: 'started' | 'ended' | 'error') =>
      item.report && send('playback', { playback_id: item.id, status, persona: item.persona })
    const finish = (status: 'ended' | 'error') => {
      queueRef.current.shift()
      // Filler lalu jawaban persona yang sama: jangan sempat kembali ke klip mendengarkan.
      if (queueRef.current[0]?.persona !== item.persona) setSpeaking(null)
      setLipsync(null)
      report(status)
      pump()
    }
    while (item.idx < item.total && item.urls[item.idx] === null) item.idx++ // bagian yang TTS-nya gagal
    if (item.idx >= item.total) return finish('ended')
    const url = item.urls[item.idx]
    if (url === undefined) return // tunggu audio_part
    if (url === null) return finish('error')
    const a = audioRef.current ?? (audioRef.current = new Audio())
    playingRef.current = true
    a.src = url
    setSpeaking(item.persona) // avatar mulai berganti klip selagi audio dimuat
    const video = item.videos?.[item.idx]
    setLipsync(video ? { persona: item.persona, url: video, key: `${item.id}:${item.idx}`, clock: () => a.currentTime } : null)
    a.onended = () => {
      playingRef.current = false
      item.idx++
      if (item.idx >= item.total) finish('ended')
      else pump()
    }
    a.onerror = () => {
      playingRef.current = false
      finish('error')
    }
    a.play()
      .then(() => {
        setAudioBlocked(false)
        send('audio_state', { blocked: false })
        setSpeaking(item.persona)
        if (!item.started) {
          item.started = true
          report('started')
        }
      })
      .catch((err: DOMException) => {
        playingRef.current = false
        setSpeaking(null)
        if (err.name === 'NotAllowedError') {
          // Autoplay diblokir browser: item tetap di antrean sampai operator mengklik halaman.
          setAudioBlocked(true)
          send('audio_state', { blocked: true })
        } else finish('error')
      })
  }, [send])

  const enqueue = useCallback(
    (item: Omit<PlayItem, 'idx' | 'started'>) => {
      queueRef.current.push({ ...item, idx: 0, started: false })
      pump()
    },
    [pump],
  )

  const unlockAudio = useCallback(() => {
    if (queueRef.current.length) pump()
    else {
      // Gestur pengguna membuka izin autoplay untuk giliran berikutnya.
      const a = audioRef.current ?? (audioRef.current = new Audio())
      a.play().catch(() => undefined)
    }
    setAudioBlocked(false)
    send('audio_state', { blocked: false })
  }, [pump, send])

  useEffect(() => {
    let closed = false
    let timer: number | undefined
    let attempts = 0

    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      const ws = new WebSocket(`${proto}://${location.host}/ws/session?role=${role}`)
      wsRef.current = ws
      ws.onopen = () => {
        attempts = 0
        setConnected(true)
      }
      ws.onclose = () => {
        setConnected(false)
        // Jeda makin panjang selama backend mati, supaya console tidak dibanjiri percobaan.
        const wait = Math.min(RECONNECT_MAX_MS, RECONNECT_MS * 2 ** attempts++)
        if (!closed) timer = window.setTimeout(connect, wait)
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
            if (ownerRef.current) {
              const total = turn.parts ?? 1
              const urls: (string | null | undefined)[] = Array(total).fill(undefined)
              urls[0] = turn.audio_url
              const videos: (string | null | undefined)[] = Array(total).fill(undefined)
              videos[0] = turn.video_url ?? null
              enqueue({ id: turn.playback_id, persona: turn.persona, urls, videos, total, report: true })
            } else setSpeaking(turn.persona)
            break
          }
          case 'audio_part': {
            const item = queueRef.current.find((i) => i.id === data.playback_id)
            if (item) {
              item.urls[data.index] = data.audio_url ?? null
              if (item.videos) item.videos[data.index] = data.video_url ?? null
              pump()
            }
            break
          }
          case 'filler':
            if (ownerRef.current && data.audio_url) enqueue({ id: `filler:${Date.now()}`, persona: data.persona, urls: [data.audio_url], total: 1, report: false })
            break
          case 'human_turn':
            setTranscript((t) => [...t, data].slice(-KEEP))
            setSttPartial('')
            break
          case 'stt_partial':
            setSttPartial(data.final ? '' : data.text)
            break
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
  }, [role, enqueue, pump, send, stopAudio])

  return { connected, snapshot, transcript, showrunner, supervisor, output, speaking, lipsync, alerts, sttPartial, audioBlocked, unlockAudio, send }
}
