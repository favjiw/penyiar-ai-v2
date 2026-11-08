import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Pendengar suara penyiar dengan Web Speech API Chrome (`id-ID`, FR-7). Sejak v2.7 dipakai
 * hands-free: prompter menyalakannya saat giliran penyiar dan transkrip final dikirim otomatis
 * setelah jeda bicara (`autoSendSilenceMs`), beserta jeda → transkrip final (stt_ms).
 */

// Web Speech belum ada di lib DOM TypeScript.
interface SpeechRecognitionLike {
  lang: string
  interimResults: boolean
  continuous: boolean
  onresult: ((e: { resultIndex: number; results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }> }) => void) | null
  onend: (() => void) | null
  onerror: ((e: { error: string }) => void) | null
  start: () => void
  stop: () => void
  abort: () => void
}

const SR: (new () => SpeechRecognitionLike) | undefined =
  (window as unknown as { SpeechRecognition?: new () => SpeechRecognitionLike; webkitSpeechRecognition?: new () => SpeechRecognitionLike })
    .SpeechRecognition ??
  (window as unknown as { webkitSpeechRecognition?: new () => SpeechRecognitionLike }).webkitSpeechRecognition

export const speechSupported = !!SR

interface Options {
  onPartial: (text: string) => void
  onFinal: (text: string, sttMs: number, speechMs: number) => void
  /** Kirim transkrip otomatis setelah jeda bicara singkat tanpa perlu melepas/klik tombol. */
  autoSendSilenceMs?: number
  /** Nyalakan ulang mikrofon otomatis bila Web Speech berhenti saat hening. */
  keepAlive?: boolean
}

export function usePushToTalk({ onPartial, onFinal, autoSendSilenceMs = 0, keepAlive = false }: Options) {
  const [listening, setListening] = useState(false)
  const [error, setError] = useState('')
  /** Kode galat Web Speech terakhir (mis. audio-capture, not-allowed); kosong bila normal. */
  const [errorCode, setErrorCode] = useState('')
  const rec = useRef<SpeechRecognitionLike | null>(null)
  const finalText = useRef('')
  const interim = useRef('')
  const releasedAt = useRef(0)
  const startedAt = useRef(0)
  const firstSpeechAt = useRef(0)
  const silenceTimer = useRef<number | undefined>()
  const restartTimer = useRef<number | undefined>()
  const cancelled = useRef(false)
  const opts = useRef({ onPartial, onFinal, autoSendSilenceMs, keepAlive })
  opts.current = { onPartial, onFinal, autoSendSilenceMs, keepAlive }

  const clearTimers = () => {
    window.clearTimeout(silenceTimer.current)
    window.clearTimeout(restartTimer.current)
  }

  const start = useCallback(() => {
    if (!SR || rec.current) return
    clearTimers()
    setError('')
    setErrorCode('')
    finalText.current = ''
    interim.current = ''
    cancelled.current = false
    releasedAt.current = 0
    startedAt.current = performance.now()
    firstSpeechAt.current = 0
    const r = new SR()
    r.lang = 'id-ID'
    r.interimResults = true
    r.continuous = true
    r.onresult = (e) => {
      setErrorCode('')
      if (!firstSpeechAt.current) firstSpeechAt.current = performance.now()
      let partial = ''
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const res = e.results[i]
        if (res.isFinal) finalText.current += res[0].transcript + ' '
        else partial += res[0].transcript
      }
      interim.current = partial
      const combined = (finalText.current + partial).trim()
      opts.current.onPartial(combined)
      window.clearTimeout(silenceTimer.current)
      if (opts.current.autoSendSilenceMs > 0 && combined) {
        const waitMs = partial ? opts.current.autoSendSilenceMs + 500 : opts.current.autoSendSilenceMs
        silenceTimer.current = window.setTimeout(() => {
          if (rec.current) {
            releasedAt.current = performance.now()
            rec.current.stop()
          }
        }, waitMs)
      }
    }
    r.onerror = (e) => {
      if (e.error !== 'aborted' && e.error !== 'no-speech') {
        setError(`STT: ${e.error}`)
        setErrorCode(e.error)
      }
    }
    r.onend = () => {
      window.clearTimeout(silenceTimer.current)
      rec.current = null
      setListening(false)
      if (cancelled.current) return opts.current.onPartial('')
      // Kata terakhir yang belum final ikut dikirim, supaya ujung kalimat tidak hilang.
      const text = (finalText.current + interim.current).trim()
      if (text) {
        const endAt = releasedAt.current || performance.now()
        const beginAt = firstSpeechAt.current || startedAt.current
        opts.current.onFinal(text, Math.max(0, Math.round(performance.now() - endAt)), Math.max(0, Math.round(endAt - beginAt)))
      } else if (opts.current.keepAlive) {
        restartTimer.current = window.setTimeout(() => {
          if (opts.current.keepAlive && !rec.current) start()
        }, 250)
      }
    }
    try {
      rec.current = r
      r.start()
      setListening(true)
    } catch (e) {
      rec.current = null
      setListening(false)
      setError(`STT: ${e instanceof Error ? e.message : String(e)}`)
    }
  }, [])

  const stop = useCallback(() => {
    clearTimers()
    if (!rec.current) return
    releasedAt.current = performance.now()
    rec.current.stop()
  }, [])

  const cancel = useCallback(() => {
    clearTimers()
    if (!rec.current) return
    cancelled.current = true
    rec.current.abort()
  }, [])

  useEffect(
    () => () => {
      clearTimers()
      rec.current?.abort()
    },
    [],
  )

  return { listening, error, errorCode, start, stop, cancel }
}
