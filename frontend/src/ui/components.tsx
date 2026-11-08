/** Komponen dasar UI Penyiar AI HITS (DESIGN.md §4, HANDOFF.md §3 langkah 2). */
import { useEffect, useRef, type ButtonHTMLAttributes, type HTMLAttributes, type ReactNode } from 'react'
import { IconAlert, IconClose, IconInfo } from './icons'

const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(' ')

// ── Tombol ────────────────────────────────────────────────────────────────
export type ButtonVariant = 'primary' | 'secondary' | 'ink' | 'danger' | 'link'
type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant
  size?: 'md' | 'lg' | 'xl'
  icon?: ReactNode
}

/** Utama = isi biru merek + teks ink; sekunder = putih + border; ink = aksi di peringatan merah; danger dipisah dari aksi lain. */
export function Button({ variant = 'secondary', size = 'md', icon, className, children, type = 'button', ...rest }: ButtonProps) {
  return (
    <button
      type={type}
      className={cx('ui-btn', variant !== 'secondary' && `ui-btn--${variant}`, size !== 'md' && `ui-btn--${size}`, className)}
      {...rest}
    >
      {icon}
      {children}
    </button>
  )
}

// ── Kartu ─────────────────────────────────────────────────────────────────
type CardProps = HTMLAttributes<HTMLElement> & { variant?: 'default' | 'flat' | 'panel'; title?: ReactNode; as?: 'section' | 'div' | 'article' }

export function Card({ variant = 'default', title, as: Tag = 'section', className, children, ...rest }: CardProps) {
  return (
    <Tag className={cx('ui-card', variant !== 'default' && `ui-card--${variant}`, className)} {...rest}>
      {title && <h2 className="ui-card__title">{title}</h2>}
      {children}
    </Tag>
  )
}

// ── Pil dan badge LIVE ────────────────────────────────────────────────────
export type PillTone = 'neutral' | 'blue' | 'yellow' | 'orange' | 'success' | 'danger'

export function Pill({ tone = 'neutral', className, children, ...rest }: HTMLAttributes<HTMLSpanElement> & { tone?: PillTone }) {
  return (
    <span className={cx('ui-pill', tone !== 'neutral' && `ui-pill--${tone}`, className)} {...rest}>
      {children}
    </span>
  )
}

export function LiveBadge({ paused = false }: { paused?: boolean }) {
  return (
    <span className={cx('ui-live', paused && 'ui-live--paused')}>
      <span className="ui-live__dot" aria-hidden="true" />
      {paused ? 'JEDA' : 'LIVE'}
    </span>
  )
}

// ── Cincin waktu ──────────────────────────────────────────────────────────
const R = 50
const CIRC = 2 * Math.PI * R
export const RING_WARN_S = 30

export type RingState = 'normal' | 'warn' | 'over'

export function ringState(remainingS: number): RingState {
  if (remainingS < 0) return 'over'
  return remainingS <= RING_WARN_S ? 'warn' : 'normal'
}

/** m:ss dari detik (dibulatkan ke atas saat hitung mundur, supaya 0:00 hanya muncul saat benar-benar habis). */
export function fmtClock(totalS: number): string {
  const s = Math.max(0, Math.ceil(totalS))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

type RingProps = {
  remainingS: number
  limitS: number
  size?: number
  /** Teks di bawah waktu; bawaan mengikuti keadaan. */
  label?: string
}

/**
 * Cincin waktu tiga keadaan: biru (normal) → emas "hampir habis" (sisa ≤30 dtk) →
 * oranye penuh "+m:ss lewat waktu" (hitung naik). SVG r=50, viewBox 120, stroke 11.
 */
export function Ring({ remainingS, limitS, size = 240, label }: RingProps) {
  const state = ringState(remainingS)
  const frac = limitS > 0 ? Math.min(1, Math.max(0, remainingS / limitS)) : 0
  const stroke = state === 'over' ? 'var(--orange-500)' : state === 'warn' ? 'var(--gold-ring)' : 'var(--brand-blue)'
  const time = state === 'over' ? `+${fmtClock(-remainingS)}` : fmtClock(remainingS)
  const text = label ?? (state === 'over' ? 'lewat waktu' : state === 'warn' ? 'hampir habis' : 'sisa waktu')
  // Skala huruf mengikuti ukuran cincin (46px waktu + 20px label pada 240px, DESIGN.md §3).
  const timePx = Math.round((size * 46) / 240)
  const labelPx = Math.max(12, Math.round((size * 20) / 240))
  return (
    <div className={cx('ui-ring', `ui-ring--${state}`)} style={{ width: size, height: size }} role="timer" aria-label={`${time} ${text}`}>
      <svg width={size} height={size} viewBox="0 0 120 120" aria-hidden="true">
        <circle cx="60" cy="60" r={R} fill="none" stroke={state === 'over' ? 'var(--orange-500)' : 'var(--n-100)'} strokeWidth="11" />
        {state !== 'over' && (
          <circle
            className="ui-ring__arc"
            cx="60"
            cy="60"
            r={R}
            fill="none"
            stroke={stroke}
            strokeWidth="11"
            strokeLinecap="round"
            strokeDasharray={CIRC}
            strokeDashoffset={CIRC * (1 - frac)}
            transform="rotate(-90 60 60)"
          />
        )}
      </svg>
      <div className="ui-ring__text" aria-hidden="true">
        <span className="ui-ring__time" style={{ fontSize: timePx }}>
          {time}
        </span>
        <span className="ui-ring__label" style={{ fontSize: labelPx }}>
          {text}
        </span>
      </div>
    </div>
  )
}

// ── Bar level suara ───────────────────────────────────────────────────────
const BAR_SHAPE = [0.55, 0.85, 1, 0.8, 0.6]
const BAR_FLOOR = 0.18

/**
 * 4–5 batang yang HANYA mengikuti level audio sungguhan (prop `level` 0..1, lihat `useAudioLevel`).
 * Hening → diam rata rendah. Tidak ada animasi looping (DESIGN.md §4).
 */
export function LevelBars({ level, bars = 5, height = 28, className }: { level: number; bars?: 4 | 5; height?: number; className?: string }) {
  const lv = Math.min(1, Math.max(0, level))
  const shape = bars === 4 ? BAR_SHAPE.slice(0, 4) : BAR_SHAPE
  return (
    <span className={cx('ui-level', className)} style={{ height }} aria-hidden="true">
      {shape.map((k, i) => (
        <span key={i} className="ui-level__bar" style={{ transform: `scaleY(${BAR_FLOOR + (1 - BAR_FLOOR) * lv * k})` }} />
      ))}
    </span>
  )
}

// ── Peringatan ────────────────────────────────────────────────────────────
export type AlertLevel = 'red' | 'yellow' | 'blue'
export const ALERT_BLUE_AUTOHIDE_MS = 10_000

type AlertProps = {
  level: AlertLevel
  title: ReactNode
  message?: ReactNode
  icon?: ReactNode
  actions?: ReactNode
  time?: string
  /** Kuning: bisa ditutup. Biru: dipanggil otomatis setelah 10 dtk. Merah: tidak dipakai (tetap sampai beres). */
  onDismiss?: () => void
}

/**
 * Peringatan konsol tiga tingkat (DESIGN.md §4). Merah: siaran terganggu, tetap sampai beres.
 * Kuning: akan jadi masalah, bisa ditutup. Biru: info, hilang sendiri setelah 10 dtk.
 */
export function Alert({ level, title, message, icon, actions, time, onDismiss }: AlertProps) {
  // onDismiss disimpan di ref supaya render ulang induk (fungsi baru tiap render) tidak mengulang timer 10 dtk.
  const dismissRef = useRef(onDismiss)
  useEffect(() => {
    dismissRef.current = onDismiss
  })
  useEffect(() => {
    if (level !== 'blue') return
    const t = window.setTimeout(() => dismissRef.current?.(), ALERT_BLUE_AUTOHIDE_MS)
    return () => window.clearTimeout(t)
  }, [level])

  const iconColor = level === 'red' ? 'var(--danger)' : level === 'blue' ? 'var(--blue-700)' : 'var(--ink)'
  const defaultIcon = level === 'blue' ? <IconInfo /> : <IconAlert />
  return (
    <div className={`ui-alert ui-alert--${level}`} role={level === 'red' ? 'alert' : 'status'}>
      <span className="ui-alert__icon" style={{ color: iconColor }}>
        {icon ?? defaultIcon}
      </span>
      <div className="ui-alert__body">
        <span className="ui-alert__title">{title}</span>
        {message && <span className="ui-alert__msg">{message}</span>}
        {actions && <div className="ui-alert__actions">{actions}</div>}
      </div>
      {time && <span className="ui-alert__time">{time}</span>}
      {level === 'yellow' && onDismiss && (
        <Button variant="link" className="ui-alert__close" onClick={onDismiss} aria-label="Tutup peringatan" icon={<IconClose size={20} />} />
      )}
    </div>
  )
}
