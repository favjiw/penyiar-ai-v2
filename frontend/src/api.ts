import type { ShowSnapshot } from './live/types'
import type { Blocker, GenerateRequest, GenerateResponse, RegenerateResponse } from './types'

export class ApiError extends Error {
  constructor(message: string, readonly status: number, readonly issues: string[] = []) {
    super(message)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  const body = await res.json().catch(() => ({}))
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

export const api = {
  generate: (req: GenerateRequest) => post<GenerateResponse>('/api/blocker/generate', req),
  regenerate: (id: string, hindari: string[]) => post<RegenerateResponse>(`/api/blocker/${id}/regenerate`, { hindari }),
  save: (b: Blocker) => request<Blocker>(`/api/blocker/${b.id}`, { method: 'PUT', body: JSON.stringify(b) }),
  lock: (id: string) => post<Blocker>(`/api/blocker/${id}/lock`),
  newVersion: (id: string) => post<Blocker>(`/api/blocker/${id}/version`),
  lockedList: () => request<Blocker[]>('/api/blockers?locked=true'),
  startShow: (blocker_id: string, mode: 'A' | 'B' = 'B', opts: { ai_persona?: string; human_name?: string } = {}) =>
    post<ShowSnapshot>('/api/show/start', { blocker_id, mode, ...opts }),
  pttTurn: (text: string, stt_ms: number) => post<{ filler?: string | null }>('/api/ptt/turn', { text, stt_ms }),
  control: (action: 'pause' | 'resume' | 'next' | 'stop') => post<ShowSnapshot>(`/api/show/${action}`),
  precheck: () =>
    post<{ models_ok: boolean; tts_ok: boolean; tts_error?: string; tts_warmup_ms?: Record<string, number>; models: Record<string, string> }>(
      '/api/precheck',
    ),
  health: () => request<{ llm_mode: string; tts_mode: string; models: Record<string, string> }>('/api/health'),
}
