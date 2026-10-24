import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Push-to-talk dengan Web Speech API Chrome (`id-ID`, FR-7). Mulai saat tombol
 * ditekan, berhenti saat dilepas; transkrip final dikirim lewat onFinal beserta
 * waktu lepas-tombol → transkrip final (stt_ms). Esc membatalkan.
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
  onFinal: (text: string, sttMs: number) => void
}

export function usePushToTalk({ onPartial, onFinal }: Options) {
  const [listening, setListening] = useState(false)
  const [error, setError] = useState('')
  const rec = useRef<SpeechRecognitionLike | null>(null)
  const finalText = useRef('')
  const interim = useRef('')
  const releasedAt = useRef(0)
  const cancelled = useRef(false)
  const cb = useRef({ onPartial, onFinal })
  cb.current = { onPartial, onFinal }

  const start = useCallback(() => {
    if (!SR || rec.current) return
    setError('')
    finalText.current = ''
    interim.current = ''
    cancelled.current = false
    const r = new SR()
    r.lang = 'id-ID'
    r.interimResults = true
    r.continuous = true
    r.onresult = (e) => {
      let partial = ''
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const res = e.results[i]
        if (res.isFinal) finalText.current += res[0].transcript + ' '
        else partial += res[0].transcript
      }
      interim.current = partial
      cb.current.onPartial((finalText.current + partial).trim())
    }
    r.onerror = (e) => {
      if (e.error !== 'aborted' && e.error !== 'no-speech') setError(`STT: ${e.error}`)
    }
    r.onend = () => {
      rec.current = null
      setListening(false)
      if (cancelled.current) return cb.current.onPartial('')
      // Kata terakhir yang belum final ikut dikirim, supaya ujung kalimat tidak hilang.
      const text = (finalText.current + interim.current).trim()
      if (text) cb.current.onFinal(text, Math.round(performance.now() - releasedAt.current))
    }
    rec.current = r
    r.start()
    setListening(true)
  }, [])

  const stop = useCallback(() => {
    if (!rec.current) return
    releasedAt.current = performance.now()
    rec.current.stop()
  }, [])

  const cancel = useCallback(() => {
    if (!rec.current) return
    cancelled.current = true
    rec.current.abort()
  }, [])

  useEffect(() => () => rec.current?.abort(), [])

  return { listening, error, start, stop, cancel }
}
