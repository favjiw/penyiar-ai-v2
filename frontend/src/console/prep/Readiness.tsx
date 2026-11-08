/**
 * Cek kesiapan berbasis kuota (mockup KonsolCekKesiapan, PRD v2.7 §6.4): tombol di header + panel.
 * Angka adalah perkiraan dari server (kuota harian dihitung sendiri, laju dari sesi sebelumnya).
 */
import { useEffect, useRef, useState } from 'react'
import { api, type Readiness, type ReadinessService } from '../../api'
import { DURASI_PILIHAN, type Durasi } from '../../lib/materi'
import { Button, IconAlert, IconCheck, IconInfo } from '../../ui'

const REFRESH_MS = 60_000

export type ReadinessState = { data: Readiness | null; at: Date | null; error: string }

export function useReadiness(mode: 'A' | 'B', target: number): ReadinessState {
  const [data, setData] = useState<Readiness | null>(null)
  const [at, setAt] = useState<Date | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let alive = true
    const load = () =>
      api
        .readiness(mode, target)
        .then((r) => {
          if (!alive) return
          setData(r)
          setAt(new Date())
          setError('')
        })
        .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)))
    void load()
    const t = window.setInterval(() => void load(), REFRESH_MS)
    return () => {
      alive = false
      window.clearInterval(t)
    }
  }, [mode, target])
  return { data, at, error }
}

/** Ringkasan untuk pil header dan baris Siap live: "Tidak terbatas" hanya bila semua layanan tanpa batas. */
export function readinessSummary(data: Readiness, target: number): { text: string; short: boolean; unknown: boolean } {
  const safe = data.minutes_safe
  const unknown = (data.unknown ?? []).length > 0 // server lama tanpa medan `unknown`: anggap kosong
  if (safe == null) return { text: unknown ? 'Belum diketahui' : 'Tidak terbatas', short: false, unknown }
  const short = safe < target
  return { text: `±${Math.min(safe, 999)} dari ${target} mnt${unknown ? '*' : ''}`, short, unknown }
}

/** "Cukup ±N menit" / "Tanpa batas" / "Belum diketahui" untuk satu layanan. */
export function serviceVerdict(s: ReadinessService): string {
  if (s.unlimited) return 'Tanpa batas'
  if (s.minutes_left == null) return 'Belum diketahui'
  return `Cukup ±${s.minutes_left} menit`
}

const serviceLine = (s: ReadinessService): string => {
  if (s.kind === 'stt') return 'Didengar browser prompter, tanpa kuota'
  if (s.paid) return 'Tanpa kuota harian (berbayar per pemakaian)'
  if (s.unlimited) return s.kind === 'tts' ? 'Suara gratis, tanpa kuota' : 'Tanpa kuota harian'
  if (s.percent_left != null) return `Kuota ${s.kind === 'llm' ? 'hari ini' : 'suara'} tersisa ${s.percent_left}%`
  return s.kind === 'tts' ? 'Sisa kuota suara tidak bisa dibaca (lihat Detail teknis)' : 'Sisa kuota belum diketahui'
}

interface Props {
  readiness: ReadinessState
  durasi: Durasi
  onDurasi: (d: Durasi) => void
}

export function ReadinessButton({ readiness, durasi, onDurasi }: Props) {
  const { data, at, error } = readiness
  const [open, setOpen] = useState(false)
  const [choice, setChoice] = useState<'backup' | 'shorten'>('backup')
  const wrap = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === 'Escape' : !wrap.current?.contains(e.target as Node)) setOpen(false)
    }
    window.addEventListener('mousedown', close)
    window.addEventListener('keydown', close)
    return () => {
      window.removeEventListener('mousedown', close)
      window.removeEventListener('keydown', close)
    }
  }, [open])

  const safe = data?.minutes_safe ?? null
  const sum = data ? readinessSummary(data, durasi) : null
  const short = !!sum?.short
  const pill = !data ? (error ? 'Belum bisa dicek' : 'Mengecek…') : sum!.text
  // Pilihan durasi yang benar-benar muat; tidak ada → opsi "kurangi target" disembunyikan.
  const shorterOption = [...DURASI_PILIHAN].reverse().find((d) => safe != null && d <= safe && d < durasi)
  const hasBackup = !!data?.fallbacks.length

  return (
    <div className="rd" ref={wrap}>
      <Button onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-controls="rd-panel" icon={<IconInfo size={18} />}>
        Cek kesiapan
        <span className={`rd-pill${short ? ' is-warn' : data ? ' is-ok' : ''}`}>
          <span className="rd-pill__dot" aria-hidden="true" />
          {pill}
        </span>
      </Button>
      {open && (
        <section id="rd-panel" className="rd-panel" aria-label="Hasil cek kesiapan">
          <div className="rd-head">
            <h2>Kesiapan siaran</h2>
            {at && <span>Dicek {at.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' })}</span>}
          </div>
          {error && !data && <p className="rd-error">Cek kesiapan gagal: {error}</p>}
          {data && (
            <div className={`rd-summary${short ? ' is-warn' : ''}`}>
              <span className="rd-summary__label">Target {durasi} menit · kuota aman sekitar</span>
              <span className="rd-summary__big">{safe == null ? sum!.text : `±${safe} menit`}</span>
              {sum!.unknown && <span>Sisa kuota {(data.unknown ?? []).join(' dan ').toLowerCase()} belum bisa dibaca; angka ini bisa lebih kecil.</span>}
              {short ? (
                <>
                  <span>
                    {data.services.find((s) => s.minutes_left === safe)?.label ?? 'Kuota'} habis ±{durasi - (safe ?? 0)} menit sebelum target. Pilih yang mau dilakukan:
                  </span>
                  <div role="radiogroup" aria-label="Kalau kuota kurang" className="rd-choices">
                    {hasBackup && (
                      <label className={`rd-choice${choice === 'backup' ? ' is-on' : ''}`}>
                        <input type="radio" name="kurang" checked={choice === 'backup'} onChange={() => setChoice('backup')} />
                        <span>
                          <strong>Lanjut pakai cadangan</strong>
                          <span>
                            Tetap {durasi} menit; setelah kuota habis, cadangan otomatis dipakai
                            {data.services.find((s) => s.minutes_left === safe)?.kind === 'tts' ? ' (suara terdengar sedikit beda).' : '.'}
                          </span>
                        </span>
                      </label>
                    )}
                    {shorterOption && (
                    <label className={`rd-choice${choice === 'shorten' ? ' is-on' : ''}`}>
                      <input
                        type="radio"
                        name="kurang"
                        checked={choice === 'shorten'}
                        onChange={() => {
                          setChoice('shorten')
                          onDurasi(shorterOption)
                        }}
                      />
                      <span>
                        <strong>Kurangi target jadi {shorterOption} menit</strong>
                        <span>Jumlah topik ikut disesuaikan saat materi dibuat lagi.</span>
                      </span>
                    </label>
                    )}
                  </div>
                </>
              ) : (
                <span>{safe == null ? (sum!.unknown ? 'Sisa kuota belum bisa dibaca.' : 'Semua layanan tanpa batas kuota.') : 'Cukup untuk target siaran.'}</span>
              )}
            </div>
          )}
          {data && (
            <ul className="rd-list">
              {data.services.map((s) => {
                const low = !s.unlimited && (s.minutes_left == null || s.minutes_left < durasi)
                return (
                  <li key={s.kind} className={low ? 'is-warn' : ''}>
                    <span className="rd-list__icon" aria-hidden="true">
                      {low ? <IconAlert size={20} /> : <IconCheck size={20} />}
                    </span>
                    <span className="rd-list__text">
                      <strong>{s.label}</strong>
                      <span>{serviceLine(s)}</span>
                      {s.percent_left != null && (
                        <span className="rd-bar" role="img" aria-label={`Sisa kuota ${s.percent_left} persen`}>
                          <span style={{ width: `${s.percent_left}%` }} />
                        </span>
                      )}
                    </span>
                    <span className="rd-list__verdict">{serviceVerdict(s)}</span>
                  </li>
                )
              })}
              {hasBackup && (
                <li>
                  <span className="rd-list__icon" aria-hidden="true">
                    <IconCheck size={20} />
                  </span>
                  <span className="rd-list__text">
                    <strong>Cadangan otomatis</strong>
                    <span>Kalau kuota habis, siaran tetap jalan pakai cadangan. Suara cadangan terdengar sedikit berbeda.</span>
                  </span>
                </li>
              )}
            </ul>
          )}
          <p className="rd-note">
            Perkiraan dari {data?.rates_source === 'log' ? 'rata-rata siaran sebelumnya' : 'angka awal (belum ada siaran sebelumnya)'}. Kuota harian otak AI dihitung sejak
            fitur ini dipakai.
          </p>
        </section>
      )}
    </div>
  )
}
