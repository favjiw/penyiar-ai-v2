import { useEffect, useState } from 'react'

/** Sumber level: AnalyserNode yang sudah tersambung (audio TTS), atau MediaStream (mic dari mixer). */
export type LevelSource = AnalyserNode | MediaStream | null | undefined

const SILENCE_RMS = 0.02 // di bawah ini dianggap hening → bar diam rata rendah
const FULL_RMS = 0.3 // RMS segini sudah dianggap level penuh

/**
 * Level audio 0..1 dari RMS sinyal (Web Audio AnalyserNode, diukur tiap frame lewat rAF).
 * Untuk MediaStream, hook membuat AudioContext + analyser sendiri lalu menutupnya saat dilepas.
 * Tanpa sumber → 0. Dipakai oleh `LevelBars`; sumbernya terpisah supaya komponen tidak peduli
 * asal audio (mic penyiar, audio TTS di /stage, atau level yang dikirim lewat WS).
 */
export function useAudioLevel(source: LevelSource): number {
  const [level, setLevel] = useState(0)

  useEffect(() => {
    if (!source) {
      setLevel(0)
      return
    }
    let ctx: AudioContext | null = null
    let analyser: AnalyserNode
    if (source instanceof MediaStream) {
      ctx = new AudioContext()
      void ctx.resume() // Chrome bisa membuatnya "suspended" bila dibuat di luar gestur pengguna
      analyser = ctx.createAnalyser()
      analyser.fftSize = 1024
      ctx.createMediaStreamSource(source).connect(analyser)
    } else {
      analyser = source // milik pemanggil (mis. jalur TTS): fftSize tidak diubah
    }
    const buf = new Float32Array(analyser.fftSize)
    let raf = 0
    let last = -1
    const tick = () => {
      analyser.getFloatTimeDomainData(buf)
      let sum = 0
      for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i]
      const rms = Math.sqrt(sum / buf.length)
      const lv = rms < SILENCE_RMS ? 0 : Math.min(1, (rms - SILENCE_RMS) / (FULL_RMS - SILENCE_RMS))
      const q = Math.round(lv * 20) / 20 // kuantisasi supaya tidak render ulang tiap frame tanpa perubahan
      if (q !== last) {
        last = q
        setLevel(q)
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => {
      cancelAnimationFrame(raf)
      setLevel(0)
      void ctx?.close()
    }
  }, [source])

  return level
}
