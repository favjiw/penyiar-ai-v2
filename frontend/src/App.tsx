import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import { BlockerStudio } from './console/BlockerStudio'
import { LivePanel } from './console/LivePanel'
import { ttsLabel, type TtsStatus } from './live/tts'
import { useLiveSession, type LiveSession } from './live/useLiveSession'
import { PrompterPage } from './prompter/PrompterPage'
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
  // Konsol selalu tersambung dan menjadi pemilik audio, di tab mana pun.
  const live = useLiveSession('console')
  const { health, tts } = useHealth(live)
  const onAir = live.snapshot.state === 'live' || live.snapshot.state === 'paused'
  const [tab, setTab] = useState<Tab>('blocker')
  const [locked, setLocked] = useState<Blocker[]>([])
  const refresh = useCallback(() => {
    api.lockedList().then(setLocked).catch(() => setLocked([]))
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
      <main>{tab === 'blocker' ? <BlockerStudio /> : <LivePanel live={live} lockedBlockers={locked} onRefreshBlockers={refresh} />}</main>
    </>
  )
}

export function App() {
  const path = window.location.pathname
  if (path.startsWith('/prompter')) return <PrompterPage />
  return <Console />
}
