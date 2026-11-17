/**
 * Pilihan tampilan karakter di layar OBS: avatar realistis (Simli) atau karakter kartun 2D beranimasi.
 * Dipilih operator di konsol (Siap live) dan disimpan di localStorage; layar OBS (jendela lain, satu asal)
 * membacanya dan ikut berganti seketika lewat event `storage`, tanpa klik apa pun di layar OBS.
 */
import { useCallback, useSyncExternalStore } from 'react'

export type AvatarStyle = 'realistic' | '2d'

export const AVATAR_STYLE_KEY = 'hits.avatarStyle'
const SAME_WINDOW_EVENT = 'hits-avatar-style'

const isStyle = (v: unknown): v is AvatarStyle => v === 'realistic' || v === '2d'

export function readAvatarStyle(): AvatarStyle {
  try {
    const raw = window.localStorage.getItem(AVATAR_STYLE_KEY)
    if (raw !== null) {
      const parsed: unknown = JSON.parse(raw)
      if (isStyle(parsed)) return parsed
    }
  } catch {
    /* abaikan: pakai bawaan */
  }
  return 'realistic'
}

function subscribe(onChange: () => void) {
  const onStorage = (e: StorageEvent) => {
    if (e.key === AVATAR_STYLE_KEY || e.key === null) onChange()
  }
  window.addEventListener('storage', onStorage)
  window.addEventListener(SAME_WINDOW_EVENT, onChange)
  return () => {
    window.removeEventListener('storage', onStorage)
    window.removeEventListener(SAME_WINDOW_EVENT, onChange)
  }
}

export function useAvatarStyle() {
  const style = useSyncExternalStore(subscribe, readAvatarStyle, () => 'realistic' as AvatarStyle)
  const setStyle = useCallback((next: AvatarStyle) => {
    try {
      window.localStorage.setItem(AVATAR_STYLE_KEY, JSON.stringify(next))
    } catch {
      /* abaikan */
    }
    window.dispatchEvent(new Event(SAME_WINDOW_EVENT))
  }, [])
  return [style, setStyle] as const
}
