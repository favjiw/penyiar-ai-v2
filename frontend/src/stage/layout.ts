/**
 * Zona aman TikTok di kanvas 9:16 (FR-10), dari stageLayout.ts repo lama.
 * Semua angka berupa pecahan kanvas 1080x1920.
 */

export const CANVAS_WIDTH = 1080
export const CANVAS_HEIGHT = 1920

export interface Rect {
  x0: number
  y0: number
  x1: number
  y1: number
}

/** Area yang tertutup UI TikTok: wajah dan teks penting tidak boleh di sini. */
export const COVERED_ZONES: Array<{ id: string; label: string; rect: Rect }> = [
  { id: 'header', label: 'Header TikTok (akun, Follow, ranking)', rect: { x0: 0, y0: 0, x1: 1, y1: 0.1 } },
  { id: 'comments', label: 'Daftar komentar', rect: { x0: 0, y0: 0.65, x1: 0.7, y1: 0.91 } },
  { id: 'bottom', label: 'Bar input & hadiah', rect: { x0: 0, y0: 0.93, x1: 1, y1: 1 } },
]

/** Margin sisi yang terpotong di ponsel yang lebih tinggi dari 9:16. */
export const SIDE_MARGIN = 0.05

export const pct = (v: number) => `${(v * 100).toFixed(2)}%`
