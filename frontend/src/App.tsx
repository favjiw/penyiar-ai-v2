import { lazy, Suspense, useCallback, useEffect, useState } from 'react'
import { api } from './api'
import { BlockerStudio } from './console/BlockerStudio'
import { LivePanel } from './console/LivePanel'
import { ttsLabel, type TtsStatus } from './live/tts'
import { useLiveSession, type LiveSession } from './live/useLiveSession'
import { NotFound } from './NotFound'
import { PrompterPage } from './prompter/PrompterPage'
import { StagePage } from './stage/StagePage'
import type { Blocker } from './types'

type Tab = 'blocker' | 'live'

type Health = { llm: string; tts?: TtsStatus } | 'down' | null

/** Status backend untuk header: dari /api/health, lalu dari snapshot siaran (lebih baru: cadangan aktif, breaker). */
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

/** Label kecil di header: mode LLM dan provider TTS aktif, mis. "LLM live · TTS: Edge (gratis)". */
function ModeBadge({ health, tts }: { health: Health; tts?: TtsStatus }) {
  if (health === 'down') return <span className="mode">backend tidak tersambung</span>
  return (
    <span className="mode" title={tts?.fallbacks?.length ? `Cadangan: ${tts.fallbacks.join(', ')}` : 'Tanpa cadangan TTS'}>
      {health ? `LLM ${health.llm} · ` : ''}
      {ttsLabel(tts)}
    </span>
  )
}

function Console() {
  // Konsol selalu tersambung tetapi bisu; audio hanya diputar di /stage (PRD v2.7 FR-10).
  const live = useLiveSession('console')
  const { health, tts } = useHealth(live)
  const onAir = live.snapshot.state === 'live' || live.snapshot.state === 'paused'
  const [tab, setTab] = useState<Tab>('blocker')
  const [locked, setLocked] = useState<Blocker[]>([])
  const refresh = useCallback(() => {
    api.list().then(setLocked).catch(() => setLocked([]))
  }, [])

  useEffect(refresh, [refresh, tab])
  useEffect(() => {
    if (onAir) setTab('live')
  }, [onAir])

  return (
    <>
      <header className="top">
        <h1>Penyiar AI · Konsol</h1>
        <nav className="tabs" role="tablist">
          <button role="tab" aria-selected={tab === 'blocker'} className={tab === 'blocker' ? 'on' : ''} onClick={() => setTab('blocker')}>
            Blocker
          </button>
          <button role="tab" aria-selected={tab === 'live'} className={tab === 'live' ? 'on' : ''} onClick={() => setTab('live')}>
            Live {onAir && <span className="dot" />}
          </button>
        </nav>
        <ModeBadge health={health} tts={tts} />
      </header>
      {(tts?.warnings ?? []).length > 0 && (
        <div className="error tts-warning" role="alert">
          {(tts?.warnings ?? []).map((w) => (
            <div key={w}>⚠ {w}</div>
          ))}
        </div>
      )}
      <main>
        {/* BlockerStudio tetap terpasang agar editan yang belum disimpan tidak hilang saat pindah tab */}
        <div hidden={tab !== 'blocker'}>
          <BlockerStudio />
        </div>
        {tab === 'live' && <LivePanel live={live} blockers={locked} onRefreshBlockers={refresh} />}
      </main>
    </>
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
