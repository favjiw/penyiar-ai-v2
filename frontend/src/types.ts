// Cermin backend/app/schemas.py (PRD §9.1).

export interface BlockerPoint {
  id: string
  text: string
  perlu_cek: boolean
}

export interface BlockerTopic {
  id: string
  judul: string
  /** Perkiraan lama obrolan topik (menit), panduan waktu di prompter (PRD v2.7). */
  menit: number
  sudut_pandang: string
  poin: BlockerPoint[]
  pertanyaan_penonton: string
  transisi: string
}

export interface Blocker {
  id: string
  tema: string
  catatan: string
  versi: number
  locked: boolean
  created_at: string
  variant_label: string
  /** Target durasi siaran saat materi dibuat; null untuk materi lama. */
  durasi_menit?: number | null
  opening: { hook: string; poin: string[] }
  topics: BlockerTopic[]
  closing: { rangkuman: string; ajakan: string }
  parent_id: string | null
  generation_id: string | null
}

export interface GenerateRequest {
  tema: string
  catatan: string
  /** Bila diisi, jumlah topik dihitung backend dari durasi (30/45/60/90). */
  durasi_menit?: number
  jumlah_topik?: number
  jumlah_varian: number
}

export interface GenerateResponse {
  variants: Blocker[]
  latency_ms: number
  attempts: number
  model: string
}

export interface RegenerateResponse {
  variant: Blocker
  latency_ms: number
  attempts: number
  model: string
}
