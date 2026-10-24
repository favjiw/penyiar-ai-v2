import { useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../api'
import type { LiveSession } from '../live/useLiveSession'
import type { Blocker } from '../types'

// Jendela stage untuk OBS: popup 9:16 tanpa tab, dibuka ulang di jendela bernama sama (dari repo lama).
const STAGE_URL = '/stage?clean=1'
const STAGE_WINDOW = 'hits-stage'
const STAGE_FEATURES = 'popup=yes,width=540,height=960,left=40,top=40'

function openStage() {
  const win = window.open(STAGE_URL, STAGE_WINDOW, STAGE_FEATURES)
  if (win) win.focus()
  else window.open(STAGE_URL, '_blank')
}

const fmtElapsed = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`
const isTyping = (el: Element | null) => !!el && ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName)

interface Props {
  live: LiveSession
  lockedBlockers: Blocker[]
  onRefreshBlockers: () => void
}

/** Kontrol dan pemantauan siaran mode B (FR-11, bagian Tahap 2). */
export function LivePanel({ live, lockedBlockers, onRefreshBlockers }: Props) {
  const { snapshot: snap, transcript, showrunner, supervisor, output } = live
  const [blockerId, setBlockerId] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [precheck, setPrecheck] = useState<string>('')
  const [elapsed, setElapsed] = useState(0)
  const transcriptEnd = useRef<HTMLDivElement>(null)
  const onAir = snap.state === 'live' || snap.state === 'paused'

  useEffect(() => {
    if (!blockerId && lockedBlockers.length) setBlockerId(lockedBlockers[0].id)
  }, [lockedBlockers, blockerId])

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

  const runPrecheck = () =>
    act(async () => {
      setPrecheck('Memeriksa… (memanaskan suara TTS)')
      const r = await api.precheck()
      const warm = r.tts_warmup_ms ? Object.values(r.tts_warmup_ms).map((ms) => `${(ms / 1000).toFixed(1)} s`).join(', ') : ''
      setPrecheck(
        [
          r.models_ok ? 'Model LLM ✓' : 'Model LLM belum diisi di .env ✗',
          r.tts_ok ? `TTS ✓ (pemanasan ${warm})` : `TTS ✗ ${r.tts_error ?? ''}`,
          r.output.stage_connected ? 'Stage tersambung ✓' : 'Stage belum dibuka (audio diputar di konsol)',
        ].join(' · '),
      )
    })

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
            </span>
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
        ) : (
          <>
            <select value={blockerId} onChange={(e) => setBlockerId(e.target.value)} onFocus={onRefreshBlockers} aria-label="Blocker terkunci">
              {lockedBlockers.length === 0 && <option value="">Belum ada blocker terkunci</option>}
              {lockedBlockers.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.tema} · {b.variant_label} · v{b.versi}
                </option>
              ))}
            </select>
            <button onClick={() => void runPrecheck()} disabled={busy}>
              Cek pra-live
            </button>
            <button className="primary" onClick={() => act(() => api.startShow(blockerId, 'B'))} disabled={busy || !blockerId}>
              Mulai mode B (Raka + Salsa)
            </button>
          </>
        )}
        <button onClick={openStage} title="Popup 9:16 untuk ditangkap OBS">
          {output?.stage_connected ? 'Stage ✓' : 'Buka Stage'}
        </button>
      </section>

      {precheck && !onAir && <div className="status">{precheck}</div>}
      {message && <div className="error">{message}</div>}
      {snap.error && <div className="error">Siaran berhenti karena galat: {snap.error}</div>}
      {live.alerts.length > 0 && (
        <div className="error" role="status">
          ⚠ {live.alerts[live.alerts.length - 1].message}
          {live.alerts.length > 1 && <span className="angle"> (+{live.alerts.length - 1} peringatan sebelumnya)</span>}
        </div>
      )}
      {live.audioBlocked && (
        <div className="error" role="alert">
          Browser memblokir audio otomatis.{' '}
          <button className="small" onClick={live.unlockAudio}>
            Aktifkan audio
          </button>
        </div>
      )}
      {!live.connected && <div className="error">Tersambung ulang ke server…</div>}

      <div className="live-grid">
        <section className="panel transcript">
          <h2>Transkrip</h2>
          {transcript.length === 0 && <p className="empty">Belum ada giliran.</p>}
          {transcript.map((t) => (
            <div key={t.turn} className={`line ${live.speaking === t.persona && t === transcript[transcript.length - 1] ? 'now' : ''}`}>
              <span className={`who ${t.persona}`}>{t.name}</span> {t.text}
              {t.supervisor !== 'forward' && <span className="badge">{t.supervisor}</span>}
              {t.tts_provider && t.tts_provider !== 'elevenlabs' && t.tts_provider !== 'mock' && <span className="badge">TTS {t.tts_provider}</span>}
            </div>
          ))}
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
                  <strong>{latestSr.decision}</strong> · jenuh {latestSr.saturation.toFixed(2)} · {latestSr.policy}
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
                TTS {snap.tts.primary}
                {snap.tts.breaker_open && ' (breaker terbuka → ' + snap.tts.fallback + ')'} · kredit {snap.tts.credits_used}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  )
}
