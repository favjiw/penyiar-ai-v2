import { useEffect, useState } from 'react'
import type { LiveSession } from './useLiveSession'

export interface ShowClockValues {
  elapsed: number
  target: number
  segElapsed: number
  segTarget: number
  /** Sisa waktu segmen (negatif = lewat waktu). */
  remaining: number
  running: boolean
}

/**
 * Jam siaran dari server (`show_clock`), dihitung maju di klien selama berjalan supaya
 * angka detik bergerak tanpa menunggu event. Dipakai prompter dan konsol.
 */
export function useShowClock(showClock: LiveSession['showClock'], tickMs = 250): ShowClockValues | null {
  const running = !!showClock?.clock.running
  const [, setN] = useState(0)
  useEffect(() => {
    if (!running) return
    const t = window.setInterval(() => setN((n) => n + 1), tickMs)
    return () => window.clearInterval(t)
  }, [running, tickMs])
  if (!showClock) return null
  const c = showClock.clock
  const drift = c.running ? (performance.now() - showClock.at) / 1000 : 0
  const segElapsed = c.segment_elapsed_s + drift
  return {
    elapsed: c.elapsed_s + drift,
    target: c.target_s,
    segElapsed,
    segTarget: c.segment_target_s,
    remaining: c.segment_target_s - segElapsed,
    running: c.running,
  }
}
