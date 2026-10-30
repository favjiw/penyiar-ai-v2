import type { LiveSession } from '../live/useLiveSession'
import { MicIndicator, Orb, type OrbState } from './Orb'

const NAMES: Record<string, string> = { raka: 'Raka', salsa: 'Salsa' }
const DEFAULT_AI = ['raka', 'salsa']

interface Props {
  live: LiveSession
  /** Mode yang dipilih di form Mulai; dipakai sebelum siaran berjalan. */
  previewMode: string
  previewAi: string
  previewHuman: string
}

/**
 * Indikator giliran bicara pengganti avatar: satu orb per penyiar AI (mode A: 1, B dan C: 2)
 * dan indikator mikrofon kecil untuk penyiar manusia (mode A dan C). Daftar peserta berupa
 * list, jadi mode dengan lebih dari dua AI cukup menambah isinya.
 */
export function VoiceStage({ live, previewMode, previewAi, previewHuman }: Props) {
  const { snapshot: snap, speaking, transcript, sttPartial, micActive, awaiting, level } = live
  const onAir = snap.state === 'live'
  const mode = snap.state === 'idle' || snap.state === 'ended' ? previewMode : snap.mode ?? previewMode
  const hasHuman = mode === 'A' || mode === 'C'
  const aiIds = mode === 'A' ? [snap.ai_persona ?? previewAi] : (snap.personas?.map((p) => p.id) ?? DEFAULT_AI)
  const humanName = snap.human?.name ?? (previewHuman || 'Penyiar')
  const humanActive = micActive || !!sttPartial
  const lastAi = [...transcript].reverse().find((t) => t.persona !== 'human')?.persona

  const stateOf = (id: string): OrbState => {
    if (!onAir) return 'idle' // belum mulai, pause, atau selesai
    if (speaking === id) return 'speaking'
    if (hasHuman) {
      if (humanActive) return 'listening'
      if (awaiting && speaking === null) return 'thinking' // menunggu LLM/TTS
      return 'listening' // menunggu manusia, atau AI lain sedang bicara
    }
    // Mode B: yang berikutnya bicara sedang menyiapkan giliran (pipelining), yang lain mendengarkan.
    if (speaking) return 'listening'
    const next = lastAi ? aiIds.find((x) => x !== lastAi) : aiIds[0]
    return id === next ? 'thinking' : 'listening'
  }

  const segment = snap.segment === 'topic' ? snap.topic?.judul : snap.segment === 'closing' ? 'Closing' : snap.segment === 'opening' ? 'Opening' : null

  return (
    <section className="panel voice-stage" aria-label="Indikator giliran bicara">
      <div className="vs-head">
        <h2>Giliran bicara</h2>
        {onAir && segment && <span className="angle">Topik aktif: {segment}</span>}
      </div>
      <div className="vs-row">
        {aiIds.map((id) => (
          <Orb key={id} persona={id} name={NAMES[id] ?? id} state={stateOf(id)} getLevel={level} />
        ))}
      </div>
      {hasHuman && (
        <div className="vs-human">
          <MicIndicator name={humanName} active={onAir && humanActive} />
        </div>
      )}
    </section>
  )
}
