import { useEffect, useRef, useState } from 'react'

/**
 * Avatar T1 (FR-8): bank klip video per persona dengan crossfade dua elemen <video>.
 *
 * - tidak ada yang bicara → klip idle; lawan bicara bicara → klip mendengarkan
 *   (acak, tanpa klip yang sama berturut-turut);
 * - persona ini mulai bicara → klip reaksi sesuai emosi (opsional, maks 1,5 s),
 *   lalu klip bicara bergantian sampai audio selesai;
 * - energi klip bicara: emosi excited/happy/surprised → "hype", selain itu "calm".
 *   (PRD menyebut energi audio RMS; emosi giliran dipakai dulu karena audio diputar
 *   oleh pemilik audio, yang belum tentu halaman ini.)
 * Gerak bibir tidak sinkron per kata: batasan tingkat T1 yang diakui di PRD.
 */

export interface Clip {
  code: string
  file: string
  state: 'idle' | 'listen' | 'talk' | 'react'
  energy?: 'calm' | 'hype'
  emotion?: string
}

interface Manifest {
  persona: string
  dummy?: boolean
  /** Panel stage 9:8 memotong klip 9:16: posisi vertikal yang tetap terlihat (0 = atas, 1 = bawah). */
  focus_y?: number
  clips: Clip[]
}

type Mode = 'idle' | 'listen' | 'talk'

interface Props {
  persona: string
  mode: Mode
  emotion?: string | null
  turnKey?: number | null // berubah setiap giliran baru persona ini → reaksi
  fadeMs?: number
  onUnavailable?: () => void
}

const HYPE = new Set(['excited', 'happy', 'surprised'])
const REACT_MAX_MS = 1500

export function pickClip(clips: Clip[], mode: Mode | 'react', opts: { emotion?: string | null; last?: string } = {}): Clip | null {
  let pool: Clip[]
  if (mode === 'react') pool = clips.filter((c) => c.state === 'react' && c.emotion === opts.emotion)
  else if (mode === 'talk') {
    const energy = opts.emotion && HYPE.has(opts.emotion) ? 'hype' : 'calm'
    pool = clips.filter((c) => c.state === 'talk' && (c.energy ?? 'calm') === energy)
    if (!pool.length) pool = clips.filter((c) => c.state === 'talk')
  } else {
    pool = clips.filter((c) => c.state === mode)
    if (!pool.length && mode === 'listen') pool = clips.filter((c) => c.state === 'idle')
  }
  if (!pool.length) return null
  const fresh = pool.length > 1 ? pool.filter((c) => c.code !== opts.last) : pool
  return fresh[Math.floor(Math.random() * fresh.length)]
}

export function VideoAvatar({ persona, mode, emotion, turnKey, fadeMs = 200, onUnavailable }: Props) {
  const [manifest, setManifest] = useState<Manifest | null>(null)
  const vids = [useRef<HTMLVideoElement>(null), useRef<HTMLVideoElement>(null)]
  const front = useRef(0)
  const last = useRef<string | undefined>()
  const want = useRef<{ mode: Mode; emotion?: string | null }>({ mode })
  const reactTimer = useRef<number>()
  const base = `/avatar-assets/${persona}/`

  // Callback di ref: induk biasa mengirim fungsi baru tiap render, dan manifest cukup diambil sekali.
  const unavailable = useRef(onUnavailable)
  unavailable.current = onUnavailable
  useEffect(() => {
    let alive = true
    fetch(`${base}manifest.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((m: Manifest) => alive && (m.clips?.length ? setManifest(m) : unavailable.current?.()))
      .catch(() => alive && unavailable.current?.())
    return () => {
      alive = false
    }
  }, [base])

  /** Putar klip di elemen belakang; crossfade setelah frame pertamanya siap (tanpa kedip hitam). */
  const show = (clip: Clip, onEnd?: () => void) => {
    const back = vids[1 - front.current].current
    const cur = vids[front.current].current
    if (!back || !cur) return
    last.current = clip.code
    back.onended = onEnd ?? null
    back.src = base + clip.file
    let swapped = false
    const swap = () => {
      if (swapped) return
      swapped = true
      back.style.opacity = '1'
      cur.style.opacity = '0'
      front.current = 1 - front.current
      window.setTimeout(() => {
        if (cur.style.opacity === '0') {
          cur.pause()
          cur.onended = null
        }
      }, fadeMs + 50)
    }
    back
      .play()
      .then(() => {
        if (!back.requestVideoFrameCallback) return swap()
        back.requestVideoFrameCallback(() => swap())
        // Jendela yang tidak sedang dirender tidak memanggil callback frame; jangan biarkan avatar kosong.
        window.setTimeout(swap, 300)
      })
      .catch(() => undefined) // autoplay video bisu jarang diblokir; klip berikutnya mencoba lagi
  }

  /**
   * Setiap mode berganti klip lewat crossfade saat klip habis, tidak di-loop: frame awal dan
   * akhir klip Flow tidak sama persis, jadi loop keras terlihat melompat.
   */
  const playMode = (m: Mode, emo?: string | null) => {
    if (!manifest) return
    const clip = pickClip(manifest.clips, m, { emotion: emo, last: last.current })
    if (!clip) return
    show(clip, () => want.current.mode === m && playMode(m, want.current.emotion))
  }

  // Mode berubah (atau giliran baru) → reaksi singkat bila ada, lalu klip mode itu.
  useEffect(() => {
    want.current = { mode, emotion }
    window.clearTimeout(reactTimer.current)
    if (!manifest) return
    if (mode === 'talk' && emotion && emotion !== 'neutral') {
      const react = pickClip(manifest.clips, 'react', { emotion })
      if (react) {
        const toTalk = () => {
          window.clearTimeout(reactTimer.current)
          if (want.current.mode === 'talk') playMode('talk', want.current.emotion)
        }
        show(react, toTalk)
        reactTimer.current = window.setTimeout(toTalk, REACT_MAX_MS)
        return
      }
    }
    playMode(mode, emotion)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [manifest, mode, turnKey])

  useEffect(() => () => window.clearTimeout(reactTimer.current), [])

  const focus = Math.min(1, Math.max(0, manifest?.focus_y ?? 0.35))
  const style = { transition: `opacity ${fadeMs}ms linear`, objectPosition: `50% ${focus * 100}%` }
  return (
    <div className="video-avatar" data-dummy={manifest?.dummy ? '1' : undefined}>
      <video ref={vids[0]} muted playsInline preload="auto" style={{ ...style, opacity: 0 }} />
      <video ref={vids[1]} muted playsInline preload="auto" style={{ ...style, opacity: 0 }} />
    </div>
  )
}
