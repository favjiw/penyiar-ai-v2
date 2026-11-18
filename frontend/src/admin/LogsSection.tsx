/**
 * Log semua siaran (admin): riwayat siaran dari database, termasuk yang lampau, dengan transkrip,
 * event mentah, konfigurasi saat siaran, materi, dan unduhan JSONL untuk analisis di luar aplikasi.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { adminApi, ApiError, type SessionDetail, type SessionSummary } from '../api'
import { Button, Pill } from '../ui'

const PAGE = 25
const errText = (e: unknown) => (e instanceof ApiError ? e.message : 'Gagal menghubungi server')
const fmtTime = (iso?: string | null) => (iso ? new Date(iso).toLocaleString('id-ID', { dateStyle: 'medium', timeStyle: 'medium' }) : '-')
const fmtDur = (s?: number | null) => (s == null ? '-' : s >= 60 ? `${Math.floor(s / 60)} mnt ${Math.round(s % 60)} dtk` : `${Math.round(s)} dtk`)
const FORMAT_LABEL: Record<string, string> = { A: 'Penyiar + AI', B: 'AI + AI' }

function statusOf(s: SessionSummary, live: string | null): { label: string; tone: 'success' | 'blue' | 'yellow' | 'neutral' } {
  if (s.session_id === live) return { label: 'Berjalan', tone: 'blue' }
  if (!s.ended) return { label: 'Terputus (tanpa penutup)', tone: 'yellow' }
  return { label: s.end_reason === 'stopped' ? 'Dihentikan operator' : s.end_reason === 'error' ? 'Berhenti karena galat' : 'Selesai', tone: s.end_reason === 'error' ? 'yellow' : 'success' }
}

const isTest = (s: SessionSummary) => s.llm_mode === 'mock' || s.tts_mode === 'mock'

export function LogsSection() {
  const initial = window.location.hash.split('/')[1] ?? ''
  const [selected, setSelected] = useState(initial)
  const open = (id: string) => {
    setSelected(id)
    window.history.replaceState(null, '', id ? `#log/${id}` : '#log')
  }
  return selected ? <SessionView id={selected} onBack={() => open('')} /> : <SessionList onOpen={open} />
}

// ── Daftar ───────────────────────────────────────────────────────────────────
function SessionList({ onOpen }: { onOpen: (id: string) => void }) {
  const [items, setItems] = useState<SessionSummary[]>([])
  const [total, setTotal] = useState(0)
  const [live, setLive] = useState<string | null>(null)
  const [offset, setOffset] = useState(0)
  const [q, setQ] = useState('')
  const [mode, setMode] = useState<'' | 'A' | 'B'>('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    setBusy(true)
    adminApi
      .sessions({ limit: PAGE, offset, q: q.trim() || undefined, mode: mode || undefined })
      .then((r) => {
        setItems(r.items)
        setTotal(r.total)
        setLive(r.live_session)
        setError('')
      })
      .catch((e) => setError(errText(e)))
      .finally(() => setBusy(false))
  }, [offset, q, mode])

  useEffect(() => {
    const t = window.setTimeout(load, q ? 250 : 0)
    return () => window.clearTimeout(t)
  }, [load, q])

  useEffect(() => {
    if (!live) return
    const t = window.setInterval(load, 8000) // siaran berjalan: daftar ikut diperbarui
    return () => window.clearInterval(t)
  }, [live, load])

  return (
    <section className="ui-card adm-group" aria-labelledby="g-logs">
      <h2 id="g-logs" className="ui-card__title">
        Riwayat siaran ({total})
      </h2>
      <p className="adm-help">Semua siaran yang tercatat di database, terbaru dulu, termasuk yang lampau. Buka satu siaran untuk membaca transkrip, event, konfigurasi, dan materinya.</p>
      <div className="users__new">
        <label className="auth-field">
          Cari (tema, peserta, ID)
          <input
            value={q}
            onChange={(e) => {
              setOffset(0)
              setQ(e.target.value)
            }}
            placeholder="mis. zodiak"
          />
        </label>
        <label className="auth-field">
          Format
          <select
            value={mode}
            onChange={(e) => {
              setOffset(0)
              setMode(e.target.value as '' | 'A' | 'B')
            }}
          >
            <option value="">Semua</option>
            <option value="A">Penyiar + AI</option>
            <option value="B">AI + AI</option>
          </select>
        </label>
        <Button onClick={load} disabled={busy}>
          {busy ? 'Memuat…' : 'Segarkan'}
        </Button>
      </div>
      {error && (
        <p className="auth-error" role="alert">
          {error}
        </p>
      )}
      {items.length === 0 && !busy ? (
        <p className="adm-help">Belum ada siaran yang cocok.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Mulai</th>
              <th>Materi</th>
              <th>Format</th>
              <th>Durasi</th>
              <th>Giliran</th>
              <th>Status</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {items.map((s) => {
              const st = statusOf(s, live)
              return (
                <tr key={s.session_id}>
                  <td>
                    <small>{fmtTime(s.started)}</small>
                  </td>
                  <td>
                    <strong>{s.tema ?? '(tanpa materi)'}</strong>
                    {s.variant_label && <small> · {s.variant_label}</small>}
                    <br />
                    <small className="adm-id">{s.session_id}</small>
                  </td>
                  <td>
                    {FORMAT_LABEL[s.mode ?? ''] ?? '-'}
                    <br />
                    <small>{s.participants.join(' + ')}</small>
                  </td>
                  <td>{fmtDur(s.elapsed_s)}</td>
                  <td>
                    {s.n_ai_turns} AI{s.n_human_turns > 0 && ` · ${s.n_human_turns} penyiar`}
                  </td>
                  <td>
                    <Pill tone={st.tone}>{st.label}</Pill> {isTest(s) && <Pill>Uji (mock)</Pill>}
                  </td>
                  <td>
                    <Button onClick={() => onOpen(s.session_id)}>Buka</Button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
      {total > PAGE && (
        <div className="adm-actions">
          <Button onClick={() => setOffset(Math.max(0, offset - PAGE))} disabled={offset === 0}>
            Sebelumnya
          </Button>
          <span className="adm-help">
            {offset + 1}–{Math.min(offset + PAGE, total)} dari {total}
          </span>
          <Button onClick={() => setOffset(offset + PAGE)} disabled={offset + PAGE >= total}>
            Berikutnya
          </Button>
        </div>
      )}
    </section>
  )
}

// ── Detail ───────────────────────────────────────────────────────────────────
type SubTab = 'transkrip' | 'event' | 'konfigurasi' | 'materi'

function SessionView({ id, onBack }: { id: string; onBack: () => void }) {
  const [d, setD] = useState<SessionDetail | null>(null)
  const [error, setError] = useState('')
  const [tab, setTab] = useState<SubTab>('transkrip')

  const load = useCallback(() => {
    adminApi.session(id).then((r) => {
      setD(r)
      setError('')
    }).catch((e) => setError(errText(e)))
  }, [id])
  useEffect(load, [load])
  useEffect(() => {
    if (!d?.live) return
    const t = window.setInterval(load, 5000) // siaran berjalan: transkrip ikut bertambah
    return () => window.clearInterval(t)
  }, [d?.live, load])

  const s = d?.summary
  return (
    <>
      <div className="adm-actions">
        <Button onClick={onBack}>← Semua siaran</Button>
        <Button onClick={load}>Segarkan</Button>
        {d && (
          <>
            <a className="ui-btn" href={`/api/admin/sessions/${id}/export/events`} download>
              Unduh event (.jsonl)
            </a>
            {d.turns.length > 0 && (
              <a className="ui-btn" href={`/api/admin/sessions/${id}/export/turns`} download>
                Unduh giliran (.jsonl)
              </a>
            )}
          </>
        )}
      </div>
      {error && (
        <p className="auth-error" role="alert">
          {error}
        </p>
      )}
      {d && s && (
        <>
          <section className="ui-card adm-group">
            <h2 className="ui-card__title">
              {s.tema ?? '(tanpa materi)'} {s.variant_label && <small>· {s.variant_label}</small>} {d.live && <Pill tone="blue">Berjalan</Pill>} {isTest(s) && <Pill>Uji (mock)</Pill>}
            </h2>
            <small className="adm-id">{s.session_id}</small>
            <dl className="adm-stats">
              <Stat k="Format" v={`${FORMAT_LABEL[s.mode ?? ''] ?? '-'} (${s.participants.join(' + ')})`} />
              <Stat k="Mulai" v={fmtTime(s.started)} />
              <Stat k="Selesai" v={fmtTime(s.ended)} />
              <Stat k="Durasi" v={fmtDur(s.elapsed_s)} />
              <Stat k="Giliran" v={`${s.n_ai_turns} AI${s.n_human_turns ? ` · ${s.n_human_turns} penyiar` : ''}`} />
              <Stat k="Event" v={String(s.n_events)} />
              <Stat k="Topik di materi" v={String(s.n_topics)} />
              <Stat k="Supervisor" v={s.supervisor_mode ?? 'tidak dicatat'} />
              <Stat k="Suara" v={s.tts_provider ?? '-'} />
              <Stat k="Kode" v={s.code?.sha ? `${s.code.sha.slice(0, 7)}${s.code.dirty ? ' (ada perubahan belum commit)' : ''}` : 'tidak dicatat'} />
            </dl>
          </section>

          <nav className="adm-tabs" aria-label="Bagian log">
            {(['transkrip', 'event', 'konfigurasi', 'materi'] as SubTab[]).map((t) => (
              <button key={t} type="button" className={`adm-tab${t === tab ? ' is-on' : ''}`} onClick={() => setTab(t)}>
                {{ transkrip: `Transkrip (${d.turns.length || s.n_ai_turns})`, event: `Event (${d.events.length})`, konfigurasi: 'Konfigurasi', materi: 'Materi' }[t]}
              </button>
            ))}
          </nav>

          {tab === 'transkrip' && <Transcript d={d} />}
          {tab === 'event' && <Events d={d} />}
          {tab === 'konfigurasi' && <Config d={d} />}
          {tab === 'materi' && <Blocker d={d} />}
        </>
      )}
    </>
  )
}

function Stat({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <dt>{k}</dt>
      <dd>{v}</dd>
    </div>
  )
}

interface Line {
  idx: number
  who: string
  human: boolean
  text: string
  raw?: string
  segment?: string | null
  topic?: string | null
  act?: string | null
  llm?: number | null
  tts?: number | null
  provider?: string | null
  t?: number | null
}

function Transcript({ d }: { d: SessionDetail }) {
  const lines = useMemo<Line[]>(() => {
    if (d.turns.length) {
      const t0 = Number(d.turns[0].t_start) || 0
      return d.turns.map((r) => ({
        idx: Number(r.turn_idx),
        who: String(r.speaker_name || r.speaker || '?'),
        human: Boolean(r.is_human),
        text: String(r.text ?? ''),
        raw: r.raw_text && r.raw_text !== r.text ? String(r.raw_text) : undefined,
        segment: r.segment as string | null,
        topic: r.topic_id as string | null,
        act: r.dialog_act as string | null,
        llm: r.latency_llm_ms as number | null,
        tts: r.latency_tts_ms as number | null,
        provider: r.tts_provider as string | null,
        t: r.t_start ? Number(r.t_start) - t0 : null,
      }))
    }
    // Sesi lama tanpa log giliran riset: ambil dari event `turn`.
    return d.events
      .filter((e) => e.type === 'turn')
      .map((e) => ({
        idx: Number(e.turn),
        who: String(e.persona ?? '?'),
        human: false,
        text: String(e.final_text ?? ''),
        raw: e.raw_text && e.raw_text !== e.final_text ? String(e.raw_text) : undefined,
        segment: e.segment as string | null,
        topic: e.topic_id as string | null,
        act: e.dialog_act as string | null,
        provider: e.tts_provider as string | null,
      }))
  }, [d])

  if (!lines.length) return <p className="adm-help">Siaran ini belum punya giliran.</p>
  return (
    <section className="ui-card adm-group">
      <ol className="adm-transcript">
        {lines.map((l) => (
          <li key={l.idx} className={l.human ? 'is-human' : ''}>
            <div className="adm-transcript__meta">
              <strong>{l.who}</strong>
              <small>#{l.idx}</small>
              {l.t != null && <small>+{fmtDur(l.t)}</small>}
              {l.segment && <Pill>{l.segment === 'topic' && l.topic ? `topik ${l.topic}` : l.segment}</Pill>}
              {l.act && <Pill tone="blue">{l.act}</Pill>}
              {l.llm != null && l.llm > 0 && <small>otak {l.llm} ms</small>}
              {l.tts != null && l.tts > 0 && <small>suara {l.tts} ms</small>}
              {l.provider && <small>{l.provider}</small>}
            </div>
            <p>{l.text || <em>(kosong)</em>}</p>
            {l.raw && (
              <details>
                <summary>Teks mentah sebelum diperbaiki</summary>
                <p>{l.raw}</p>
              </details>
            )}
          </li>
        ))}
      </ol>
    </section>
  )
}

function Events({ d }: { d: SessionDetail }) {
  const [type, setType] = useState('')
  const counts = useMemo(() => {
    const c = new Map<string, number>()
    for (const e of d.events) c.set(String(e.type), (c.get(String(e.type)) ?? 0) + 1)
    return [...c.entries()]
  }, [d])
  const shown = type ? d.events.filter((e) => e.type === type) : d.events
  return (
    <section className="ui-card adm-group">
      <div className="adm-chips">
        <button type="button" className={`adm-chip${type === '' ? ' is-on' : ''}`} onClick={() => setType('')}>
          semua ({d.events.length})
        </button>
        {counts.map(([t, n]) => (
          <button key={t} type="button" className={`adm-chip${type === t ? ' is-on' : ''}`} onClick={() => setType(t)}>
            {t} ({n})
          </button>
        ))}
      </div>
      <ul className="adm-events">
        {shown.map((e, i) => (
          <li key={i}>
            <details>
              <summary>
                <Pill>{String(e.type)}</Pill> <small>{fmtTime(e.ts as string)}</small> <span className="adm-evsum">{summaryOf(e)}</span>
              </summary>
              <pre className="adm-json">{JSON.stringify(e, null, 2)}</pre>
            </details>
          </li>
        ))}
      </ul>
    </section>
  )
}

function summaryOf(e: Record<string, unknown>): string {
  const pick = (...ks: string[]) => ks.map((k) => (e[k] != null && e[k] !== '' ? `${k}=${typeof e[k] === 'object' ? '…' : String(e[k]).slice(0, 60)}` : '')).filter(Boolean).join(' ')
  switch (e.type) {
    case 'turn':
      return `${e.persona ?? ''}: ${String(e.final_text ?? '').slice(0, 90)}`
    case 'session_end':
      return pick('reason', 'turns', 'elapsed_s')
    case 'operator_action':
      return pick('action', 'from_segment', 'to_segment')
    case 'topic_change':
      return pick('judul', 'reason')
    case 'showrunner':
      return pick('decision', 'steer_hint', 'reason')
    case 'point_start':
    case 'point_end':
      return pick('point_id', 'reason', 'limit_s')
    default:
      return pick('mode', 'stage', 'message')
  }
}

function Config({ d }: { d: SessionDetail }) {
  const entries = Object.entries(d.config)
  return (
    <section className="ui-card adm-group">
      <p className="adm-help">Keadaan sistem saat siaran dimulai (dicatat di event session_start): setelan yang berlaku, model, versi prompt, hash prompt dan persona, seed, dan commit kode.</p>
      <table>
        <tbody>
          {entries.map(([k, v]) => (
            <tr key={k}>
              <th scope="row">{k}</th>
              <td>{typeof v === 'object' && v !== null ? <pre className="adm-json">{JSON.stringify(v, null, 2)}</pre> : String(v)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

function Blocker({ d }: { d: SessionDetail }) {
  const b = d.blocker as null | {
    tema?: string
    opening?: { hook?: string; poin?: string[] }
    topics?: { judul?: string; menit?: number; sudut_pandang?: string; poin?: { text: string }[]; pertanyaan_penonton?: string; transisi?: string }[]
    closing?: { rangkuman?: string; ajakan?: string }
  }
  if (!b) return <p className="adm-help">Materi sesi ini tidak tercatat.</p>
  return (
    <section className="ui-card adm-group">
      <p>
        <strong>Opening:</strong> {b.opening?.hook}
      </p>
      {b.topics?.map((t, i) => (
        <div key={i} className="adm-snippet">
          <strong>
            Topik {i + 1}: {t.judul} {t.menit ? <small>({t.menit} mnt)</small> : null}
          </strong>
          <small>{t.sudut_pandang}</small>
          <ul>
            {t.poin?.map((p, j) => (
              <li key={j}>{p.text}</li>
            ))}
          </ul>
          <small>Tanya penonton: {t.pertanyaan_penonton}</small>
          <small>Transisi: {t.transisi}</small>
        </div>
      ))}
      <p>
        <strong>Closing:</strong> {b.closing?.rangkuman} {b.closing?.ajakan}
      </p>
    </section>
  )
}
