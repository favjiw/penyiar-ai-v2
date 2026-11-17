import { useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../api'
import { Button } from '../ui'
import { useAuth } from './AuthContext'
import './auth.css'

const ROLE_LABEL = { penyiar: 'Penyiar', operator: 'Operator', admin: 'Admin' } as const

/** Menu akun di header konsol: nama, ganti kata sandi, kelola pengguna (admin), keluar. Tidak tampil tanpa login. */
export function AccountChip() {
  const { user, authRequired, can, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const [changing, setChanging] = useState(false)
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])

  if (!authRequired) return null

  const change = async (e: React.FormEvent) => {
    e.preventDefault()
    setMsg(null)
    try {
      await api.changePassword(current, next)
      setMsg({ ok: true, text: 'Kata sandi diganti. Masuk ulang…' })
      window.setTimeout(() => window.location.reload(), 900)
    } catch (err) {
      setMsg({ ok: false, text: err instanceof ApiError ? err.message : 'Gagal mengganti kata sandi' })
    }
  }

  return (
    <div className="acct" ref={ref}>
      <Button onClick={() => setOpen((o) => !o)} aria-haspopup="menu" aria-expanded={open}>
        {user.display_name}
      </Button>
      {open && (
        <div className="acct__menu" role="menu">
          <div className="acct__who">
            <strong>{user.display_name}</strong>
            <span>
              {user.username} · {ROLE_LABEL[user.role]}
            </span>
          </div>
          {can('admin') && (
            <a className="acct__item" role="menuitem" href="/pengguna">
              Kelola pengguna
            </a>
          )}
          {!changing ? (
            <button className="acct__item" role="menuitem" onClick={() => setChanging(true)}>
              Ganti kata sandi
            </button>
          ) : (
            <form className="acct__form" onSubmit={change}>
              <label className="auth-field">
                Kata sandi sekarang
                <input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" required />
              </label>
              <label className="auth-field">
                Kata sandi baru (min. 10 karakter)
                <input type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" minLength={10} required />
              </label>
              {msg && <p className={msg.ok ? 'auth-ok' : 'auth-error'}>{msg.text}</p>}
              <Button type="submit" variant="primary">
                Simpan
              </Button>
            </form>
          )}
          <button className="acct__item" role="menuitem" onClick={() => void logout()}>
            Keluar
          </button>
        </div>
      )}
    </div>
  )
}
