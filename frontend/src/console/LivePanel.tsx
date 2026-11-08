/**
 * Konsol · Saat live (mockup KonsolLive + KonsolPeringatan, HANDOFF §1):
 * header LIVE + kontrol, peringatan tiga tingkat, progres siaran per segmen, siapa bicara
 * (bar level nyata), urutan materi + bahan obrolan + cincin waktu, saran pengarah acara,
 * transkrip, dan status. Nama model/vendor dan log mentah hanya di "Detail teknis".
 */
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { api, ApiError } from '../api'
import { ttsLabel } from '../live/tts'
import type { AlertEvent, ShowrunnerDecision } from '../live/types'
import type { LiveSession } from '../live/useLiveSession'
import { useShowClock } from '../live/useShowClock'
import { shout } from '../lib/materi'
import { openStageWindow } from '../stage/openStageWindow'
import { Alert, Button, fmtClock, IconCheck, IconInfo, IconMic, IconMicOff, IconMonitorOff, LevelBars, LiveBadge, Ring } from '../ui'
import './live.css'

const ON_SCHEDULE_S = 60 // selisih ≤1 menit = "Sesuai jadwal"
const OPENING_CLOSING_MIN = 3
const isTyping = (el: Element | null) => !!el && ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName)
const fmtTime = (ts?: number) => (ts ? new Date(ts * 1000).toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' }) : '')

interface ShownAlert {
  id: string
  level: 'red' | 'yellow' | 'blue'
  title: string
  message: string
  icon?: ReactNode
  actions?: ReactNode
  time?: string
}

/** Level audio AI yang diputar di layar OBS (diteruskan server), dibaca per frame. */
function useRelayedLevel(getLevel: () => number | null, active: boolean) {
  const [level, setLevel] = useState(0)
  useEffect(() => {
    if (!active) {
      setLevel(0)
      return
    }
    let raf = 0
    let last = -1
    const tick = () => {
      const lv = Math.round((getLevel() ?? 0) * 20) / 20
      if (lv !== last) setLevel((last = lv))
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [getLevel, active])
  return level
}

/** Saran pengarah acara dalam kalimat operator (bukan istilah teknis). */
function adviceText(d: ShowrunnerDecision | undefined, totalPoints: number): string {
  if (!d) return ''
  const covered = `${d.points_covered.length}/${totalPoints || '?'} bahan obrolan sudah dibahas`
  if (d.advisory) {
    const parts = [covered]
    if (d.steer_hint) parts.push(`coba bahas: ${d.steer_hint}`)
    if (d.decision === 'transition' || d.aksi === 'pindah_topik') parts.push('siap pindah topik')
    if (d.decision === 'close' || d.aksi === 'tutup') parts.push('siap ke penutup')
    return parts.join(' · ')
  }
  if (d.decision === 'transition') return `${covered}. AI akan pindah ke topik berikutnya.`
  if (d.decision === 'close') return `${covered}. AI akan masuk ke penutup.`
  if (d.decision === 'steer' && d.steer_hint) return `${covered}. AI diarahkan ke: ${d.steer_hint}`
  return `${covered}. Obrolan lanjut.`
}

export function LivePanel({ live }: { live: LiveSession }) {
  const { snapshot: snap, transcript, showrunner, supervisor, output, showClock, alerts, lastNudge } = live
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [confirmStop, setConfirmStop] = useState(false)
  const [dismissed, setDismissed] = useState<Set<string>>(new Set())
  const transcriptEnd = useRef<HTMLDivElement>(null)
  const clock = useShowClock(showClock)
  const paused = snap.state === 'paused'
  const isModeA = snap.mode === 'A'

  const personas = snap.personas ?? []
  const speakingAi = personas.find((p) => p.id === live.speaking)
  const aiLevel = useRelayedLevel(live.level, !!speakingAi)

  useEffect(() => {
    // Tanpa return: scrollIntoView di Chromium baru mengembalikan Promise, dan React mengira itu cleanup.
    transcriptEnd.current?.scrollIntoView({ block: 'nearest' })
  }, [transcript.length])

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    setMessage('')
    try {
      await fn()
    } catch (e) {
      setMessage(e instanceof ApiError ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }
  const control = (a: 'pause' | 'resume' | 'next' | 'stop') => act(() => api.control(a))
  const openStage = () => openStageWindow(isModeA ? 'A' : 'B', snap.ai_persona)

  // Pintasan (FR-11): P jeda/lanjut, N topik selanjutnya, S akhiri (dengan konfirmasi di halaman), Esc batal.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (isTyping(document.activeElement) || e.ctrlKey || e.metaKey || e.altKey || e.repeat) return
      const k = e.key.toLowerCase()
      if (k === 'escape') return setConfirmStop(false)
      if (confirmStop || busy) return // konfirmasi akhiri sedang terbuka: pintasan lain ditahan
      if (k === 'p') void control(paused ? 'resume' : 'pause')
      else if (k === 'n' && snap.segment !== 'closing') void control('next')
      else if (k === 's') setConfirmStop(true)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  // ── Materi dan segmen ───────────────────────────────────────────────────
  const rundown = snap.rundown
  const topics = rundown?.topics ?? []
  const ti = snap.segment === 'topic' ? topics.findIndex((t) => t.id === snap.topic?.id) : -1
  // Topik yang tidak ditemukan (data belum sinkron) dianggap belum masuk topik mana pun.
  const segIdx = snap.segment === 'opening' || ti < 0 ? (snap.segment === 'closing' ? topics.length + 1 : 0) : ti + 1
  const segPlan = [OPENING_CLOSING_MIN, ...topics.map((t) => t.menit ?? 9), OPENING_CLOSING_MIN]
  const plannedStart = segPlan.slice(0, segIdx).reduce((a, b) => a + b, 0) * 60
  // Selisih jadwal: segmen ini mulai lebih lambat/cepat dari rencana, ditambah lewat waktu segmen ini.
  const drift = clock ? clock.elapsed - clock.segElapsed - plannedStart + Math.max(0, clock.segElapsed - clock.segTarget) : 0
  const onSchedule = Math.abs(drift) <= ON_SCHEDULE_S
  const schedule = onSchedule ? 'Sesuai jadwal' : drift > 0 ? `Lebih lambat ±${Math.round(drift / 60)} mnt` : `Lebih cepat ±${Math.round(-drift / 60)} mnt`
  const segLabel = snap.segment === 'topic' && ti >= 0 ? `Topik ${ti + 1} dari ${topics.length}` : snap.segment === 'closing' ? 'Closing' : 'Opening'
  const topic = ti >= 0 ? topics[ti] : null
  const points = snap.topic_points ?? []
  // Poin aktif dari server; hanya bila server tidak menandai, pakai poin pertama yang belum dibahas.
  // Tepat setelah pindah topik, poin dari server belum tiba: tampilkan poin materi, mulai dari yang pertama.
  const pointList = points.length ? points : (topic?.poin ?? []).map((p) => ({ ...p, covered: false, current: undefined as boolean | undefined }))
  const flagged = pointList.findIndex((p) => p.current)
  const currentIdx = topic ? (flagged >= 0 ? flagged : pointList.findIndex((p) => !p.covered)) : -1
  const advice = topic ? adviceText([...showrunner].reverse().find((d) => d.topic_id === topic.id), topic.poin.length) : ''
  const avgTopicMin = Math.round(segPlan.slice(1, -1).reduce((a, b) => a + b, 0) / Math.max(1, topics.length))

  // ── Peringatan ──────────────────────────────────────────────────────────
  // Sebelum status keluaran pertama tiba, jangan menuduh layar/prompter tertutup.
  const known = output !== null
  const stageOpen = !known || (output?.clients?.stage ?? 0) > 0
  const prompterOpen = !known || (output?.clients?.prompter ?? 0) > 0
  const micDown = isModeA && !!output?.mic?.down
  const derived: ShownAlert[] = []
  if (micDown)
    derived.push({
      id: 'mic',
      level: 'red',
      icon: <IconMicOff />,
      title: 'Mikrofon studio tidak terdengar',
      message:
        output?.mic?.reason === 'denied' || output?.mic?.reason === 'not-allowed'
          ? 'Browser prompter belum diberi izin mikrofon. Penyiar belum bisa ngobrol dengan AI.'
          : 'Tidak ada suara dari mixer. Penyiar belum bisa ngobrol dengan AI.',
      actions: !paused && (
        <Button variant="ink" onClick={() => void control('pause')}>
          Jeda siaran
        </Button>
      ),
    })
  if (!stageOpen)
    derived.push({
      id: 'stage',
      level: 'red',
      icon: <IconMonitorOff />,
      title: 'Layar untuk OBS tertutup',
      message: 'Penonton tidak mendengar suara AI. Buka lagi lalu pastikan OBS menangkap jendela yang sama.',
      actions: (
        <Button variant="ink" onClick={openStage}>
          Buka lagi layar OBS
        </Button>
      ),
    })
  else if (known && !output?.audio_ready)
    derived.push({
      id: 'stage-audio',
      level: 'red',
      title: 'Suara AI tertahan di layar OBS',
      message: 'Browser butuh satu klik di jendela layar OBS supaya suara AI bisa diputar.',
      actions: (
        <Button variant="ink" onClick={openStage}>
          Tampilkan jendelanya
        </Button>
      ),
    })
  if (isModeA && !prompterOpen)
    derived.push({
      id: 'prompter',
      level: 'red',
      title: 'Prompter tertutup',
      message: 'Penyiar tidak melihat materi, dan suara penyiar tidak didengar AI.',
      actions: (
        <Button variant="ink" onClick={() => window.open('/prompter', 'hits-prompter')}>
          Buka prompter
        </Button>
      ),
    })
  const fromServer: ShownAlert[] = alerts
    .filter((a: AlertEvent) => !dismissed.has(a.id))
    .reverse()
    .map((a) => ({ id: a.id, level: a.level, title: a.title, message: a.message, time: fmtTime(a.at) }))
  const order = { red: 0, yellow: 1, blue: 2 }
  // Merah dulu (tetap sampai beres), lalu kuning, lalu biru; di dalam tingkat yang sama terbaru di atas.
  const shown = [...derived, ...fromServer].sort((a, b) => order[a.level] - order[b.level])
  const hasRed = shown.some((a) => a.level === 'red') || !!snap.error

  useEffect(() => {
    document.title = `${hasRed ? '(!) ' : ''}${paused ? 'JEDA' : 'LIVE'} · Penyiar AI HITS`
  }, [hasRed, paused])

  // Simpan hanya id yang masih ada di daftar peringatan (daftar dibatasi 20 item di useLiveSession).
  const dismiss = (id: string) => setDismissed((s) => new Set([...s, id].filter((x) => alerts.some((a) => a.id === x))))

  // ── Siapa bicara ────────────────────────────────────────────────────────
  const thinkingId = snap.thinking ?? (snap.busy && !speakingAi ? snap.ai_persona : null)
  const humanTalking = live.micActive && !!live.sttPartial
  const people = (snap.participants ?? personas.map((p) => ({ ...p, kind: 'ai' as const }))).map((p) => {
    if (p.kind === 'human') {
      const status = micDown ? 'Mic tidak terdengar' : humanTalking ? 'Sedang bicara' : speakingAi || thinkingId ? 'Menunggu giliran' : 'Giliran bicara'
      const pill = micDown ? 'Tidak terdengar' : live.micActive ? 'Mic aktif' : 'Mic dijeda'
      return { ...p, status, pill, on: humanTalking }
    }
    const status = speakingAi?.id === p.id ? 'Sedang bicara' : thinkingId === p.id ? 'Menyiapkan jawaban' : 'Mendengarkan'
    return { ...p, status, pill: '', on: speakingAi?.id === p.id }
  })

  // ── Status ──────────────────────────────────────────────────────────────
  const tts = snap.tts
  const backupVoice = !!tts?.last_provider && tts.last_provider !== tts.primary && tts.last_provider !== 'mock'
  type Row = { label: string; value: string; tone: 'ok' | 'bad' | 'info' }
  const statusRows: Row[] = []
  if (isModeA) statusRows.push({ label: 'Mikrofon studio', value: micDown ? 'Tidak terdengar' : live.micActive ? 'Mendengarkan penyiar' : 'Dijeda saat AI bicara', tone: micDown ? 'bad' : 'ok' })
  statusRows.push({ label: 'Layar untuk OBS', value: !stageOpen ? 'Tertutup' : output?.audio_ready ? 'Tersambung' : 'Belum bersuara', tone: stageOpen && output?.audio_ready ? 'ok' : 'bad' })
  if (isModeA) statusRows.push({ label: 'Prompter', value: prompterOpen ? 'Tersambung' : 'Tertutup', tone: prompterOpen ? 'ok' : 'bad' })
  statusRows.push({ label: 'Suara AI', value: backupVoice ? 'Cadangan aktif' : 'Normal', tone: backupVoice ? 'info' : 'ok' })

  const hostName = snap.human?.name
  const who = isModeA ? `${hostName ?? 'Penyiar'} + ${personas[0]?.name ?? 'AI'}` : personas.map((p) => p.name).join(' + ')

  return (
    <div className="lv">
      <header className="lv-top">
        <div className="lv-top__inner">
          <img src="/logo-hits.png" alt="HITS Unikom Radio 103.9 FM" className="lv-top__logo" />
          <LiveBadge paused={paused} />
          <span className="lv-top__title">
            <span className="lv-top__name">{snap.blocker?.variant_label}</span>
            <span className="lv-top__sub">
              {who} · {segLabel}
            </span>
          </span>
          <span className="lv-top__spacer" />
          {!live.connected && <span className="lv-top__offline">Menyambung ulang ke server…</span>}
          <div className="lv-top__actions">
            <Button onClick={() => void control(paused ? 'resume' : 'pause')} disabled={busy} title="Pintasan: P">
              {paused ? 'Lanjutkan' : 'Jeda'}
            </Button>
            <Button onClick={() => void control('next')} disabled={busy || snap.segment === 'closing'} title="Pintasan: N">
              Topik selanjutnya
            </Button>
            <span className="lv-top__sep" aria-hidden="true" />
            {confirmStop ? (
              <span className="lv-stop" role="alertdialog" aria-label="Konfirmasi akhiri siaran">
                <span>Akhiri siaran sekarang?</span>
                <Button variant="danger" onClick={() => void control('stop').then(() => setConfirmStop(false))} disabled={busy} autoFocus>
                  Ya, akhiri
                </Button>
                <Button onClick={() => setConfirmStop(false)}>Batal</Button>
              </span>
            ) : (
              <Button variant="danger" onClick={() => setConfirmStop(true)} title="Pintasan: S">
                Akhiri siaran
              </Button>
            )}
          </div>
        </div>
      </header>

      <main className="lv-main">
        <div className="lv-col">
          {(shown.length > 0 || message || snap.error) && (
            <section className="ui-alert-stack" aria-label="Peringatan" aria-live="assertive">
              {snap.error && <Alert level="red" title="Siaran berhenti karena gangguan" message="Lihat Detail teknis untuk penyebabnya." />}
              {message && <Alert level="yellow" title="Perintah tidak berhasil" message={message} onDismiss={() => setMessage('')} />}
              {shown.map((a) => (
                <Alert
                  key={a.id}
                  level={a.level}
                  title={a.title}
                  message={a.message}
                  icon={a.icon}
                  actions={a.actions}
                  time={a.time}
                  onDismiss={a.level === 'red' ? undefined : () => dismiss(a.id)}
                />
              ))}
            </section>
          )}

          <section className="lv-card lv-progress" aria-label="Progres siaran">
            <div className="lv-progress__head">
              <span className="lv-progress__time">{fmtClock(clock?.elapsed ?? 0)}</span>
              <span className="lv-progress__of">dari {fmtClock(clock?.target ?? 0)} menit siaran</span>
              <span className={`lv-progress__pill${onSchedule || paused ? ' is-ok' : ''}`}>{paused ? 'Dijeda' : schedule}</span>
            </div>
            <div className="lv-bar" role="img" aria-label={`${segLabel} berjalan; ${segIdx} dari ${segPlan.length} bagian selesai`}>
              {segPlan.map((m, i) => (
                <span key={i} className={`lv-bar__seg${i < segIdx ? ' is-done' : i === segIdx ? ' is-now' : ''}`} style={{ flexGrow: m }}>
                  {i === segIdx && clock && <span className="lv-bar__fill" style={{ width: `${Math.min(100, (clock.segElapsed / Math.max(1, clock.segTarget)) * 100)}%` }} />}
                </span>
              ))}
            </div>
            <span className="lv-progress__legend">
              Opening {OPENING_CLOSING_MIN} mnt · {topics.length} topik × ±{avgTopicMin} mnt · Closing {OPENING_CLOSING_MIN} mnt
            </span>
          </section>

          <section className="lv-people" aria-label="Siapa bicara">
            {people.map((p) => (
              <div key={p.id} className={`lv-person${p.on ? ' is-on' : ''}`}>
                <span className={`lv-person__avatar lv-person__avatar--${p.kind === 'human' ? 'human' : p.id}`} aria-hidden="true">
                  {p.kind === 'human' && (micDown ? <IconMicOff size={22} /> : <IconMic size={22} />)}
                </span>
                <span className="lv-person__text">
                  <span className="lv-person__name">{p.name}</span>
                  <span className="lv-person__status">{p.status}</span>
                </span>
                {p.kind === 'human' ? <span className={`lv-person__pill${micDown ? ' is-bad' : ''}`}>{p.pill}</span> : <LevelBars level={p.on ? aiLevel : 0} />}
              </div>
            ))}
          </section>

          <section className="lv-card">
            <ol className="lv-order" aria-label="Urutan materi">
              {['Opening', ...topics.map((_, i) => `Topik ${i + 1}`), 'Closing'].map((label, i) => (
                <li key={label} className={i < segIdx ? 'is-done' : i === segIdx ? 'is-now' : ''} aria-current={i === segIdx ? 'step' : undefined}>
                  {i < segIdx && <IconCheck size={16} />}
                  {label}
                </li>
              ))}
            </ol>
            <div className="lv-topic">
              <div className="lv-topic__main">
                <h2>{topic?.judul ?? segLabel}</h2>
                {topic ? (
                  <>
                    <p className="lv-topic__ask">
                      <span>Tanya penonton</span>
                      {shout(topic.pertanyaan_penonton)}
                    </p>
                    <ul className="lv-points">
                      {pointList.map((p, i) => {
                        const st = p.covered && i !== currentIdx ? 'done' : i === currentIdx ? 'now' : 'todo'
                        return (
                          <li key={i} className={`lv-point lv-point--${st}`}>
                            {st === 'done' ? (
                              <span className="lv-point__mark" role="img" aria-label="Sudah dibahas">
                                <IconCheck size={20} />
                              </span>
                            ) : (
                              <span className="lv-point__mark lv-point__dot" role="img" aria-label={st === 'now' ? 'Sedang dibahas' : 'Belum dibahas'} />
                            )}
                            <span>{p.text}</span>
                          </li>
                        )
                      })}
                    </ul>
                  </>
                ) : (
                  <p className="lv-topic__ask">
                    <span>{snap.segment === 'closing' ? 'Ajakan' : 'Kalimat pembuka'}</span>
                    {shout((snap.segment === 'closing' ? rundown?.closing.ajakan : rundown?.opening.hook) ?? '')}
                  </p>
                )}
              </div>
              {clock && clock.segTarget > 0 && (
                <Ring remainingS={clock.remaining} limitS={clock.segTarget} size={160} label={paused ? 'dijeda' : clock.remaining > 30 ? 'tersisa' : undefined} />
              )}
            </div>
            {topic && lastNudge?.topic_id === topic.id && (
              <div className="lv-advice">
                <IconInfo size={22} />
                <span>
                  <strong>Kode halus terkirim:</strong> topik lewat ±{Math.round(lastNudge.overrun_s / 60)} mnt, AI menawarkan pindah ke “{lastNudge.to}”. Penyiar yang memutuskan.
                </span>
              </div>
            )}
            {advice && (
              <div className="lv-advice">
                <IconInfo size={22} />
                <span>
                  <strong>Saran pengarah acara:</strong> {advice}
                </span>
              </div>
            )}
          </section>

          <section className="lv-card lv-transcript">
            <h2>Transkrip</h2>
            <div className="lv-transcript__list">
              {transcript.length === 0 && <p className="lv-empty">Belum ada obrolan.</p>}
              {transcript.map((t) => (
                <p key={t.turn} className="lv-line">
                  <span className={`lv-line__who lv-line__who--${t.persona === 'human' ? 'human' : t.persona}`}>{t.name}</span>
                  <span>{t.text}</span>
                </p>
              ))}
              {live.sttPartial && (
                <p className="lv-line is-partial">
                  <span className="lv-line__who lv-line__who--human">{hostName ?? 'Penyiar'}</span>
                  <span>{live.sttPartial}…</span>
                </p>
              )}
              <div ref={transcriptEnd} />
            </div>
          </section>
        </div>

        <aside className="lv-side">
          <h2>Status</h2>
          <ul className="lv-status">
            {statusRows.map((r) => (
              <li key={r.label} className={`lv-status__row is-${r.tone}`}>
                <span className="lv-status__dot" aria-hidden="true" />
                <span className="lv-status__label">{r.label}</span>
                <span className="lv-status__value">{r.value}</span>
              </li>
            ))}
          </ul>
          <details className="lv-tech">
            <summary>Detail teknis</summary>
            <div className="lv-tech__body">
              <p>
                Mode {snap.mode} · giliran {snap.turn}
                {isModeA && ` · filler siap ${snap.fillers_ready ?? 0}`}
              </p>
              {tts && (
                <p>
                  {ttsLabel(tts)}
                  {tts.fallback_uses ? ` · cadangan dipakai ${tts.fallback_uses}×` : ''}
                  {tts.credits_used > 0 ? ` · kredit ${tts.credits_used}` : ''}
                </p>
              )}
              <p>Klien: {Object.entries(output?.clients ?? {}).map(([r, n]) => `${r} ${n}`).join(', ')}</p>
              {snap.error && <p className="lv-tech__err">Galat: {snap.error}</p>}
              <h3>Showrunner</h3>
              {showrunner.length === 0 ? (
                <p>Belum ada keputusan.</p>
              ) : (
                <ol reversed>
                  {showrunner
                    .slice(-6)
                    .reverse()
                    .map((d) => (
                      <li key={`${d.turn}-${d.topic_id}-${d.decision}`}>
                        g{d.turn} {d.topic_id}: {d.decision} · jenuh {d.saturation.toFixed(2)} · {d.policy}
                        {d.forced && ' · forced'} · {d.latency_ms} ms · {d.reason}
                      </li>
                    ))}
                </ol>
              )}
              <h3>Supervisor</h3>
              {supervisor.length === 0 ? (
                <p>Semua ucapan lolos.</p>
              ) : (
                <ol reversed>
                  {supervisor
                    .slice(-8)
                    .reverse()
                    .map((v) => (
                      <li key={v.turn}>
                        g{v.turn} {v.persona}: {v.action}
                        {v.rule_hits.length > 0 && ` [${v.rule_hits.join(', ')}]`}
                        {v.evidence && ` · ${v.evidence}`}
                      </li>
                    ))}
                </ol>
              )}
              <h3>Peringatan mentah</h3>
              {alerts.length === 0 ? (
                <p>Tidak ada.</p>
              ) : (
                <ol reversed>
                  {alerts
                    .slice()
                    .reverse()
                    .map((a) => (
                      <li key={a.id}>
                        {fmtTime(a.at)} [{a.stage}/{a.code}] {a.detail}
                      </li>
                    ))}
                </ol>
              )}
            </div>
          </details>
        </aside>
      </main>
    </div>
  )
}
