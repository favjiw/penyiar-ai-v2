import type { ShowSnapshot } from './live/types'
import type { TtsStatus } from './live/tts'
import type { Blocker, GenerateRequest, GenerateResponse, RegenerateResponse } from './types'

export class ApiError extends Error {
  constructor(message: string, readonly status: number, readonly issues: string[] = []) {
    super(message)
  }
}

/** Sesi login habis di tengah jalan (mis. dicabut admin): muat ulang, halaman login yang muncul. */
function sessionExpired(path: string) {
  if (!path.startsWith('/api/auth/')) window.location.reload()
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  const body = await res.json().catch(() => ({}))
  if (res.status === 401) sessionExpired(path)
  if (!res.ok) {
    // FastAPI: detail berupa string, atau daftar galat validasi (422)
    const detail = Array.isArray(body.detail)
      ? body.detail.map((d: { msg: string }) => d.msg).join('; ')
      : body.detail ?? res.statusText
    throw new ApiError(detail, res.status, body.issues ?? [])
  }
  return body as T
}

const post = <T>(path: string, data?: unknown) =>
  request<T>(path, { method: 'POST', body: data === undefined ? undefined : JSON.stringify(data) })

export interface VoiceOption {
  id: string
  provider: 'elevenlabs' | 'edge'
  name: string
  gender: 'male' | 'female'
  notes: string
}

export interface VoiceCatalog {
  provider: string
  voices: VoiceOption[]
  current: Record<string, string>
}

export interface ReadinessService {
  kind: 'llm' | 'tts' | 'stt'
  label: string
  percent_left: number | null
  minutes_left: number | null
  unlimited: boolean
  /** Otak AI hanya memakai model berbayar per panggilan (tanpa kuota harian). */
  paid?: boolean
}

export interface Readiness {
  services: ReadinessService[]
  minutes_safe: number | null
  /** Layanan berkuota yang sisanya belum bisa dibaca (mis. Suara AI tanpa izin baca kredit). */
  unknown?: string[] // server lama belum mengirim
  target_minutes: number
  fallbacks: string[]
  rates_source: 'log' | 'bawaan'
  estimated: boolean
}

export type Role = 'penyiar' | 'operator' | 'admin'

export interface AuthUser {
  id: number
  username: string
  display_name: string
  role: Role
  active: boolean
}

export interface UserRow extends AuthUser {
  created_at: string
  last_login_at: string | null
}

export interface AdminField {
  key: string
  label: string
  kind: 'text' | 'secret' | 'number' | 'bool' | 'choice' | 'face'
  help: string
  choices: string[]
  source: 'admin' | 'env'
  value?: string // bukan rahasia
  is_set?: boolean // rahasia: sudah terisi?
  masked?: string // rahasia: "••••" + 4 karakter terakhir
}

export interface AdminConfig {
  groups: { id: string; label: string; fields: AdminField[] }[]
  secrets_enabled: boolean
  pending: boolean
  live: boolean
  changed?: string[]
  applied?: boolean
  apply_error?: string | null
}

export interface AdminVoice {
  id: string
  provider: 'elevenlabs' | 'edge'
  name: string
  gender: 'male' | 'female'
  notes: string
}

export interface AdminFace {
  id: string
  name: string
  notes: string
}

export type TestService = 'gemini' | 'compat' | 'elevenlabs' | 'simli'

export interface AdminPersona {
  id: string
  name: string
  gender: 'male' | 'female'
  voices: Record<string, string>
  speaking_style: string
  catchphrases: string[]
  topic_limits: string[]
  background_facts: string[]
  do_not: string[]
  opinions: string[]
  filler_bank: string
}

export interface AdminPromptRow {
  name: string
  version: string
  active: boolean
  created_at: string
  created_by: string | null
  placeholders: string[]
}

export interface AdminSnippet {
  key: string
  text: string
  placeholders: string[]
  updated_at: string
  updated_by: string | null
}

export interface AdminSupervisor {
  banned: { word: string; category: string }[]
  fallbacks: { id: number; persona: string; kind: string; text: string }[]
  kinds: string[]
}

export const adminApi = {
  config: () => request<AdminConfig>('/api/admin/config'),
  /** null = hapus timpaan (kembali ke .env); kunci rahasia "" = biarkan. */
  saveConfig: (values: Record<string, string | null>) => request<AdminConfig>('/api/admin/config', { method: 'PUT', body: JSON.stringify({ values }) }),
  test: (service: TestService) => post<{ ok: boolean; message: string }>(`/api/admin/test/${service}`),
  voices: () => request<AdminVoice[]>('/api/admin/voices'),
  addVoice: (v: Omit<AdminVoice, 'notes'> & { notes?: string }) => post<{ voice: AdminVoice; warning: string | null }>('/api/admin/voices', v),
  patchVoice: (id: string, patch: Partial<Pick<AdminVoice, 'name' | 'gender' | 'notes'>>) =>
    request<AdminVoice>(`/api/admin/voices/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  deleteVoice: (id: string) => request<{ ok: boolean }>(`/api/admin/voices/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  faces: () => request<AdminFace[]>('/api/admin/faces'),
  addFace: (f: { id: string; name: string; notes?: string }) => post<AdminFace>('/api/admin/faces', f),
  deleteFace: (id: string) => request<{ ok: boolean }>(`/api/admin/faces/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  personas: () => request<AdminPersona[]>('/api/admin/personas'),
  savePersona: (p: AdminPersona) => request<AdminPersona>(`/api/admin/personas/${p.id}`, { method: 'PUT', body: JSON.stringify(p) }),
  prompts: () => request<AdminPromptRow[]>('/api/admin/prompts'),
  promptBody: (name: string, version: string) => request<{ body: string }>(`/api/admin/prompts/${name}/${encodeURIComponent(version)}`),
  addPromptVersion: (name: string, version: string, body: string, activate: boolean) =>
    post<{ ok: boolean }>(`/api/admin/prompts/${name}`, { version, body, activate }),
  activatePrompt: (name: string, version: string) => post<{ ok: boolean }>(`/api/admin/prompts/${name}/${encodeURIComponent(version)}/activate`),
  snippets: () => request<AdminSnippet[]>('/api/admin/snippets'),
  saveSnippet: (key: string, text: string) => request<{ ok: boolean }>(`/api/admin/snippets/${encodeURIComponent(key)}`, { method: 'PUT', body: JSON.stringify({ text }) }),
  supervisor: () => request<AdminSupervisor>('/api/admin/supervisor'),
  addBanned: (word: string, category: string) => post<{ ok: boolean }>('/api/admin/supervisor/banned', { word, category }),
  deleteBanned: (word: string) => request<{ ok: boolean }>(`/api/admin/supervisor/banned/${encodeURIComponent(word)}`, { method: 'DELETE' }),
  addFallback: (persona: string, kind: string, text: string) => post<{ ok: boolean }>('/api/admin/supervisor/fallbacks', { persona, kind, text }),
  deleteFallback: (id: number) => request<{ ok: boolean }>(`/api/admin/supervisor/fallbacks/${id}`, { method: 'DELETE' }),
}

export const api = {
  me:() => request<{ user: AuthUser; auth_required: boolean }>('/api/auth/me'),
  login: (username: string, password: string) => post<{ user: AuthUser }>('/api/auth/login', { username, password }),
  logout: () => post<{ ok: boolean }>('/api/auth/logout'),
  changePassword: (current: string, next: string) => post<{ ok: boolean }>('/api/auth/password', { current, new: next }),
  users: () => request<UserRow[]>('/api/users'),
  createUser: (u: { username: string; password: string; role: Role; display_name: string }) => post<AuthUser>('/api/users', u),
  updateUser: (id: number, patch: Partial<{ role: Role; active: boolean; display_name: string; password: string }>) =>
    request<AuthUser>(`/api/users/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  readiness: (mode: 'A' | 'B', target_minutes: number) => request<Readiness>(`/api/readiness?mode=${mode}&target_minutes=${target_minutes}`),
  voices: () => request<VoiceCatalog>('/api/voices'),
  generate: (req: GenerateRequest) => post<GenerateResponse>('/api/blocker/generate', req),
  /** Buat ulang satu varian (boleh belum disimpan); hasilnya juga belum disimpan. */
  regenerate: (blocker: Blocker, hindari: string[]) => post<RegenerateResponse>('/api/blocker/regenerate', { blocker, hindari }),
  /** Simpan varian hasil generate yang dipilih operator (generate sendiri tidak menyimpan). Aman diulang. */
  create: (b: Blocker) => post<Blocker>('/api/blockers', b),
  /** Simpan editan; materi yang belum pernah disimpan dibuat dulu (mengedit = memilih untuk disimpan). */
  save: async (b: Blocker): Promise<Blocker> => {
    try {
      return await request<Blocker>(`/api/blocker/${b.id}`, { method: 'PUT', body: JSON.stringify(b) })
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) return post<Blocker>('/api/blockers', b)
      throw e
    }
  },
  lock: (id: string) => post<Blocker>(`/api/blocker/${id}/lock`),
  newVersion: (id: string) => post<Blocker>(`/api/blocker/${id}/version`),
  list: () => request<Blocker[]>('/api/blockers'),
  startShow: (blocker_id: string, mode: 'A' | 'B' = 'B', opts: { ai_persona?: string; human_name?: string; voices?: Record<string, string> } = {}) =>
    post<ShowSnapshot>('/api/show/start', { blocker_id, mode, ...opts }),
  pttTurn: (text: string, stt_ms: number, speech_ms = 0) =>
    post<{ filler?: string | null; responder?: string }>('/api/ptt/turn', { text, stt_ms, speech_ms }),
  /** Batalkan pindah topik dari ucapan penyiar (mode A); 409 bila jendela batal sudah lewat. */
  undoTopic: () => post<ShowSnapshot>('/api/show/undo-topic'),
  control: (action: 'pause' | 'resume' | 'next' | 'stop') => post<ShowSnapshot>(`/api/show/${action}`),
  voiceSample: (persona: string, voice_id = '') =>
    post<{ audio_url: string; voice: string; provider: string; fallback: boolean }>('/api/voices/sample', { persona, voice_id }),
  precheck: (voices: Record<string, string> = {}, mode: 'A' | 'B' = 'B', target_minutes = 60) =>
    post<{ models_ok: boolean; tts_ok: boolean; tts_error?: string; tts_warmup_ms?: Record<string, number>; models: Record<string, string>; readiness?: Readiness }>(
      '/api/precheck',
      { voices, mode, target_minutes },
    ),
  health: () => request<{ llm_mode: string; tts_mode: string; models: Record<string, string>; tts?: TtsStatus }>('/api/health'),
  simliToken: (persona: string) => post<{ session_token: string }>('/api/simli/token', { persona }),
}
