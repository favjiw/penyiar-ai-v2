// Event /ws/session (PRD §6.3), cermin backend/app/show/engine.py.

import type { TtsStatus } from './tts'

export type ShowStateName = 'idle' | 'live' | 'paused' | 'ended'

export interface TranscriptEntry {
  turn: number
  persona: string
  name: string
  text: string
  emotion: string
  segment: 'opening' | 'topic' | 'closing'
  topic_id: string | null
  supervisor: 'forward' | 'regenerate' | 'fallback'
  tts_provider: string
  gap_ms: number
  ts?: number // detik epoch, dari server
}

export interface TurnEvent extends TranscriptEntry {
  audio_url: string | null
  duration_s: number
  playback_id: string
  parts?: number // mode A: jumlah bagian kalimat; bagian 2..n datang lewat audio_part
}

export interface TopicPoint {
  id: string
  text: string
  covered: boolean
  current?: boolean // poin yang sedang dibahas (batas waktu per poin)
}

/** Jam satu obrolan (poin): `played_s` dari audio yang sudah diputar; `running` = ada giliran yang sedang diputar. */
export type PointClock =
  | { active: false; limit_s?: number }
  | { active: true; topic_id: string; point_id: string; idx: number; total: number; text: string; limit_s: number; played_s: number; running: boolean; ts: number }

export interface AlertEvent {
  id: string
  level: 'red' | 'yellow' | 'blue'
  code: string
  title: string
  message: string
  /** Pesan mentah (nama vendor/model) untuk Detail teknis. */
  detail: string
  stage: string
  turn: number
  at: number
}

/** Jam siaran dari server (PRD v2.7): waktu aktif tanpa jeda; klien menghitung maju selama `running`. */
export interface ShowClock {
  elapsed_s: number
  target_s: number
  segment_elapsed_s: number
  segment_target_s: number
  running: boolean
}

export interface OnAirTopic {
  id: string | null
  judul: string
  pertanyaan_penonton: string
}

export interface ShowrunnerDecision {
  advisory?: boolean // mode A: saran untuk penyiar, tidak memindah topik
  turn: number
  topic_id: string
  points_covered: string[]
  saturation: number
  decision: 'continue' | 'steer' | 'transition' | 'close'
  aksi?: 'lanjut' | 'pindah_topik' | 'tutup'
  steer_hint: string
  next_speaker: string | null
  reason: string
  policy: string
  forced: boolean
  latency_ms: number
}

export interface SupervisorEvent {
  turn: number
  persona: string
  mode: string
  action: 'forward' | 'regenerate' | 'fallback'
  checks: Record<string, string>
  rule_hits: string[]
  evidence: string
  regenerations: number
  timed_out: boolean
}

/** Blocker terkunci apa adanya, dikirim di snapshot untuk prompter penyiar manusia. */
export interface Rundown {
  opening: { hook: string; poin: string[] }
  topics: { id: string; judul: string; menit?: number; sudut_pandang: string; poin: { id: string; text: string }[]; pertanyaan_penonton: string; transisi: string }[]
  closing: { rangkuman: string; ajakan: string }
}

export interface ShowSnapshot {
  state: ShowStateName
  session_id?: string
  mode?: string
  blocker?: { id: string; tema: string; variant_label: string; topics: string[] }
  rundown?: Rundown
  personas?: { id: string; name: string }[]
  segment?: 'opening' | 'topic' | 'closing'
  topic?: OnAirTopic | null
  speaking?: string | null
  turn?: number
  elapsed_s?: number
  transcript?: TranscriptEntry[]
  showrunner?: ShowrunnerDecision | null
  coverage?: Record<string, { covered: string[]; total: number }>
  tts?: TtsStatus
  error?: string | null
  // mode A
  human?: { id: string; name: string }
  ai_persona?: string
  busy?: boolean
  thinking?: string | null // id AI yang sedang menyiapkan jawaban (mode A)
  participants?: { id: string; name: string; kind: 'human' | 'ai' }[]
  topic_points?: TopicPoint[]
  point_clock?: PointClock
  show_clock?: ShowClock
  /** Perkiraan menit suara AI tersisa (null = tidak diketahui). */
  tts_minutes_left?: number | null
  tts_quota_low?: boolean
  fillers_ready?: number
}

export interface OutputStatus {
  is_audio_owner: boolean
  audio_owner_role: string | null
  audio_blocked: boolean
  audio_ready?: boolean
  clients: Record<string, number>
  /** Status mic penyiar dari prompter (mode A); null bila belum ada laporan. */
  mic?: { down: boolean; reason: string } | null
}
