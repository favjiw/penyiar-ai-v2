/**
 * Editor materi tiga kolom (mockup EditorMateri, HANDOFF §1; dimajukan dari tahap 8):
 * susunan materi (status + menit) · editor bagian aktif · pratinjau prompter.
 * Simpan otomatis, tanpa tombol kunci: materi dikunci saat live dimulai.
 *
 * Draf lokal adalah sumber kebenaran selama mengetik; respons simpan dari server
 * (yang menomori ulang id t1, t1p1, …) tidak disalin balik supaya kursor tidak lompat.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../../api'
import {
  closingIssue,
  MAX_OPENING_POINTS,
  MAX_POINTS,
  MAX_TOPICS,
  MIN_OPENING_POINTS,
  MIN_POINTS,
  openingIssue,
  OPENING_CLOSING_MENIT,
  planMinutes,
  shout,
  topicIssue,
} from '../../lib/materi'
import type { Blocker, BlockerTopic } from '../../types'
import { Button, IconCheck, IconClose } from '../../ui'

const AUTOSAVE_MS = 700
const SECTION_MENIT = OPENING_CLOSING_MENIT / 2

type SaveState = { kind: 'saved' } | { kind: 'dirty' } | { kind: 'saving' } | { kind: 'error'; message: string }

interface Props {
  initial: Blocker
  targetMinutes: number
  /** Kembali ke pilihan materi; menerima versi terakhir (id bisa berubah bila dibuat versi baru). */
  onClose: (latest: Blocker) => void
  /** "Pakai materi ini": pilih lalu kembali. */
  onUse: (latest: Blocker) => void
}

const emptyTopic = (): BlockerTopic => ({
  id: '',
  judul: '',
  menit: 9,
  sudut_pandang: '',
  poin: Array.from({ length: MIN_POINTS }, () => ({ id: '', text: '', perlu_cek: false })),
  pertanyaan_penonton: '',
  transisi: '',
})

export function MateriEditor({ initial, targetMinutes, onClose, onUse }: Props) {
  const [draft, setDraft] = useState<Blocker>(() => structuredClone(initial))
  const [active, setActive] = useState(1) // 0 = Opening, 1..n = topik, n+1 = Closing
  const [save, setSave] = useState<SaveState>({ kind: 'saved' })
  const [removed, setRemoved] = useState<{ topic: BlockerTopic; index: number } | null>(null)
  const [busy, setBusy] = useState(false)
  const rev = useRef(0)
  const savedRev = useRef(0)
  const timer = useRef<number>()
  const draftRef = useRef(draft)
  draftRef.current = draft
  const inFlight = useRef<Promise<boolean> | null>(null)

  const readOnly = draft.locked
  const nT = draft.topics.length
  const total = nT + 2
  const a = Math.min(active, total - 1)
  const isOpening = a === 0
  const isClosing = a === total - 1
  const ti = a - 1

  /**
   * Simpan draf terbaru. Simpanan diantrekan satu per satu (tidak ada dua PUT bersamaan).
   * Mengembalikan true hanya bila draf yang terakhir diubah sudah tersimpan di server.
   */
  const doSave = useCallback(async (): Promise<boolean> => {
    window.clearTimeout(timer.current)
    const run = async (): Promise<boolean> => {
      if (savedRev.current === rev.current) return true
      const sentRev = rev.current
      setSave({ kind: 'saving' })
      try {
        await api.save(draftRef.current)
        savedRev.current = Math.max(savedRev.current, sentRev)
        setSave(rev.current === sentRev ? { kind: 'saved' } : { kind: 'dirty' })
        return savedRev.current === rev.current
      } catch (e) {
        setSave({ kind: 'error', message: e instanceof ApiError ? e.message : String(e) })
        return false
      }
    }
    const next = (inFlight.current ?? Promise.resolve(true)).then(run, run)
    inFlight.current = next
    return next
  }, [])

  /** Ubah draf (salinan dalam), tandai belum tersimpan, jadwalkan simpan otomatis. */
  const update = (fn: (d: Blocker) => void) => {
    if (readOnly) return
    setDraft((cur) => {
      const next = structuredClone(cur)
      fn(next)
      return next
    })
    rev.current++
    setSave({ kind: 'dirty' })
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => void doSave(), AUTOSAVE_MS)
  }

  // Editor dilepas tanpa tombol (mis. siaran dimulai dari tab lain): kirim editan yang tertunda.
  // Bila materi sudah terkunci, server menolak (BlockerLocked) dan tidak ada yang berubah.
  useEffect(
    () => () => {
      window.clearTimeout(timer.current)
      if (savedRev.current !== rev.current) void api.save(draftRef.current).catch(() => undefined)
    },
    [],
  )
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => {
      if (savedRev.current !== rev.current) e.preventDefault()
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [])

  const leave = async (use: boolean) => {
    setBusy(true)
    const ok = await doSave()
    setBusy(false)
    // Gagal simpan: tetap di editor dengan pesan galat, supaya yang dipakai live = yang terlihat.
    if (ok) (use ? onUse : onClose)(draftRef.current)
  }

  const makeVersion = async () => {
    setBusy(true)
    try {
      const v = await api.newVersion(draft.id)
      setDraft(v)
      rev.current = savedRev.current = 0
      setSave({ kind: 'saved' })
    } catch (e) {
      setSave({ kind: 'error', message: e instanceof ApiError ? e.message : String(e) })
    } finally {
      setBusy(false)
    }
  }

  // ── Turunan untuk tampilan ───────────────────────────────────────────────
  const sections = [
    { label: 'Opening', badge: 'O', issue: openingIssue(draft), min: SECTION_MENIT },
    ...draft.topics.map((t, i) => ({ label: t.judul || 'Topik tanpa judul', badge: String(i + 1), issue: topicIssue(t), min: t.menit })),
    { label: 'Closing', badge: 'C', issue: closingIssue(draft), min: SECTION_MENIT },
  ]
  const issueCount = sections.filter((x) => x.issue).length
  const plan = planMinutes(draft)
  const planOk = Math.abs(plan - targetMinutes) <= 3

  const topic = !isOpening && !isClosing ? draft.topics[ti] : null
  const points = topic ? topic.poin : isOpening ? draft.opening.poin.map((text) => ({ id: '', text, perlu_cek: false })) : []
  const [minP, maxP] = topic ? [MIN_POINTS, MAX_POINTS] : [MIN_OPENING_POINTS, MAX_OPENING_POINTS]
  const filled = points.filter((p) => p.text.trim()).length
  const setPoint = (i: number, text: string) =>
    update((d) => {
      if (topic) d.topics[ti].poin[i].text = text
      else d.opening.poin[i] = text
    })
  const removePoint = (i: number) =>
    update((d) => {
      if (topic) d.topics[ti].poin.splice(i, 1)
      else d.opening.poin.splice(i, 1)
    })
  const addPoint = () =>
    update((d) => {
      if (topic) d.topics[ti].poin.push({ id: '', text: '', perlu_cek: false })
      else d.opening.poin.push('')
    })
  const setTopic = <K extends keyof BlockerTopic>(k: K, v: BlockerTopic[K]) =>
    update((d) => {
      d.topics[ti][k] = v
    })
  const moveTopic = (dir: -1 | 1) => {
    const to = ti + dir
    if (to < 0 || to >= nT) return
    update((d) => {
      const [t] = d.topics.splice(ti, 1)
      d.topics.splice(to, 0, t)
    })
    setActive(to + 1)
  }
  const removeTopic = () => {
    if (nT <= 1) return
    setRemoved({ topic: structuredClone(draft.topics[ti]), index: ti })
    update((d) => {
      d.topics.splice(ti, 1)
    })
    setActive(Math.max(1, Math.min(ti + 1, nT - 1)))
  }
  const undoRemove = () => {
    if (!removed || nT >= MAX_TOPICS) return
    const r = removed
    update((d) => {
      d.topics.splice(r.index, 0, r.topic)
    })
    setActive(r.index + 1)
    setRemoved(null)
  }
  const addTopic = () => {
    if (nT >= MAX_TOPICS) return
    update((d) => {
      d.topics.push(emptyTopic())
    })
    setActive(nT + 1)
  }

  const preview = topic
    ? { chip: `Topik ${ti + 1} dari ${nT}`, title: topic.judul || 'Judul topik', boxLabel: 'TANYA PENONTON', box: shout(topic.pertanyaan_penonton) || 'Pertanyaan belum diisi', items: topic.poin.map((p) => p.text).filter((x) => x.trim()) }
    : isOpening
      ? { chip: 'Opening', title: 'Opening', boxLabel: 'KALIMAT PEMBUKA', box: shout(draft.opening.hook), items: draft.opening.poin.filter((x) => x.trim()) }
      : { chip: 'Closing', title: 'Closing', boxLabel: 'AJAKAN', box: shout(draft.closing.ajakan), items: draft.closing.rangkuman.trim() ? [draft.closing.rangkuman] : [] }

  const saveLabel =
    readOnly
      ? 'Terkunci'
      : save.kind === 'saved'
        ? 'Tersimpan otomatis'
        : save.kind === 'saving'
          ? 'Menyimpan…'
          : save.kind === 'dirty'
            ? 'Belum tersimpan'
            : 'Gagal menyimpan'

  return (
    <div className="ed">
      <header className="ed-top">
        <div className="ed-top__inner">
          <Button variant="link" onClick={() => void leave(false)} disabled={busy}>
            ← Pilihan materi
          </Button>
          <span className="ed-top__sep" aria-hidden="true" />
          <label className="ed-title">
            <span className="ed-title__label">Judul materi · tema {draft.tema}</span>
            <input value={draft.variant_label} onChange={(e) => update((d) => void (d.variant_label = e.target.value))} readOnly={readOnly} aria-label="Judul materi" />
          </label>
          <span className={`ed-save ed-save--${readOnly ? 'locked' : save.kind}`} role="status" title={save.kind === 'error' ? save.message : undefined}>
            {save.kind === 'saved' && !readOnly && <IconCheck size={16} />}
            {saveLabel}
          </span>
          <span className={`ed-plan${planOk ? ' is-ok' : ''}`}>
            Rencana {plan} dari {targetMinutes} menit
          </span>
          {issueCount > 0 && <span className="ed-issues">{issueCount} bagian belum lengkap</span>}
          <span className="ed-top__spacer" />
          {readOnly ? (
            <Button variant="primary" onClick={() => void makeVersion()} disabled={busy}>
              Buat versi baru untuk mengubah
            </Button>
          ) : (
            <Button variant="primary" onClick={() => void leave(true)} disabled={busy}>
              Pakai materi ini
            </Button>
          )}
        </div>
        {save.kind === 'error' && (
          <div className="ed-banner" role="alert">
            Belum tersimpan: {save.message}{' '}
            <Button variant="link" onClick={() => void doSave()}>
              Coba lagi
            </Button>
          </div>
        )}
        {readOnly && (
          <div className="ed-banner ed-banner--info" role="status">
            Materi ini sudah pernah dipakai live dan terkunci. Buat versi baru kalau mau mengubah isinya.
          </div>
        )}
      </header>

      <main className="ed-main">
        <nav className="ed-nav" aria-label="Susunan materi">
          <span className="ed-col-label">Susunan materi</span>
          {sections.map((x, i) => (
            <button key={i} type="button" className={`ed-nav__item${i === a ? ' is-on' : ''}`} aria-current={i === a ? 'step' : undefined} onClick={() => setActive(i)}>
              <span className="ed-nav__badge">{x.badge}</span>
              <span className="ed-nav__text">
                <span className="ed-nav__label">{x.label}</span>
                <span className={`ed-nav__status${x.issue ? ' is-warn' : ''}`}>
                  ±{x.min} mnt · {x.issue || 'Lengkap'}
                </span>
              </span>
            </button>
          ))}
          {!readOnly &&
            (nT < MAX_TOPICS ? (
              <Button variant="link" onClick={addTopic}>
                + Tambah topik
              </Button>
            ) : (
              <span className="ed-hint">Maksimal {MAX_TOPICS} topik. Hapus satu topik dulu kalau mau menambah.</span>
            ))}
          {removed && (
            <div className="ed-undo" role="status">
              Topik “{removed.topic.judul || 'tanpa judul'}” dihapus.
              <Button variant="link" onClick={undoRemove} disabled={nT >= MAX_TOPICS}>
                Urungkan
              </Button>
              <Button variant="link" aria-label="Tutup" onClick={() => setRemoved(null)} icon={<IconClose size={16} />} />
            </div>
          )}
        </nav>

        <section className="ed-form" aria-label="Ubah bagian">
          <fieldset disabled={readOnly} className="ed-fieldset">
            <div className="ed-form__head">
              <h2>{topic ? `Topik ${ti + 1}` : isOpening ? 'Opening' : 'Closing'}</h2>
              {topic && (
                <div className="ed-form__tools">
                  <Button onClick={() => moveTopic(-1)} disabled={ti === 0} aria-label="Geser topik ke atas">
                    ↑
                  </Button>
                  <Button onClick={() => moveTopic(1)} disabled={ti === nT - 1} aria-label="Geser topik ke bawah">
                    ↓
                  </Button>
                  <Button variant="danger" onClick={removeTopic} disabled={nT <= 1}>
                    Hapus topik
                  </Button>
                </div>
              )}
            </div>

            {topic && (
              <>
                <label className="ed-field">
                  <span className="ed-field__label">Judul topik</span>
                  <input value={topic.judul} onChange={(e) => setTopic('judul', e.target.value)} placeholder="Misal: First date gagal gara-gara beda elemen" />
                </label>
                <div className="ed-field ed-field--main">
                  <label className="ed-field__label" htmlFor="ed-q">
                    Pertanyaan ke penonton
                  </label>
                  <textarea id="ed-q" rows={2} value={topic.pertanyaan_penonton} onChange={(e) => setTopic('pertanyaan_penonton', e.target.value)} placeholder="Satu pertanyaan pemantik, misal: Elemen zodiak kalian apa?" />
                  <span className="ed-hint">Paling menonjol di prompter. Otomatis ditulis kapital dengan tanda jeda / dan //.</span>
                </div>
              </>
            )}
            {isOpening && (
              <div className="ed-field ed-field--main">
                <label className="ed-field__label" htmlFor="ed-hook">
                  Kalimat pembuka
                </label>
                <textarea id="ed-hook" rows={2} value={draft.opening.hook} onChange={(e) => update((d) => void (d.opening.hook = e.target.value))} />
              </div>
            )}

            {(topic || isOpening) && (
              <div className="ed-points">
                <div className="ed-points__head">
                  <span className="ed-field__label">{topic ? 'Bahan obrolan' : 'Yang dilakukan saat pembukaan'}</span>
                  <span className={`ed-count${filled < minP ? ' is-warn' : ''}`}>
                    {filled < minP ? `Tambah ${minP - filled} lagi, minimal ${minP}` : `${points.length} dari maks. ${maxP}`}
                  </span>
                </div>
                {points.map((p, i) => (
                  <div className="ed-point" key={`${a}-${i}`}>
                    <span className="ed-point__n" aria-hidden="true">
                      {i + 1}
                    </span>
                    <input value={p.text} onChange={(e) => setPoint(i, e.target.value)} aria-label={`Bahan ${i + 1}`} placeholder="Tulis satu bahan obrolan" />
                    {topic && (
                      <button
                        type="button"
                        className={`ed-cek${p.perlu_cek ? ' is-on' : ''}`}
                        aria-pressed={p.perlu_cek}
                        title="Tandai kalau perlu dicek faktanya sebelum live"
                        onClick={() =>
                          update((d) => {
                            d.topics[ti].poin[i].perlu_cek = !d.topics[ti].poin[i].perlu_cek
                          })
                        }
                      >
                        Cek fakta
                      </button>
                    )}
                    <Button variant="link" onClick={() => removePoint(i)} aria-label={`Hapus bahan ${i + 1}`} icon={<IconClose size={18} />} />
                  </div>
                ))}
                {points.length < maxP && (
                  <Button variant="link" onClick={addPoint}>
                    + Tambah {topic ? 'bahan' : ''}
                  </Button>
                )}
              </div>
            )}

            {topic && (
              <div className="ed-grid">
                <label className="ed-field">
                  <span className="ed-field__label">
                    Perkiraan durasi <span className="ed-hint">Panduan waktu di prompter, bukan paksaan</span>
                  </span>
                  <span className="ed-minutes">
                    <input type="number" min={3} max={20} value={topic.menit} onChange={(e) => setTopic('menit', Math.max(1, Math.min(30, Number(e.target.value) || 1)))} />
                    menit
                  </span>
                </label>
                <label className="ed-field">
                  <span className="ed-field__label">
                    Sudut pandang <span className="ed-hint">Arah obrolan untuk AI, tidak dibacakan</span>
                  </span>
                  <input value={topic.sudut_pandang} onChange={(e) => setTopic('sudut_pandang', e.target.value)} />
                </label>
                <label className="ed-field ed-field--wide">
                  <span className="ed-field__label">
                    Kalimat pindah ke topik berikutnya <span className="ed-hint">Ditonjolkan di prompter saat waktu hampir habis</span>
                  </span>
                  <input value={topic.transisi} onChange={(e) => setTopic('transisi', e.target.value)} />
                </label>
              </div>
            )}

            {isClosing && (
              <>
                <label className="ed-field">
                  <span className="ed-field__label">Rangkuman obrolan</span>
                  <textarea rows={2} value={draft.closing.rangkuman} onChange={(e) => update((d) => void (d.closing.rangkuman = e.target.value))} />
                </label>
                <div className="ed-field ed-field--main">
                  <label className="ed-field__label" htmlFor="ed-ajak">
                    Ajakan ke penonton
                  </label>
                  <textarea id="ed-ajak" rows={2} value={draft.closing.ajakan} onChange={(e) => update((d) => void (d.closing.ajakan = e.target.value))} />
                  <span className="ed-hint">Misalnya ajak follow, ikut konten minggu depan, atau sebut acara berikutnya.</span>
                </div>
              </>
            )}
          </fieldset>
        </section>

        <aside className="ed-preview" aria-label="Pratinjau prompter">
          <span className="ed-col-label">Tampilan di prompter penyiar</span>
          <div className="ed-pv">
            <span className="ed-pv__chip">{preview.chip}</span>
            <span className="ed-pv__title">{preview.title}</span>
            <div className="ed-pv__box">
              <span className="ed-pv__boxlabel">{preview.boxLabel}</span>
              <span className="ed-pv__boxtext">{preview.box}</span>
            </div>
            <ul className="ed-pv__items">
              {preview.items.map((t, i) => (
                <li key={i}>{t}</li>
              ))}
            </ul>
          </div>
          <p className="ed-hint">Perubahan langsung terlihat di sini. Materi baru dikunci saat siaran dimulai, jadi aman diubah kapan saja sebelum live.</p>
        </aside>
      </main>
    </div>
  )
}
