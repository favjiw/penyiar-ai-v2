import { useCallback, useEffect, useState } from 'react'
import { api, ApiError, type Role, type UserRow } from '../api'
import { Button, Pill } from '../ui'
import { useAuth } from './AuthContext'
import './auth.css'

const ROLES: { value: Role; label: string; hint: string }[] = [
  { value: 'penyiar', label: 'Penyiar', hint: 'prompter saja' },
  { value: 'operator', label: 'Operator', hint: 'konsol, materi, siaran' },
  { value: 'admin', label: 'Admin', hint: 'semua + kelola pengguna' },
]

const fmt = (iso: string | null) => (iso ? new Date(iso).toLocaleString('id-ID', { dateStyle: 'medium', timeStyle: 'short' }) : 'belum pernah')

export function UsersPage() {
  const { user: me, can } = useAuth()
  const [rows, setRows] = useState<UserRow[]>([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [form, setForm] = useState({ username: '', display_name: '', password: '', role: 'penyiar' as Role })
  const isAdmin = can('admin')

  const load = useCallback(() => {
    api.users().then(setRows).catch((e) => setError(e instanceof ApiError ? e.message : 'Gagal memuat'))
  }, [])
  useEffect(() => {
    document.title = 'Pengguna · Penyiar AI HITS'
    if (isAdmin) load()
  }, [isAdmin, load])

  if (!isAdmin)
    return (
      <main className="users">
        <section className="ui-card">
          <h1>Khusus admin</h1>
          <p>Akun Anda tidak boleh mengelola pengguna.</p>
          <a className="ui-btn" href="/">
            Kembali
          </a>
        </section>
      </main>
    )

  const run = async (fn: () => Promise<unknown>, ok: string) => {
    setError('')
    setNotice('')
    try {
      await fn()
      setNotice(ok)
      load()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Gagal')
    }
  }

  const add = (e: React.FormEvent) => {
    e.preventDefault()
    void run(async () => {
      await api.createUser(form)
      setForm({ username: '', display_name: '', password: '', role: 'penyiar' })
    }, `Pengguna ${form.username.toLowerCase()} dibuat`)
  }

  const resetPassword = (u: UserRow) => {
    const pw = window.prompt(`Kata sandi baru untuk ${u.username} (min. 10 karakter). Beri tahu orangnya lewat jalur pribadi.`)
    if (pw) void run(() => api.updateUser(u.id, { password: pw }), `Kata sandi ${u.username} diganti; sesi loginnya dicabut`)
  }

  return (
    <main className="users">
      <div className="users__top">
        <h1>Pengguna</h1>
        <a className="ui-btn" href="/admin">
          Admin
        </a>
        <a className="ui-btn" href="/">
          Kembali ke konsol
        </a>
      </div>
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

      <section className="ui-card">
        <h2 className="ui-card__title">Tambah pengguna</h2>
        <form className="users__new" onSubmit={add}>
          <label className="auth-field">
            Nama pengguna
            <input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} autoCapitalize="none" spellCheck={false} placeholder="rani" required />
          </label>
          <label className="auth-field">
            Nama tampilan
            <input value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} placeholder="Rani" />
          </label>
          <label className="auth-field">
            Kata sandi awal
            <input type="text" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} minLength={10} autoComplete="off" required />
          </label>
          <label className="auth-field">
            Peran
            <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
              {ROLES.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label} ({r.hint})
                </option>
              ))}
            </select>
          </label>
          <Button type="submit" variant="primary">
            Tambah
          </Button>
        </form>
      </section>

      <section className="ui-card">
        <h2 className="ui-card__title">Daftar ({rows.length})</h2>
        <table>
          <thead>
            <tr>
              <th>Pengguna</th>
              <th>Peran</th>
              <th>Masuk terakhir</th>
              <th>Aksi</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((u) => (
              <tr key={u.id} className={u.active ? '' : 'is-off'}>
                <td>
                  <strong>{u.display_name}</strong>
                  <br />
                  <small>{u.username}</small> {!u.active && <Pill tone="danger">nonaktif</Pill>} {u.id === me.id && <Pill tone="blue">Anda</Pill>}
                </td>
                <td>
                  <select
                    value={u.role}
                    aria-label={`Peran ${u.username}`}
                    onChange={(e) => void run(() => api.updateUser(u.id, { role: e.target.value as Role }), `Peran ${u.username} diubah; sesi loginnya dicabut`)}
                  >
                    {ROLES.map((r) => (
                      <option key={r.value} value={r.value}>
                        {r.label}
                      </option>
                    ))}
                  </select>
                </td>
                <td>{fmt(u.last_login_at)}</td>
                <td>
                  <span className="users__row-actions">
                    <Button onClick={() => resetPassword(u)}>Ganti sandi</Button>
                    <Button
                      variant={u.active ? 'danger' : 'secondary'}
                      onClick={() => void run(() => api.updateUser(u.id, { active: !u.active }), u.active ? `${u.username} dinonaktifkan` : `${u.username} diaktifkan`)}
                    >
                      {u.active ? 'Nonaktifkan' : 'Aktifkan'}
                    </Button>
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  )
}
