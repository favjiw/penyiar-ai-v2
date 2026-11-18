/**
 * Halaman admin (/admin): kunci API, model, suara, dan wajah Simli, tanpa menyentuh .env di server.
 * Tab: Otak AI · Suara · Avatar (Simli). Pengguna ada di /pengguna.
 * Kunci API tidak pernah dikirim balik dari server: hanya "••••" + 4 karakter terakhir.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { adminApi, api, ApiError, type AdminConfig, type AdminFace, type AdminField, type AdminVoice, type TestService } from '../api'
import { useAuth } from '../auth/AuthContext'
import { Button, Pill } from '../ui'
import { LogsSection } from './LogsSection'
import { PersonasSection, PromptsSection, SnippetsSection, SupervisorSection } from './ContentSections'
import '../auth/auth.css'
import './admin.css'

type Tab = 'ai' | 'suara' | 'simli' | 'siaran' | 'persona' | 'prompt' | 'supervisor' | 'log'

const TABS: { id: Tab; label: string; groups: string[] }[] = [
  { id: 'ai', label: 'Otak AI', groups: ['gemini', 'compat'] },
  { id: 'suara', label: 'Suara', groups: ['tts'] },
  { id: 'simli', label: 'Avatar (Simli)', groups: ['simli'] },
  { id: 'siaran', label: 'Alur siaran', groups: ['show', 'kuota'] },
  { id: 'persona', label: 'Penyiar AI', groups: ['persona'] },
  { id: 'prompt', label: 'Prompt & teks', groups: [] },
  { id: 'supervisor', label: 'Supervisor', groups: ['supervisor'] },
  { id: 'log', label: 'Log siaran', groups: [] },
]

const TEST_FOR: Record<string, { service: TestService; label: string }> = {
  gemini: { service: 'gemini', label: 'Uji Gemini' },
  compat: { service: 'compat', label: 'Uji LLM cadangan' },
  tts: { service: 'elevenlabs', label: 'Uji ElevenLabs' },
  simli: { service: 'simli', label: 'Uji Simli' },
}

const errText = (e: unknown) => (e instanceof ApiError ? e.message : 'Gagal menghubungi server')

export function AdminPage() {
  const { can } = useAuth()
  const isAdmin = can('admin')
  const [tab, setTab] = useState<Tab>(() => (TABS.find((t) => t.id === window.location.hash.slice(1).split('/')[0])?.id ?? 'ai'))
  const [cfg, setCfg] = useState<AdminConfig | null>(null)
  const [faces, setFaces] = useState<AdminFace[]>([])
  const [error, setError] = useState('')

  const load = useCallback(() => {
    adminApi.config().then(setCfg).catch((e) => setError(errText(e)))
    adminApi.faces().then(setFaces).catch(() => undefined)
  }, [])

  useEffect(() => {
    document.title = 'Admin · Penyiar AI HITS'
    if (isAdmin) load()
  }, [isAdmin, load])

  const choose = (t: Tab) => {
    setTab(t)
    window.history.replaceState(null, '', `#${t}`)
  }

  if (!isAdmin)
    return (
      <main className="users">
        <section className="ui-card">
          <h1>Khusus admin</h1>
          <p>Akun Anda tidak boleh membuka halaman admin.</p>
          <a className="ui-btn" href="/">
            Kembali
          </a>
        </section>
      </main>
    )

  const groups = cfg?.groups.filter((g) => TABS.find((t) => t.id === tab)!.groups.includes(g.id)) ?? []

  return (
    <main className="users adm">
      <div className="users__top">
        <h1>Admin</h1>
        <a className="ui-btn" href="/pengguna">
          Pengguna
        </a>
        <a className="ui-btn" href="/">
          Kembali ke konsol
        </a>
      </div>

      <nav className="adm-tabs" aria-label="Bagian admin">
        {TABS.map((t) => (
          <button key={t.id} type="button" className={`adm-tab${t.id === tab ? ' is-on' : ''}`} aria-current={t.id === tab ? 'page' : undefined} onClick={() => choose(t.id)}>
            {t.label}
          </button>
        ))}
      </nav>

      {error && (
        <p className="auth-error" role="alert">
          {error}
        </p>
      )}
      {cfg && !cfg.secrets_enabled && (
        <p className="adm-warn" role="status">
          Kunci API belum bisa disimpan dari halaman ini: <code>SECRETS_KEY</code> belum diatur di server. Buat dengan <code>python -m app.cli gen-secrets-key</code>, taruh di <code>.env</code> server, lalu mulai ulang aplikasi. Setelan lain tetap bisa diubah.
        </p>
      )}
      {cfg?.pending && (
        <p className="adm-warn" role="status">
          {cfg.live ? 'Ada siaran yang sedang berjalan: perubahan tersimpan dan berlaku setelah siaran selesai.' : 'Ada perubahan yang belum berlaku. Muat ulang halaman ini setelah siaran selesai.'}
        </p>
      )}
      {cfg?.apply_error && (
        <p className="auth-error" role="alert">
          Tersimpan, tetapi belum bisa diterapkan: {cfg.apply_error}. Setelan lama tetap dipakai.
        </p>
      )}

      {groups.map((g) => (
        <ConfigGroup key={g.id} id={g.id} label={g.label} fields={g.fields} faces={faces} secretsEnabled={cfg?.secrets_enabled ?? false} onSaved={setCfg} />
      ))}

      {tab === 'suara' && <VoicesSection />}
      {tab === 'persona' && <PersonasSection />}
      {tab === 'prompt' && (
        <>
          <PromptsSection />
          <SnippetsSection />
        </>
      )}
      {tab === 'supervisor' && <SupervisorSection />}
      {tab === 'log' && <LogsSection />}
      {tab === 'simli' && <FacesSection faces={faces} inUse={cfg ? facesInUse(cfg) : new Set()} onChange={load} />}
    </main>
  )
}

function facesInUse(cfg: AdminConfig): Set<string> {
  const keys = new Set(['SIMLI_FACE_ID_RAKA', 'SIMLI_FACE_ID_SALSA', 'SIMLI_FACE_ID'])
  return new Set(cfg.groups.flatMap((g) => g.fields).filter((f) => keys.has(f.key) && f.value).map((f) => f.value!))
}

// ── Setelan ──────────────────────────────────────────────────────────────────
function ConfigGroup({
  id, label, fields, faces, secretsEnabled, onSaved,
}: {
  id: string
  label: string
  fields: AdminField[]
  faces: AdminFace[]
  secretsEnabled: boolean
  onSaved: (c: AdminConfig) => void
}) {
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [test, setTest] = useState<{ busy: boolean; ok?: boolean; text?: string }>({ busy: false })
  const dirty = Object.keys(draft).length > 0
  const testing = TEST_FOR[id]

  const save = async (values: Record<string, string | null>, okText: string) => {
    setBusy(true)
    setMsg(null)
    try {
      const next = await adminApi.saveConfig(values)
      onSaved(next)
      setDraft({})
      setMsg({ ok: true, text: next.applied ? `${okText} Sudah berlaku.` : next.live ? `${okText} Berlaku setelah siaran selesai.` : okText })
    } catch (e) {
      setMsg({ ok: false, text: errText(e) })
    } finally {
      setBusy(false)
    }
  }

  const runTest = async () => {
    if (!testing) return
    setTest({ busy: true })
    try {
      const r = await adminApi.test(testing.service)
      setTest({ busy: false, ok: r.ok, text: r.message })
    } catch (e) {
      setTest({ busy: false, ok: false, text: errText(e) })
    }
  }

  return (
    <section className="ui-card adm-group" aria-labelledby={`g-${id}`}>
      <h2 id={`g-${id}`} className="ui-card__title">
        {label}
      </h2>
      <div className="adm-fields">
        {fields.map((f) => (
          <FieldRow key={f.key} f={f} faces={faces} secretsEnabled={secretsEnabled} value={draft[f.key]} onChange={(v) => setDraft((d) => ({ ...d, [f.key]: v }))} onReset={() => void save({ [f.key]: null }, `${f.label} dikembalikan ke bawaan server.`)} busy={busy} />
        ))}
      </div>
      <div className="adm-actions">
        <Button variant="primary" disabled={!dirty || busy} onClick={() => void save(draft, 'Tersimpan.')}>
          {busy ? 'Menyimpan…' : 'Simpan'}
        </Button>
        {dirty && (
          <Button variant="link" onClick={() => setDraft({})}>
            Batalkan
          </Button>
        )}
        {testing && (
          <Button onClick={() => void runTest()} disabled={test.busy || dirty} title={dirty ? 'Simpan dulu: uji memakai setelan yang tersimpan' : undefined}>
            {test.busy ? 'Menguji…' : testing.label}
          </Button>
        )}
      </div>
      {msg && (
        <p className={msg.ok ? 'auth-ok' : 'auth-error'} role={msg.ok ? 'status' : 'alert'}>
          {msg.text}
        </p>
      )}
      {test.text && (
        <p className={test.ok ? 'auth-ok' : 'auth-error'} role="status">
          {test.text}
        </p>
      )}
    </section>
  )
}

function FieldRow({
  f, faces, secretsEnabled, value, onChange, onReset, busy,
}: {
  f: AdminField
  faces: AdminFace[]
  secretsEnabled: boolean
  value: string | undefined
  onChange: (v: string) => void
  onReset: () => void
  busy: boolean
}) {
  const shown = value ?? f.value ?? ''
  const hint = f.help && <span className="adm-help">{f.help}</span>
  return (
    <div className="adm-row">
      <label className="auth-field">
        <span className="adm-label">
          {f.label} {f.source === 'admin' ? <Pill tone="blue">Diatur di sini</Pill> : <Pill>Bawaan server</Pill>}
        </span>
        {f.kind === 'secret' ? (
          <input
            type="password"
            value={value ?? ''}
            onChange={(e) => onChange(e.target.value)}
            placeholder={f.is_set ? `Terisi (${f.masked}). Ketik untuk mengganti` : 'Belum diisi'}
            autoComplete="off"
            spellCheck={false}
            disabled={!secretsEnabled}
          />
        ) : f.kind === 'choice' ? (
          <select value={shown} onChange={(e) => onChange(e.target.value)}>
            {f.choices.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        ) : f.kind === 'bool' ? (
          <select value={shown} onChange={(e) => onChange(e.target.value)}>
            <option value="true">Ya</option>
            <option value="false">Tidak</option>
          </select>
        ) : f.kind === 'face' ? (
          <select value={shown} onChange={(e) => onChange(e.target.value)}>
            <option value="">(bawaan)</option>
            {faces.map((x) => (
              <option key={x.id} value={x.id}>
                {x.name}
              </option>
            ))}
            {shown && !faces.some((x) => x.id === shown) && <option value={shown}>{shown}</option>}
          </select>
        ) : (
          <input value={shown} onChange={(e) => onChange(e.target.value)} inputMode={f.kind === 'number' ? 'decimal' : undefined} spellCheck={false} />
        )}
        {hint}
      </label>
      {f.source === 'admin' && (
        <Button variant="link" onClick={onReset} disabled={busy}>
          Kembalikan ke bawaan server
        </Button>
      )}
    </div>
  )
}

// ── Suara ────────────────────────────────────────────────────────────────────
function VoicesSection() {
  const [voices, setVoices] = useState<AdminVoice[]>([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [playing, setPlaying] = useState('')
  const audio = useRef<HTMLAudioElement | null>(null)
  const [form, setForm] = useState({ provider: 'elevenlabs' as 'elevenlabs' | 'edge', id: '', name: '', gender: 'female' as 'male' | 'female', notes: '' })

  const load = useCallback(() => {
    adminApi.voices().then(setVoices).catch((e) => setError(errText(e)))
  }, [])
  useEffect(load, [load])

  const run = async (fn: () => Promise<unknown>, ok: string) => {
    setError('')
    setNotice('')
    try {
      await fn()
      if (ok) setNotice(ok)
      load()
    } catch (e) {
      setError(errText(e))
    }
  }

  const add = (e: React.FormEvent) => {
    e.preventDefault()
    void run(async () => {
      const r = await adminApi.addVoice(form)
      setNotice(r.warning ? `Suara ${r.voice.name} ditambahkan. ${r.warning}` : `Suara ${r.voice.name} ditambahkan.`)
      setForm({ ...form, id: '', name: '', notes: '' })
    }, '')
  }

  const listen = async (v: AdminVoice) => {
    setError('')
    setPlaying(v.id)
    try {
      const r = await api.voiceSample(v.gender === 'male' ? 'raka' : 'salsa', v.id)
      audio.current?.pause()
      audio.current = new Audio(r.audio_url)
      audio.current.onended = () => setPlaying('')
      await audio.current.play()
      if (r.fallback) setNotice('Suara utama gagal; yang terdengar adalah suara cadangan.')
    } catch (e) {
      setPlaying('')
      setError(errText(e))
    }
  }

  return (
    <section className="ui-card adm-group" aria-labelledby="g-voices">
      <h2 id="g-voices" className="ui-card__title">
        Daftar suara ({voices.length})
      </h2>
      <p className="adm-help">Suara di daftar ini yang bisa dipilih operator sebelum live. Untuk ElevenLabs, suara harus sudah ada di akun (My Voices); ID-nya diperiksa saat ditambahkan.</p>
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
      <table>
        <thead>
          <tr>
            <th>Nama</th>
            <th>Penyedia</th>
            <th>Gender</th>
            <th>Aksi</th>
          </tr>
        </thead>
        <tbody>
          {voices.map((v) => (
            <tr key={v.id}>
              <td>
                <strong>{v.name}</strong>
                <br />
                <small className="adm-id">{v.id}</small>
                {v.notes && (
                  <>
                    <br />
                    <small>{v.notes}</small>
                  </>
                )}
              </td>
              <td>{v.provider === 'elevenlabs' ? 'ElevenLabs' : 'Edge'}</td>
              <td>{v.gender === 'male' ? 'Pria' : 'Wanita'}</td>
              <td>
                <span className="users__row-actions">
                  <Button onClick={() => void listen(v)} disabled={playing === v.id}>
                    {playing === v.id ? 'Memutar…' : 'Dengar'}
                  </Button>
                  <Button
                    variant="danger"
                    onClick={() => {
                      if (window.confirm(`Hapus suara ${v.name} dari daftar?`)) void run(() => adminApi.deleteVoice(v.id), `Suara ${v.name} dihapus.`)
                    }}
                  >
                    Hapus
                  </Button>
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3 className="adm-sub">Tambah suara</h3>
      <form className="users__new" onSubmit={add}>
        <label className="auth-field">
          Penyedia
          <select value={form.provider} onChange={(e) => setForm({ ...form, provider: e.target.value as 'elevenlabs' | 'edge' })}>
            <option value="elevenlabs">ElevenLabs</option>
            <option value="edge">Edge (gratis)</option>
          </select>
        </label>
        <label className="auth-field">
          ID suara
          <input value={form.id} onChange={(e) => setForm({ ...form, id: e.target.value })} placeholder={form.provider === 'edge' ? 'id-ID-ArdiNeural' : 'vChnJZ1Cu89g2XXumPfT'} spellCheck={false} required />
        </label>
        <label className="auth-field">
          Nama (kosong = ambil dari ElevenLabs)
          <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required={form.provider === 'edge'} />
        </label>
        <label className="auth-field">
          Gender
          <select value={form.gender} onChange={(e) => setForm({ ...form, gender: e.target.value as 'male' | 'female' })}>
            <option value="female">Wanita</option>
            <option value="male">Pria</option>
          </select>
        </label>
        <label className="auth-field">
          Catatan
          <input value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} placeholder="Santai, suara anak muda" />
        </label>
        <Button type="submit" variant="primary">
          Tambah
        </Button>
      </form>
    </section>
  )
}

// ── Wajah Simli ──────────────────────────────────────────────────────────────
function FacesSection({ faces, inUse, onChange }: { faces: AdminFace[]; inUse: Set<string>; onChange: () => void }) {
  const [error, setError] = useState('')
  const [form, setForm] = useState({ id: '', name: '' })

  const run = async (fn: () => Promise<unknown>) => {
    setError('')
    try {
      await fn()
      onChange()
    } catch (e) {
      setError(errText(e))
    }
  }

  return (
    <section className="ui-card adm-group" aria-labelledby="g-faces">
      <h2 id="g-faces" className="ui-card__title">
        Daftar wajah ({faces.length})
      </h2>
      <p className="adm-help">Tambahkan ID wajah dari akun Simli, lalu pilih untuk Raka dan Salsa di atas. Perubahan wajah berlaku di layar OBS setelah dimuat ulang.</p>
      {error && (
        <p className="auth-error" role="alert">
          {error}
        </p>
      )}
      <table>
        <thead>
          <tr>
            <th>Nama</th>
            <th>ID wajah</th>
            <th>Aksi</th>
          </tr>
        </thead>
        <tbody>
          {faces.map((f) => (
            <tr key={f.id}>
              <td>
                <strong>{f.name}</strong> {inUse.has(f.id) && <Pill tone="blue">Dipakai</Pill>}
              </td>
              <td>
                <small className="adm-id">{f.id}</small>
              </td>
              <td>
                <Button
                  variant="danger"
                  disabled={inUse.has(f.id)}
                  title={inUse.has(f.id) ? 'Sedang dipilih untuk penyiar; pilih wajah lain dulu' : undefined}
                  onClick={() => {
                    if (window.confirm(`Hapus wajah ${f.name} dari daftar?`)) void run(() => adminApi.deleteFace(f.id))
                  }}
                >
                  Hapus
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3 className="adm-sub">Tambah wajah</h3>
      <form
        className="users__new"
        onSubmit={(e) => {
          e.preventDefault()
          void run(async () => {
            await adminApi.addFace(form)
            setForm({ id: '', name: '' })
          })
        }}
      >
        <label className="auth-field">
          ID wajah Simli
          <input value={form.id} onChange={(e) => setForm({ ...form, id: e.target.value })} placeholder="bf13113a-355a-4d97-8b90-4edccd1da7b2" spellCheck={false} required />
        </label>
        <label className="auth-field">
          Nama
          <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Raka (jaket navy)" required />
        </label>
        <Button type="submit" variant="primary">
          Tambah
        </Button>
      </form>
    </section>
  )
}
