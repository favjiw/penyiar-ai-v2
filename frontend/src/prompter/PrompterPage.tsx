/**
 * Prompter penyiar (PRD v2.7 FR-11, mockup Prompter*): dibaca dari 1–1,5 m, tanpa pengaturan,
 * dan siaran bisa berjalan tanpa satu klik pun dari penyiar.
 * - Band status berganti warna: Giliranmu (kuning) · AI bicara (biru) · AI mikir (abu) ·
 *   Pindah topik (hijau) · Mic tidak terdengar (merah muda).
 * - Topik + TANYA PENONTON besar + bahan obrolan; cincin waktu segmen; "Siaran m:ss / target".
 * - Mic hands-free (Web Speech), dijeda saat AI berpikir/bicara (giliran ketat, tanpa menyela).
 * - Tombol "Topik selanjutnya" (N) hanya opsional.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../api'
import { shout } from '../lib/materi'
import { useLiveSession } from '../live/useLiveSession'
import { useShowClock } from '../live/useShowClock'
import { fmtClock, IconCheck, IconMicOff, LevelBars, Ring, ringState } from '../ui'
import './prompter.css'
import { useMicMonitor } from './useMicMonitor'
import { speechSupported, usePushToTalk } from './usePushToTalk'

const TOPIC_BAND_MS = 6000 // lama band "Pindah topik" tampil setelah topik berganti
const AUTO_SEND_SILENCE_MS = 1200
const MIC_ERROR_CODES = new Set(['audio-capture', 'not-allowed', 'service-not-allowed'])

type Band =
  | { kind: 'turn' }
  | { kind: 'ai-speak'; name: string }
  | { kind: 'ai-think'; name: string }
  | { kind: 'switch'; title: string }
  | { kind: 'mic-down' }
  | { kind: 'paused' }
  | { kind: 'ai-between' }

/** Kalimat terakhir (kode halus selalu di akhir giliran). */
const lastSentence = (text: string) => {
  const parts = text.trim().split(/(?<=[.!?])\s+/)
  return parts[parts.length - 1] ?? text
}

/** Detik berjalan lokal: setiap `ms` render ulang selama `active`. */
function useTicker(active: boolean, ms = 250) {
  const [, setN] = useState(0)
  useEffect(() => {
    if (!active) return
    const t = window.setInterval(() => setN((n) => n + 1), ms)
    return () => window.clearInterval(t)
  }, [active, ms])
}

/** Level audio AI yang diputar di layar OBS (diteruskan server), dibaca per frame. */
function useRelayedLevel(getLevel: () => number | null, active: boolean) {
  const [level, setLevel] = useState(0)
  useEffect(() => {
    if (!active) {
      setLevel(0)
      return
    }
    let raf = 0
    let last = -1
    const tick = () => {
      const lv = Math.round((getLevel() ?? 0) * 20) / 20
      if (lv !== last) setLevel((last = lv))
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [getLevel, active])
  return level
}

export function PrompterPage() {
  const live = useLiveSession('prompter')
  const { snapshot: snap, transcript, showClock, lastTopicChange, lastNudge, send } = live
  const [partial, setPartial] = useState('')
  const [message, setMessage] = useState('')
  const lastPartialSent = useRef(0)
  const onAir = snap.state === 'live' || snap.state === 'paused'
  const paused = snap.state === 'paused'
  const isModeA = snap.mode === 'A'
  const personas = snap.personas ?? []
  const ai = personas.find((p) => p.id === snap.ai_persona) ?? personas[0]
  const speakingAi = personas.find((p) => p.id === live.speaking)
  const thinkingAi = personas.find((p) => p.id === snap.thinking) ?? (snap.busy ? ai : undefined)
  const aiBusy = !!speakingAi || !!thinkingAi || !!snap.busy
  const shouldListen = isModeA && snap.state === 'live' && !aiBusy

  useTicker(onAir) // band "Pindah topik" berakhir sendiri setelah beberapa detik
  const clock = useShowClock(showClock)

  // ── Mic hands-free ──────────────────────────────────────────────────────
  const sendTurn = async (text: string, sttMs: number, speechMs = 0) => {
    setPartial('')
    send('stt_partial', { text: '', final: true })
    try {
      await api.pttTurn(text, sttMs, speechMs)
      setMessage('')
    } catch (e) {
      setMessage(e instanceof ApiError ? e.message : String(e))
    }
  }
  const stt = usePushToTalk({
    onPartial: (text) => {
      setPartial(text)
      const now = performance.now()
      if (now - lastPartialSent.current > 300) {
        lastPartialSent.current = now
        send('stt_partial', { text })
      }
    },
    onFinal: (text, sttMs, speechMs) => void sendTurn(text, sttMs, speechMs),
    autoSendSilenceMs: AUTO_SEND_SILENCE_MS,
    keepAlive: shouldListen,
  })
  const { start: startMic, cancel: cancelMic, listening } = stt
  useEffect(() => {
    if (!speechSupported) return
    if (shouldListen && !listening) startMic()
    // Giliran ketat: AI mikir/bicara, jeda, atau selesai → mic dijeda (ucapan yang belum selesai tetap dikirim).
    else if (!shouldListen && listening && !partial) cancelMic()
  }, [shouldListen, listening, partial, startMic, cancelMic])
  useEffect(() => {
    send('stt_partial', { text: '', active: listening })
  }, [listening, send])

  // Mic dipantau saat giliran penyiar (mode A live) dan di layar tunggu, supaya mic bisa dicek sebelum live.
  const mic = useMicMonitor((isModeA && snap.state === 'live') || !onAir)
  const micDown = isModeA && onAir && (mic.down || MIC_ERROR_CODES.has(stt.errorCode))
  const aiLevel = useRelayedLevel(live.level, !!speakingAi)
  // Konsol menampilkan peringatan merah "Mikrofon studio tidak terdengar" dari laporan ini (HANDOFF §2).
  const micReason = micDown ? mic.reason || stt.errorCode || 'stt' : ''
  useEffect(() => {
    send('mic_state', { down: !!micReason, reason: micReason })
  }, [micReason, send, live.connected])

  const next = useCallback(async () => {
    try {
      await api.control('next')
    } catch (e) {
      setMessage(e instanceof ApiError ? e.message : String(e))
    }
  }, [])

  // N = Topik selanjutnya (opsional). Tidak ada pintasan lain: penyiar tidak perlu menekan apa pun.
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (!onAir || !isModeA || e.ctrlKey || e.metaKey || e.altKey || e.repeat) return
      if (e.key.toLowerCase() === 'n') void next()
    }
    window.addEventListener('keydown', down)
    return () => window.removeEventListener('keydown', down)
  }, [onAir, isModeA, next])

  useEffect(() => {
    document.title = 'Prompter · Penyiar AI HITS'
  }, [])

  // ── Sebelum dan sesudah siaran ──────────────────────────────────────────
  if (!onAir) {
    return (
      <div className="pr pr--wait">
        <img src="/logo-hits.png" alt="HITS Unikom Radio 103.9 FM" className="pr-wait__logo" />
        <h1 className="pr-wait__title">{snap.state === 'ended' ? 'Siaran selesai' : 'Menunggu produser…'}</h1>
        <p className="pr-wait__hint">
          {snap.state === 'ended'
            ? 'Terima kasih! Layar ini siap untuk siaran berikutnya.'
            : 'Layar ini otomatis berganti saat siaran dimulai dari konsol. Kamu tidak perlu menekan apa pun.'}
        </p>
        {!speechSupported && <p className="pr-wait__warn">Buka prompter di Google Chrome supaya mikrofon bisa mendengar suaramu.</p>}
        <div className="pr-wait__mic" aria-live="polite">
          {mic.down ? <IconMicOff size={36} /> : <LevelBars level={mic.level} height={40} />}
          <span>
            <strong>{mic.down ? (mic.reason === 'denied' ? 'Izin mikrofon belum diberikan' : 'Mikrofon tidak terdengar') : `Mikrofon: ${mic.device || 'bawaan Chrome'}`}</strong>
            <span>
              {mic.reason === 'denied'
                ? 'Izinkan mikrofon lewat ikon di ujung kiri bilah alamat Chrome, lalu muat ulang halaman ini.'
                : 'Coba bicara: bar ikut bergerak. Ganti mic lewat setelan suara Chrome atau sistem operasi.'}
            </span>
          </span>
        </div>
        {!live.connected && <p className="pr-wait__warn">Belum tersambung ke server…</p>}
      </div>
    )
  }

  // ── Isi segmen ──────────────────────────────────────────────────────────
  const rundown = snap.rundown
  const topics = rundown?.topics ?? []
  const ti = snap.segment === 'topic' ? topics.findIndex((t) => t.id === snap.topic?.id) : -1
  const topic = ti >= 0 ? topics[ti] : null
  const nextTopic = ti >= 0 ? topics[ti + 1] : snap.segment === 'opening' ? topics[0] : undefined
  const chip = topic ? `Topik ${ti + 1} dari ${topics.length}` : snap.segment === 'closing' ? 'Closing' : 'Opening'
  const title = topic?.judul ?? (snap.segment === 'closing' ? 'Closing' : 'Opening')
  const box = topic
    ? { label: 'TANYA PENONTON', text: shout(topic.pertanyaan_penonton) }
    : snap.segment === 'closing'
      ? { label: 'AJAKAN', text: shout(rundown?.closing.ajakan ?? '') }
      : { label: 'KALIMAT PEMBUKA', text: shout(rundown?.opening.hook ?? '') }
  const points = snap.topic_points ?? []
  // Poin aktif dari server; hanya bila server tidak menandai, pakai poin pertama yang belum dibahas.
  // Tepat setelah pindah topik, poin dari server belum tiba: tampilkan poin materi, mulai dari yang pertama.
  const pointList = points.length ? points : (topic?.poin ?? []).map((p) => ({ ...p, covered: false, current: undefined as boolean | undefined }))
  const flagged = pointList.findIndex((p) => p.current)
  const currentIdx = topic ? (flagged >= 0 ? flagged : pointList.findIndex((p) => !p.covered)) : -1
  const items: { text: string; state: 'done' | 'now' | 'todo' }[] = topic
    ? pointList.map((p, i) => ({
        text: p.text,
        state: p.covered && i !== currentIdx ? 'done' : i === currentIdx ? 'now' : 'todo',
      }))
    : snap.segment === 'closing'
      ? rundown?.closing.rangkuman
        ? [{ text: rundown.closing.rangkuman, state: 'todo' }]
        : []
      : (rundown?.opening.poin ?? []).map((t) => ({ text: t, state: 'todo' as const }))

  // ── Jam ──────────────────────────────────────────────────────────────────
  const elapsed = clock?.elapsed ?? 0
  const segTarget = clock?.segTarget ?? 0
  const remaining = clock?.remaining ?? 0
  const rs = ringState(remaining)
  const nearEnd = rs !== 'normal'

  // ── Band status ─────────────────────────────────────────────────────────
  // Pindah lewat ucapan: band tampil selama jendela batal (sama dengan server); pindah lain 6 dtk.
  const switchMs = lastTopicChange?.topic.reason === 'voice' ? (lastTopicChange.topic.undo_s ?? 0) * 1000 : TOPIC_BAND_MS
  const recentSwitch = lastTopicChange && performance.now() - lastTopicChange.at < switchMs ? lastTopicChange : null
  const voiceSwitch = recentSwitch?.topic.reason === 'voice' ? recentSwitch.topic : null
  const band: Band = micDown
    ? { kind: 'mic-down' }
    : paused
      ? { kind: 'paused' }
      : recentSwitch
        ? { kind: 'switch', title: recentSwitch.topic.id ? `Lanjut ke ${chip.replace(/ dari \d+$/, '')}` : 'Masuk Closing' }
        : speakingAi
          ? { kind: 'ai-speak', name: speakingAi.name }
          : thinkingAi
            ? { kind: 'ai-think', name: thinkingAi.name }
            : isModeA
              ? { kind: 'turn' }
              : { kind: 'ai-between' }
  const lastHuman = [...transcript].reverse().find((t) => t.persona === 'human')?.text
  // Kode halus ditonjolkan selama giliran AI yang memuatnya masih diputar.
  const lastAiTurn = [...transcript].reverse().find((t) => t.persona !== 'human')?.turn
  const nudgeNow = lastNudge && lastNudge.turn === lastAiTurn && topic?.id === lastNudge.topic_id ? lastNudge : null

  return (
    <div className="pr">
      <section className={`pr-band pr-band--${band.kind}`} aria-live="polite" role={band.kind === 'mic-down' ? 'alert' : undefined}>
        <div className="pr-band__text">
          {band.kind === 'turn' && (
            <>
              <h1>Giliranmu</h1>
              <p>Ngomong aja. {ai?.name ?? 'AI'} jawab begitu kamu jeda.</p>
              {partial && <p className="pr-band__quote">“{partial}”</p>}
            </>
          )}
          {band.kind === 'ai-speak' && (
            <>
              <h1>{band.name} bicara</h1>
              <p>{isModeA ? 'Tunggu sampai selesai. Mic kamu dijeda.' : 'Siaran AI + AI berjalan sendiri.'}</p>
              {nudgeNow && (
                <div className="pr-nudge">
                  <span className="pr-nudge__label">Kode pindah topik</span>
                  <p>“{lastSentence(nudgeNow.text)}”</p>
                </div>
              )}
            </>
          )}
          {band.kind === 'ai-think' && (
            <>
              <h1>{band.name} mikir</h1>
              <p>{isModeA ? 'Sebentar, jawaban sedang disiapkan. Mic kamu dijeda.' : 'Giliran berikutnya sedang disiapkan.'}</p>
              {isModeA && lastHuman && <p className="pr-band__quote">Kamu: “{lastHuman}”</p>}
            </>
          )}
          {band.kind === 'switch' && (
            <>
              <h1>{band.title}</h1>
              {voiceSwitch?.said ? (
                <p>Dari ucapanmu: “{voiceSwitch.said}”</p>
              ) : (
                <p>{snap.topic?.judul && snap.segment === 'topic' ? snap.topic.judul : 'Saatnya merangkum obrolan.'}</p>
              )}
            </>
          )}
          {band.kind === 'mic-down' && (
            <>
              <h1>Mic tidak terdengar</h1>
              <p>{mic.reason === 'denied' || stt.errorCode === 'not-allowed' ? 'Izin mikrofon di browser ini belum diberikan. Minta produser memeriksanya.' : 'Tunggu sebentar, produser sedang memeriksa mixer.'}</p>
              <p>{ai?.name ?? 'AI'} diam dulu sampai suaramu terdengar lagi.</p>
            </>
          )}
          {band.kind === 'ai-between' && (
            <>
              <h1>AI + AI</h1>
              <p>Siaran berjalan sendiri. Giliran berikutnya segera.</p>
            </>
          )}
          {band.kind === 'paused' && (
            <>
              <h1>Siaran dijeda</h1>
              <p>Tunggu produser melanjutkan siaran.</p>
            </>
          )}
        </div>
        <div className="pr-band__side">
          {band.kind === 'turn' && <LevelBars level={mic.level} height={160} className="pr-bars" />}
          {band.kind === 'ai-speak' && <LevelBars level={aiLevel} height={160} className="pr-bars" />}
          {band.kind === 'ai-think' && (
            <span className="pr-dots" aria-hidden="true">
              <span />
              <span />
              <span />
            </span>
          )}
          {band.kind === 'mic-down' && <IconMicOff size={140} />}
          {band.kind === 'switch' && voiceSwitch && (
            <button
              type="button"
              className="pr-undo"
              onClick={() => void api.undoTopic().catch(() => setMessage('Waktu batal sudah lewat. Pakai Topik selanjutnya bila perlu.'))}
            >
              Batal, kembali ke {voiceSwitch.from}
            </button>
          )}
        </div>
      </section>

      <section className="pr-body">
        <div className="pr-main">
          <span className="pr-chip">{chip}</span>
          <h2 className="pr-title">{title}</h2>
          {box.text && (
            <div className="pr-box">
              <span className="pr-box__label">{box.label}</span>
              <span className="pr-box__text">{box.text}</span>
            </div>
          )}
          {items.length > 0 && (
            <>
              <span className="pr-label">{topic ? 'Bahan obrolan' : snap.segment === 'closing' ? 'Rangkuman' : 'Pembukaan'}</span>
              <ul className="pr-items">
                {items.map((it, i) => (
                  <li key={i} className={`pr-item pr-item--${it.state}`}>
                    {it.state === 'done' ? (
                      <span className="pr-item__mark" role="img" aria-label="Sudah dibahas">
                        <IconCheck size={36} />
                      </span>
                    ) : (
                      <span className="pr-item__mark pr-item__dot" role="img" aria-label={it.state === 'now' ? 'Sedang dibahas' : 'Belum dibahas'} />
                    )}
                    {it.text}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>

        <aside className="pr-side">
          <div className="pr-total">
            Siaran {fmtClock(elapsed)} / {fmtClock(clock?.target ?? 0)}
            {paused && ' · dijeda'}
          </div>
          {segTarget > 0 && (
            <div className="pr-ring">
              <Ring remainingS={remaining} limitS={segTarget} size={240} label={paused ? 'dijeda' : rs === 'normal' ? 'tersisa' : undefined} />
            </div>
          )}
          {isModeA && snap.segment !== 'closing' && (
            <div className="pr-next">
              {nearEnd && topic?.transisi ? (
                <>
                  <span className="pr-next__label">Siap pindah? Ucapkan:</span>
                  <span className="pr-next__say">{shout(topic.transisi)}</span>
                </>
              ) : (
                <span className="pr-next__label">Berikutnya: {nextTopic?.judul ?? 'Closing'}</span>
              )}
              <button type="button" className="pr-next__btn" onClick={() => void next()}>
                {nearEnd ? 'atau klik Topik selanjutnya' : 'Topik selanjutnya'} <kbd>N</kbd>
              </button>
            </div>
          )}
          {message && (
            <p className="pr-msg" role="alert">
              {message}
            </p>
          )}
        </aside>
      </section>
    </div>
  )
}
