/** Status TTS dari backend (`FailoverTTS.status()`), dipakai label operator. */
export interface TtsStatus {
  primary: string
  fallback: string | null
  fallbacks?: string[]
  breaker_open: boolean
  credits_used: number
  fallback_uses?: number
  last_provider?: string | null
  warnings?: string[]
}

const LABELS: Record<string, string> = {
  edge: 'Edge (gratis)',
  elevenlabs: 'ElevenLabs',
  gtts: 'gTTS (gratis)',
  mock: 'mock (hening)',
}

export const ttsName = (id: string) => LABELS[id] ?? id

/** Label kecil untuk operator, mis. "TTS: Edge (gratis)" atau "TTS: ElevenLabs → Edge (gratis) aktif". */
export function ttsLabel(tts: TtsStatus | null | undefined): string {
  if (!tts) return 'TTS: memeriksa…'
  const using = tts.last_provider && tts.last_provider !== tts.primary ? tts.last_provider : null
  if (tts.breaker_open && tts.fallback) return `TTS: ${ttsName(tts.primary)} → ${ttsName(tts.fallback)} aktif (utama dilewati)`
  if (using) return `TTS: ${ttsName(tts.primary)} → ${ttsName(using)} aktif`
  return `TTS: ${ttsName(tts.primary)}`
}
