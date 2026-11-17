import { useEffect, useRef, useState } from 'react'
import { LogLevel, SimliClient } from 'simli-client'
import { api } from '../api'

interface SimliAvatarProps {
  persona: 'raka' | 'salsa'
  name: string
  audioReady?: boolean
  getAudioTrack: () => MediaStreamTrack | null
  setLocalMuted: (muted: boolean) => void
  onToggle2D?: () => void
}

export function SimliAvatar({
  name,
  getAudioTrack,
  setLocalMuted,
  onToggle2D,
}: SimliAvatarProps) {
  const [status, setStatus] = useState<'idle' | 'connecting' | 'connected' | 'error'>('idle')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [elapsedSec, setElapsedSec] = useState(0)

  const videoRef = useRef<HTMLVideoElement>(null)
  const audioRef = useRef<HTMLAudioElement>(null)
  const clientRef = useRef<SimliClient | null>(null)
  const timerRef = useRef<number | null>(null)

  const stopSimli = () => {
    if (timerRef.current) {
      window.clearInterval(timerRef.current)
      timerRef.current = null
    }
    if (clientRef.current) {
      void clientRef.current.stop().catch(() => {})
      clientRef.current = null
    }
    setLocalMuted(false)
    setStatus('idle')
  }

  const startSimli = async () => {
    if (clientRef.current) return
    setStatus('connecting')
    setErrorMsg(null)

    try {
      const { session_token } = await api.simliToken()
      if (!videoRef.current || !audioRef.current) return

      const client = new SimliClient(
        session_token,
        videoRef.current,
        audioRef.current,
        null, // iceServers (null = livekit transport)
        LogLevel.DEBUG,
        'livekit'
      )
      clientRef.current = client

      client.on('error', (detail: string) => {
        setStatus('error')
        setErrorMsg(detail || 'Koneksi Simli gagal')
        setLocalMuted(false)
      })

      client.on('startup_error', (detail: string) => {
        setStatus('error')
        setErrorMsg(detail || 'Gagal memulai Simli')
        setLocalMuted(false)
      })

      client.on('stop', () => {
        stopSimli()
      })

      await client.start()

      // Sambungkan track audio TTS ke Simli worklet
      const track = getAudioTrack()
      if (track) {
        client.listenToMediastreamTrack(track)
      }

      setStatus('connected')
      setLocalMuted(true)
      setElapsedSec(0)

      // Mulai timer pelindung durasi uji coba
      timerRef.current = window.setInterval(() => {
        setElapsedSec((s) => {
          if (s >= 300) {
            // Cap 5 menit tercapai
            stopSimli()
            return s
          }
          return s + 1
        })
      }, 1000)
    } catch (err: any) {
      setStatus('error')
      setErrorMsg(err.message || String(err))
      setLocalMuted(false)
    }
  }

  useEffect(() => {
    return () => {
      stopSimli()
    }
  }, [])

  const formatTime = (sec: number) => {
    const m = Math.floor(sec / 60)
    const s = sec % 60
    return `${m}:${s < 10 ? '0' : ''}${s}`
  }

  return (
    <div className="simli-container">
      {/* Elemen Video & Audio Simli */}
      <video
        ref={videoRef}
        autoPlay
        playsInline
        className={`simli-video ${status === 'connected' ? 'is-visible' : 'is-hidden'}`}
      />
      <audio ref={audioRef} autoPlay />

      {/* Kontrol & Status Overlay */}
      <div className="simli-hud">
        <div className="simli-badge-group">
          <span className={`simli-status-dot is-${status}`} />
          <span className="simli-status-text">
            {status === 'idle' && 'Simli: Belum Terhubung'}
            {status === 'connecting' && 'Simli: Menghubungkan…'}
            {status === 'connected' && `Simli Realtime (${formatTime(elapsedSec)} / 05:00)`}
            {status === 'error' && 'Simli: Gangguan'}
          </span>
        </div>

        <div className="simli-actions">
          {status === 'idle' && (
            <button
              type="button"
              className="simli-btn simli-btn--primary"
              onClick={startSimli}
            >
              Mulai Simli ({name})
            </button>
          )}

          {status === 'connected' && (
            <button
              type="button"
              className="simli-btn simli-btn--danger"
              onClick={stopSimli}
            >
              Putus Simli (Hemat Kuota)
            </button>
          )}

          {status === 'error' && (
            <button
              type="button"
              className="simli-btn simli-btn--primary"
              onClick={startSimli}
            >
              Coba Lagi
            </button>
          )}

          {onToggle2D && (
            <button
              type="button"
              className="simli-btn simli-btn--secondary"
              onClick={() => {
                stopSimli()
                onToggle2D()
              }}
            >
              Kembali ke 2D
            </button>
          )}
        </div>

        {errorMsg && <div className="simli-error">{errorMsg}</div>}
      </div>

      {status !== 'connected' && (
        <div className="simli-placeholder">
          <div className="simli-placeholder__avatar">👤</div>
          <p className="simli-placeholder__hint">
            {status === 'connecting'
              ? 'Memuat stream avatar realistis dari Simli...'
              : 'Klik "Mulai Simli" untuk menghubungkan avatar visual realistis.'}
          </p>
        </div>
      )}
    </div>
  )
}
