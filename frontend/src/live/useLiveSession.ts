import { useCallback, useEffect, useRef, useState } from 'react'
import type { AlertEvent, OnAirTopic, OutputStatus, PointClock, ShowClock, ShowSnapshot, ShowrunnerDecision, SupervisorEvent, TranscriptEntry, TurnEvent } from './types'

export type Role = 'console' | 'prompter' | 'stage'
const RECONNECT_MS = 1500
const RECONNECT_MAX_MS = 10000
/** Keterangan tambahan di event topic_change (PRD v2.7): pindah lewat ucapan penyiar atau pembatalannya. */
export interface TopicChangeInfo {
  reason?: 'voice' | 'undo'
  said?: string
  from?: string
  rule?: string
  undo_s?: number
}

const KEEP = 200
const LEVEL_SEND_MS = 100
const REMOTE_LEVEL_STALE_MS = 500

export interface LiveSession {
  connected: boolean
  snapshot: ShowSnapshot
  transcript: TranscriptEntry[]
  showrunner: ShowrunnerDecision[]
  supervisor: SupervisorEvent[]
  output: OutputStatus | null
  /** Jam obrolan per poin terbaru dari server, beserta waktu terimanya (untuk menghitung mundur di klien). */
  pointClock: { clock: PointClock; at: number } | null
  /** Jam siaran terbaru dari server beserta waktu terimanya (performance.now()). */
  showClock: { clock: ShowClock; at: number } | null
  /** Pindah topik terakhir yang terjadi saat klien ini tersambung (untuk band "Pindah topik"). */
  lastTopicChange: { topic: (OnAirTopic | { id: null; judul: string }) & TopicChangeInfo; at: number } | null
  /** Kode halus pindah topik terakhir dari AI (mode A, PRD v2.7 FR-4). */
  lastNudge: { turn: number; topic_id: string; to: string; text: string; overrun_s: number } | null
  speaking: string | null
  /** Peringatan dari server (PRD v2.7 §6.3); `id` lokal untuk menutup per item. */
  alerts: AlertEvent[]
  sttPartial: string
  /** Mikrofon penyiar manusia sedang ditahan (push-to-talk di prompter). */
  micActive: boolean
  /** Amplitudo audio yang sedang diputar, 0..1; null bila klien ini bukan pemilik audio. */
  level: () => number | null
  audioBlocked: boolean
  /** /stage: Web Audio sudah menyala (gestur pengguna); suara AI bisa diputar tanpa klik lagi. */
  audioReady: boolean
  unlockAudio: () => void
  send: (action: string, data?: Record<string, unknown>) => void
}

/** Satu hal yang diputar berurutan: filler, atau giliran AI yang bisa terdiri dari beberapa bagian kalimat. */
interface PlayItem {
  id: string
  persona: string
  urls: (string | null | undefined)[] // undefined = bagian belum tiba; null = TTS bagian itu gagal (dilewati)
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
  const [pointClock, setPointClock] = useState<{ clock: PointClock; at: number } | null>(null)
  const [showClock, setShowClock] = useState<{ clock: ShowClock; at: number } | null>(null)
  const [lastTopicChange, setLastTopicChange] = useState<LiveSession['lastTopicChange']>(null)
  const [lastNudge, setLastNudge] = useState<LiveSession['lastNudge']>(null)
  const [speaking, setSpeaking] = useState<string | null>(null)
  const [alerts, setAlerts] = useState<LiveSession['alerts']>([])
  const [sttPartial, setSttPartial] = useState('')
  const [micActive, setMicActive] = useState(false)
  const [audioBlocked, setAudioBlocked] = useState(false)
  const [audioReady, setAudioReady] = useState(false)

  const wsRef = useRef<WebSocket | null>(null)
  const ownerRef = useRef(false)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const ctxRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const samplesRef = useRef<Uint8Array | null>(null)
  const queueRef = useRef<PlayItem[]>([])
  const playingRef = useRef(false)
  const sessionRef = useRef<string | undefined>()
  // Naik setiap stopAudio: callback pemutaran lama (resume/play yang masih menunggu) diabaikan.
  const genRef = useRef(0)
  const alertSeq = useRef(0) // id unik per peringatan (untuk ditutup satu per satu)
  const reportedReadyRef = useRef<boolean | null>(null)
  // Level dari stage (lewat WS) untuk klien yang bukan pemilik audio: konsol dan prompter.
  const remoteLevelRef = useRef<{ level: number; at: number }>({ level: 0, at: 0 })

  const send = useCallback((action: string, data: Record<string, unknown> = {}) => {
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ action, data }))
  }, [])

  /** Satu elemen audio, dialirkan lewat Web Audio supaya amplitudonya bisa dibaca (mulut avatar, bar level). */
  const getAudio = useCallback((): HTMLAudioElement => {
    let a = audioRef.current
    if (!a) {
      a = new Audio()
      audioRef.current = a
      try {
        const ctx = new AudioContext()
        const analyser = ctx.createAnalyser()
        analyser.fftSize = 512
        const src = ctx.createMediaElementSource(a)
        src.connect(analyser)
        analyser.connect(ctx.destination)
        ctxRef.current = ctx
        analyserRef.current = analyser
        samplesRef.current = new Uint8Array(analyser.fftSize)
      } catch {
        // Tanpa Web Audio audio tetap diputar lewat elemen; level dianggap nol (bar diam).
      }
    }
    return a
  }, [])

  const level = useCallback((): number | null => {
    const analyser = analyserRef.current
    const samples = samplesRef.current
    if (!ownerRef.current) {
      if (role === 'stage') return null
      const r = remoteLevelRef.current
      return Date.now() - r.at < REMOTE_LEVEL_STALE_MS ? r.level : 0
    }
    if (!analyser || !samples) return null
    analyser.getByteTimeDomainData(samples)
    let sum = 0
    for (const v of samples) {
      const x = (v - 128) / 128
      sum += x * x
    }
    return Math.min(1, Math.sqrt(sum / samples.length) * 3.2)
  }, [role])

  const stopAudio = useCallback(() => {
    genRef.current++
    const a = audioRef.current
    if (a) {
      a.onended = a.onerror = null
      a.pause()
    }
    queueRef.current = []
    playingRef.current = false
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
      // Filler lalu jawaban persona yang sama: jangan sempat kembali ke state listening.
      if (queueRef.current[0]?.persona !== item.persona) setSpeaking(null)
      report(status)
      pump()
    }
    while (item.idx < item.total && item.urls[item.idx] === null) item.idx++ // bagian yang TTS-nya gagal
    if (item.idx >= item.total) return finish('ended')
    const url = item.urls[item.idx]
    if (url === undefined) return // tunggu audio_part
    if (url === null) return finish('error')
    const a = getAudio()
    const gen = genRef.current
    const stale = () => gen !== genRef.current || queueRef.current[0] !== item
    playingRef.current = true
    a.src = url
    setSpeaking(item.persona) // indikator mulai berganti selagi audio dimuat
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
    // AudioContext yang masih suspended membisukan elemen tanpa galat; perlakukan sebagai audio diblokir.
    const begin = async () => {
      const ctx = ctxRef.current
      const running = () => ctx?.state === 'running'
      if (ctx && !running()) {
        await Promise.race([ctx.resume().catch(() => undefined), new Promise((r) => window.setTimeout(r, 250))])
        if (!running()) throw new DOMException('AudioContext suspended', 'NotAllowedError')
      }
      if (stale()) return // dihentikan (sela, lompat, stop) selagi menunggu: jangan putar URL lama
      await a.play()
    }
    begin()
      .then(() => {
        if (stale()) return
        setAudioBlocked(false)
        setAudioReady(true)
        send('audio_state', { blocked: false })
        setSpeaking(item.persona)
        if (!item.started) {
          item.started = true
          report('started')
        }
      })
      .catch((err: DOMException) => {
        if (stale()) return // AbortError dari pause/ganti src setelah stopAudio: bukan galat item baru
        playingRef.current = false
        setSpeaking(null)
        if (err.name === 'NotAllowedError') {
          // Autoplay diblokir browser: item tetap di antrean sampai operator mengklik halaman.
          setAudioBlocked(true)
          setAudioReady(false)
          reportedReadyRef.current = false
          send('audio_state', { blocked: true, ready: false })
        } else finish('error')
      })
  }, [send, getAudio])

  const enqueue = useCallback(
    (item: Omit<PlayItem, 'idx' | 'started'>) => {
      queueRef.current.push({ ...item, idx: 0, started: false })
      pump()
    },
    [pump],
  )

  /** Gestur pengguna membuka izin autoplay; stage melaporkan siap bersuara ke server (cek kesiapan). */
  const unlockAudio = useCallback(() => {
    getAudio()
    const ctx = ctxRef.current
    const done = () => {
      const ready = !ctx || ctx.state === 'running'
      setAudioReady(ready)
      if (ready) setAudioBlocked(false)
      // Kirim hanya bila berubah: listener ini jalan di setiap klik/tombol pada jendela stage.
      if (reportedReadyRef.current !== ready) {
        reportedReadyRef.current = ready
        send('audio_state', { blocked: !ready, ready })
      }
      if (ready && queueRef.current.length) pump()
    }
    if (ctx && ctx.state !== 'running') void ctx.resume().catch(() => undefined).then(done)
    else done()
  }, [pump, send, getAudio])

  // Hanya /stage yang memutar audio (PRD v2.7 FR-10): klik atau tombol pertama di layar itu
  // menyiapkan Web Audio sebelum giliran pertama tiba.
  useEffect(() => {
    if (role !== 'stage') return
    // Klik di mana pun pada jendela stage menyalakan suara (juga saat on air, tanpa teks di layar).
    const arm = () => unlockAudio()
    window.addEventListener('pointerdown', arm)
    window.addEventListener('keydown', arm)
    return () => {
      window.removeEventListener('pointerdown', arm)
      window.removeEventListener('keydown', arm)
    }
  }, [role, unlockAudio])

  // Stage meneruskan level audio yang sedang diputar ke konsol/prompter (±10 kali per detik).
  useEffect(() => {
    if (role !== 'stage') return
    let lastSent = -1
    const t = window.setInterval(() => {
      if (!ownerRef.current) return
      const lv = playingRef.current ? Math.round((level() ?? 0) * 20) / 20 : 0
      if (lv === 0 && lastSent === 0) return
      lastSent = lv
      send('level', { level: lv, persona: queueRef.current[0]?.persona ?? null })
    }, LEVEL_SEND_MS)
    return () => window.clearInterval(t)
  }, [role, level, send])

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
        reportedReadyRef.current = null // server baru/terhubung ulang belum tahu status suara stage
        setConnected(true)
        if (role === 'stage' && ctxRef.current?.state === 'running') {
          reportedReadyRef.current = true
          ws.send(JSON.stringify({ action: 'audio_state', data: { blocked: false, ready: true } }))
        }
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
            setPointClock(snap.point_clock ? { clock: snap.point_clock, at: Date.now() } : null)
            setShowClock(snap.show_clock ? { clock: snap.show_clock, at: performance.now() } : null)
            // Selain pemutar, siapa yang bicara mengikuti server (termasuk null setelah giliran selesai).
            if (!ownerRef.current) setSpeaking(snap.speaking ?? null)
            if (snap.session_id !== sessionRef.current) {
              // Sesi baru, atau sambung ulang: ambil ulang riwayat dari snapshot.
              sessionRef.current = snap.session_id
              setShowrunner(snap.showrunner ? [snap.showrunner] : [])
              setSupervisor([])
              setAlerts([])
              setLastTopicChange(null)
              setLastNudge(null)
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
              enqueue({ id: turn.playback_id, persona: turn.persona, urls, total, report: true })
            } else setSpeaking(turn.persona)
            break
          }
          case 'audio_part': {
            const item = queueRef.current.find((i) => i.id === data.playback_id)
            if (item) {
              item.urls[data.index] = data.audio_url ?? null
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
            if (typeof data.active === 'boolean') setMicActive(data.active)
            setSttPartial(data.final ? '' : data.text)
            break
          case 'speaking':
            if (!ownerRef.current) setSpeaking(data.persona ?? null)
            break
          case 'topic_change':
            setSnapshot((s) => ({ ...s, topic: data, segment: data.id ? 'topic' : data.judul === 'Opening' ? 'opening' : 'closing' }))
            // Batal pindah: band/peringatan "pindah topik" selesai, bukan pindah baru.
            setLastTopicChange(data.reason === 'undo' ? null : { topic: data, at: performance.now() })
            break
          case 'nudge':
            setLastNudge(data)
            break
          case 'show_clock':
            setShowClock({ clock: data as ShowClock, at: performance.now() })
            break
          case 'point_clock':
            setPointClock({ clock: data as PointClock, at: Date.now() })
            break
          case 'showrunner':
            setShowrunner((l) => [...l, data].slice(-KEEP))
            break
          case 'supervisor':
            setSupervisor((l) => [...l, data].slice(-KEEP))
            break
          case 'alert':
            setAlerts((l) => [...l, { ...data, id: `a${++alertSeq.current}` }].slice(-20))
            break
          case 'level':
            remoteLevelRef.current = { level: Number(data.level) || 0, at: Date.now() }
            break
          case 'output_status':
            // Pengaman di klien: selain /stage tidak pernah memutar audio, apa pun kata server.
            ownerRef.current = role === 'stage' && data.is_audio_owner
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

  return { connected, snapshot, transcript, showrunner, supervisor, output, pointClock, showClock, lastTopicChange, lastNudge, speaking, alerts, sttPartial, micActive, level, audioBlocked, audioReady, unlockAudio, send }
}
