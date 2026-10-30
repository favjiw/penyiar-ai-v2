import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import { BlockerStudio } from './console/BlockerStudio'
import { LivePanel } from './console/LivePanel'
import { useLiveSession } from './live/useLiveSession'
import { PrompterPage } from './prompter/PrompterPage'
import type { Blocker } from './types'

type Tab = 'blocker' | 'live'

function ModeBadge() {
  const [mode, setMode] = useState('memeriksa backend…')
  useEffect(() => {
    api
      .health()
      .then((h) => setMode(`LLM ${h.llm_mode} · TTS ${h.tts_mode}`))
      .catch(() => setMode('backend tidak tersambung'))
  }, [])
  return <span className="mode">{mode}</span>
}

function Console() {
  // Konsol selalu tersambung dan menjadi pemilik audio, di tab mana pun.
  const live = useLiveSession('console')
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
        <ModeBadge />
      </header>
      <main>{tab === 'blocker' ? <BlockerStudio /> : <LivePanel live={live} lockedBlockers={locked} onRefreshBlockers={refresh} />}</main>
    </>
  )
}

export function App() {
  const path = window.location.pathname
  if (path.startsWith('/prompter')) return <PrompterPage />
  return <Console />
}
