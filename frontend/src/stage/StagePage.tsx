import { useCallback, useEffect, useState } from 'react'
import { useLiveSession } from '../live/useLiveSession'
import { COVERED_ZONES, pct, SIDE_MARGIN } from './layout'
import { VideoAvatar } from './VideoAvatar'
import './stage.css'

const NAMES: Record<string, string> = { raka: 'Raka', salsa: 'Salsa' }
const MODE_B_PANELS = ['raka', 'salsa']

/**
 * Stage 9:16 untuk OBS (FR-10): avatar video T1 (FR-8) per panel, HUD, dan audio.
 * Bila klip persona belum ada (manifest tidak ditemukan), panel memakai placeholder.
 * `?clean=1` menyembunyikan info debug, `?zones=1` menampilkan zona tertutup TikTok.
 */
export function StagePage() {
  const params = new URLSearchParams(location.search)
  const clean = params.has('clean')
  const zones = params.has('zones')
  const live = useLiveSession('stage')
  const { snapshot: snap, speaking, output, transcript } = live
  const [noVideo, setNoVideo] = useState<Record<string, boolean>>({})
  const markNoVideo = useCallback((id: string) => setNoVideo((v) => (v[id] ? v : { ...v, [id]: true })), [])
  const lastTurn = transcript[transcript.length - 1]
  // Mode A (FR-10): panel atas untuk kamera studio (source OBS terpisah, area transparan), panel bawah avatar AI.
  const modeA = snap.mode === 'A' && !!snap.ai_persona
  const panels: (string | null)[] = modeA ? [null, snap.ai_persona as string] : MODE_B_PANELS
  const topic = snap.segment === 'topic' ? snap.topic : null
  const segmentLabel = snap.segment === 'opening' ? 'Opening' : snap.segment === 'closing' ? 'Closing' : topic?.judul

  useEffect(() => {
    document.title = 'Stage · Penyiar AI'
  }, [])

  return (
    <div className={`stage-root ${modeA ? 'mode-a' : ''}`} onClick={live.audioBlocked ? live.unlockAudio : undefined}>
      <div className="canvas">
        {panels.map((id, i) =>
          id === null ? (
            <div key="camera" className="panel-av top camera" aria-label="area kamera studio" />
          ) : (
            <div key={id} className={`panel-av ${i === 0 ? 'top' : 'bottom'} ${speaking === id ? 'speaking' : ''}`}>
              {noVideo[id] ? (
                <div className="placeholder" aria-hidden>
                  {NAMES[id]?.[0] ?? '?'}
                </div>
              ) : (
                <VideoAvatar
                  persona={id}
                  // Mode A: penyiar manusia yang banyak bicara, jadi AI terlihat mendengarkan saat diam.
                  mode={speaking === id ? 'talk' : speaking || modeA ? 'listen' : 'idle'}
                  emotion={lastTurn?.persona === id ? lastTurn.emotion : null}
                  turnKey={lastTurn?.persona === id ? lastTurn.turn : null}
                  onUnavailable={() => markNoVideo(id)}
                />
              )}
              <div className="nameplate">
                <span className="ai-label">AI</span>
                <span className="name">{NAMES[id] ?? id}</span>
                {speaking === id && <span className="eq" aria-label="sedang bicara">●●●</span>}
              </div>
            </div>
          ),
        )}

        <div className="hud">
          <div className="program-pill">HITS UNIKOM RADIO · LIVE</div>
          {segmentLabel && <div className="topic-title">{segmentLabel}</div>}
          {/* Closing memakai ajakan blocker di field yang sama */}
          {snap.segment !== 'opening' && snap.topic?.pertanyaan_penonton && <div className="question">❓ {snap.topic.pertanyaan_penonton}</div>}
        </div>

        {zones &&
          COVERED_ZONES.map((z) => (
            <div
              key={z.id}
              className="zone"
              style={{ left: pct(z.rect.x0), top: pct(z.rect.y0), width: pct(z.rect.x1 - z.rect.x0), height: pct(z.rect.y1 - z.rect.y0) }}
            >
              {z.label}
            </div>
          ))}
        {zones && (
          <>
            <div className="zone side" style={{ left: 0, width: pct(SIDE_MARGIN) }} />
            <div className="zone side" style={{ right: 0, width: pct(SIDE_MARGIN) }} />
          </>
        )}

        {live.audioBlocked && <div className="unlock">Klik di mana saja untuk mengaktifkan audio</div>}
        {!clean && (
          <div className="debug">
            {live.connected ? 'WS ✓' : 'WS ✗'} · {snap.state} · audio: {output?.is_audio_owner ? 'stage ini' : output?.audio_owner_role ?? '-'}
          </div>
        )}
      </div>
    </div>
  )
}
