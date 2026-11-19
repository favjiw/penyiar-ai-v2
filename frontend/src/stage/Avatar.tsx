/**
 * Satu panel karakter kartun 2D beranimasi di layar OBS (gratis, tanpa layanan berbayar).
 *
 * Animasi 2D digerakkan per frame dari level audio sungguhan yang sedang diputar (tanpa render ulang React):
 * napas, goyang kepala, anggukan saat bicara, kedip acak (kadang dua kali), lirikan mata, alis naik pada aksen,
 * dan bukaan mulut mengikuti amplitudo.
 */
import { useEffect, useRef, type RefObject } from 'react'

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

/** Bagian karakter yang digerakkan per frame. */
interface Rig {
  torso: RefObject<SVGGElement>
  head: RefObject<SVGGElement>
  hairBack: RefObject<SVGGElement>
  brows: RefObject<SVGGElement>
  eyes: RefObject<SVGGElement>
  mouth: RefObject<SVGEllipseElement>
}

const rand = (a: number, b: number) => a + Math.random() * (b - a)

export function AvatarPanel({ persona, name, speaking, getLevel }: Props) {
  const rig: Rig = {
    torso: useRef<SVGGElement>(null),
    head: useRef<SVGGElement>(null),
    hairBack: useRef<SVGGElement>(null),
    brows: useRef<SVGGElement>(null),
    eyes: useRef<SVGGElement>(null),
    mouth: useRef<SVGEllipseElement>(null),
  }
  const discRef = useRef<HTMLDivElement>(null)
  const speakingRef = useRef(speaking)
  speakingRef.current = speaking
  const t = THEME[persona]

  // Animasi karakter 2D: satu loop per panel.
  useEffect(() => {
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
    let raf = 0
    let last = performance.now()
    let smooth = 0 // level audio yang dihaluskan
    let peak = 0 // aksen: naik cepat, turun pelan
    let nextBlink = last + rand(1200, 3500)
    let blinkStart = -1
    let nextLook = last + rand(900, 2400)
    let look = { x: 0, y: 0, tx: 0, ty: 0 }

    const set = (el: SVGElement | HTMLElement | null, transform: string) => {
      if (el) el.style.transform = transform
    }

    const tick = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000)
      last = now
      const t = now / 1000
      const talk = speakingRef.current ? 1 : 0
      const raw = talk ? (getLevel() ?? 0) : 0
      smooth += (raw - smooth) * Math.min(1, dt * 14)
      peak = Math.max(smooth, peak - dt * 1.4)

      if (!reduced) {
        // Napas dan goyang pelan saat diam; saat bicara kepala mengangguk dan miring mengikuti energi suara.
        const breathe = Math.sin(t * 1.7)
        const idleSway = Math.sin(t * 0.7) * 0.9 + Math.sin(t * 1.9 + 1) * 0.4
        const talkSway = (Math.sin(t * 3.3) * 1.7 + Math.sin(t * 5.1 + 2) * 0.9) * (0.35 + smooth)
        const tilt = idleSway * (1 - 0.6 * talk) + talk * talkSway
        const headY = breathe * 1.1 + talk * (-smooth * 5 + Math.sin(t * 4.2) * 0.8)
        const headX = Math.sin(t * 0.9) * 1.2 + talk * Math.sin(t * 2.4) * 1.6
        const head = `translate(${headX.toFixed(2)}px, ${headY.toFixed(2)}px) rotate(${tilt.toFixed(2)}deg)`
        set(rig.head.current, head)
        set(rig.hairBack.current, `translate(${(headX * 0.6).toFixed(2)}px, ${(headY * 0.8).toFixed(2)}px) rotate(${(tilt * 0.7).toFixed(2)}deg)`)
        set(rig.torso.current, `translateY(${(breathe * 0.8 + talk * smooth * -1.5).toFixed(2)}px) scaleY(${(1 + breathe * 0.006).toFixed(4)})`)

        // Kedip acak, sesekali dua kali berturut-turut.
        let blink = 0
        if (blinkStart < 0 && now >= nextBlink) blinkStart = now
        if (blinkStart >= 0) {
          const p = (now - blinkStart) / 150
          if (p >= 1) {
            blinkStart = -1
            nextBlink = now + (Math.random() < 0.16 ? 200 : rand(2200, 5200))
          } else blink = Math.sin(Math.PI * p)
        }

        // Lirikan: mata berpindah sedikit tiap 1-3 detik (hampir lurus saat bicara).
        if (now >= nextLook) {
          const range = talk ? 0.5 : 1
          look.tx = rand(-2.6, 2.6) * range
          look.ty = rand(-1.4, 1.4) * range
          nextLook = now + rand(1000, 3000)
        }
        look.x += (look.tx - look.x) * Math.min(1, dt * 9)
        look.y += (look.ty - look.y) * Math.min(1, dt * 9)
        set(rig.eyes.current, `translate(${look.x.toFixed(2)}px, ${look.y.toFixed(2)}px) scaleY(${(1 - blink * 0.92).toFixed(3)})`)

        // Alis naik pada aksen suara.
        set(rig.brows.current, `translateY(${(-peak * talk * 4.5).toFixed(2)}px)`)
      }

      // Bukaan mulut mengikuti amplitudo (mulut hanya ada saat bicara).
      set(rig.mouth.current, `scale(${(0.92 + 0.22 * smooth).toFixed(3)}, ${(0.18 + 0.9 * Math.min(1, smooth * 1.5)).toFixed(3)})`)
      set(discRef.current, `scale(${(1 + 0.05 * smooth).toFixed(3)})`)
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => {
      cancelAnimationFrame(raf)
      for (const el of [rig.head.current, rig.hairBack.current, rig.torso.current, rig.eyes.current, rig.brows.current, discRef.current]) set(el, '')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [getLevel])

  return (
    <div className="stage-panel" style={{ background: `repeating-conic-gradient(${t.checker} 0 25%, #FFFFFF 0 50%) 0 0 / 60px 60px` }}>
      <div className="stage-panel__glow" aria-hidden="true" />
      <Doodles color={t.doodle} flip={persona === 'salsa'} />
      <div ref={discRef} className="stage-panel__disc" style={{ background: t.disc }} aria-hidden="true" />
      <svg
        className="stage-avatar"
        role="img"
        aria-label={`${name} ${speaking ? 'sedang bicara' : 'sedang mendengarkan'}`}
        viewBox="0 0 300 300"
      >
        {persona === 'raka' ? <Raka speaking={speaking} rig={rig} /> : <Salsa speaking={speaking} rig={rig} />}
      </svg>
    </div>
  )
}

type PartProps = { speaking: boolean; rig: Rig }
const INK = '#111312'

function Raka({ speaking, rig }: PartProps) {
  return (
    <>
      <g ref={rig.torso} className="stage-rig stage-rig--torso">
        <path d="M40 300c4-58 46-86 110-86s106 28 110 86z" fill="#FFFFFF" stroke={INK} strokeWidth="4" strokeLinejoin="round" />
        <path d="M118 214c8 18 20 26 32 26s24-8 32-26" fill="none" stroke={INK} strokeWidth="4" strokeLinecap="round" />
        <rect x="132" y="178" width="36" height="40" rx="10" fill="#E9B98C" stroke={INK} strokeWidth="4" />
      </g>
      <g ref={rig.head} className="stage-rig stage-rig--head">
        <ellipse cx="96" cy="126" rx="12" ry="16" fill="#E9B98C" stroke={INK} strokeWidth="4" />
        <ellipse cx="204" cy="126" rx="12" ry="16" fill="#E9B98C" stroke={INK} strokeWidth="4" />
        <rect x="98" y="62" width="104" height="128" rx="50" fill="#F1C9A0" stroke={INK} strokeWidth="4" />
        <path d="M94 104c-4-40 22-62 58-62 34 0 56 18 54 58-14-14-32-22-58-20-22 2-40 10-54 24z" fill="#2A2420" stroke={INK} strokeWidth="4" strokeLinejoin="round" />
        <g ref={rig.brows} className="stage-rig stage-rig--brows">
          <path d="M122 104l18-4M178 104l-18-4" stroke={INK} strokeWidth="4" strokeLinecap="round" />
        </g>
        <g ref={rig.eyes} className="stage-rig stage-rig--eyes">
          <circle cx="130" cy="122" r="6" fill={INK} />
          <circle cx="170" cy="122" r="6" fill={INK} />
        </g>
        {speaking ? (
          <ellipse ref={rig.mouth} className="stage-avatar__mouth" cx="150" cy="158" rx="14" ry="11" fill="#7A2E2A" stroke={INK} strokeWidth="3.5" />
        ) : (
          <path d="M138 156c6 6 18 6 24 0" fill="none" stroke={INK} strokeWidth="4" strokeLinecap="round" />
        )}
        <path d="M86 128c-6-60 26-92 64-92s70 32 64 92" fill="none" stroke={INK} strokeWidth="9" strokeLinecap="round" />
        <rect x="74" y="110" width="26" height="42" rx="10" fill="#69C1D5" stroke={INK} strokeWidth="4" />
        <rect x="200" y="110" width="26" height="42" rx="10" fill="#69C1D5" stroke={INK} strokeWidth="4" />
      </g>
    </>
  )
}

function Salsa({ speaking, rig }: PartProps) {
  return (
    <>
      <g ref={rig.hairBack} className="stage-rig stage-rig--head">
        <path d="M84 120c-8 70 0 130 20 170h92c20-40 28-100 20-170z" fill="#3B2A22" stroke={INK} strokeWidth="4" strokeLinejoin="round" />
      </g>
      <g ref={rig.torso} className="stage-rig stage-rig--torso">
        <path d="M40 300c4-58 46-86 110-86s106 28 110 86z" fill="#DBF4FA" stroke={INK} strokeWidth="4" strokeLinejoin="round" />
        <path d="M120 214c8 16 18 22 30 22s22-6 30-22" fill="none" stroke={INK} strokeWidth="4" strokeLinecap="round" />
        <rect x="134" y="178" width="32" height="40" rx="10" fill="#F3D2B3" stroke={INK} strokeWidth="4" />
      </g>
      <g ref={rig.head} className="stage-rig stage-rig--head">
        <rect x="100" y="62" width="100" height="126" rx="48" fill="#F8DCC2" stroke={INK} strokeWidth="4" />
        <path d="M96 128c-6-52 18-84 56-84 36 0 58 26 52 84-10-30-24-46-44-52-14 18-38 30-64 52z" fill="#3B2A22" stroke={INK} strokeWidth="4" strokeLinejoin="round" />
        <g ref={rig.brows} className="stage-rig stage-rig--brows">
          <path d={speaking ? 'M124 106l14-3M176 106l-14-3' : 'M124 108l14-2M176 108l-14-2'} stroke={INK} strokeWidth="4" strokeLinecap="round" />
        </g>
        <g ref={rig.eyes} className="stage-rig stage-rig--eyes">
          <circle cx="132" cy="126" r="6" fill={INK} />
          <circle cx="168" cy="126" r="6" fill={INK} />
        </g>
        {speaking ? (
          <ellipse ref={rig.mouth} className="stage-avatar__mouth" cx="150" cy="160" rx="12" ry="10" fill="#7A2E2A" stroke={INK} strokeWidth="3.5" />
        ) : (
          <path d="M138 158c6 6 18 6 24 0" fill="none" stroke={INK} strokeWidth="4" strokeLinecap="round" />
        )}
        <circle cx="118" cy="146" r="7" fill="#F5A9A0" opacity=".7" />
        <circle cx="182" cy="146" r="7" fill="#F5A9A0" opacity=".7" />
        <path d="M88 130c-6-60 26-92 62-92s68 32 62 92" fill="none" stroke={INK} strokeWidth="9" strokeLinecap="round" />
        <rect x="76" y="112" width="26" height="42" rx="10" fill="#FEE980" stroke={INK} strokeWidth="4" />
        <rect x="198" y="112" width="26" height="42" rx="10" fill="#FEE980" stroke={INK} strokeWidth="4" />
      </g>
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
