/**
 * Layar untuk OBS (`/stage`, PRD v2.7 FR-10): hanya karakter, tanpa teks atau komponen,
 * dan satu-satunya pemutar audio siaran. Mode B: dua panel bertumpuk (9:16).
 * Mode A: satu panel AI (kamera studio ditumpuk di OBS).
 * Mode full free service: klip video persona (T1, gratis); bila klip belum ada di
 * assets/avatar, panel jatuh kembali ke karakter kartun 2D beranimasi.
 */
import { useCallback, useEffect, useState } from 'react'
import { useLiveSession } from '../live/useLiveSession'
import { AvatarPanel, type AvatarPersona } from './Avatar'
import { VideoAvatar } from './VideoAvatar'
import './stage.css'

const NAMES: Record<AvatarPersona, string> = { raka: 'Raka', salsa: 'Salsa' }
const isPersona = (x: unknown): x is AvatarPersona => x === 'raka' || x === 'salsa'

export function StagePage() {
  const live = useLiveSession('stage')
  const { snapshot: snap, speaking, level, audioReady, unlockAudio, output, send, connected, transcript } = live
  const params = new URLSearchParams(window.location.search)
  const [noVideo, setNoVideo] = useState<Partial<Record<AvatarPersona, boolean>>>({})
  const markNoVideo = useCallback((id: AvatarPersona) => setNoVideo((v) => (v[id] ? v : { ...v, [id]: true })), [])
  const lastTurn = transcript[transcript.length - 1]

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

  const shown = personas.join(',')
  useEffect(() => {
    if (!connected) return
    const active = Object.fromEntries(shown.split(',').map((p) => [p, noVideo[p as AvatarPersona] ? '2d' : 'video']))
    send('avatar_state', { personas: active })
  }, [shown, noVideo, send, connected])

  return (
    <div className={`stage stage--${mode === 'A' ? 'a' : 'b'}`}>
      {personas.map((p) =>
        noVideo[p] ? (
          <AvatarPanel key={p} persona={p} name={NAMES[p]} speaking={speaking === p} getLevel={level} />
        ) : (
          <div key={p} className="stage-panel">
            <VideoAvatar
              persona={p}
              // Mode A: penyiar manusia yang banyak bicara, jadi AI terlihat mendengarkan saat diam.
              mode={speaking === p ? 'talk' : speaking || mode === 'A' ? 'listen' : 'idle'}
              emotion={lastTurn?.persona === p ? lastTurn.emotion : null}
              onUnavailable={() => markNoVideo(p)}
            />
          </div>
        ),
      )}

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
