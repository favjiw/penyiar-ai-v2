import { useEffect, useState } from 'react'

/**
 * State yang diingat di localStorage (nama penyiar, suara terakhir, durasi; HANDOFF §2).
 * localStorage bisa tidak tersedia (mode privat, situs diblokir): selalu di dalam try/catch,
 * dan halaman tetap jalan dengan nilai bawaan.
 */
export function usePersisted<T>(key: string, initial: T, isValid: (v: unknown) => v is T = (_v): _v is T => true) {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = window.localStorage.getItem(key)
      if (raw !== null) {
        const parsed: unknown = JSON.parse(raw)
        if (isValid(parsed)) return parsed
      }
    } catch {
      /* abaikan: pakai nilai bawaan */
    }
    return initial
  })
  useEffect(() => {
    try {
      window.localStorage.setItem(key, JSON.stringify(value))
    } catch {
      /* abaikan */
    }
  }, [key, value])
  return [value, setValue] as const
}
