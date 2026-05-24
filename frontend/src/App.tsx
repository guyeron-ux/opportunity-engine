import { useState, useEffect, useCallback, useRef } from 'react'
import { api, type Opportunity } from './api'
import { exportToMarkdown, exportToPDF } from './utils/export'
import { OpportunityTable } from './components/OpportunityTable'
import { OpportunityDetail } from './components/OpportunityDetail'
import { FilterPanel } from './components/FilterPanel'
import { NotificationPanel } from './components/NotificationPanel'
import { CycleBanner } from './components/CycleBanner'
import { UploadModal } from './components/UploadModal'
import { SystemLogicModal } from './components/SystemLogicModal'
import { useWebSocket, type WsMessage } from './hooks/useWebSocket'

interface Filters {
  min_score: number
  types: string[]
  categories: string[]
  industries: string[]
  gtm: string[]
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
      // text filters are always done client-side with contains matching —
      // the LLM may return "Legal Technology" for "Legal" or "SaaS Platform" for "SaaS"
      const opps = await api.getOpportunities(Object.keys(params).length ? params : undefined)
      let filtered = opps
      // type: exact (controlled values — Moonshot / Pragmatic)
      if (filters.types.length > 0) filtered = filtered.filter(o => filters.types.includes(o.classification.type))
      // category / industry: contains, case-insensitive
      if (filters.categories.length > 0) filtered = filtered.filter(o =>
        filters.categories.some(c => o.classification.category.toLowerCase().includes(c.toLowerCase()))
      )
      if (filters.industries.length > 0) filtered = filtered.filter(o =>
        filters.industries.some(ind => o.classification.industry.toLowerCase().includes(ind.toLowerCase()))
      )
      // GTM: "B2B" matches "B2B", "B2B/B2C", "B2B/B2G", etc.
      if (filters.gtm.length > 0) filtered = filtered.filter(o =>
        filters.gtm.some(g => o.classification.go_to_market.includes(g))
      )
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
    min_score: 0, types: [], categories: [], industries: [], gtm: [],
  })
  const [selected, setSelected] = useState<Opportunity | null>(null)
  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set())

  // Cycle state — driven by backend polling, not local guess
  const [cycleRunning, setCycleRunning] = useState(false)
  const [cycleStartedAt, setCycleStartedAt] = useState<string | null>(null)
  const [cycleStats, setCycleStats] = useState<CycleStats>({ signals: 0, scored: 0, total: 0 })
  const [lastEvent, setLastEvent] = useState('')
  const [triggerError, setTriggerError] = useState('')
  const [showUpload, setShowUpload] = useState(false)
  const [showSystemLogic, setShowSystemLogic] = useState(false)
  const [calibratingIds, setCalibratingIds] = useState<Set<string>>(new Set())
  const [reratingIds, setReratingIds] = useState<Set<string>>(new Set())

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
      case 'quota_exceeded':
        setCycleRunning(false)
        setLastEvent('')
        setTriggerError(`Search quota exhausted — renew Tavily API key at app.tavily.com`)
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
      case 'opportunity_updated': {
        const updatedId = msg.data.id as string
        // Clear from any pending operation tracking
        setCalibratingIds(prev => { const n = new Set(prev); n.delete(updatedId); return n })
        setReratingIds(prev => { const n = new Set(prev); n.delete(updatedId); return n })
        // Refresh list + re-fetch selected opp if it matches
        refetch()
        setSelected(prev => {
          if (prev && prev.id === updatedId) {
            api.getOpportunity(prev.id).then(updated => setSelected(updated)).catch(() => {})
          }
          return prev
        })
        break
      }
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

  async function triggerCalibrate() {
    setTriggerError('')
    try {
      const res = await api.rerateCalibrate(75)
      if (!res.ok) {
        setTriggerError(res.message)
      } else {
        setCycleRunning(true)
        setCycleStartedAt(new Date().toISOString())
        setCycleStats({ signals: 0, scored: 0, total: 0 })
        setLastEvent('Calibrating 75+ opportunities…')
      }
    } catch {
      setTriggerError('Could not reach backend')
    }
  }

  function handleCheck(id: string, checked: boolean) {
    setCheckedIds(prev => {
      const next = new Set(prev)
      checked ? next.add(id) : next.delete(id)
      return next
    })
  }

  function handleCheckAll(checked: boolean) {
    setCheckedIds(checked ? new Set(data.map(o => o.id)) : new Set())
  }

  async function handleBulkDelete() {
    if (!window.confirm(`Delete ${checkedIds.size} opportunit${checkedIds.size === 1 ? 'y' : 'ies'}? This cannot be undone.`)) return
    await Promise.all([...checkedIds].map(id => api.deleteOpportunity(id).catch(() => {})))
    setCheckedIds(new Set())
    refetch()
  }

  async function handleBulkRerate() {
    const ids = [...checkedIds]
    setReratingIds(prev => new Set([...prev, ...ids]))
    setCheckedIds(new Set())
    await Promise.all(ids.map(id => api.rerateOne(id).catch(() => {})))
  }

  async function handleBulkCalibrate() {
    const ids = [...checkedIds]
    setCalibratingIds(prev => new Set([...prev, ...ids]))
    setCheckedIds(new Set())
    await Promise.all(ids.map(id => api.calibrateOne(id).catch(() => {})))
  }

  function handleBulkExport(format: 'md' | 'pdf') {
    const opps = data.filter(o => checkedIds.has(o.id))
    if (opps.length === 0) return
    format === 'md' ? exportToMarkdown(opps) : exportToPDF(opps)
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
            onClick={() => setShowSystemLogic(true)}
            className="text-xs border border-gray-700 hover:border-gray-500 text-gray-500 hover:text-gray-300 px-2.5 py-2 rounded-lg transition-colors"
            title="How the system works"
          >
            ?
          </button>
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
            title="Refresh classification metadata only (scores stay frozen)"
          >
            ↻ Rerate
          </button>
          <button
            onClick={triggerCalibrate}
            disabled={cycleRunning}
            className="text-xs border border-amber-700 hover:border-amber-500 disabled:opacity-40 disabled:cursor-not-allowed text-amber-400 hover:text-amber-300 px-3 py-2 rounded-lg transition-colors"
            title="Full rescore of 75+ opportunities with latest rubric + Devil's Advocate"
          >
            ⚖ Calibrate 75+
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

      {/* Per-opp background operation indicator */}
      {(calibratingIds.size > 0 || reratingIds.size > 0) && (
        <div className="px-6 py-1.5 border-b border-gray-800 flex items-center gap-4 text-xs">
          {calibratingIds.size > 0 && (
            <span className="text-amber-400 animate-pulse">
              ⚖ Calibrating {calibratingIds.size} opportunit{calibratingIds.size === 1 ? 'y' : 'ies'} in background…
            </span>
          )}
          {reratingIds.size > 0 && (
            <span className="text-cyan-400 animate-pulse">
              ↻ Rerating {reratingIds.size} opportunit{reratingIds.size === 1 ? 'y' : 'ies'} in background…
            </span>
          )}
        </div>
      )}

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">
        <div className="hidden lg:block p-4 border-r border-gray-800 overflow-y-auto">
          <FilterPanel filters={filters} onChange={setFilters} />
        </div>

        <main className="flex-1 flex flex-col overflow-hidden">
          {checkedIds.size > 0 ? (
            <div className="px-4 py-2 border-b border-violet-800/50 bg-violet-950/30 flex items-center gap-2 flex-wrap text-xs">
              <span className="text-violet-300 font-semibold mr-1">{checkedIds.size} selected</span>
              <button
                onClick={handleBulkRerate}
                className="border border-gray-600 hover:border-gray-400 text-gray-300 px-2.5 py-1 rounded-lg transition-colors"
                title="Classification-only rerate (scores frozen)"
              >↻ Rerate</button>
              <button
                onClick={handleBulkCalibrate}
                className="border border-amber-700 hover:border-amber-500 text-amber-400 hover:text-amber-300 px-2.5 py-1 rounded-lg transition-colors"
                title="Full rescore with latest rubric + Devil's Advocate"
              >⚖ Calibrate</button>
              <button
                onClick={() => handleBulkExport('md')}
                className="border border-gray-600 hover:border-gray-400 text-gray-300 px-2.5 py-1 rounded-lg transition-colors"
              >↓ MD</button>
              <button
                onClick={() => handleBulkExport('pdf')}
                className="border border-gray-600 hover:border-gray-400 text-gray-300 px-2.5 py-1 rounded-lg transition-colors"
              >↓ PDF</button>
              <button
                onClick={handleBulkDelete}
                className="border border-red-800 hover:border-red-600 text-red-400 hover:text-red-300 px-2.5 py-1 rounded-lg transition-colors"
              >🗑 Delete</button>
              <button
                onClick={() => setCheckedIds(new Set())}
                className="ml-auto text-gray-600 hover:text-gray-400 px-2 py-1 transition-colors"
              >✕ Clear</button>
            </div>
          ) : (
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
          )}

          <OpportunityTable
            opportunities={data}
            onOpen={setSelected}
            loading={loading}
            checkedIds={checkedIds}
            onCheck={handleCheck}
            onCheckAll={handleCheckAll}
          />
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

      {showSystemLogic && (
        <SystemLogicModal onClose={() => setShowSystemLogic(false)} />
      )}
    </div>
  )
}
