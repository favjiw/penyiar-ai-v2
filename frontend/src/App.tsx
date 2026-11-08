import { lazy, Suspense, useEffect, useState } from 'react'
import { api } from './api'
import { LivePanel } from './console/LivePanel'
import { PrepPage } from './console/prep/PrepPage'
import { ttsLabel, type TtsStatus } from './live/tts'
import { useLiveSession, type LiveSession } from './live/useLiveSession'
import { NotFound } from './NotFound'
import { PrompterPage } from './prompter/PrompterPage'
import { StagePage } from './stage/StagePage'
import { IconAlert } from './ui'

type Health = { llm: string; tts?: TtsStatus } | 'down' | null

/** Status backend: dari /api/health, lalu dari snapshot siaran (lebih baru: cadangan aktif, breaker). */
function useHealth(live: LiveSession) {
  const [health, setHealth] = useState<Health>(null)
  const state = live.snapshot.state
  useEffect(() => {
    api
      .health()
      .then((h) => setHealth({ llm: h.llm_mode, tts: h.tts }))
      .catch(() => setHealth('down'))
  }, [state, live.connected])
  const tts = live.snapshot.tts ?? (health && health !== 'down' ? health.tts : undefined)
  return { health, tts }
}

/**
 * Nama model/vendor dan pesan mentah hanya di "Detail teknis" (DESIGN.md §5), untuk peneliti.
 * Peringatan suara tetap terlihat sebagai tanda kecil di judulnya.
 */
function TechDetails({ health, tts }: { health: Health; tts?: TtsStatus }) {
  const warnings = tts?.warnings ?? []
  return (
    <details className="tech">
      <summary>
        Detail teknis{warnings.length > 0 && <span className="tech__badge">{warnings.length} catatan</span>}
      </summary>
      <div className="tech__body">
        <div>{health === 'down' ? 'Server tidak tersambung' : `LLM ${health ? health.llm : '…'} · ${ttsLabel(tts)}`}</div>
        {tts?.fallbacks?.length ? <div>Cadangan suara: {tts.fallbacks.join(', ')}</div> : null}
        {warnings.map((w) => (
          <div key={w} className="tech__warn">
            {w}
          </div>
        ))}
      </div>
    </details>
  )
}

function Console() {
  // Konsol selalu tersambung tetapi bisu; audio hanya diputar di /stage (PRD v2.7 FR-10).
  const live = useLiveSession('console')
  const { health, tts } = useHealth(live)
  const onAir = live.snapshot.state === 'live' || live.snapshot.state === 'paused'

  useEffect(() => {
    document.title = onAir ? 'LIVE · Penyiar AI HITS' : 'Siapkan siaran · Penyiar AI HITS'
  }, [onAir])

  // Saat live, panel live memakai header sendiri (LIVE + kontrol siaran, mockup KonsolLive).
  if (onAir) return <LivePanel live={live} />

  return (
    <div className="console">
      <PrepPage
        live={live}
        headerExtras={
          <>
            {!live.connected && (
              <span className="console-top__offline" role="status">
                Menyambung ke server…
              </span>
            )}
            <TechDetails health={health} tts={tts} />
          </>
        }
      />
      {/* Peringatan suara tetap terlihat (FR-6) sebelum live; saat live, konsol live punya peringatan sendiri. */}
      {(tts?.warnings ?? []).length > 0 && (
        <div className="console-warn console-warn--float" role="status">
          <IconAlert size={20} />
          <span>Ada catatan soal suara AI: {(tts?.warnings ?? [])[0]}</span>
        </div>
      )}
    </div>
  )
}

const DevGallery = import.meta.env.DEV ? lazy(() => import('./ui/DevGallery').then((m) => ({ default: m.DevGallery }))) : null

const stripSlash = (p: string) => (p.length > 1 ? p.replace(/\/+$/, '') : p)

export function App() {
  const path = stripSlash(window.location.pathname)
  if (path === '/prompter') return <PrompterPage />
  if (path === '/stage') return <StagePage />
  if (DevGallery && path === '/_ui')
    return (
      <Suspense fallback={null}>
        <DevGallery />
      </Suspense>
    )
  if (path === '/') return <Console />
  return <NotFound />
}
