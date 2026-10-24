import { useEffect } from 'react'
import { useLiveSession } from '../live/useLiveSession'
import { COVERED_ZONES, pct, SIDE_MARGIN } from './layout'
import './stage.css'

const PANELS = [
  { id: 'raka', name: 'Raka' },
  { id: 'salsa', name: 'Salsa' },
]

/**
 * Stage sementara Tahap 2: kanvas 9:16 untuk OBS dengan HUD dan audio, tanpa video.
 * Avatar video (FR-8) menggantikan placeholder panel di Tahap 3.
 * `?clean=1` menyembunyikan info debug, `?zones=1` menampilkan zona tertutup TikTok.
 */
export function StagePage() {
  const params = new URLSearchParams(location.search)
  const clean = params.has('clean')
  const zones = params.has('zones')
  const live = useLiveSession('stage')
  const { snapshot: snap, speaking, output } = live
  const topic = snap.segment === 'topic' ? snap.topic : null
  const segmentLabel = snap.segment === 'opening' ? 'Opening' : snap.segment === 'closing' ? 'Closing' : topic?.judul

  useEffect(() => {
    document.title = 'Stage · Penyiar AI'
  }, [])

  return (
    <div className="stage-root" onClick={live.audioBlocked ? live.unlockAudio : undefined}>
      <div className="canvas">
        {PANELS.map((p, i) => (
          <div key={p.id} className={`panel-av ${i === 0 ? 'top' : 'bottom'} ${speaking === p.id ? 'speaking' : ''}`}>
            <div className="placeholder" aria-hidden>
              {p.name[0]}
            </div>
            <div className="nameplate">
              <span className="ai-label">AI</span>
              <span className="name">{p.name}</span>
              {speaking === p.id && <span className="eq" aria-label="sedang bicara">●●●</span>}
            </div>
          </div>
        ))}

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
