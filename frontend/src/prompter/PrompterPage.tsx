import { useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../api'
import { useLiveSession } from '../live/useLiveSession'
import './prompter.css'
import { speechSupported, usePushToTalk } from './usePushToTalk'

const isTyping = (el: Element | null) => !!el && ['INPUT', 'TEXTAREA'].includes(el.tagName)

/**
 * Prompter mode A (FR-11): blocker layar besar untuk penyiar manusia, push-to-talk
 * (FR-7), dan saran Showrunner. Terbaca dari 1–1,5 m; semua kontrol punya pintasan:
 * tahan Spasi = bicara, Esc = batal, N = next topik.
 */
export function PrompterPage() {
  const live = useLiveSession('prompter')
  const { snapshot: snap, transcript, showrunner } = live
  const [toggleMode, setToggleMode] = useState(false)
  const [partial, setPartial] = useState('')
  const [typed, setTyped] = useState('')
  const [message, setMessage] = useState('')
  const lastPartialSent = useRef(0)
  const onAir = snap.state === 'live' || snap.state === 'paused'
  const ai = snap.personas?.[0]
  const advice = [...showrunner].reverse().find((d) => d.advisory)

  const sendTurn = async (text: string, sttMs: number) => {
    setPartial('')
    live.send('stt_partial', { text: '', final: true })
    try {
      await api.pttTurn(text, sttMs)
      setMessage('')
    } catch (e) {
      setMessage(e instanceof ApiError ? e.message : String(e))
    }
  }

  const ptt = usePushToTalk({
    onPartial: (text) => {
      setPartial(text)
      const now = performance.now()
      if (now - lastPartialSent.current > 300) {
        lastPartialSent.current = now
        live.send('stt_partial', { text })
      }
    },
    onFinal: (text, sttMs) => void sendTurn(text, sttMs),
  })

  // Konsol menyalakan indikator mikrofon selama tombol bicara ditahan.
  const { send } = live
  useEffect(() => {
    send('stt_partial', { text: '', active: ptt.listening })
  }, [ptt.listening, send])

  const next = async () => {
    try {
      await api.control('next')
    } catch (e) {
      setMessage(e instanceof ApiError ? e.message : String(e))
    }
  }

  // Pintasan keyboard (FR-11)
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (!onAir || isTyping(document.activeElement)) return
      if (e.code === 'Space') {
        e.preventDefault()
        if (e.repeat) return
        if (toggleMode && ptt.listening) ptt.stop()
        else ptt.start()
      } else if (e.key === 'Escape') ptt.cancel()
      else if (e.key.toLowerCase() === 'n') void next()
    }
    const up = (e: KeyboardEvent) => {
      if (e.code === 'Space' && !toggleMode && !isTyping(document.activeElement)) {
        e.preventDefault()
        ptt.stop()
      }
    }
    window.addEventListener('keydown', down)
    window.addEventListener('keyup', up)
    return () => {
      window.removeEventListener('keydown', down)
      window.removeEventListener('keyup', up)
    }
  })

  useEffect(() => {
    document.title = 'Prompter · Penyiar AI'
  }, [])

  if (!onAir) {
    return (
      <div className="prompter idle">
        <h1>Prompter</h1>
        <p>{snap.state === 'ended' ? 'Siaran selesai.' : 'Menunggu operator memulai siaran mode A dari konsol.'}</p>
        {!live.connected && <p className="warn">Belum tersambung ke server…</p>}
      </div>
    )
  }
  if (snap.mode !== 'A') {
    return (
      <div className="prompter idle">
        <h1>Prompter</h1>
        <p>Siaran yang berjalan adalah mode B (AI + AI); prompter dipakai di mode A.</p>
      </div>
    )
  }

  const segment = snap.segment === 'topic' ? snap.topic?.judul : snap.segment === 'closing' ? 'Closing' : 'Opening'
  const points = snap.topic_points ?? []
  const covered = points.filter((p) => p.covered).length
  const recent = transcript.slice(-4)
  const aiSpeaking = live.speaking === snap.ai_persona || snap.busy

  return (
    <div className="prompter">
      <header>
        <span className={`state ${snap.state}`}>{snap.state === 'paused' ? 'PAUSE' : '● LIVE'}</span>
        <span className="tema">{snap.blocker?.tema}</span>
        <span className="with">bersama {ai?.name} (AI)</span>
        <button className="next" onClick={() => void next()}>
          Next topik <kbd>N</kbd>
        </button>
      </header>

      <section className="topic">
        <div className="segment">{segment}</div>
        {snap.topic?.pertanyaan_penonton && <div className="question">❓ {snap.topic.pertanyaan_penonton}</div>}
        {points.length > 0 && (
          <ul className="points">
            {points.map((p) => (
              <li key={p.id} className={p.covered ? 'done' : ''}>
                <span className="check">{p.covered ? '✓' : '○'}</span> {p.text}
              </li>
            ))}
          </ul>
        )}
      </section>

      {advice && (
        <section className="advice">
          Poin tercakup {covered}/{points.length}
          {advice.steer_hint && <> · saran: {advice.steer_hint.replace(/^bahas t\d+p\d+: /, '').replace(/^sudut baru: /, '')}</>}
          {(advice.decision === 'transition' || advice.decision === 'close') && <strong> · siap pindah</strong>}
        </section>
      )}

      <section className="talk">
        {speechSupported ? (
          <button
            className={`ptt ${ptt.listening ? 'on' : ''}`}
            onPointerDown={() => (toggleMode && ptt.listening ? ptt.stop() : ptt.start())}
            onPointerUp={() => !toggleMode && ptt.stop()}
            onPointerLeave={() => !toggleMode && ptt.listening && ptt.stop()}
          >
            {ptt.listening ? 'Mendengarkan… lepas untuk kirim' : toggleMode ? 'Tekan untuk bicara' : 'Tahan untuk bicara'}
            <kbd>Spasi</kbd>
          </button>
        ) : (
          <form
            className="typed"
            onSubmit={(e) => {
              e.preventDefault()
              if (typed.trim()) void sendTurn(typed.trim(), 0)
              setTyped('')
            }}
          >
            <input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="Browser ini tanpa Web Speech: ketik ucapan lalu Enter" />
          </form>
        )}
        <label className="toggle">
          <input type="checkbox" checked={toggleMode} onChange={(e) => setToggleMode(e.target.checked)} /> tekan sekali mulai, tekan lagi selesai
        </label>
        <div className="partial">{partial || (aiSpeaking ? `${ai?.name} sedang menjawab…` : '')}</div>
        {(ptt.error || message) && <div className="warn">{ptt.error || message}</div>}
        {ptt.listening && <div className="hint">Esc = batal</div>}
      </section>

      <section className="recent">
        {recent.map((t) => (
          <div key={t.turn} className={t.persona === 'human' ? 'me' : 'ai'}>
            <b>{t.name}:</b> {t.text}
          </div>
        ))}
      </section>
    </div>
  )
}
