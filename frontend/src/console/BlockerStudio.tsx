import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../api'
import type { Blocker, GenerateRequest } from '../types'
import { BlockerEditor } from './BlockerEditor'
import { BlockerView, VariantCard } from './VariantCard'

type Busy = null | 'generate' | 'save' | 'lock' | 'version' | `regen:${string}`

interface ErrorState {
  message: string
  issues: string[]
}

const MAX_TEMA = 60
const MAX_CATATAN = 500

const fmtTime = (iso: string) => new Date(iso).toLocaleString('id-ID', { dateStyle: 'medium', timeStyle: 'short' })

/** Generator dan editor blocker di konsol operator (FR-1, FR-11). */
export function BlockerStudio() {
  const [form, setForm] = useState<GenerateRequest>({ tema: '', catatan: '', jumlah_topik: 3, jumlah_varian: 3 })
  const [variants, setVariants] = useState<Blocker[]>([])
  const [active, setActive] = useState<Blocker | null>(null)
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState<Busy>(null)
  const [error, setError] = useState<ErrorState | null>(null)
  const [status, setStatus] = useState('')
  const [elapsed, setElapsed] = useState(0)
  const [lockedList, setLockedList] = useState<Blocker[]>([])
  const timer = useRef<number>()

  const refreshLocked = useCallback(() => {
    api.lockedList().then(setLockedList).catch(() => setLockedList([]))
  }, [])
  useEffect(refreshLocked, [refreshLocked])

  // Peringatan bila menutup tab dengan editan yang belum disimpan
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => {
      if (dirty) e.preventDefault()
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  const run = async <T,>(kind: Busy, fn: () => Promise<T>): Promise<T | undefined> => {
    setBusy(kind)
    setError(null)
    try {
      return await fn()
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e), 0)
      setError({ message: err.message, issues: err.issues })
      return undefined
    } finally {
      setBusy(null)
    }
  }

  const confirmDiscard = () => !dirty || window.confirm('Editan belum disimpan akan hilang. Lanjutkan?')

  const replaceVariant = (oldId: string, next: Blocker) => setVariants((vs) => vs.map((v) => (v.id === oldId ? next : v)))

  const generate = async () => {
    if (!form.tema.trim() || busy || !confirmDiscard()) return
    setStatus('')
    setElapsed(0)
    const started = Date.now()
    timer.current = window.setInterval(() => setElapsed((Date.now() - started) / 1000), 200)
    const res = await run('generate', () => api.generate({ ...form, tema: form.tema.trim() }))
    window.clearInterval(timer.current)
    if (!res) return
    setVariants(res.variants)
    setActive(null)
    setDirty(false)
    setStatus(
      `${res.variants.length} varian dalam ${(res.latency_ms / 1000).toFixed(1)} s · ${res.model}` +
        (res.attempts > 1 ? ' · diulang sekali' : ''),
    )
  }

  const select = (v: Blocker) => {
    if (active?.id === v.id || !confirmDiscard()) return
    setActive(structuredClone(v))
    setDirty(false)
  }

  const regenerate = async (v: Blocker) => {
    if (active?.id === v.id && !confirmDiscard()) return
    const hindari = variants.filter((x) => x.id !== v.id).map((x) => x.variant_label)
    const res = await run(`regen:${v.id}`, () => api.regenerate(v.id, hindari))
    if (!res) return
    replaceVariant(v.id, res.variant)
    if (active?.id === v.id) {
      setActive(structuredClone(res.variant))
      setDirty(false)
    }
    setStatus(`Varian dibuat ulang dalam ${(res.latency_ms / 1000).toFixed(1)} s`)
  }

  const save = async (): Promise<Blocker | undefined> => {
    if (!active || active.locked) return undefined
    const saved = await run('save', () => api.save(active))
    if (!saved) return undefined
    setActive(saved)
    setDirty(false)
    replaceVariant(saved.id, saved)
    setStatus('Tersimpan')
    return saved
  }

  const lock = async () => {
    if (!active || active.locked) return
    const current = dirty ? await save() : active
    if (!current) return
    const toCheck = current.topics.flatMap((t) => t.poin).filter((p) => p.perlu_cek).length
    const msg =
      (toCheck ? `Masih ada ${toCheck} poin bertanda "perlu cek". ` : '') +
      'Blocker yang dikunci tidak bisa diubah lagi (perubahan dibuat sebagai versi baru). Kunci sekarang?'
    if (!window.confirm(msg)) return
    const locked = await run('lock', () => api.lock(current.id))
    if (!locked) return
    setActive(locked)
    replaceVariant(locked.id, locked)
    refreshLocked()
    setStatus(`Blocker dikunci: ${locked.id}`)
  }

  const newVersion = async () => {
    if (!active?.locked) return
    const draft = await run('version', () => api.newVersion(active.id))
    if (!draft) return
    setActive(draft)
    setDirty(false)
    setStatus(`Versi ${draft.versi} dibuat dari ${active.id}; silakan edit lalu kunci`)
  }

  const openLocked = (b: Blocker) => {
    if (!confirmDiscard()) return
    setActive(b)
    setDirty(false)
  }

  // Pintasan keyboard (FR-11): Ctrl+S simpan draf
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault()
        if (dirty && !busy) void save()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  return (
    <div className="layout">
      <div>
        <section className="panel">
          <h2>Generator blocker</h2>
          <form
            className="gen"
            onSubmit={(e) => {
              e.preventDefault()
              void generate()
            }}
          >
            <label className="field">
              Tema
              <input
                type="text"
                value={form.tema}
                maxLength={MAX_TEMA}
                placeholder="mis. Zodiak"
                autoFocus
                onChange={(e) => setForm({ ...form, tema: e.target.value })}
              />
              <span className="count">
                {form.tema.length}/{MAX_TEMA}
              </span>
            </label>
            <label className="field">
              Catatan (opsional)
              <textarea
                value={form.catatan}
                maxLength={MAX_CATATAN}
                rows={1}
                placeholder="sasaran penonton, nuansa, hal yang dihindari"
                onChange={(e) => setForm({ ...form, catatan: e.target.value })}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                    e.preventDefault()
                    void generate()
                  }
                }}
              />
              <span className="count">
                {form.catatan.length}/{MAX_CATATAN}
              </span>
            </label>
            <label className="field">
              Topik
              <select value={form.jumlah_topik} onChange={(e) => setForm({ ...form, jumlah_topik: Number(e.target.value) })}>
                {[1, 2, 3].map((n) => (
                  <option key={n}>{n}</option>
                ))}
              </select>
              <span className="count">&nbsp;</span>
            </label>
            <label className="field">
              Varian
              <select value={form.jumlah_varian} onChange={(e) => setForm({ ...form, jumlah_varian: Number(e.target.value) })}>
                {[2, 3].map((n) => (
                  <option key={n}>{n}</option>
                ))}
              </select>
              <span className="count">&nbsp;</span>
            </label>
            <div>
              <button type="submit" className="primary" disabled={!form.tema.trim() || busy !== null}>
                {busy === 'generate' ? `Membuat… ${elapsed.toFixed(0)} s` : 'Buat varian'}
              </button>
              <span className="count">&nbsp;</span>
            </div>
          </form>
          <div className="status" aria-live="polite">
            {status} {variants.length === 0 && !status && <span>Ketik tema lalu tekan Enter.</span>}
          </div>
          {error && (
            <div className="error" role="alert">
              {error.message}
              {error.issues.length > 0 && (
                <ul>
                  {error.issues.map((i) => (
                    <li key={i}>{i}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </section>

        {variants.length > 0 && (
          <div className="variants">
            {variants.map((v) => (
              <VariantCard
                key={v.id}
                blocker={v}
                selected={active?.id === v.id}
                busy={busy !== null}
                onSelect={() => select(v)}
                onRegenerate={() => void regenerate(v)}
              />
            ))}
          </div>
        )}

        {active && (
          <section className="panel editor">
            <div className="head">
              <h2>
                {active.locked ? 'Blocker terkunci' : 'Edit blocker'}: {active.tema}
                <span className="badge locked">v{active.versi}</span>
                {active.locked && <span className="badge locked">terkunci</span>}
              </h2>
              {active.locked ? (
                <button onClick={() => void newVersion()} disabled={busy !== null}>
                  Buat versi baru
                </button>
              ) : (
                <>
                  <span className="angle">{dirty ? 'Belum disimpan' : 'Tersimpan'}</span>
                  <button onClick={() => void save()} disabled={!dirty || busy !== null} title="Ctrl+S">
                    Simpan <kbd>Ctrl+S</kbd>
                  </button>
                  <button className="primary" onClick={() => void lock()} disabled={busy !== null}>
                    Kunci blocker
                  </button>
                </>
              )}
            </div>
            {active.locked ? (
              <div className="card">
                <h3>{active.variant_label}</h3>
                <BlockerView blocker={active} />
              </div>
            ) : (
              <BlockerEditor
                blocker={active}
                onChange={(b) => {
                  setActive(b)
                  setDirty(true)
                }}
              />
            )}
          </section>
        )}
      </div>

      <aside className="panel side">
        <h2>Blocker terkunci</h2>
        {lockedList.length === 0 ? (
          <p className="empty">Belum ada. Blocker yang dikunci akan muncul di sini dan bisa dipakai untuk live (Tahap 2).</p>
        ) : (
          <ul>
            {lockedList.map((b) => (
              <li key={b.id}>
                <button onClick={() => openLocked(b)}>
                  {b.tema} · {b.variant_label}
                  <span className="meta">
                    v{b.versi} · {fmtTime(b.created_at)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </aside>
    </div>
  )
}
