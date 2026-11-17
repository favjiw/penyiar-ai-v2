/**
 * Layar untuk OBS (`/stage`, PRD v2.7 FR-10): hanya karakter, tanpa teks atau komponen,
 * dan satu-satunya pemutar audio siaran. Mode B: dua panel bertumpuk (9:16).
 * Mode A: satu panel AI (kamera studio ditumpuk di OBS).
 * Karakternya avatar Simli per panel; karakter 2D menjadi cadangan otomatis (Avatar.tsx).
 */
import { useCallback, useEffect, useState } from 'react'
import { useLiveSession } from '../live/useLiveSession'
import { AvatarPanel, type AvatarPersona } from './Avatar'
import type { AvatarState } from './useSimliStream'
import './stage.css'

const NAMES: Record<AvatarPersona, string> = { raka: 'Raka', salsa: 'Salsa' }
const isPersona = (x: unknown): x is AvatarPersona => x === 'raka' || x === 'salsa'

export function StagePage() {
  const live = useLiveSession('stage')
  const { snapshot: snap, speaking, level, audioReady, unlockAudio, output, send, connected, getAudioTrack, setLocalMuted } = live
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

  // Status avatar tiap panel dilaporkan ke server; konsol memberi peringatan kuning bila ada yang jatuh ke karakter 2D.
  const [avatars, setAvatars] = useState<Record<string, AvatarState>>({})
  const onAvatarState = useCallback((persona: string, state: AvatarState) => setAvatars((a) => (a[persona] === state ? a : { ...a, [persona]: state })), [])
  const shown = personas.join(',')
  useEffect(() => {
    if (!connected) return // kirim ulang setiap kali sambungan WS (kembali) terbuka: server tidak menyimpannya antar sambungan
    const active = Object.fromEntries(Object.entries(avatars).filter(([p]) => shown.split(',').includes(p)))
    send('avatar_state', { personas: active })
  }, [avatars, shown, send, connected])

  return (
    <div className={`stage stage--${mode === 'A' ? 'a' : 'b'}`}>
      {personas.map((p) => (
        <AvatarPanel
          key={p}
          persona={p}
          name={NAMES[p]}
          speaking={speaking === p}
          getLevel={level}
          getAudioTrack={getAudioTrack}
          setLocalMuted={setLocalMuted}
          audioReady={audioReady}
          onAvatarState={onAvatarState}
        />
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
