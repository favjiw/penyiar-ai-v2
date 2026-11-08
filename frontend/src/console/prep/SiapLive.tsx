/**
 * Langkah 3 "Siap live" (mockup Main): format, durasi, nama penyiar, teman ngobrol AI + suara,
 * cek otomatis, dan satu-satunya tombol Mulai live di konsol.
 */
import { useEffect, useRef, useState } from 'react'
import { api, ApiError, type Readiness, type VoiceCatalog, type VoiceOption } from '../../api'
import { DURASI_PILIHAN, factCheckCount, materiIssues, materiSummary, planMinutes, type Durasi } from '../../lib/materi'
import { usePersisted } from '../../lib/usePersisted'
import type { LiveSession } from '../../live/useLiveSession'
import { openStageWindow } from '../../stage/openStageWindow'
import type { Blocker } from '../../types'
import { Button, IconAlert, IconCheck, IconPlay } from '../../ui'
import { readinessSummary } from './Readiness'

type Mode = 'A' | 'B'
type Persona = 'raka' | 'salsa'
const PERSONAS: { id: Persona; name: string; gender: 'male' | 'female' }[] = [
  { id: 'salsa', name: 'Salsa', gender: 'female' },
  { id: 'raka', name: 'Raka', gender: 'male' },
]
const PRECHECK_DEBOUNCE_MS = 800

const isMode = (v: unknown): v is Mode => v === 'A' || v === 'B'
const isPersona = (v: unknown): v is Persona => v === 'raka' || v === 'salsa'
const isDurasi = (v: unknown): v is Durasi => DURASI_PILIHAN.includes(v as Durasi)
const isStr = (v: unknown): v is string => typeof v === 'string'
const isVoiceMap = (v: unknown): v is Record<string, string> =>
  !!v && typeof v === 'object' && Object.values(v as object).every((x) => typeof x === 'string')

export function useDurasi() {
  return usePersisted<Durasi>('hits.durasi', 60, isDurasi)
}

export function useMode() {
  return usePersisted<Mode>('hits.mode', 'A', isMode)
}

interface Props {
  live: LiveSession
  mode: Mode
  onMode: (m: Mode) => void
  readiness: Readiness | null
  materi: Blocker | null
  durasi: Durasi
  onDurasi: (d: Durasi) => void
  onEdit: () => void
  onRegenerateForDuration: () => void
  generating: boolean
}

type Precheck = { state: 'idle' | 'running' } | { state: 'ok' } | { state: 'fail'; message: string; detail?: string }

export function SiapLive({ live, mode, onMode: setMode, readiness, materi, durasi, onDurasi, onEdit, onRegenerateForDuration, generating }: Props) {
  const { output } = live
  const [aiPersona, setAiPersona] = usePersisted<Persona>('hits.aiPersona', 'salsa', isPersona)
  const [hostName, setHostName] = usePersisted<string>('hits.hostName', '', isStr)
  const [voices, setVoices] = usePersisted<Record<string, string>>('hits.voices', {}, isVoiceMap)
  const [catalog, setCatalog] = useState<VoiceCatalog | null>(null)
  const [precheck, setPrecheck] = useState<Precheck>({ state: 'idle' })
  const [sample, setSample] = useState<{ persona: string; state: 'loading' | 'playing' | 'fallback' | 'error'; message?: string } | null>(null)
  const [confirmFacts, setConfirmFacts] = useState(false)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState('')
  const audioBusy = useRef(false) // contoh suara dan cek kesiapan sama-sama mengganti suara aktif di server
  const [audioBusyState, setAudioBusyState] = useState(false)
  const setBusyFlag = (v: boolean) => {
    audioBusy.current = v
    setAudioBusyState(v)
  }
  const sampleAudio = useRef<HTMLAudioElement | null>(null)

  useEffect(() => {
    api
      .voices()
      .then(setCatalog)
      .catch(() => setCatalog(null))
  }, [])

  // Suara tersimpan dari provider lain (mis. setelah TTS_PROVIDER diganti) dibuang supaya Mulai tidak 422.
  useEffect(() => {
    if (!catalog) return
    const valid = Object.fromEntries(
      Object.entries(voices).filter(([, id]) => catalog.voices.some((v) => v.id === id && v.provider === catalog.provider)),
    )
    if (Object.keys(valid).length !== Object.keys(voices).length) setVoices(valid)
  }, [catalog, voices, setVoices])

  const aiIds: Persona[] = mode === 'A' ? [aiPersona] : ['raka', 'salsa']
  // Tanpa katalog suara, id tersimpan tidak bisa divalidasi: pakai suara bawaan supaya Mulai tidak 422.
  const chosen = catalog ? Object.fromEntries(aiIds.filter((id) => voices[id]).map((id) => [id, voices[id]])) : {}
  const chosenKey = JSON.stringify(chosen)
  const defaultVoiceId = (id: string) => catalog?.current[id]?.split('|')[0] ?? ''
  const effectiveVoice = (id: string) => voices[id] || defaultVoiceId(id)
  const voiceName = (id: string) => catalog?.voices.find((v) => v.id === effectiveVoice(id))?.name ?? 'bawaan'
  const sameVoice = mode === 'B' && !!effectiveVoice('raka') && effectiveVoice('raka') === effectiveVoice('salsa')

  // Cek otak AI + suara AI: sekali saat materi siap, lalu lagi bila suara berubah (memanaskan suara terpilih).
  useEffect(() => {
    if (!materi || !catalog) return
    let cancelled = false
    let t = 0
    const run = async () => {
      if (cancelled) return
      if (audioBusy.current) {
        t = window.setTimeout(() => void run(), PRECHECK_DEBOUNCE_MS) // contoh suara sedang diputar: coba lagi
        return
      }
      setBusyFlag(true)
      setPrecheck({ state: 'running' })
      try {
        // Memanaskan suara terpilih (memakai kredit bila ElevenLabs): hanya saat materi/suara berubah, bukan mode/durasi.
        const r = await api.precheck(JSON.parse(chosenKey) as Record<string, string>)
        if (cancelled) return
        if (!r.models_ok) setPrecheck({ state: 'fail', message: 'Otak AI belum diatur', detail: 'Model LLM belum diisi di .env' })
        else if (!r.tts_ok) setPrecheck({ state: 'fail', message: 'Suara AI belum siap', detail: r.tts_error })
        else setPrecheck({ state: 'ok' })
      } catch (e) {
        if (!cancelled) setPrecheck({ state: 'fail', message: 'Cek kesiapan gagal', detail: e instanceof Error ? e.message : String(e) })
      } finally {
        setBusyFlag(false)
      }
    }
    t = window.setTimeout(() => void run(), PRECHECK_DEBOUNCE_MS)
    return () => {
      cancelled = true
      window.clearTimeout(t)
    }
  }, [materi?.id, catalog, chosenKey]) // eslint-disable-line react-hooks/exhaustive-deps

  const playSample = async (persona: Persona) => {
    if (audioBusy.current) return
    setBusyFlag(true)
    sampleAudio.current?.pause()
    setSample({ persona, state: 'loading' })
    try {
      const r = await api.voiceSample(persona, voices[persona] ?? '')
      const a = new Audio(r.audio_url)
      sampleAudio.current = a
      a.onended = () => setSample((s) => (s?.persona === persona && s.state === 'playing' ? null : s))
      await a.play()
      setSample(r.fallback ? { persona, state: 'fallback' } : { persona, state: 'playing' })
    } catch (e) {
      setSample({ persona, state: 'error', message: e instanceof Error ? e.message : String(e) })
    } finally {
      setBusyFlag(false)
    }
  }
  useEffect(() => () => sampleAudio.current?.pause(), [])

  const issues = materi ? materiIssues(materi) : []
  const facts = materi ? factCheckCount(materi) : 0
  const stageOpen = (output?.clients?.stage ?? 0) > 0
  const stageReady = stageOpen && !!output?.audio_ready
  const prompterOpen = (output?.clients?.prompter ?? 0) > 0
  const plan = materi ? planMinutes(materi) : 0
  const durMismatch = !!materi?.durasi_menit && materi.durasi_menit !== durasi
  // Jangan mulai selagi cek kesiapan/contoh suara mengganti suara di server (bisa bertabrakan dengan pilihan suara siaran).
  const canStart = !!materi && issues.length === 0 && (mode === 'B' || !!hostName.trim()) && !starting && live.connected && !audioBusyState

  const start = async () => {
    if (!materi || !canStart) return
    if (facts > 0 && !confirmFacts) {
      setConfirmFacts(true)
      return
    }
    setConfirmFacts(false)
    setError('')
    // Popup wajib dibuka langsung di dalam klik ini (sebelum await), supaya tidak diblokir browser.
    if (!stageOpen) openStageWindow(mode, aiPersona)
    if (mode === 'A' && !prompterOpen) window.open('/prompter', 'hits-prompter')
    setStarting(true)
    try {
      await api.startShow(
        materi.id,
        mode,
        mode === 'A' ? { ai_persona: aiPersona, human_name: hostName.trim(), voices: chosen } : { voices: chosen },
      )
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e))
    } finally {
      setStarting(false)
    }
  }

  const voiceOptions = (gender: 'male' | 'female'): VoiceOption[] =>
    catalog ? catalog.voices.filter((v) => v.provider === catalog.provider && v.gender === gender) : []

  return (
    <aside className="prep-step prep-siap" aria-labelledby="siap-title">
      <div className="prep-step__head">
        <span className="prep-step__n" aria-hidden="true">
          3
        </span>
        <h2 id="siap-title">Siap live</h2>
      </div>

      <div className="siap-materi">
        <span className="siap-label">Materi</span>
        {materi ? (
          <>
            <span className="siap-materi__title">{materi.variant_label}</span>
            <span className="siap-materi__meta">{materiSummary(materi)}</span>
          </>
        ) : (
          <span className="siap-materi__meta">Belum ada. Buat atau pilih materi dulu.</span>
        )}
      </div>

      <fieldset className="siap-field">
        <legend>Format siaran</legend>
        <div className="siap-modes">
          {(
            [
              ['A', 'Penyiar + AI', 'Kamu ngobrol bareng 1 AI'],
              ['B', 'AI + AI', 'Raka dan Salsa jalan sendiri'],
            ] as const
          ).map(([m, title, hint]) => (
            <label key={m} className={`siap-mode${mode === m ? ' is-on' : ''}`}>
              <input type="radio" name="mode" checked={mode === m} onChange={() => setMode(m)} />
              <span className="siap-mode__title">{title}</span>
              <span className="siap-mode__hint">{hint}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset className="siap-field">
        <legend>Durasi siaran</legend>
        <div className="siap-seg" role="radiogroup" aria-label="Durasi siaran">
          {DURASI_PILIHAN.map((d) => (
            <button key={d} type="button" role="radio" aria-checked={durasi === d} className={durasi === d ? 'is-on' : ''} onClick={() => onDurasi(d)}>
              {d} mnt
            </button>
          ))}
        </div>
        <span className="siap-hint">Jumlah topik menyesuaikan, ±9 menit per topik.</span>
      </fieldset>

      {mode === 'A' && (
        <label className="siap-field siap-name">
          <span className="siap-legend">Nama penyiar</span>
          <input value={hostName} maxLength={40} onChange={(e) => setHostName(e.target.value)} placeholder="Misal: Favian" />
          <span className="siap-hint">Diingat untuk siaran berikutnya</span>
        </label>
      )}

      <fieldset className="siap-field">
        <legend>{mode === 'A' ? 'Teman ngobrol AI' : 'Penyiar AI'}</legend>
        <div className="siap-ais" role={mode === 'A' ? 'radiogroup' : undefined} aria-label={mode === 'A' ? 'Teman ngobrol AI' : undefined}>
          {PERSONAS.map((p) => {
            const active = aiIds.includes(p.id)
            const opts = voiceOptions(p.gender)
            const s = sample?.persona === p.id ? sample : null
            return (
              <div key={p.id} className={`siap-ai${active ? ' is-on' : ''}`}>
                {mode === 'A' ? (
                  <label className="siap-ai__pick">
                    <input type="radio" name="ai" checked={aiPersona === p.id} onChange={() => setAiPersona(p.id)} />
                    <span className={`siap-ai__dot siap-ai__dot--${p.id}`} aria-hidden="true" />
                    <span className="siap-ai__name">{p.name}</span>
                  </label>
                ) : (
                  <span className="siap-ai__pick">
                    <span className={`siap-ai__dot siap-ai__dot--${p.id}`} aria-hidden="true" />
                    <span className="siap-ai__name">{p.name}</span>
                  </span>
                )}
                {active && (
                  <div className="siap-ai__voice">
                    <label className="siap-ai__select">
                      <span className="visually-hidden">Suara {p.name}</span>
                      <select value={voices[p.id] ?? ''} onChange={(e) => setVoices({ ...voices, [p.id]: e.target.value })} disabled={!catalog}>
                        <option value="">Suara bawaan{catalog ? ` (${catalog.voices.find((v) => v.id === defaultVoiceId(p.id))?.name ?? 'bawaan'})` : ''}</option>
                        {opts.map((v) => (
                          <option key={v.id} value={v.id}>
                            Suara: {v.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <Button
                      onClick={() => void playSample(p.id)}
                      disabled={audioBusyState}
                      aria-label={`Dengar suara ${voiceName(p.id)}`}
                      title={`Dengar suara ${voiceName(p.id)}`}
                      icon={<IconPlay size={18} />}
                    />
                  </div>
                )}
                {active && s && s.state !== 'playing' && (
                  <span className={`siap-hint${s.state === 'loading' ? '' : ' is-warn'}`} role="status">
                    {s.state === 'loading'
                      ? 'Menyiapkan contoh suara…'
                      : s.state === 'fallback'
                        ? 'Suara utama gagal; yang terdengar suara cadangan.'
                        : `Contoh suara gagal: ${s.message ?? ''}`}
                  </span>
                )}
              </div>
            )
          })}
        </div>
        {sameVoice && (
          <span className="siap-hint is-warn" role="status">
            Raka dan Salsa memakai suara yang sama.
          </span>
        )}
      </fieldset>

      <div className="siap-checks">
        <span className="siap-label">Cek otomatis</span>
        <ul>
          <Check ok={stageReady}>
            {!stageOpen ? 'Layar untuk OBS belum dibuka' : stageReady ? 'Layar untuk OBS siap bersuara' : 'Layar OBS terbuka, klik sekali di jendelanya'}
            {!stageReady && (
              <Button variant="link" onClick={() => openStageWindow(mode, aiPersona)}>
                {stageOpen ? 'Tampilkan' : 'Buka'}
              </Button>
            )}
          </Check>
          {mode === 'A' && (
            <Check ok={prompterOpen}>
              {prompterOpen ? 'Prompter terbuka' : 'Prompter belum dibuka'}
              {!prompterOpen && (
                <Button variant="link" onClick={() => window.open('/prompter', 'hits-prompter')}>
                  Buka
                </Button>
              )}
            </Check>
          )}
          <Check ok={precheck.state === 'ok'} pending={precheck.state === 'running' || precheck.state === 'idle'}>
            {precheck.state === 'ok'
              ? 'Otak AI dan suara AI siap'
              : precheck.state === 'fail'
                ? `${precheck.message}`
                : materi
                  ? 'Mengecek otak AI dan suara AI…'
                  : 'Otak AI dan suara AI dicek setelah materi dipilih'}
            {precheck.state === 'fail' && precheck.detail && <span className="siap-detail" title={precheck.detail}> · detail</span>}
          </Check>
          {readiness && (
            <Check ok={!readinessSummary(readiness, durasi).short && !readinessSummary(readiness, durasi).unknown}>
              Kesiapan siaran ·{' '}
              {readiness.minutes_safe == null
                ? readiness.unknown.length
                  ? `sisa kuota ${readiness.unknown.join(' dan ').toLowerCase()} belum diketahui`
                  : 'kuota tidak membatasi'
                : `±${readiness.minutes_safe} dari ${durasi} menit${readiness.minutes_safe < durasi && readiness.fallbacks.length ? ', lalu cadangan' : ''}${readiness.unknown.length ? ` (${readiness.unknown.join(', ').toLowerCase()} belum diketahui)` : ''}`}
            </Check>
          )}
          {materi && (
            <Check ok={issues.length === 0}>
              {issues.length === 0 ? 'Materi lengkap' : `Materi belum lengkap: ${issues.length} bagian`}
              {issues.length > 0 && (
                <Button variant="link" onClick={onEdit}>
                  Lengkapi
                </Button>
              )}
            </Check>
          )}
          {materi && durMismatch && (
            <Check ok={false}>
              Materi dibuat untuk {materi.durasi_menit} menit, rencana ±{plan} menit
              <Button variant="link" onClick={onRegenerateForDuration} disabled={generating}>
                {generating ? 'Membuat…' : `Buat untuk ${durasi} menit`}
              </Button>
            </Check>
          )}
        </ul>
      </div>

      {confirmFacts && (
        <div className="siap-confirm" role="alertdialog" aria-labelledby="facts-title">
          <span id="facts-title" className="siap-confirm__title">
            Ada {facts} bahan obrolan bertanda “Cek fakta”.
          </span>
          <span>Materi akan dikunci saat live dimulai. Sudah dicek?</span>
          <div className="siap-confirm__actions">
            <Button variant="ink" onClick={() => void start()}>
              Sudah, mulai live
            </Button>
            <Button
              onClick={() => {
                setConfirmFacts(false)
                onEdit()
              }}
            >
              Periksa dulu
            </Button>
          </div>
        </div>
      )}
      {error && (
        <div className="siap-error" role="alert">
          {error}
        </div>
      )}
      {!confirmFacts && (
        <Button variant="primary" size="xl" className="siap-start" onClick={() => void start()} disabled={!canStart}>
          <span className="siap-start__dot" aria-hidden="true" />
          {starting ? 'Memulai…' : 'Mulai live'}
        </Button>
      )}
      {!canStart && !starting && (
        <span className="siap-hint siap-why">
          {!live.connected
            ? 'Server belum tersambung.'
            : !materi
              ? 'Pilih materi dulu.'
              : issues.length
                ? 'Lengkapi materi dulu.'
                : mode === 'A' && !hostName.trim()
                  ? 'Isi nama penyiar dulu.'
                  : audioBusyState
                    ? 'Tunggu sebentar, suara AI sedang dicek.'
                    : ''}
        </span>
      )}
    </aside>
  )
}

function Check({ ok, pending, children }: { ok: boolean; pending?: boolean; children: React.ReactNode }) {
  return (
    <li className={`siap-check${ok ? ' is-ok' : pending ? ' is-pending' : ' is-warn'}`}>
      <span className="siap-check__icon" aria-hidden="true">
        {ok ? <IconCheck size={20} /> : <IconAlert size={20} />}
      </span>
      <span className="siap-check__text">{children}</span>
      <span className="visually-hidden">{ok ? '(siap)' : pending ? '(sedang dicek)' : '(perlu tindakan)'}</span>
    </li>
  )
}
