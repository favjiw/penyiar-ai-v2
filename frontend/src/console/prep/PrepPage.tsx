/**
 * Konsol · Siapkan siaran (mockup Main, HANDOFF §1): satu halaman tiga langkah.
 * (1) tema + target pendengar → Buat materi, (2) pilih materi, (3) Siap live.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../../api'
import { topicsForDuration } from '../../lib/materi'
import { usePersisted } from '../../lib/usePersisted'
import type { LiveSession } from '../../live/useLiveSession'
import type { Blocker } from '../../types'
import { Button } from '../../ui'
import { MateriCard } from './MateriCard'
import { MateriEditor } from './MateriEditor'
import { SiapLive, useDurasi } from './SiapLive'
import './prep.css'

const MAX_TEMA = 60
const MAX_CATATAN = 500
const isStr = (v: unknown): v is string => typeof v === 'string'

export function PrepPage({ live }: { live: LiveSession }) {
  const [tema, setTema] = usePersisted<string>('hits.tema', '', isStr)
  const [catatan, setCatatan] = usePersisted<string>('hits.catatan', '', isStr)
  const [selectedId, setSelectedId] = usePersisted<string>('hits.materi', '', isStr)
  const [durasi, setDurasi] = useDurasi()
  const [all, setAll] = useState<Blocker[]>([])
  const [variants, setVariants] = useState<Blocker[]>([])
  const [editing, setEditing] = useState<Blocker | null>(null)
  const [showSaved, setShowSaved] = useState(false)
  const [busy, setBusy] = useState<null | 'generate' | `regen:${string}`>(null)
  const [elapsed, setElapsed] = useState(0)
  const [error, setError] = useState<{ message: string; issues: string[] } | null>(null)
  const [lastGen, setLastGen] = useState<{ n: number; topics: number; durasi: number } | null>(null)
  const temaRef = useRef<HTMLInputElement>(null)

  // Varian lebih dulu: berisi editan terbaru sebelum daftar tersimpan dimuat ulang.
  const selected = variants.find((b) => b.id === selectedId) ?? all.find((b) => b.id === selectedId) ?? null

  const refresh = useCallback(async () => {
    try {
      const list = await api.list()
      setAll(list)
      return list
    } catch {
      return null
    }
  }, [])

  // Pulihkan pilihan terakhir: kartu = varian dari permintaan generate yang sama.
  useEffect(() => {
    void refresh().then((list) => {
      if (!list) return
      const sel = list.find((b) => b.id === selectedId)
      if (sel) setVariants(sel.generation_id ? list.filter((b) => b.generation_id === sel.generation_id) : [sel])
    })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const generate = async (opts?: { tema: string; catatan: string }) => {
    const t = (opts?.tema ?? tema).trim()
    if (!t || busy) return
    setBusy('generate')
    setError(null)
    setElapsed(0)
    const started = Date.now()
    const tick = window.setInterval(() => setElapsed((Date.now() - started) / 1000), 200)
    try {
      const res = await api.generate({ tema: t, catatan: (opts?.catatan ?? catatan).trim(), durasi_menit: durasi, jumlah_varian: 3 })
      setVariants(res.variants)
      setSelectedId(res.variants[0]?.id ?? '')
      setLastGen({ n: res.variants.length, topics: res.variants[0]?.topics.length ?? topicsForDuration(durasi), durasi })
      await refresh()
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e), 0)
      setError({ message: err.message, issues: err.issues })
    } finally {
      window.clearInterval(tick)
      setBusy(null)
    }
  }

  const regenerate = async (v: Blocker) => {
    if (busy) return
    setBusy(`regen:${v.id}`)
    setError(null)
    try {
      const res = await api.regenerate(
        v.id,
        variants.filter((x) => x.id !== v.id).map((x) => x.variant_label),
      )
      setVariants((vs) => vs.map((x) => (x.id === v.id ? res.variant : x)))
      if (selectedId === v.id) setSelectedId(res.variant.id)
      await refresh()
    } catch (e) {
      setError({ message: e instanceof ApiError ? e.message : String(e), issues: [] })
    } finally {
      setBusy(null)
    }
  }

  const afterEdit = (latest: Blocker, use: boolean) => {
    const oldId = editing?.id // bisa beda dari latest.id bila editor membuat versi baru
    setVariants((vs) => (vs.some((x) => x.id === oldId) ? vs.map((x) => (x.id === oldId ? latest : x)) : [latest]))
    if (use || selectedId === oldId) setSelectedId(latest.id)
    setEditing(null)
    void refresh()
  }

  const useSaved = (b: Blocker) => {
    setSelectedId(b.id)
    setVariants(b.generation_id ? all.filter((x) => x.generation_id === b.generation_id) : [b])
    setShowSaved(false)
  }

  if (editing) {
    return <MateriEditor initial={editing} targetMinutes={editing.durasi_menit ?? durasi} onClose={(b) => afterEdit(b, false)} onUse={(b) => afterEdit(b, true)} />
  }

  const temaVariants = variants.length ? variants[0].tema : ''

  return (
    <main className="prep">
      <div className="prep-main">
        <section className="prep-step" aria-labelledby="step1">
          <div className="prep-step__head">
            <span className="prep-step__n" aria-hidden="true">
              1
            </span>
            <h2 id="step1">Mau ngobrolin apa hari ini?</h2>
          </div>
          <form
            className="prep-form"
            onSubmit={(e) => {
              e.preventDefault()
              void generate()
            }}
          >
            <label className="prep-input">
              <span>Tema</span>
              <input ref={temaRef} value={tema} maxLength={MAX_TEMA} onChange={(e) => setTema(e.target.value)} placeholder="Misal: Zodiak" required />
            </label>
            <label className="prep-input prep-input--wide">
              <span>Target pendengar dan catatan</span>
              <input value={catatan} maxLength={MAX_CATATAN} onChange={(e) => setCatatan(e.target.value)} placeholder="Misal: mahasiswa, anak muda Bandung · jangan bahas politik" />
            </label>
            <Button type="submit" variant="primary" size="lg" disabled={!tema.trim() || !!busy}>
              {busy === 'generate' ? `Membuat… ${elapsed.toFixed(0)} dtk` : 'Buat materi'}
            </Button>
          </form>
          <div className="prep-summary">
            {busy === 'generate' ? (
              <span>
                Menyusun {topicsForDuration(durasi)} topik untuk siaran {durasi} menit. Biasanya 10–20 detik.
              </span>
            ) : lastGen ? (
              <span>
                {lastGen.topics} topik untuk siaran {lastGen.durasi} menit · {lastGen.n} pilihan
              </span>
            ) : (
              <span>
                Akan dibuat {topicsForDuration(durasi)} topik untuk siaran {durasi} menit · 3 pilihan
              </span>
            )}
            <Button variant="link" onClick={() => temaRef.current?.focus()}>
              Ubah
            </Button>
          </div>
          {error && (
            <div className="prep-error" role="alert">
              {error.message}
              {error.issues.length > 0 && (
                <ul>
                  {error.issues.map((x) => (
                    <li key={x}>{x}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </section>

        <section className="prep-step" aria-labelledby="step2">
          <div className="prep-step__head">
            <span className="prep-step__n" aria-hidden="true">
              2
            </span>
            <h2 id="step2">Pilih materi</h2>
            {temaVariants && <span className="prep-step__meta">{variants.length} pilihan dari tema {temaVariants}</span>}
            <span className="prep-step__spacer" />
            <Button variant="link" onClick={() => setShowSaved((s) => !s)} aria-expanded={showSaved}>
              Materi tersimpan ({all.length})
            </Button>
          </div>

          {showSaved && (
            <div className="prep-saved">
              {all.length === 0 ? (
                <p className="prep-empty">Belum ada materi tersimpan.</p>
              ) : (
                <ul>
                  {all.map((b) => (
                    <li key={b.id}>
                      <button type="button" className={`prep-saved__item${b.id === selectedId ? ' is-on' : ''}`} onClick={() => useSaved(b)}>
                        <span className="prep-saved__title">
                          {b.tema} · {b.variant_label}
                        </span>
                        <span className="prep-saved__meta">
                          {b.topics.length} topik · v{b.versi} · {b.locked ? 'pernah dipakai live' : 'draf'} · {new Date(b.created_at).toLocaleString('id-ID', { dateStyle: 'medium', timeStyle: 'short' })}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {variants.length === 0 ? (
            <p className="prep-empty">Ketik tema lalu tekan “Buat materi”. Tiga pilihan materi akan muncul di sini.</p>
          ) : (
            <div className="prep-cards">
              {variants.map((v) => (
                <MateriCard
                  key={v.id}
                  materi={v}
                  selected={v.id === selectedId}
                  busy={busy === `regen:${v.id}`}
                  onUse={() => setSelectedId(v.id)}
                  onEdit={() => setEditing(v)}
                  onRegenerate={() => void regenerate(v)}
                />
              ))}
            </div>
          )}
        </section>
      </div>

      <SiapLive
        live={live}
        materi={selected}
        durasi={durasi}
        onDurasi={setDurasi}
        onEdit={() => selected && setEditing(selected)}
        onRegenerateForDuration={() => selected && void generate({ tema: selected.tema, catatan: selected.catatan })}
        generating={busy === 'generate'}
      />
    </main>
  )
}
