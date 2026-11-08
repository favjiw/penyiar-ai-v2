/** Aturan dan tampilan materi yang dipakai konsol, editor, dan prompter (PRD v2.7, DESIGN.md §3). */
import type { Blocker, BlockerTopic } from '../types'

export const DURASI_PILIHAN = [30, 45, 60, 90] as const
export type Durasi = (typeof DURASI_PILIHAN)[number]
export const OPENING_CLOSING_MENIT = 6 // Opening ±3 + Closing ±3
export const MAX_TOPICS = 8
export const MIN_POINTS = 3
export const MAX_POINTS = 5
export const MIN_OPENING_POINTS = 2
export const MAX_OPENING_POINTS = 3

/** Cermin backend `topics_for_duration`: (durasi − 6) / 9, dibatasi 1..8. */
export const topicsForDuration = (d: number) => Math.max(1, Math.min(MAX_TOPICS, Math.round((d - OPENING_CLOSING_MENIT) / 9)))

/** Total rencana menit materi: Opening + Closing + jumlah menit topik. */
export const planMinutes = (b: Pick<Blocker, 'topics'>) => OPENING_CLOSING_MENIT + b.topics.reduce((acc, t) => acc + (Number(t.menit) || 0), 0)

/**
 * Gaya tulisan HITS di prompter: KAPITAL, koma → "/", akhir kalimat → "//".
 * Data tetap disimpan normal; ini hanya untuk tampilan.
 */
export function shout(text: string): string {
  const t = text.trim()
  if (!t) return ''
  const s = t
    .toUpperCase()
    .replace(/\s*,\s*/g, '/ ')
    .replace(/([.!?])\s+(?=\S)/g, (_, p: string) => (p === '?' ? '?// ' : '// '))
  return /\?$/.test(s) ? `${s}//` : `${s.replace(/[.!]$/, '')}//`
}

export function topicIssue(t: BlockerTopic): string {
  const filled = t.poin.filter((p) => p.text.trim()).length
  if (!t.judul.trim()) return 'Judul masih kosong'
  if (!t.pertanyaan_penonton.trim()) return 'Pertanyaan masih kosong'
  if (filled < MIN_POINTS) return `Kurang ${MIN_POINTS - filled} bahan obrolan`
  if (filled > MAX_POINTS) return `Kelebihan ${filled - MAX_POINTS} bahan obrolan`
  if (!t.transisi.trim()) return 'Kalimat pindah kosong'
  if (!t.sudut_pandang.trim()) return 'Sudut pandang kosong'
  return ''
}

export const openingIssue = (b: Blocker) => (b.opening.hook.trim() ? '' : 'Kalimat pembuka kosong')
export const closingIssue = (b: Blocker) => (b.closing.rangkuman.trim() && b.closing.ajakan.trim() ? '' : 'Masih ada yang kosong')

/** Semua masalah yang membuat materi belum bisa dipakai live (cermin `validate_for_lock` backend). */
export function materiIssues(b: Blocker): string[] {
  const out: string[] = []
  const o = openingIssue(b)
  if (o) out.push(`Opening: ${o.toLowerCase()}`)
  b.topics.forEach((t, i) => {
    const x = topicIssue(t)
    if (x) out.push(`Topik ${i + 1}: ${x.toLowerCase()}`)
  })
  const c = closingIssue(b)
  if (c) out.push(`Closing: ${c.toLowerCase()}`)
  return out
}

export const factCheckCount = (b: Blocker) => b.topics.reduce((n, t) => n + t.poin.filter((p) => p.perlu_cek && p.text.trim()).length, 0)

export const materiSummary = (b: Blocker) => `Opening · ${b.topics.length} topik · Closing · ±${planMinutes(b)} menit`
