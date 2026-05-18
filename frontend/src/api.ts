// In production (Netlify), set VITE_API_URL to your Railway backend URL.
// Locally, Vite proxies /api → localhost:8000 so no env var needed.
const BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') + '/api'
  || '/api'

export interface RatingFactor {
  score: number
  rationale: string
  evidence: string[]
}

export interface Ratings {
  market_size: RatingFactor
  pain_severity: RatingFactor
  solution_clarity: RatingFactor
  competitive_insight: RatingFactor
  monetization_potential: RatingFactor
  signal_authority: RatingFactor
}

export interface Classification {
  type: string
  category: string
  industry: string
  tech_stack: string[]
  tags: string[]
}

export interface ResearchData {
  pain_point_summary: string
  affected_segments: string[]
  market_size_estimate: string
  market_growth_rate: string
  competitors: Array<{ name: string; weakness: string; url?: string }>
  monetization_models: string[]
  solution_hypothesis: string
  sources: string[]
  signal_sources: string[]
}

export interface UserInteraction {
  notes: string
  archived: boolean
  archived_at: string | null
  deeper_research_requested: boolean
  last_viewed: string | null
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
  archive: (id: string) => req(`/opportunities/${id}/archive`, { method: 'POST' }),
  requestInfo: (id: string) => req(`/opportunities/${id}/request-info`, { method: 'POST' }),
  getSettings: () => req<Record<string, unknown>>('/settings'),
  updateSettings: (patch: Record<string, unknown>) =>
    req('/settings', { method: 'PATCH', body: JSON.stringify(patch) }),
  triggerCycle: () => req<{ ok: boolean; message: string }>('/cycle/run', { method: 'POST' }),
  getCycleStatus: () => req<CycleStatus>('/cycle/status'),
}
