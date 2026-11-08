/**
 * Panduan pengguna baru (mockup Tutorial, DESIGN.md §4): sapaan → 5 langkah dengan sorotan elemen.
 * Posisi sorotan dihitung dari elemen sungguhan (getBoundingClientRect, atribut `data-tour`), bukan angka tetap.
 * Muncul otomatis saat konsol pertama dibuka (flag localStorage), bisa dibuka lagi lewat tombol "Panduan".
 * Keyboard: ← kembali, → lanjut, Esc lewati.
 */
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Button } from '../../ui'

export const TOUR_SEEN_KEY = 'hits.tourSeen'

const STEPS = [
  {
    target: 'tema',
    title: 'Mulai dari tema',
    body: 'Ketik tema obrolan dan target pendengarnya, lalu klik Buat materi. AI menyiapkan beberapa pilihan materi obrolan dalam beberapa detik.',
  },
  {
    target: 'materi',
    title: 'Pilih satu materi',
    body: 'Bandingkan pilihannya, lalu klik Pakai ini. Mau mengubah bahan obrolan atau urutan? Klik Lihat & ubah. Materi yang dipakai langsung muncul di panel kanan.',
  },
  {
    target: 'siap',
    title: 'Atur format siaran',
    body: 'Pilih Penyiar + AI atau AI + AI, lalu durasi siaran (biasanya 60 menit). Isi nama penyiar sekali saja, lalu pilih teman ngobrol AI. Klik tombol putar untuk mendengar suaranya dulu.',
  },
  {
    target: 'cek',
    title: 'Cek kesiapan',
    body: 'Klik untuk memastikan semuanya siap dan melihat apakah kuota cukup untuk durasi yang dipilih.',
  },
  {
    target: 'mulai',
    title: 'Mulai live',
    body: 'Kalau semua tanda sudah hijau, klik Mulai live. Prompter penyiar dan layar untuk OBS ikut terbuka otomatis.',
  },
] as const

const CARD_W = 440
const GAP = 16
const PAD = 8

export function hasSeenTour(): boolean {
  try {
    return window.localStorage.getItem(TOUR_SEEN_KEY) === '1'
  } catch {
    return true // penyimpanan tidak tersedia: jangan memaksa panduan muncul terus
  }
}

function markSeen() {
  try {
    window.localStorage.setItem(TOUR_SEEN_KEY, '1')
  } catch {
    /* abaikan */
  }
}

type Box = { x: number; y: number; w: number; h: number }

/** Kotak elemen target + posisi kartu (di bawah, di atas, atau di kiri bila elemen tinggi). */
function layout(el: Element | null, cardH: number): { spot: Box; card: { left: number; top: number }; arrow: 'up' | 'down' | 'right' | 'left' | 'none' } | null {
  if (!el) return null
  const r = el.getBoundingClientRect()
  const vw = window.innerWidth
  const vh = window.innerHeight
  const spot = { x: r.left - PAD, y: r.top - PAD, w: r.width + PAD * 2, h: r.height + PAD * 2 }
  const clampX = (x: number) => Math.max(16, Math.min(vw - CARD_W - 16, x))
  const clampY = (y: number) => Math.max(16, Math.min(vh - cardH - 16, y))
  // Urutan: di bawah, di atas, di kanan, di kiri elemen; bila tidak ada ruang, pojok kanan bawah layar.
  if (spot.y + spot.h + GAP + cardH < vh) return { spot, card: { left: clampX(spot.x), top: spot.y + spot.h + GAP }, arrow: 'up' }
  if (spot.y - GAP - cardH > 0) return { spot, card: { left: clampX(spot.x), top: spot.y - GAP - cardH }, arrow: 'down' }
  if (spot.x + spot.w + GAP + CARD_W < vw - 16) return { spot, card: { left: spot.x + spot.w + GAP, top: clampY(spot.y + 24) }, arrow: 'left' }
  if (spot.x - GAP - CARD_W > 16) return { spot, card: { left: spot.x - GAP - CARD_W, top: clampY(spot.y + 24) }, arrow: 'right' }
  return { spot, card: { left: vw - CARD_W - 16, top: vh - cardH - 16 }, arrow: 'none' }
}

export function GuidedTour({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [i, setI] = useState(0) // 0 = sapaan, 1..5 = langkah
  const [pos, setPos] = useState<ReturnType<typeof layout>>(null)
  const cardRef = useRef<HTMLElement>(null)

  const opener = useRef<Element | null>(null)

  // Simpan elemen yang membuka panduan, kembalikan fokus ke sana saat ditutup.
  useEffect(() => {
    if (!open) return
    opener.current = document.activeElement
    return () => {
      const el = opener.current
      if (el instanceof HTMLElement) el.focus()
    }
  }, [open])

  const close = useCallback(() => {
    markSeen()
    setI(0) // dibuka lagi mulai dari sapaan, tanpa sempat merender langkah lama
    onClose()
  }, [onClose])

  const step = i > 0 ? STEPS[i - 1] : null

  // Hitung ulang posisi saat langkah berganti, jendela berubah ukuran, atau halaman digulir.
  useLayoutEffect(() => {
    if (!open || !step) return
    const el = document.querySelector(`[data-tour="${step.target}"]`)
    el?.scrollIntoView({ block: 'nearest', behavior: 'auto' })
    // Tinggi kartu diukur dari elemen sebenarnya (teks tiap langkah beda panjang); 260 sebelum kartu tampil.
    const update = () => setPos(layout(document.querySelector(`[data-tour="${step.target}"]`), cardRef.current?.offsetHeight || 260))
    update()
    const raf = requestAnimationFrame(update) // ulangi setelah kartu langkah ini dirender dengan teks barunya
    window.addEventListener('resize', update)
    window.addEventListener('scroll', update, true)
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', update)
      window.removeEventListener('scroll', update, true)
    }
  }, [open, step])

  useEffect(() => {
    if (open) cardRef.current?.focus()
  }, [open, i])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') return close()
      if (e.key === 'Tab') {
        // Dialog modal: fokus berputar di dalam kartu, tidak lari ke halaman di belakang.
        const items = cardRef.current?.querySelectorAll<HTMLElement>('button, [href], input, [tabindex]:not([tabindex="-1"])')
        if (!items || items.length === 0) return
        const first = items[0]
        const last = items[items.length - 1]
        if (e.shiftKey && (document.activeElement === first || document.activeElement === cardRef.current)) {
          e.preventDefault()
          last.focus()
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault()
          first.focus()
        }
        return
      }
      if (e.repeat) return
      if (e.key === 'ArrowRight') {
        if (i >= STEPS.length) close()
        else setI(i + 1)
      } else if (e.key === 'ArrowLeft') setI(Math.max(i === 0 ? 0 : 1, i - 1))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, close, i])

  if (!open) return null

  if (!step) {
    return (
      <div className="tour-backdrop">
        <section className="tour-welcome" role="dialog" aria-modal="true" aria-labelledby="tw-title" tabIndex={-1} ref={cardRef}>
          <img src="/logo-hits.png" alt="HITS Unikom Radio 103.9 FM" className="tour-welcome__logo" />
          <h2 id="tw-title">Halo! Siap siaran bareng AI?</h2>
          <p>
            Panduan singkat ini menunjukkan 5 langkah dari tema sampai mulai live. Kamu bisa membukanya lagi kapan saja lewat tombol <strong>Panduan</strong> di kanan atas.
          </p>
          <div className="tour-actions">
            <Button variant="primary" size="lg" onClick={() => setI(1)}>
              Mulai panduan
            </Button>
            <Button size="lg" onClick={close}>
              Nanti saja
            </Button>
          </div>
        </section>
      </div>
    )
  }

  return (
    <div className="tour-layer">
      {pos ? (
        <div className="tour-spot" style={{ left: pos.spot.x, top: pos.spot.y, width: pos.spot.w, height: pos.spot.h }} aria-hidden="true" />
      ) : (
        <div className="tour-backdrop tour-backdrop--plain" aria-hidden="true" />
      )}
      <section
        className="tour-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="ts-title"
        tabIndex={-1}
        ref={cardRef}
        style={pos ? { left: pos.card.left, top: pos.card.top } : { left: 'max(16px, calc(50% - 220px))', top: '30%' }}
      >
        {pos && pos.arrow !== 'none' && <span className={`tour-arrow tour-arrow--${pos.arrow}`} aria-hidden="true" />}
        <div className="tour-card__head">
          <span>
            Langkah {i} dari {STEPS.length}
          </span>
          <Button variant="link" onClick={close}>
            Lewati panduan
          </Button>
        </div>
        <h2 id="ts-title">{step.title}</h2>
        <p>{step.body}</p>
        {!pos && <p className="tour-card__missing">Bagian ini belum tampil di layar sekarang.</p>}
        <div className="tour-card__foot">
          <div className="tour-dots" aria-hidden="true">
            {STEPS.map((_, k) => (
              <span key={k} className={k + 1 === i ? 'is-on' : k + 1 < i ? 'is-done' : ''} />
            ))}
          </div>
          {i > 1 && <Button onClick={() => setI(i - 1)}>Kembali</Button>}
          <Button variant="primary" onClick={() => (i === STEPS.length ? close() : setI(i + 1))}>
            {i === STEPS.length ? 'Selesai' : 'Lanjut'}
          </Button>
        </div>
      </section>
    </div>
  )
}
