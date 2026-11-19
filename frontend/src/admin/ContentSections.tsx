/**
 * Bagian admin untuk konten yang tidak boleh hardcode: persona, prompt berversi, potongan teks prompt,
 * kata terlarang dan kalimat aman Supervisor. Perubahan berlaku di giliran/siaran berikutnya.
 */
import { useCallback, useEffect, useState } from 'react'
import { adminApi, ApiError, type AdminPersona, type AdminPromptRow, type AdminSnippet, type AdminSupervisor } from '../api'
import { Button, Pill } from '../ui'

const errText = (e: unknown) => (e instanceof ApiError ? e.message : 'Gagal menghubungi server')
const lines = (s: string) => s.split('\n').map((x) => x.trim()).filter(Boolean)

function Messages({ error, notice }: { error: string; notice: string }) {
  return (
    <>
      {error && (
        <p className="auth-error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="auth-ok" role="status">
          {notice}
        </p>
      )}
    </>
  )
}

// ── Persona ──────────────────────────────────────────────────────────────────
const LIST_FIELDS: { key: 'catchphrases' | 'topic_limits' | 'background_facts' | 'do_not' | 'opinions'; label: string; help: string }[] = [
  { key: 'catchphrases', label: 'Catchphrase', help: 'Satu per baris. Dipakai sesekali.' },
  { key: 'background_facts', label: 'Fakta latar', help: 'Satu per baris. Dipegang konsisten oleh penyiar (dan Supervisor).' },
  { key: 'opinions', label: 'Pendapat', help: 'Satu per baris.' },
  { key: 'topic_limits', label: 'Batas topik', help: 'Satu per baris. Hal yang tidak dibahas.' },
  { key: 'do_not', label: 'Jangan', help: 'Satu per baris. Larangan gaya/perilaku.' },
]

export function PersonasSection() {
  const [items, setItems] = useState<AdminPersona[]>([])
  const [error, setError] = useState('')
  useEffect(() => {
    adminApi.personas().then(setItems).catch((e) => setError(errText(e)))
  }, [])
  return (
    <>
      <p className="adm-help">Kartu penyiar AI. Perubahan dipakai siaran berikutnya; isi kartu (hash) dicatat di log tiap sesi.</p>
      {error && (
        <p className="auth-error" role="alert">
          {error}
        </p>
      )}
      {items.map((p) => (
        <PersonaCard key={p.id} initial={p} />
      ))}
    </>
  )
}

function PersonaCard({ initial }: { initial: AdminPersona }) {
  const [p, setP] = useState(initial)
  const [text, setText] = useState<Record<string, string>>(() => Object.fromEntries(LIST_FIELDS.map((f) => [f.key, initial[f.key].join('\n')])))
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  const save = async () => {
    setBusy(true)
    setMsg(null)
    try {
      const body: AdminPersona = { ...p, ...Object.fromEntries(LIST_FIELDS.map((f) => [f.key, lines(text[f.key])])) }
      const saved = await adminApi.savePersona(body)
      setP(saved)
      setText(Object.fromEntries(LIST_FIELDS.map((f) => [f.key, saved[f.key].join('\n')])))
      setMsg({ ok: true, text: 'Tersimpan. Dipakai di siaran berikutnya.' })
    } catch (e) {
      setMsg({ ok: false, text: errText(e) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="ui-card adm-group" aria-labelledby={`p-${p.id}`}>
      <h2 id={`p-${p.id}`} className="ui-card__title">
        {p.name} <small className="adm-id">({p.id})</small>
      </h2>
      <div className="users__new">
        <label className="auth-field">
          Nama
          <input value={p.name} onChange={(e) => setP({ ...p, name: e.target.value })} />
        </label>
        <label className="auth-field">
          Gender
          <select value={p.gender} onChange={(e) => setP({ ...p, gender: e.target.value as 'male' | 'female' })}>
            <option value="male">Pria</option>
            <option value="female">Wanita</option>
          </select>
        </label>
        <label className="auth-field">
          Suara Edge bawaan
          <input value={p.voices.edge ?? ''} onChange={(e) => setP({ ...p, voices: { ...p.voices, edge: e.target.value } })} spellCheck={false} />
        </label>
      </div>
      <label className="auth-field">
        Gaya bicara
        <textarea className="adm-text" rows={4} value={p.speaking_style} onChange={(e) => setP({ ...p, speaking_style: e.target.value })} />
      </label>
      {LIST_FIELDS.map((f) => (
        <label key={f.key} className="auth-field">
          {f.label}
          <textarea className="adm-text" rows={4} value={text[f.key]} onChange={(e) => setText({ ...text, [f.key]: e.target.value })} spellCheck />
          <span className="adm-help">{f.help}</span>
        </label>
      ))}
      <div className="adm-actions">
        <Button variant="primary" onClick={() => void save()} disabled={busy}>
          {busy ? 'Menyimpan…' : 'Simpan'}
        </Button>
      </div>
      {msg && (
        <p className={msg.ok ? 'auth-ok' : 'auth-error'} role={msg.ok ? 'status' : 'alert'}>
          {msg.text}
        </p>
      )}
    </section>
  )
}

// ── Prompt berversi ──────────────────────────────────────────────────────────
const PROMPT_LABELS: Record<string, string> = {
  persona: 'Penyiar AI (sistem)',
  showrunner: 'Pengarah acara',
  supervisor: 'Supervisor',
  summary: 'Ringkasan obrolan',
  blocker: 'Pembuat materi',
}

/** Usulan nama versi berikutnya: persona-v4 → persona-v5; selain itu tambah -2. */
function nextVersion(current: string): string {
  const m = current.match(/^(.*?)(\d+)$/)
  return m ? `${m[1]}${Number(m[2]) + 1}` : `${current}-2`
}

export function PromptsSection() {
  const [rows, setRows] = useState<AdminPromptRow[]>([])
  const [name, setName] = useState('persona')
  const [body, setBody] = useState('')
  const [version, setVersion] = useState('')
  const [activate, setActivate] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(() => {
    adminApi.prompts().then(setRows).catch((e) => setError(errText(e)))
  }, [])
  useEffect(load, [load])

  const names = [...new Set(rows.map((r) => r.name))]
  const versions = rows.filter((r) => r.name === name)
  const active = versions.find((r) => r.active)

  // Isi editor dari versi aktif setiap ganti prompt atau setelah versi aktif berubah.
  useEffect(() => {
    if (!active) return
    adminApi.promptBody(active.name, active.version).then((r) => {
      setBody(r.body)
      setVersion(nextVersion(active.version))
    }).catch((e) => setError(errText(e)))
  }, [active?.name, active?.version]) // eslint-disable-line react-hooks/exhaustive-deps

  const run = async (fn: () => Promise<unknown>, ok: string) => {
    setError('')
    setNotice('')
    try {
      await fn()
      setNotice(ok)
      load()
    } catch (e) {
      setError(errText(e))
    }
  }

  const load_version = (v: string) => {
    adminApi.promptBody(name, v).then((r) => setBody(r.body)).catch((e) => setError(errText(e)))
  }

  return (
    <section className="ui-card adm-group" aria-labelledby="g-prompts">
      <h2 id="g-prompts" className="ui-card__title">
        Prompt berversi
      </h2>
      <p className="adm-help">Setiap perubahan jadi versi baru; versi lama tetap tersimpan dan bisa diaktifkan lagi. Versi aktif dipakai di siaran berikutnya, dan namanya dicatat di log tiap sesi.</p>
      <Messages error={error} notice={notice} />
      <label className="auth-field">
        Prompt
        <select value={name} onChange={(e) => setName(e.target.value)}>
          {names.map((n) => (
            <option key={n} value={n}>
              {PROMPT_LABELS[n] ?? n}
            </option>
          ))}
        </select>
      </label>
      <table>
        <thead>
          <tr>
            <th>Versi</th>
            <th>Dibuat</th>
            <th>Aksi</th>
          </tr>
        </thead>
        <tbody>
          {versions.map((v) => (
            <tr key={v.version}>
              <td>
                <strong>{v.version}</strong> {v.active && <Pill tone="blue">Aktif</Pill>}
              </td>
              <td>
                <small>
                  {new Date(v.created_at).toLocaleString('id-ID', { dateStyle: 'medium', timeStyle: 'short' })} · {v.created_by ?? '-'}
                </small>
              </td>
              <td>
                <span className="users__row-actions">
                  <Button onClick={() => load_version(v.version)}>Lihat</Button>
                  {!v.active && <Button onClick={() => void run(() => adminApi.activatePrompt(name, v.version), `Versi ${v.version} diaktifkan.`)}>Aktifkan</Button>}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {active && (
        <p className="adm-help">
          Placeholder yang diisi program (harus tetap ada, tidak boleh ditambah): {active.placeholders.length ? active.placeholders.map((p) => `{${p}}`).join(' ') : 'tidak ada'}
        </p>
      )}
      <label className="auth-field">
        Isi prompt
        <textarea className="adm-text adm-text--tall" value={body} onChange={(e) => setBody(e.target.value)} spellCheck={false} />
      </label>
      <div className="users__new">
        <label className="auth-field">
          Nama versi baru
          <input value={version} onChange={(e) => setVersion(e.target.value)} spellCheck={false} />
        </label>
        <label className="auth-field">
          <span>Langsung aktifkan</span>
          <select value={activate ? 'ya' : 'tidak'} onChange={(e) => setActivate(e.target.value === 'ya')}>
            <option value="ya">Ya</option>
            <option value="tidak">Tidak, simpan saja</option>
          </select>
        </label>
        <Button variant="primary" onClick={() => void run(() => adminApi.addPromptVersion(name, version.trim(), body, activate), `Versi ${version} disimpan${activate ? ' dan diaktifkan' : ''}.`)}>
          Simpan sebagai versi baru
        </Button>
      </div>
    </section>
  )
}

// ── Potongan teks prompt ─────────────────────────────────────────────────────
const SNIPPET_GROUPS: [string, string][] = [
  ['turn.', 'Prompt giliran penyiar'],
  ['length.', 'Petunjuk panjang giliran'],
  ['dialog_act.', 'Tugas giliran (aksi dialog)'],
  ['sr.', 'Prompt pengarah acara'],
  ['sup.', 'Prompt Supervisor'],
  ['sum.', 'Prompt ringkasan'],
  ['gen.', 'Prompt pembuat materi'],
]

function groupOf(key: string): string {
  return SNIPPET_GROUPS.find(([p]) => key.startsWith(p))?.[1] ?? 'Gaya HITS dan lain-lain'
}

export function SnippetsSection() {
  const [items, setItems] = useState<AdminSnippet[]>([])
  const [error, setError] = useState('')
  const load = useCallback(() => {
    adminApi.snippets().then(setItems).catch((e) => setError(errText(e)))
  }, [])
  useEffect(load, [load])

  const groups = new Map<string, AdminSnippet[]>()
  for (const s of items) groups.set(groupOf(s.key), [...(groups.get(groupOf(s.key)) ?? []), s])

  return (
    <>
      <p className="adm-help">Potongan teks yang disusun program menjadi prompt (dulu tertulis di kode). Kata dalam kurung kurawal, mis. {'{tema}'}, diisi program dan tidak boleh dihapus.</p>
      {error && (
        <p className="auth-error" role="alert">
          {error}
        </p>
      )}
      {[...groups.entries()].map(([title, list]) => (
        <details key={title} className="ui-card adm-group">
          <summary className="ui-card__title">
            {title} ({list.length})
          </summary>
          {list.map((s) => (
            <SnippetRow key={s.key} s={s} onSaved={load} />
          ))}
        </details>
      ))}
    </>
  )
}

function SnippetRow({ s, onSaved }: { s: AdminSnippet; onSaved: () => void }) {
  const [text, setText] = useState(s.text)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const dirty = text !== s.text
  const save = async () => {
    setMsg(null)
    try {
      await adminApi.saveSnippet(s.key, text)
      setMsg({ ok: true, text: 'Tersimpan.' })
      onSaved()
    } catch (e) {
      setMsg({ ok: false, text: errText(e) })
    }
  }
  return (
    <div className="adm-snippet">
      <label className="auth-field">
        <span>
          <code>{s.key}</code> {s.placeholders.map((p) => <Pill key={p}>{`{${p}}`}</Pill>)}
        </span>
        <textarea className="adm-text" rows={Math.min(8, Math.max(2, Math.ceil(text.length / 90)))} value={text} onChange={(e) => setText(e.target.value)} />
      </label>
      <div className="adm-actions">
        <Button variant="primary" onClick={() => void save()} disabled={!dirty}>
          Simpan
        </Button>
        {dirty && (
          <Button variant="link" onClick={() => setText(s.text)}>
            Batalkan
          </Button>
        )}
        {msg && <span className={msg.ok ? 'auth-ok' : 'auth-error'}>{msg.text}</span>}
      </div>
    </div>
  )
}

// ── Supervisor: kata terlarang dan kalimat aman ──────────────────────────────
export function SupervisorSection() {
  const [data, setData] = useState<AdminSupervisor | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [word, setWord] = useState({ word: '', category: '' })
  const [line, setLine] = useState({ persona: 'raka', kind: 'topic', text: '' })

  const load = useCallback(() => {
    adminApi.supervisor().then(setData).catch((e) => setError(errText(e)))
  }, [])
  useEffect(load, [load])

  const run = async (fn: () => Promise<unknown>, ok: string) => {
    setError('')
    setNotice('')
    try {
      await fn()
      setNotice(ok)
      load()
    } catch (e) {
      setError(errText(e))
    }
  }

  const categories = [...new Set((data?.banned ?? []).map((b) => b.category))]
  const personas = [...new Set((data?.fallbacks ?? []).map((f) => f.persona))]

  return (
    <>
      <Messages error={error} notice={notice} />
      <section className="ui-card adm-group" aria-labelledby="g-banned">
        <h2 id="g-banned" className="ui-card__title">
          Kata terlarang ({data?.banned.length ?? 0})
        </h2>
        <p className="adm-help">Dicocokkan sebagai kata utuh tanpa beda huruf besar. Ucapan yang memuatnya ditulis ulang oleh Supervisor (mode aturan atau penuh).</p>
        {categories.map((c) => (
          <div key={c} className="adm-chips">
            <strong>{c}</strong>
            {data!.banned.filter((b) => b.category === c).map((b) => (
              <button key={b.word} type="button" className="adm-chip" title="Hapus" onClick={() => void run(() => adminApi.deleteBanned(b.word), `'${b.word}' dihapus.`)}>
                {b.word} ✕
              </button>
            ))}
          </div>
        ))}
        <form
          className="users__new"
          onSubmit={(e) => {
            e.preventDefault()
            void run(async () => {
              await adminApi.addBanned(word.word, word.category)
              setWord({ ...word, word: '' })
            }, `'${word.word.trim().toLowerCase()}' ditambahkan.`)
          }}
        >
          <label className="auth-field">
            Kata atau frasa
            <input value={word.word} onChange={(e) => setWord({ ...word, word: e.target.value })} required />
          </label>
          <label className="auth-field">
            Kategori
            <input list="kategori" value={word.category} onChange={(e) => setWord({ ...word, category: e.target.value })} placeholder="kasar_berat" required />
            <datalist id="kategori">
              {categories.map((c) => (
                <option key={c} value={c} />
              ))}
            </datalist>
          </label>
          <Button type="submit" variant="primary">
            Tambah
          </Button>
        </form>
      </section>

      <section className="ui-card adm-group" aria-labelledby="g-fallbacks">
        <h2 id="g-fallbacks" className="ui-card__title">
          Kalimat aman ({data?.fallbacks.length ?? 0})
        </h2>
        <p className="adm-help">Dipakai menggantikan ucapan yang gagal diperbaiki, atau saat penyiar AI gagal menjawab. Dipilih bergiliran per penyiar dan bagian siaran.</p>
        <table>
          <thead>
            <tr>
              <th>Penyiar</th>
              <th>Bagian</th>
              <th>Kalimat</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {(data?.fallbacks ?? []).map((f) => (
              <tr key={f.id}>
                <td>{f.persona}</td>
                <td>{f.kind}</td>
                <td>{f.text}</td>
                <td>
                  <Button variant="danger" onClick={() => void run(() => adminApi.deleteFallback(f.id), 'Kalimat dihapus.')}>
                    Hapus
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <form
          className="users__new"
          onSubmit={(e) => {
            e.preventDefault()
            void run(async () => {
              await adminApi.addFallback(line.persona, line.kind, line.text)
              setLine({ ...line, text: '' })
            }, 'Kalimat ditambahkan.')
          }}
        >
          <label className="auth-field">
            Penyiar
            <select value={line.persona} onChange={(e) => setLine({ ...line, persona: e.target.value })}>
              {(personas.length ? personas : ['raka', 'salsa']).map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>
          <label className="auth-field">
            Bagian
            <select value={line.kind} onChange={(e) => setLine({ ...line, kind: e.target.value })}>
              {(data?.kinds ?? ['opening', 'topic', 'closing']).map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </select>
          </label>
          <label className="auth-field" style={{ gridColumn: 'span 2' }}>
            Kalimat
            <input value={line.text} onChange={(e) => setLine({ ...line, text: e.target.value })} required />
          </label>
          <Button type="submit" variant="primary">
            Tambah
          </Button>
        </form>
      </section>
    </>
  )
}
