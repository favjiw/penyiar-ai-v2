/**
 * Layar untuk OBS (`/stage`, PRD v2.7 FR-10): hanya karakter, tanpa teks atau komponen,
 * dan satu-satunya pemutar audio siaran. Mode B: dua panel bertumpuk (9:16).
 * Mode A: satu panel AI (kamera studio ditumpuk di OBS).
 */
import { useEffect } from 'react'
import { useLiveSession } from '../live/useLiveSession'
import { AvatarPanel, type AvatarPersona } from './Avatar'
import './stage.css'

const NAMES: Record<AvatarPersona, string> = { raka: 'Raka', salsa: 'Salsa' }
const isPersona = (x: unknown): x is AvatarPersona => x === 'raka' || x === 'salsa'

export function StagePage() {
  const live = useLiveSession('stage')
  const { snapshot: snap, speaking, level, audioReady, unlockAudio, output } = live
  const params = new URLSearchParams(window.location.search)

  useEffect(() => {
    document.title = 'Layar untuk OBS · Penyiar AI HITS'
  }, [])

  // Sebelum siaran, mode dan persona mengikuti parameter dari konsol (?mode=A&ai=salsa).
  const mode = snap.mode ?? (params.get('mode') === 'A' ? 'A' : 'B')
  const aiParam = params.get('ai')
  const soloAi: AvatarPersona = isPersona(snap.ai_persona) ? snap.ai_persona : isPersona(aiParam) ? aiParam : 'salsa'
  const personas: AvatarPersona[] = mode === 'A' ? [soloAi] : ['raka', 'salsa']
  const onAir = snap.state === 'live' || snap.state === 'paused'
  const showArm = !onAir && !audioReady && output?.is_audio_owner === true

  return (
    <div className={`stage stage--${mode === 'A' ? 'a' : 'b'}`}>
      {personas.map((p) => (
        <AvatarPanel key={p} persona={p} name={NAMES[p]} speaking={speaking === p} getLevel={level} />
      ))}
      {/* Satu-satunya elemen non-karakter, dan hanya SEBELUM live: browser butuh satu klik di
          jendela ini supaya suara AI boleh diputar. Saat on air tidak pernah tampil (tanpa teks);
          klik di mana pun pada jendela tetap menyalakan suara, dan konsol yang memberi tahu operator. */}
      {showArm && (
        <button type="button" className="stage-unlock" onClick={unlockAudio}>
          <span>Klik sekali untuk menyalakan suara AI</span>
        </button>
      )}
    </div>
  )
}
