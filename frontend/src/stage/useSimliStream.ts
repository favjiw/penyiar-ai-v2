/**
 * Sambungan avatar Simli untuk satu panel karakter di /stage. Tanpa klik dan tanpa teks: tersambung sendiri
 * saat layar dibuka, menyambung ulang bila putus (jeda 5 s, berlipat dua sampai 60 s), dan selama belum
 * tersambung panel memakai karakter 2D sebagai cadangan. Kunci API tetap di server; browser hanya menerima token sesi.
 *
 * Suara: begitu elemen audio Simli benar-benar memutar, suara lokal persona ini dibisukan (supaya tidak ada gema);
 * bila Simli putus atau audionya berhenti, suara lokal menyala lagi, jadi siaran tidak pernah hening karena avatar.
 */
import { useEffect, useRef, useState } from 'react'
import { LogLevel, SimliClient } from 'simli-client'
import { ApiError, api } from '../api'

/** simli: video realistis tampil; connecting: menyambung; fallback: Simli gagal/putus (2D sementara); 2d: kartun 2D dipilih operator. */
export type AvatarState = 'simli' | 'connecting' | 'fallback' | '2d'

const RETRY_MIN_MS = 5_000
const RETRY_MAX_MS = 60_000

export function useSimliStream(
  persona: string,
  getAudioTrack: (persona: string) => MediaStreamTrack | null,
  setLocalMuted: (persona: string, muted: boolean) => void,
  audioReady: boolean,
  enabled = true,
) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const audioRef = useRef<HTMLAudioElement>(null)
  // connecting: percobaan pertama; connected: sesi tersambung; failed: putus/gagal (menunggu sambung ulang); off: Simli tidak dikonfigurasi.
  const [phase, setPhase] = useState<'connecting' | 'connected' | 'failed' | 'off'>('connecting')
  const [videoReady, setVideoReady] = useState(false) // frame video pertama sudah tampil

  // Fungsi dari useLiveSession stabil, tetapi simpan lewat ref agar efek sambungan tidak ikut dimulai ulang.
  const track = useRef(getAudioTrack)
  const mute = useRef(setLocalMuted)
  track.current = getAudioTrack
  mute.current = setLocalMuted

  useEffect(() => {
    if (!enabled) return // kartun 2D dipilih: tidak membuka sesi Simli sama sekali (hemat kuota)
    setPhase('connecting')
    let alive = true
    let client: SimliClient | null = null
    let timer: number | undefined
    let attempt = 0
    const video = videoRef.current
    const audio = audioRef.current

    const onAudioPlaying = () => mute.current(persona, true)
    const onAudioStopped = () => mute.current(persona, false)
    const onVideoPlaying = () => setVideoReady(true)
    audio?.addEventListener('playing', onAudioPlaying)
    audio?.addEventListener('pause', onAudioStopped)
    audio?.addEventListener('emptied', onAudioStopped)
    video?.addEventListener('playing', onVideoPlaying)

    const teardown = () => {
      mute.current(persona, false)
      setVideoReady(false)
      const c = client
      client = null // handler 'stop' membedakan penutupan sendiri dari putus tak terduga lewat ini
      if (c) void c.stop().catch(() => undefined)
    }

    const retryLater = () => {
      if (!alive) return
      const delay = Math.min(RETRY_MAX_MS, RETRY_MIN_MS * 2 ** attempt)
      attempt += 1
      timer = window.setTimeout(() => void connect(), delay)
    }

    const fail = (c: SimliClient | null) => {
      if (!alive || (c && c !== client)) return
      teardown()
      setPhase('failed')
      retryLater()
    }

    const connect = async () => {
      if (!alive || !video || !audio) return
      let c: SimliClient | null = null
      try {
        const { session_token } = await api.simliToken(persona)
        if (!alive) return
        c = new SimliClient(session_token, video, audio, null, LogLevel.ERROR, 'livekit')
        client = c
        const current = c
        // Alasan dicatat di konsol browser (bukan ke server) supaya wajah/akun yang bermasalah mudah dilacak.
        c.on('error', (detail) => { console.warn(`[simli:${persona}] error`, detail); fail(current) })
        c.on('startup_error', (detail) => { console.warn(`[simli:${persona}] startup_error`, detail); fail(current) })
        c.on('stop', () => { if (client === current) console.warn(`[simli:${persona}] stop tak terduga`); fail(current) })
        await c.start()
        if (!alive || client !== c) return
        const t = track.current(persona)
        if (t) c.listenToMediastreamTrack(t)
        attempt = 0
        setPhase('connected')
        void audio.play().catch(() => undefined) // bila diblokir autoplay, dicoba lagi saat suara dinyalakan (efek di bawah)
      } catch (e) {
        if (e instanceof ApiError && e.status === 400) {
          // SIMLI_API_KEY belum diisi: pakai karakter 2D tanpa mencoba lagi.
          setPhase('off')
          return
        }
        console.warn(`[simli:${persona}] gagal tersambung`, e)
        fail(c)
      }
    }

    void connect()
    return () => {
      alive = false
      window.clearTimeout(timer)
      audio?.removeEventListener('playing', onAudioPlaying)
      audio?.removeEventListener('pause', onAudioStopped)
      audio?.removeEventListener('emptied', onAudioStopped)
      video?.removeEventListener('playing', onVideoPlaying)
      teardown()
    }
  }, [persona, enabled])

  // Autoplay: suara Simli baru boleh diputar setelah satu klik di layar OBS (stage-unlock, atau klik di mana pun saat live).
  useEffect(() => {
    if (audioReady && phase === 'connected') void audioRef.current?.play().catch(() => undefined)
  }, [audioReady, phase])

  const state: AvatarState = !enabled ? '2d' : phase === 'connected' && videoReady ? 'simli' : phase === 'connecting' || phase === 'connected' ? 'connecting' : 'fallback'
  return { videoRef, audioRef, state }
}
