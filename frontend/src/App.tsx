import { useState, useEffect, useCallback, useRef } from 'react'
import { api, type Opportunity } from './api'
import { OpportunityTable } from './components/OpportunityTable'
import { OpportunityDetail } from './components/OpportunityDetail'
import { FilterPanel } from './components/FilterPanel'
import { NotificationPanel } from './components/NotificationPanel'
import { CycleBanner } from './components/CycleBanner'
import { UploadModal } from './components/UploadModal'
import { useWebSocket, type WsMessage } from './hooks/useWebSocket'

interface Filters {
  min_score: number
  types: string[]
  categories: string[]
  industries: string[]
}

interface CycleStats {
  signals: number
  scored: number
  total: number
}

function useOpportunities(filters: Filters) {
  const [data, setData] = useState<Opportunity[]>([])
  const [loading, setLoading] = useState(true)

  const fetch = useCallback(async () => {
    setLoading(true)
    try {
      const params: Record<string, string> = {}
      if (filters.min_score > 0) params.min_score = String(filters.min_score)
      if (filters.types.length === 1) params.type = filters.types[0]
      if (filters.categories.length === 1) params.category = filters.categories[0]
      if (filters.industries.length === 1) params.industry = filters.industries[0]
      const opps = await api.getOpportunities(Object.keys(params).length ? params : undefined)
      let filtered = opps
      if (filters.types.length > 1) filtered = filtered.filter(o => filters.types.includes(o.classification.type))
      if (filters.categories.length > 1) filtered = filtered.filter(o => filters.categories.includes(o.classification.category))
      if (filters.industries.length > 1) filtered = filtered.filter(o => filters.industries.includes(o.classification.industry))
      setData(filtered)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [filters])

  useEffect(() => { fetch() }, [fetch])
  return { data, loading, refetch: fetch }
}

export default function App() {
  const [filters, setFilters] = useState<Filters>({
    min_score: 0, types: [], categories: [], industries: [],
  })
  const [selected, setSelected] = useState<Opportunity | null>(null)

  // Cycle state — driven by backend polling, not local guess
  const [cycleRunning, setCycleRunning] = useState(false)
  const [cycleStartedAt, setCycleStartedAt] = useState<string | null>(null)
  const [cycleStats, setCycleStats] = useState<CycleStats>({ signals: 0, scored: 0, total: 0 })
  const [lastEvent, setLastEvent] = useState('')
  const [triggerError, setTriggerError] = useState('')
  const [showUpload, setShowUpload] = useState(false)

  // Shared WebSocket message bus — notifications + banner both consume this
  const wsNotifyRef = useRef<((msg: WsMessage) => void) | null>(null)

  const { data, loading, refetch } = useOpportunities(filters)

  // Poll /api/cycle/status every 4s to stay in sync with server
  useEffect(() => {
    let timer: ReturnType<typeof setInterval>

    async function poll() {
      try {
        const status = await api.getCycleStatus()
        const wasRunning = cycleRunning
        setCycleRunning(status.cycle_running)
        if (status.cycle_running && !wasRunning) {
          // Just started (detected by poll) — record start time
          setCycleStartedAt(status.last_run)
          setCycleStats({ signals: 0, scored: 0, total: 0 })
        }
        if (!status.cycle_running && wasRunning) {
          // Just finished — refresh table
          refetch()
          setCycleStats({ signals: 0, scored: 0, total: 0 })
          setLastEvent('')
        }
      } catch {
        // silently ignore poll errors
      }
    }

    poll()
    timer = setInterval(poll, 4000)
    return () => clearInterval(timer)
  }, [cycleRunning, refetch])

  // WebSocket handler — updates banner stats + forwards to notification panel
  const handleWsMessage = useCallback((msg: WsMessage) => {
    // Forward to notification panel
    wsNotifyRef.current?.(msg)

    switch (msg.event) {
      case 'cycle_start':
        setCycleRunning(true)
        setCycleStartedAt(msg.data.timestamp as string)
        setCycleStats({ signals: 0, scored: 0, total: 0 })
        setLastEvent('Scouts scanning sources…')
        break
      case 'scouts_done':
        setCycleStats(s => ({ ...s, signals: msg.data.signal_count as number, total: msg.data.signal_count as number }))
        setLastEvent(`${msg.data.signal_count} signals collected — starting analysis`)
        break
      case 'batch_done':
        setCycleStats(s => ({ ...s, scored: msg.data.processed as number, total: msg.data.total as number }))
        setLastEvent(`Analyzing signal ${msg.data.processed}/${msg.data.total}…`)
        break
      case 'opportunity_added':
        setCycleStats(s => ({ ...s, scored: s.scored }))
        setLastEvent(`Scored: ${msg.data.title} (${(msg.data.score as number).toFixed(1)})`)
        refetch()
        break
      case 'cycle_done':
        setCycleRunning(false)
        setLastEvent('')
        refetch()
        break
      case 'cycle_error':
        setCycleRunning(false)
        setLastEvent('')
        setTriggerError(`Cycle error: ${msg.data.error}`)
        break
      case 'rerate_start':
        setCycleRunning(true)
        setCycleStartedAt(new Date().toISOString())
        setCycleStats({ signals: 0, scored: 0, total: msg.data.total as number })
        setLastEvent(`Re-rating ${msg.data.total} opportunities…`)
        break
      case 'rerate_progress':
        setCycleStats(s => ({ ...s, scored: msg.data.done as number, total: msg.data.total as number }))
        setLastEvent(`Re-rated: ${msg.data.title} → ${msg.data.type} (${(msg.data.score as number).toFixed(1)})`)
        break
      case 'rerate_done':
        setCycleRunning(false)
        setLastEvent('')
        refetch()
        break
      case 'rerate_error':
        setCycleRunning(false)
        setLastEvent('')
        setTriggerError(`Re-rate error: ${msg.data.error}`)
        break
    }
  }, [refetch])

  useWebSocket(handleWsMessage)

  async function triggerCycle() {
    setTriggerError('')
    try {
      const res = await api.triggerCycle()
      if (!res.ok) {
        setTriggerError(res.message)
      } else {
        setCycleRunning(true)
        setCycleStartedAt(new Date().toISOString())
        setCycleStats({ signals: 0, scored: 0, total: 0 })
        setLastEvent('Starting scouts…')
      }
    } catch {
      setTriggerError('Could not reach backend')
    }
  }

  async function triggerRerate() {
    setTriggerError('')
    try {
      const res = await api.rerateAll()
      if (!res.ok) {
        setTriggerError(res.message)
      } else {
        setCycleRunning(true)
        setCycleStartedAt(new Date().toISOString())
        setLastEvent('Re-rating opportunities…')
      }
    } catch {
      setTriggerError('Could not reach backend')
    }
  }

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="border-b border-gray-800 px-6 py-3 flex items-center gap-4">
        <div className="flex items-center gap-2">
          <span className="text-xl">📡</span>
          <h1 className="font-bold text-lg tracking-tight">Opportunity Engine</h1>
        </div>
        <div className="flex-1" />
        <div className="flex items-center gap-3">
          {triggerError && (
            <span className="text-xs text-red-400">{triggerError}</span>
          )}
          <button
            onClick={() => setShowUpload(true)}
            disabled={cycleRunning}
            className="text-xs border border-gray-600 hover:border-gray-400 disabled:opacity-40 disabled:cursor-not-allowed text-gray-300 px-3 py-2 rounded-lg transition-colors"
            title="Import from PDF or Markdown"
          >
            ↑ Import
          </button>
          <button
            onClick={triggerRerate}
            disabled={cycleRunning}
            className="text-xs border border-gray-600 hover:border-gray-400 disabled:opacity-40 disabled:cursor-not-allowed text-gray-300 px-3 py-2 rounded-lg transition-colors"
            title="Re-score existing opportunities with updated rubric"
          >
            ↻ Rerate
          </button>
          <button
            onClick={triggerCycle}
            disabled={cycleRunning}
            className="text-xs bg-violet-700 hover:bg-violet-600 disabled:opacity-40 disabled:cursor-not-allowed text-white px-4 py-2 rounded-lg font-semibold transition-colors"
          >
            {cycleRunning ? '⏳ Running…' : '▶ Run Cycle'}
          </button>
          <NotificationPanel wsNotifyRef={wsNotifyRef} />
        </div>
      </header>

      {/* Cycle progress banner */}
      <CycleBanner
        running={cycleRunning}
        startedAt={cycleStartedAt}
        stats={cycleStats}
        lastEvent={lastEvent}
      />

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">
        <div className="hidden lg:block p-4 border-r border-gray-800 overflow-y-auto">
          <FilterPanel filters={filters} onChange={setFilters} />
        </div>

        <main className="flex-1 flex flex-col overflow-hidden">
          <div className="px-6 py-2 border-b border-gray-800 flex items-center gap-4 text-xs text-gray-500">
            <span>{data.length} opportunit{data.length === 1 ? 'y' : 'ies'}</span>
            {data.length > 0 && (
              <>
                <span>·</span>
                <span>Avg score: {(data.reduce((s, o) => s + o.composite_score, 0) / data.length).toFixed(1)}</span>
                <span>·</span>
                <span>{data.filter(o => o.classification.type === 'Moonshot').length} Moonshots</span>
              </>
            )}
          </div>

          <OpportunityTable opportunities={data} onSelect={setSelected} loading={loading} />
        </main>
      </div>

      {selected && (
        <OpportunityDetail
          opp={selected}
          onClose={() => setSelected(null)}
          onUpdate={refetch}
        />
      )}

      {showUpload && (
        <UploadModal onClose={() => setShowUpload(false)} />
      )}
    </div>
  )
}
