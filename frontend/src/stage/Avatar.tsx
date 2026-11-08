/**
 * Avatar ilustrasi sementara untuk layar OBS (mockup StageModeA/B). Avatar final = klip video
 * realistis (FR-8); komponen ini cukup diganti tanpa mengubah StagePage.
 * Mulut mengikuti level audio sungguhan yang sedang diputar (bukan animasi loop).
 */
import { useEffect, useRef } from 'react'

export type AvatarPersona = 'raka' | 'salsa'

const THEME: Record<AvatarPersona, { checker: string; doodle: string; disc: string }> = {
  raka: { checker: '#F2FAFC', doodle: '#CDEDF4', disc: 'var(--brand-blue)' },
  salsa: { checker: '#FFFBE6', doodle: '#F6E7A6', disc: 'var(--brand-yellow)' },
}

interface Props {
  persona: AvatarPersona
  name: string
  speaking: boolean
  /** Level audio 0..1 yang sedang diputar; null bila tidak tersedia. */
  getLevel: () => number | null
}

export function AvatarPanel({ persona, name, speaking, getLevel }: Props) {
  const mouthRef = useRef<SVGEllipseElement>(null)
  const discRef = useRef<HTMLDivElement>(null)
  const t = THEME[persona]

  // Mulut dan lingkaran latar mengikuti level audio per frame, tanpa render ulang React.
  useEffect(() => {
    if (!speaking) return
    let raf = 0
    let smooth = 0
    const tick = () => {
      const lv = getLevel() ?? 0
      smooth = smooth * 0.5 + lv * 0.5
      if (mouthRef.current) mouthRef.current.style.transform = `scaleY(${(0.2 + 0.8 * smooth).toFixed(3)})`
      if (discRef.current) discRef.current.style.transform = `scale(${(1 + 0.05 * smooth).toFixed(3)})`
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => {
      cancelAnimationFrame(raf)
      if (discRef.current) discRef.current.style.transform = ''
    }
  }, [speaking, getLevel])

  return (
    <div className="stage-panel" style={{ background: `repeating-conic-gradient(${t.checker} 0 25%, #FFFFFF 0 50%) 0 0 / 60px 60px` }}>
      <div className="stage-panel__glow" aria-hidden="true" />
      <Doodles color={t.doodle} flip={persona === 'salsa'} />
      <div ref={discRef} className="stage-panel__disc" style={{ background: t.disc }} aria-hidden="true" />
      <svg
        className={`stage-avatar ${speaking ? 'is-speaking' : 'is-idle'}`}
        role="img"
        aria-label={`${name} ${speaking ? 'sedang bicara' : 'sedang mendengarkan'}`}
        viewBox="0 0 300 300"
      >
        <g className="stage-avatar__body">{persona === 'raka' ? <Raka speaking={speaking} mouthRef={mouthRef} /> : <Salsa speaking={speaking} mouthRef={mouthRef} />}</g>
      </svg>
    </div>
  )
}

type PartProps = { speaking: boolean; mouthRef: React.RefObject<SVGEllipseElement> }
const INK = '#111312'

function Raka({ speaking, mouthRef }: PartProps) {
  return (
    <>
      <path d="M40 300c4-58 46-86 110-86s106 28 110 86z" fill="#FFFFFF" stroke={INK} strokeWidth="4" strokeLinejoin="round" />
      <path d="M118 214c8 18 20 26 32 26s24-8 32-26" fill="none" stroke={INK} strokeWidth="4" strokeLinecap="round" />
      <rect x="132" y="178" width="36" height="40" rx="10" fill="#E9B98C" stroke={INK} strokeWidth="4" />
      <ellipse cx="96" cy="126" rx="12" ry="16" fill="#E9B98C" stroke={INK} strokeWidth="4" />
      <ellipse cx="204" cy="126" rx="12" ry="16" fill="#E9B98C" stroke={INK} strokeWidth="4" />
      <rect x="98" y="62" width="104" height="128" rx="50" fill="#F1C9A0" stroke={INK} strokeWidth="4" />
      <path d="M94 104c-4-40 22-62 58-62 34 0 56 18 54 58-14-14-32-22-58-20-22 2-40 10-54 24z" fill="#2A2420" stroke={INK} strokeWidth="4" strokeLinejoin="round" />
      <path d="M122 104l18-4M178 104l-18-4" stroke={INK} strokeWidth="4" strokeLinecap="round" />
      <g className="stage-avatar__eyes">
        <circle cx="130" cy="122" r="6" fill={INK} />
        <circle cx="170" cy="122" r="6" fill={INK} />
      </g>
      {speaking ? (
        <ellipse ref={mouthRef} className="stage-avatar__mouth" cx="150" cy="158" rx="14" ry="11" fill="#7A2E2A" stroke={INK} strokeWidth="3.5" />
      ) : (
        <path d="M138 156c6 6 18 6 24 0" fill="none" stroke={INK} strokeWidth="4" strokeLinecap="round" />
      )}
      <path d="M86 128c-6-60 26-92 64-92s70 32 64 92" fill="none" stroke={INK} strokeWidth="9" strokeLinecap="round" />
      <rect x="74" y="110" width="26" height="42" rx="10" fill="#69C1D5" stroke={INK} strokeWidth="4" />
      <rect x="200" y="110" width="26" height="42" rx="10" fill="#69C1D5" stroke={INK} strokeWidth="4" />
    </>
  )
}

function Salsa({ speaking, mouthRef }: PartProps) {
  return (
    <>
      <path d="M84 120c-8 70 0 130 20 170h92c20-40 28-100 20-170z" fill="#3B2A22" stroke={INK} strokeWidth="4" strokeLinejoin="round" />
      <path d="M40 300c4-58 46-86 110-86s106 28 110 86z" fill="#DBF4FA" stroke={INK} strokeWidth="4" strokeLinejoin="round" />
      <path d="M120 214c8 16 18 22 30 22s22-6 30-22" fill="none" stroke={INK} strokeWidth="4" strokeLinecap="round" />
      <rect x="134" y="178" width="32" height="40" rx="10" fill="#F3D2B3" stroke={INK} strokeWidth="4" />
      <rect x="100" y="62" width="100" height="126" rx="48" fill="#F8DCC2" stroke={INK} strokeWidth="4" />
      <path d="M96 128c-6-52 18-84 56-84 36 0 58 26 52 84-10-30-24-46-44-52-14 18-38 30-64 52z" fill="#3B2A22" stroke={INK} strokeWidth="4" strokeLinejoin="round" />
      <path d={speaking ? 'M124 106l14-3M176 106l-14-3' : 'M124 108l14-2M176 108l-14-2'} stroke={INK} strokeWidth="4" strokeLinecap="round" />
      <g className="stage-avatar__eyes">
        <circle cx="132" cy="126" r="6" fill={INK} />
        <circle cx="168" cy="126" r="6" fill={INK} />
      </g>
      {speaking ? (
        <ellipse ref={mouthRef} className="stage-avatar__mouth" cx="150" cy="160" rx="12" ry="10" fill="#7A2E2A" stroke={INK} strokeWidth="3.5" />
      ) : (
        <path d="M138 158c6 6 18 6 24 0" fill="none" stroke={INK} strokeWidth="4" strokeLinecap="round" />
      )}
      <circle cx="118" cy="146" r="7" fill="#F5A9A0" opacity=".7" />
      <circle cx="182" cy="146" r="7" fill="#F5A9A0" opacity=".7" />
      <path d="M88 130c-6-60 26-92 62-92s68 32 62 92" fill="none" stroke={INK} strokeWidth="9" strokeLinecap="round" />
      <rect x="76" y="112" width="26" height="42" rx="10" fill="#FEE980" stroke={INK} strokeWidth="4" />
      <rect x="198" y="112" width="26" height="42" rx="10" fill="#FEE980" stroke={INK} strokeWidth="4" />
    </>
  )
}

function Doodles({ color, flip }: { color: string; flip: boolean }) {
  return (
    <svg
      className="stage-panel__doodles"
      aria-hidden="true"
      viewBox="0 0 540 480"
      preserveAspectRatio="xMidYMid slice"
      fill="none"
      stroke={color}
      strokeWidth="3"
      strokeLinecap="round"
      strokeLinejoin="round"
      style={flip ? { transform: 'scaleX(-1)' } : undefined}
    >
      <path d="M34 150h64a14 14 0 0 1 14 14v26a14 14 0 0 1-14 14H62l-14 12v-12h-14a14 14 0 0 1-14-14v-26a14 14 0 0 1 14-14z" />
      <path d="M48 177h0M66 177h0M84 177h0" strokeWidth="6" />
      <path d="M478 168c-8-12-26-6-22 8 3 10 22 20 22 20s19-10 22-20c4-14-14-20-22-8z" />
      <path d="M440 300h62a14 14 0 0 1 14 14v22a14 14 0 0 1-14 14h-10v12l-14-12h-38a14 14 0 0 1-14-14v-22a14 14 0 0 1 14-14z" />
      <path d="M30 330c10-12 20 12 30 0s20 12 30 0" />
    </svg>
  )
}
