// In production (Netlify), VITE_API_URL is baked in at build time.
// Locally, Vite proxies /api → localhost:8000 so no env var needed.
const _origin = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '')
const BASE = _origin ? `${_origin}/api` : '/api'

export interface RatingFactor {
  score: number
  rationale: string
  evidence: string[]
  solution_tam?: string
  industry_size?: string
  capital_efficiency?: number
  time_to_revenue?: number
  execution_accessibility?: number
}

export interface Ratings {
  market_size: RatingFactor
  pain_severity: RatingFactor
  solution_clarity: RatingFactor
  competitive_insight: RatingFactor
  monetization_potential: RatingFactor
  startup_viability: RatingFactor
  signal_authority: RatingFactor
}

export interface Classification {
  type: string
  moonshot_justification: string
  category: string
  industry: string
  go_to_market: string
  tech_stack: string[]
  tags: string[]
}

export interface ResearchData {
  pain_point_summary: string
  affected_segments: string[]
  market_size_estimate: string
  solution_tam_estimate: string
  tam_derivation: string
  market_growth_rate: string
  competitors: Array<{ name: string; weakness: string; url?: string }>
  monetization_models: string[]
  solution_hypothesis: string
  sources: string[]
  signal_sources: string[]
}

export interface DevilsAdvocate {
  bear_case: string
  key_risks: string[]
  biggest_threat: string
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

export interface UserInteraction {
  notes: string
  archived: boolean
  archived_at: string | null
  deeper_research_requested: boolean
  last_viewed: string | null
  chat: ChatMessage[]
}

export interface Opportunity {
  id: string
  title: string
  created_at: string
  updated_at: string
  composite_score: number
  ratings: Ratings
  classification: Classification
  research: ResearchData
  user: UserInteraction
  cycle_id: string
  devils_advocate?: DevilsAdvocate
}

export interface CycleStatus {
  cycle_running: boolean
  last_run: string | null
  last_summary: Record<string, unknown> | null
}

async function req<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

export const api = {
  getOpportunities: (params?: Record<string, string | number>) => {
    const qs = params ? '?' + new URLSearchParams(params as Record<string, string>).toString() : ''
    return req<Opportunity[]>(`/opportunities${qs}`)
  },
  getOpportunity: (id: string) => req<Opportunity>(`/opportunities/${id}`),
  annotate: (id: string, notes: string) =>
    req(`/opportunities/${id}/annotate`, { method: 'POST', body: JSON.stringify({ notes }) }),
  patchOpportunity: (id: string, patch: { title?: string; notes?: string }) =>
    req<Opportunity>(`/opportunities/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  deleteOpportunity: (id: string) =>
    req<{ ok: boolean }>(`/opportunities/${id}`, { method: 'DELETE' }),
  calibrateOne: (id: string) =>
    req<{ ok: boolean }>(`/opportunities/${id}/calibrate`, { method: 'POST' }),
  archive: (id: string) => req(`/opportunities/${id}/archive`, { method: 'POST' }),
  requestInfo: (id: string) => req(`/opportunities/${id}/request-info`, { method: 'POST' }),
  getSettings: () => req<Record<string, unknown>>('/settings'),
  updateSettings: (patch: Record<string, unknown>) =>
    req('/settings', { method: 'PATCH', body: JSON.stringify(patch) }),
  triggerCycle: () => req<{ ok: boolean; message: string }>('/cycle/run', { method: 'POST' }),
  getCycleStatus: () => req<CycleStatus>('/cycle/status'),
  getImports: () => req<Array<{ id: string; filename: string; imported_at: string; signals_extracted: number; opportunities_added: number }>>('/imports'),
  rerateAll: () => req<{ ok: boolean; message: string }>('/opportunities/rerate', { method: 'POST' }),
  rerateCalibrate: (threshold = 75) =>
    req<{ ok: boolean; message: string }>('/opportunities/rerate-calibrate', {
      method: 'POST',
      body: JSON.stringify({ threshold }),
    }),
  chat: async (
    id: string,
    message: string,
    onChunk: (s: string) => void,
  ): Promise<Array<{ type: string; data?: Record<string, unknown> }>> => {
    const res = await fetch(BASE + `/opportunities/${id}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    })
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
    const reader = res.body!.getReader()
    const decoder = new TextDecoder()
    let actions: Array<{ type: string; data?: Record<string, unknown> }> = []
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          const payload = JSON.parse(line.slice(6))
          if (payload.chunk) onChunk(payload.chunk)
          if (payload.done) actions = payload.actions ?? []
        } catch {
          // ignore parse errors
        }
      }
    }
    return actions
  },
  rerateOne: (id: string) =>
    req<{ ok: boolean }>(`/opportunities/${id}/rerate`, { method: 'POST' }),
  rerateWithContext: (id: string, chatContext: ChatMessage[]) =>
    req<{ ok: boolean }>(`/opportunities/${id}/rerate-with-context`, {
      method: 'POST',
      body: JSON.stringify({ chat_context: chatContext }),
    }),
  clearChat: (id: string) =>
    req<{ ok: boolean }>(`/opportunities/${id}/chat`, { method: 'DELETE' }),
  deepResearch: (id: string, task: string) =>
    req<{ ok: boolean }>(`/opportunities/${id}/deep-research`, {
      method: 'POST',
      body: JSON.stringify({ task }),
    }),
  uploadFile: async (file: File): Promise<{ ok: boolean; message: string }> => {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch(BASE + '/upload', { method: 'POST', body: form })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      return { ok: false, message: err.detail || res.statusText }
    }
    return res.json()
  },
}
