import { useEffect, useState } from 'react'
import { api } from './api'
import { BlockerStudio } from './console/BlockerStudio'

function ModeBadge() {
  const [mode, setMode] = useState('memeriksa backend…')
  useEffect(() => {
    api
      .health()
      .then((h) => setMode(`LLM ${h.llm_mode} · TTS ${h.tts_mode}${h.models.blocker ? ` · ${h.models.blocker}` : ''}`))
      .catch(() => setMode('backend tidak tersambung'))
  }, [])
  return <span className="mode">{mode}</span>
}

export function App() {
  // /prompter (Tahap 4) dan /stage (Tahap 2-3) menyusul; sementara hanya konsol.
  const path = window.location.pathname
  if (path.startsWith('/prompter') || path.startsWith('/stage')) {
    return <main className="empty">Halaman {path} dibuat di tahap berikutnya (PRD §13).</main>
  }
  return (
    <>
      <header className="top">
        <h1>Penyiar AI · Konsol</h1>
        <ModeBadge />
      </header>
      <main>
        <BlockerStudio />
      </main>
    </>
  )
}
