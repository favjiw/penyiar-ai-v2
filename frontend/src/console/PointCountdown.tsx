import { useEffect, useState } from 'react'
import type { LiveSession } from '../live/useLiveSession'

const fmt = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`

/** Sisa waktu obrolan (poin) untuk kedua penyiar; null bila batas waktu mati atau bukan segmen topik. */
export function usePointCountdown(pc: LiveSession['pointClock']) {
  const [now, setNow] = useState(Date.now())
  const running = !!pc && pc.clock.active && pc.clock.running
  useEffect(() => {
    if (!running) return
    const t = window.setInterval(() => setNow(Date.now()), 250)
    return () => window.clearInterval(t)
  }, [running])
  if (!pc || !pc.clock.active) return null
  const c = pc.clock
  const extra = c.running ? Math.max(0, now - pc.at) / 1000 : 0
  return { remaining: Math.max(0, c.limit_s - c.played_s - extra), idx: c.idx, total: c.total, text: c.text, limit: c.limit_s }
}

/** Label kecil "Poin 2/4 · 0:42" (atau "⏱ 1:00" saat di luar segmen topik) dengan warna peringatan saat waktu menipis. */
export function PointCountdown({ pointClock }: { pointClock: LiveSession['pointClock'] }) {
  const cd = usePointCountdown(pointClock)
  if (cd) {
    const low = cd.remaining <= 15
    return (
      <span className={`point-countdown${low ? ' low' : ''}`} title={cd.text} aria-label={`Sisa waktu obrolan poin ${cd.idx + 1} dari ${cd.total}`}>
        Poin {cd.idx + 1}/{cd.total} · {fmt(cd.remaining)}
      </span>
    )
  }
  const idleLimit = pointClock && !pointClock.clock.active ? pointClock.clock.limit_s : undefined
  if (!idleLimit || idleLimit <= 0) return null
  return (
    <span className="point-countdown" title="Batas waktu obrolan per poin" aria-label={`Timer obrolan per poin ${fmt(idleLimit)}`}>
      ⏱ {fmt(idleLimit)}
    </span>
  )
}
