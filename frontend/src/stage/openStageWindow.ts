/** Nama jendela tetap: membuka ulang memakai jendela yang sama, jadi OBS tetap menangkap jendela itu. */
export const STAGE_WINDOW_NAME = 'hits-stage'

/**
 * Buka layar untuk OBS sebagai popup (HANDOFF §2): mode B 540×960 dua panel, mode A 540×480 satu panel.
 * Dipanggil dari klik tombol supaya tidak diblokir pemblokir popup.
 */
export function openStageWindow(mode: 'A' | 'B', aiPersona?: string): Window | null {
  const q = new URLSearchParams({ mode })
  if (mode === 'A' && aiPersona) q.set('ai', aiPersona)
  const height = mode === 'A' ? 480 : 960
  const win = window.open(`/stage?${q}`, STAGE_WINDOW_NAME, `popup,width=540,height=${height}`)
  win?.focus()
  return win
}
