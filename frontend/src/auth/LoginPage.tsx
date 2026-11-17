import { useEffect, useState } from 'react'
import { api, ApiError } from '../api'
import { Button } from '../ui'
import './auth.css'

export function LoginPage({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    document.title = 'Masuk · Penyiar AI HITS'
  }, [])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await api.login(username, password)
      onLoggedIn()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Server tidak bisa dihubungi')
      setBusy(false)
    }
  }

  return (
    <main className="auth">
      <form className="ui-card auth-card" onSubmit={submit}>
        <img src="/logo-hits.png" alt="HITS Unikom Radio 103.9 FM" className="auth-card__logo" />
        <h1>Masuk</h1>
        <p>Penyiar AI HITS. Minta akun ke admin bila belum punya.</p>
        <label className="auth-field">
          Nama pengguna
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" autoCapitalize="none" spellCheck={false} autoFocus required />
        </label>
        <label className="auth-field">
          Kata sandi
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
        </label>
        {error && (
          <p className="auth-error" role="alert">
            {error}
          </p>
        )}
        <Button type="submit" variant="primary" size="lg" disabled={busy || !username || !password}>
          {busy ? 'Memeriksa…' : 'Masuk'}
        </Button>
      </form>
    </main>
  )
}
