import { useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../api'
import type { LiveSession } from '../live/useLiveSession'
import { ttsLabel } from '../live/tts'
import { openStageWindow } from '../stage/openStageWindow'
import { PointCountdown } from './PointCountdown'
import { VoiceStage } from './VoiceStage'

const fmtElapsed = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`
const fmtClock = (ts?: number) => (ts ? new Date(ts * 1000).toLocaleTimeString('id-ID', { hour12: false }) : '')
const isTyping = (el: Element | null) => !!el && ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName)

interface Props {
  live: LiveSession
}

/** Judul segmen untuk satu giliran: Opening, Closing, atau judul topik (id `t2` = topik kedua). */
function segmentLabel(t: { segment: string; topic_id: string | null }, topics: string[]): string {
  if (t.segment === 'opening') return 'Opening'
  if (t.segment === 'closing') return 'Closing'
  const i = t.topic_id ? Number(t.topic_id.replace(/\D/g, '')) - 1 : -1
  return topics[i] ?? 'Topik'
}

/**
 * Kontrol dan pemantauan siaran yang sedang berjalan (FR-11): orb giliran bicara, transkrip, panel agen.
 * Persiapan dan tombol Mulai ada di halaman Siapkan siaran (console/prep, PRD v2.7).
 */
export function LivePanel({ live }: Props) {
  const { snapshot: snap, transcript, showrunner, supervisor, output, pointClock } = live
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [elapsed, setElapsed] = useState(0)
  const transcriptEnd = useRef<HTMLDivElement>(null)
  const onAir = snap.state === 'live' || snap.state === 'paused'
  const stageOpen = (output?.clients?.stage ?? 0) > 0
  const openStage = () => openStageWindow(snap.mode === 'A' ? 'A' : 'B', snap.ai_persona)

  // Jam siaran: snapshot server + detak lokal
  useEffect(() => {
    setElapsed(snap.elapsed_s ?? 0)
    if (snap.state !== 'live') return
    const started = Date.now() - (snap.elapsed_s ?? 0) * 1000
    const t = window.setInterval(() => setElapsed((Date.now() - started) / 1000), 500)
    return () => window.clearInterval(t)
  }, [snap.state, snap.elapsed_s])

  useEffect(() => {
    // Tanpa return: scrollIntoView di Chromium baru mengembalikan Promise, dan React mengira itu cleanup.
    transcriptEnd.current?.scrollIntoView({ block: 'nearest' })
  }, [transcript.length])

  const act = async (fn: () => Promise<unknown>, ok?: string) => {
    setBusy(true)
    setMessage('')
    try {
      await fn()
      if (ok) setMessage(ok)
    } catch (e) {
      setMessage(e instanceof ApiError ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const control = (a: 'pause' | 'resume' | 'next' | 'stop') => act(() => api.control(a))
  const stop = () => window.confirm('Hentikan siaran sekarang?') && control('stop')

  // Pintasan keyboard (FR-11): P pause/lanjut, N next topik, S stop
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!onAir || isTyping(document.activeElement) || e.ctrlKey || e.metaKey || e.altKey) return
      const k = e.key.toLowerCase()
      if (k === 'p') void control(snap.state === 'paused' ? 'resume' : 'pause')
      else if (k === 'n') void control('next')
      else if (k === 's') void stop()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const latestSr = showrunner[showrunner.length - 1]
  const topics = snap.blocker?.topics ?? []

  return (
    <div className="live">
      <section className="panel live-bar">
        <span className={`pill state-${snap.state}`}>{snap.state === 'live' ? '● LIVE' : snap.state === 'paused' ? 'PAUSE' : snap.state === 'ended' ? 'SELESAI' : 'SIAP'}</span>
        {onAir ? (
          <>
            <strong>
              {snap.blocker?.tema} · {snap.blocker?.variant_label}
            </strong>
            <span className="angle">
              {fmtElapsed(elapsed)} · giliran {snap.turn}
              {` · mode ${snap.mode}`}
              {snap.mode !== 'B' && ` dengan ${snap.human?.name} · filler ${snap.fillers_ready ?? 0}`}
            </span>
            <PointCountdown pointClock={pointClock} />
            <span className="spacer" />
            <button onClick={() => control(snap.state === 'paused' ? 'resume' : 'pause')} disabled={busy}>
              {snap.state === 'paused' ? 'Lanjut' : 'Pause'} <kbd>P</kbd>
            </button>
            <button onClick={() => control('next')} disabled={busy} title="Lompat ke topik berikutnya atau penutup">
              Next topik <kbd>N</kbd>
            </button>
            <button className="danger" onClick={() => void stop()} disabled={busy}>
              Stop <kbd>S</kbd>
            </button>
          </>
        ) : null}
        <a className="button-link" href="/prompter" target="hits-prompter" title="Prompter (tablet atau monitor kedua)">
          {output?.clients?.prompter ? 'Prompter terbuka' : 'Buka Prompter'}
        </a>
        <button
          type="button"
          onClick={openStage}
          title="Layar karakter untuk ditangkap OBS; satu-satunya pemutar suara AI"
        >
          {!stageOpen ? 'Buka layar OBS' : output?.audio_ready ? 'Layar OBS siap' : 'Layar OBS belum bersuara'}
        </button>
      </section>

      {message && <div className="error">{message}</div>}
      {snap.error && <div className="error">Siaran berhenti karena galat: {snap.error}</div>}
      {live.alerts.length > 0 && (
        <div className="error" role="status">
          ⚠ {live.alerts[live.alerts.length - 1].message}
          {live.alerts.length > 1 && <span className="angle"> (+{live.alerts.length - 1} peringatan sebelumnya)</span>}
        </div>
      )}
      {onAir && !stageOpen && (
        <div className="error" role="alert">
          Layar untuk OBS belum terbuka. Penonton tidak mendengar suara AI.{' '}
          <button className="small" onClick={openStage}>
            Buka layar OBS
          </button>
        </div>
      )}
      {stageOpen && !output?.audio_ready && (
        <div className={onAir ? 'error' : 'status'} role={onAir ? 'alert' : 'status'}>
          {onAir
            ? 'Suara AI tertahan: browser butuh satu klik di jendela layar OBS.'
            : 'Layar OBS terbuka. Klik sekali di jendelanya supaya suara AI bisa diputar.'}{' '}
          <button className="small" onClick={openStage}>
            Tampilkan jendelanya
          </button>
        </div>
      )}
      {!live.connected && <div className="error">Tersambung ulang ke server…</div>}

      <VoiceStage live={live} previewMode={snap.mode ?? 'B'} previewAi={snap.ai_persona ?? 'salsa'} previewHuman={snap.human?.name ?? ''} />

      <div className="live-grid">
        <section className="panel transcript">
          <h2>Transkrip</h2>
          {transcript.length === 0 && <p className="empty">Belum ada giliran.</p>}
          {transcript.map((t) => (
            <div key={t.turn} className={`line ${live.speaking === t.persona && t === transcript[transcript.length - 1] ? 'now' : ''}`}>
              <span className="meta">
                {fmtClock(t.ts)} · {segmentLabel(t, topics)}
              </span>
              <span className={`who ${t.persona}`}>{t.name}</span> {t.text}
              {t.supervisor !== 'forward' && <span className="badge">{t.supervisor}</span>}
              {t.tts_provider && snap.tts && t.tts_provider !== snap.tts.primary && t.tts_provider !== 'mock' && <span className="badge">TTS {t.tts_provider}</span>}
            </div>
          ))}
          {live.sttPartial && (
            <div className="line partial">
              <span className="who human">{snap.human?.name ?? 'Penyiar'}</span> {live.sttPartial}…
            </div>
          )}
          <div ref={transcriptEnd} />
        </section>

        <div className="side-stack">
          <section className="panel">
            <h2>On air</h2>
            <div className="onair-seg">
              {snap.segment === 'topic' ? snap.topic?.judul : snap.segment === 'closing' ? 'Closing' : snap.segment === 'opening' ? 'Opening' : '–'}
            </div>
            {snap.topic?.pertanyaan_penonton && <div className="angle">❓ {snap.topic.pertanyaan_penonton}</div>}
            <ul className="coverage">
              {topics.map((judul, i) => {
                const c = snap.coverage?.[`t${i + 1}`]
                return (
                  <li key={judul}>
                    <span>{judul}</span>
                    <meter min={0} max={c?.total ?? 1} value={c?.covered.length ?? 0} />
                    <span className="angle">
                      {c?.covered.length ?? 0}/{c?.total ?? '?'}
                    </span>
                  </li>
                )
              })}
            </ul>
          </section>

          <section className="panel">
            <h2>Showrunner</h2>
            {latestSr ? (
              <>
                <div>
                  <strong>{latestSr.aksi ?? latestSr.decision}</strong> ({latestSr.decision}) · jenuh {latestSr.saturation.toFixed(2)} · {latestSr.policy}
                  {latestSr.forced && <span className="badge">forced</span>}
                </div>
                {latestSr.steer_hint && <div className="angle">→ {latestSr.steer_hint}</div>}
                <div className="angle">{latestSr.reason}</div>
                <ol className="log" reversed>
                  {showrunner
                    .slice(-6, -1)
                    .reverse()
                    .map((d) => (
                      <li key={`${d.turn}-${d.topic_id}`}>
                        g{d.turn} {d.topic_id}: {d.decision}
                      </li>
                    ))}
                </ol>
              </>
            ) : (
              <p className="empty">Belum ada keputusan.</p>
            )}
          </section>

          <section className="panel">
            <h2>Supervisor</h2>
            {supervisor.length === 0 ? (
              <p className="empty">Semua ucapan lolos.</p>
            ) : (
              <ol className="log" reversed>
                {supervisor
                  .slice(-8)
                  .reverse()
                  .map((v) => (
                    <li key={v.turn}>
                      g{v.turn} {v.persona}: <strong>{v.action}</strong>
                      {v.rule_hits.length > 0 && <span className="angle"> [{v.rule_hits.join(', ')}]</span>}
                      {v.evidence && <div className="angle">{v.evidence}</div>}
                    </li>
                  ))}
              </ol>
            )}
          </section>

          <section className="panel">
            <h2>Output</h2>
            <div className="angle">
              Audio: {output?.audio_owner_role ?? 'belum ada pemutar'} · klien {Object.entries(output?.clients ?? {}).map(([r, n]) => `${r} ${n}`).join(', ')}
            </div>
            {snap.tts && (
              <div className="angle">
                {ttsLabel(snap.tts)}
                {snap.tts.fallback_uses ? ` · cadangan dipakai ${snap.tts.fallback_uses}×` : ''}
                {snap.tts.credits_used > 0 ? ` · kredit ${snap.tts.credits_used}` : ''}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  )
}
