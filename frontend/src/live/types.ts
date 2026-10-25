// Event /ws/session (PRD §6.3), cermin backend/app/show/engine.py.

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
}

export interface TurnEvent extends TranscriptEntry {
  audio_url: string | null
  video_url?: string | null // avatar T2 (lip-sync MuseTalk) untuk bagian pertama
  duration_s: number
  playback_id: string
  parts?: number // mode A: jumlah bagian kalimat; bagian 2..n datang lewat audio_part
}

export interface TopicPoint {
  id: string
  text: string
  covered: boolean
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

export interface ShowSnapshot {
  state: ShowStateName
  session_id?: string
  mode?: string
  blocker?: { id: string; tema: string; variant_label: string; topics: string[] }
  personas?: { id: string; name: string }[]
  segment?: 'opening' | 'topic' | 'closing'
  topic?: OnAirTopic | null
  speaking?: string | null
  turn?: number
  elapsed_s?: number
  transcript?: TranscriptEntry[]
  showrunner?: ShowrunnerDecision | null
  coverage?: Record<string, { covered: string[]; total: number }>
  tts?: { primary: string; fallback: string | null; breaker_open: boolean; credits_used: number }
  error?: string | null
  // mode A
  human?: { id: string; name: string }
  ai_persona?: string
  busy?: boolean
  topic_points?: TopicPoint[]
  fillers_ready?: number
}

export interface OutputStatus {
  is_audio_owner: boolean
  audio_owner_role: string | null
  stage_connected: boolean
  audio_blocked: boolean
  clients: Record<string, number>
}
