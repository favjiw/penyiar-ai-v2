import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, ApiError, type AuthUser, type Role } from '../api'
import { LoginPage } from './LoginPage'

interface AuthValue {
  user: AuthUser
  /** false = server berjalan tanpa login (pengembangan lokal): tidak ada tombol Keluar. */
  authRequired: boolean
  can: (minimum: Role) => boolean
  logout: () => Promise<void>
}

const RANK: Record<Role, number> = { penyiar: 1, operator: 2, admin: 3 }
const Ctx = createContext<AuthValue | null>(null)

export function useAuth(): AuthValue {
  const v = useContext(Ctx)
  if (!v) throw new Error('useAuth di luar AuthGate')
  return v
}

type State =
  | { phase: 'loading' }
  | { phase: 'login' }
  | { phase: 'error'; message: string }
  | { phase: 'ready'; user: AuthUser; authRequired: boolean }

/** Gerbang login: tanpa sesi yang sah, halaman apa pun (termasuk /stage dan /prompter) hanya menampilkan layar masuk. */
export function AuthGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>({ phase: 'loading' })

  const load = useCallback(() => {
    api
      .me()
      .then((r) => setState({ phase: 'ready', user: r.user, authRequired: r.auth_required }))
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) setState({ phase: 'login' })
        else setState({ phase: 'error', message: 'Server tidak bisa dihubungi. Coba muat ulang halaman.' })
      })
  }, [])
  useEffect(load, [load])

  const logout = useCallback(async () => {
    await api.logout().catch(() => undefined)
    setState({ phase: 'login' })
  }, [])

  const value = useMemo<AuthValue | null>(
    () =>
      state.phase === 'ready'
        ? { user: state.user, authRequired: state.authRequired, can: (m) => RANK[state.user.role] >= RANK[m], logout }
        : null,
    [state, logout],
  )

  if (state.phase === 'loading') return null
  if (state.phase === 'error') return <p style={{ padding: 24, fontFamily: 'var(--font)' }}>{state.message}</p>
  if (state.phase === 'login') return <LoginPage onLoggedIn={load} />
  return <Ctx.Provider value={value!}>{children}</Ctx.Provider>
}
