import { useEffect, useRef } from 'react'
import './orb.css'

export type OrbState = 'idle' | 'listening' | 'thinking' | 'speaking'

export const ORB_STATE_LABEL: Record<OrbState, string> = {
  idle: 'diam',
  listening: 'mendengarkan',
  thinking: 'berpikir',
  speaking: 'berbicara',
}

interface Props {
  persona: string
  name: string
  state: OrbState
  /** Amplitudo audio 0..1; null bila amplitudo tidak tersedia (klien bukan pemilik audio). */
  getLevel: () => number | null
}

const ATTACK = 0.55 // naik cepat mengikuti suara
const RELEASE = 0.14 // turun pelan supaya tidak bergetar kasar

/**
 * Orb giliran bicara: lingkaran bergradasi yang bernapas saat mendengarkan, berkilau saat
 * berpikir, dan membesar mengikuti amplitudo audio saat berbicara. Amplitudo ditulis langsung
 * ke variabel CSS `--lvl` tiap frame (tanpa render React). Warna dari `--orb-<persona>-1/2`.
 */
export function Orb({ persona, name, state, getLevel }: Props) {
  const el = useRef<HTMLDivElement>(null)
  const getLevelRef = useRef(getLevel)
  getLevelRef.current = getLevel

  useEffect(() => {
    const node = el.current
    if (!node) return
    if (state !== 'speaking' || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      node.style.setProperty('--lvl', '0')
      return
    }
    let raf = 0
    let smooth = 0
    const t0 = performance.now()
    const frame = (now: number) => {
      // Tanpa amplitudo asli: denyut bicara buatan supaya orb tetap terlihat aktif.
      const raw = getLevelRef.current() ?? 0.32 + 0.16 * Math.sin((now - t0) / 140)
      smooth += (raw - smooth) * (raw > smooth ? ATTACK : RELEASE)
      node.style.setProperty('--lvl', smooth.toFixed(3))
      raf = requestAnimationFrame(frame)
    }
    raf = requestAnimationFrame(frame)
    return () => cancelAnimationFrame(raf)
  }, [state])

  return (
    <figure className="orb-wrap">
      <div ref={el} className="orb" data-state={state} data-persona={persona} role="img" aria-label={`${name}: ${ORB_STATE_LABEL[state]}`}>
        <div className="orb-fill" />
      </div>
      <figcaption>
        <span className="orb-name">{name}</span>
        <span className="orb-state" aria-live="polite">
          {ORB_STATE_LABEL[state]}
        </span>
      </figcaption>
    </figure>
  )
}

/** Indikator mikrofon penyiar manusia: kecil, menyala saat push-to-talk ditahan. */
export function MicIndicator({ name, active }: { name: string; active: boolean }) {
  return (
    <div className={`mic-indicator ${active ? 'on' : ''}`} role="img" aria-label={`${name}: mikrofon ${active ? 'menyala' : 'mati'}`}>
      <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
        <path
          d="M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V22h2v-3.08A7 7 0 0 0 19 12h-2z"
          fill="currentColor"
        />
      </svg>
      <span className="mic-name">{name}</span>
      <span className="orb-state">{active ? 'bicara' : 'diam'}</span>
    </div>
  )
}
