import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import { BlockerStudio } from './console/BlockerStudio'
import { LivePanel } from './console/LivePanel'
import { useLiveSession } from './live/useLiveSession'
import { StagePage } from './stage/StagePage'
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
  // Konsol selalu tersambung: tetap memutar audio bila stage belum dibuka, di tab mana pun.
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
  if (path.startsWith('/stage')) return <StagePage />
  if (path.startsWith('/prompter')) return <main className="empty">Prompter dibuat di Tahap 4 (PRD §13).</main>
  return <Console />
}
