import { useEffect, useState } from 'react'

/** Lama sunyi-digital (sinyal nol, bukan sekadar ruangan sepi) sebelum dianggap mic putus. */
export const MIC_DEAD_AFTER_MS = 8000
const DEAD_RMS = 1e-6 // praktis nol: hanya perangkat lepas/driver diam total, bukan ruangan sepi atau noise gate ringan
const SILENCE_RMS = 0.02
const FULL_RMS = 0.3

export interface MicState {
  /** Level 0..1 dari mic sungguhan (untuk bar level); 0 saat hening. */
  level: number
  /** Mic tidak terdengar: izin ditolak, perangkat lepas, atau sinyal nol ≥8 dtk. */
  down: boolean
  reason: '' | 'denied' | 'ended' | 'silent' | 'unavailable'
  /** Nama perangkat input bawaan yang dipakai Chrome (Web Speech juga memakai yang ini). */
  device: string
}

/**
 * Pantau mikrofon studio di prompter lewat getUserMedia + AnalyserNode (HANDOFF §2):
 * bar level mengikuti suara asli, dan mic yang putus terdeteksi tanpa menunggu STT.
 * Web Speech tidak memberi akses ke stream-nya, jadi stream ini dibuka terpisah.
 */
export function useMicMonitor(enabled: boolean): MicState {
  // Dimatikan saat jeda/selesai oleh pemanggil (enabled=false) supaya cek sunyi 8 dtk tidak jalan.
  const [state, setState] = useState<MicState>({ level: 0, down: false, reason: '', device: '' })

  useEffect(() => {
    if (!enabled) {
      setState({ level: 0, down: false, reason: '', device: '' })
      return
    }
    let stopped = false
    let stream: MediaStream | null = null
    let ctx: AudioContext | null = null
    let raf = 0
    let device = ''
    const set = (partial: Omit<MicState, 'device'>) => {
      const s = { ...partial, device }
      if (!stopped) setState((prev) => (prev.level === s.level && prev.down === s.down && prev.reason === s.reason && prev.device === s.device ? prev : s))
    }

    ;(async () => {
      if (!navigator.mediaDevices?.getUserMedia) return set({ level: 0, down: true, reason: 'unavailable' })
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false } })
      } catch {
        return set({ level: 0, down: true, reason: 'denied' })
      }
      if (stopped) return stream.getTracks().forEach((t) => t.stop())
      const track = stream.getAudioTracks()[0]
      device = track?.label ?? ''
      track?.addEventListener('ended', () => set({ level: 0, down: true, reason: 'ended' }))
      ctx = new AudioContext()
      void ctx.resume()
      const analyser = ctx.createAnalyser()
      analyser.fftSize = 1024
      ctx.createMediaStreamSource(stream).connect(analyser)
      const buf = new Float32Array(analyser.fftSize)
      let deadSince = performance.now()
      let ended = false
      track?.addEventListener('ended', () => (ended = true))
      const tick = () => {
        analyser.getFloatTimeDomainData(buf)
        let sum = 0
        for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i]
        const rms = Math.sqrt(sum / buf.length)
        const now = performance.now()
        // AudioContext yang masih suspended membaca nol: jangan dihitung sebagai mic putus.
        if (rms > DEAD_RMS || ctx?.state !== 'running') deadSince = now
        const level = rms < SILENCE_RMS ? 0 : Math.round(Math.min(1, (rms - SILENCE_RMS) / (FULL_RMS - SILENCE_RMS)) * 20) / 20
        if (ended) set({ level: 0, down: true, reason: 'ended' })
        else if (now - deadSince >= MIC_DEAD_AFTER_MS) set({ level: 0, down: true, reason: 'silent' })
        else set({ level, down: false, reason: '' })
        raf = requestAnimationFrame(tick)
      }
      raf = requestAnimationFrame(tick)
    })()

    return () => {
      stopped = true
      cancelAnimationFrame(raf)
      stream?.getTracks().forEach((t) => t.stop())
      void ctx?.close()
    }
  }, [enabled])

  return state
}
