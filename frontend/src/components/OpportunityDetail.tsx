import { useState, useRef, useEffect } from 'react'
import type { Opportunity } from '../api'
import { api } from '../api'
import { ScoreBar } from './ScoreBar'
import { ChatPanel } from './ChatPanel'

interface Props {
  opp: Opportunity
  onClose: () => void
  onUpdate: () => void
}

const FACTORS: Array<{ key: keyof Opportunity['ratings']; label: string; weight: number }> = [
  { key: 'market_size', label: 'Market Size', weight: 0.25 },
  { key: 'pain_severity', label: 'Pain Severity', weight: 0.25 },
  { key: 'solution_clarity', label: 'Solution Clarity', weight: 0.15 },
  { key: 'competitive_insight', label: 'Competitive Insight', weight: 0.15 },
  { key: 'monetization_potential', label: 'Monetization', weight: 0.15 },
  { key: 'signal_authority', label: 'Signal Authority', weight: 0.05 },
]

export function OpportunityDetail({ opp, onClose, onUpdate }: Props) {
  const [notes, setNotes] = useState(opp.user.notes || '')
  const [saving, setSaving] = useState(false)
  const [editingTitle, setEditingTitle] = useState(false)
  const [titleDraft, setTitleDraft] = useState(opp.title)
  const [deepResearchOpen, setDeepResearchOpen] = useState(false)
  const [deepResearchTask, setDeepResearchTask] = useState('')
  const [deepResearchRunning, setDeepResearchRunning] = useState(false)
  const titleInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (editingTitle) titleInputRef.current?.focus()
  }, [editingTitle])

  async function saveTitle() {
    const trimmed = titleDraft.trim()
    if (!trimmed || trimmed === opp.title) { setEditingTitle(false); return }
    await api.patchOpportunity(opp.id, { title: trimmed })
    setEditingTitle(false)
    onUpdate()
  }

  function onTitleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter') saveTitle()
    if (e.key === 'Escape') { setTitleDraft(opp.title); setEditingTitle(false) }
  }

  async function saveNotes() {
    setSaving(true)
    await api.annotate(opp.id, notes)
    setSaving(false)
    onUpdate()
  }

  async function handleArchive() {
    await api.archive(opp.id)
    onClose()
    onUpdate()
  }

  async function handleDeepResearch() {
    const task = deepResearchTask.trim() || 'Validate TAM, find more competitors, identify additional monetization models'
    setDeepResearchRunning(true)
    try {
      await api.deepResearch(opp.id, task)
      setDeepResearchOpen(false)
      setDeepResearchTask('')
    } finally {
      setDeepResearchRunning(false)
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex items-start justify-end p-4 bg-black/60">
      <div className="w-full max-w-2xl bg-gray-900 border border-gray-700 rounded-2xl shadow-2xl overflow-y-auto max-h-[calc(100vh-2rem)]">
        {/* Header */}
        <div className="sticky top-0 bg-gray-900 border-b border-gray-800 px-6 py-4 flex items-center gap-3">
          <div className="flex-1 min-w-0">
            {editingTitle ? (
              <input
                ref={titleInputRef}
                value={titleDraft}
                onChange={e => setTitleDraft(e.target.value)}
                onBlur={saveTitle}
                onKeyDown={onTitleKeyDown}
                className="w-full bg-gray-800 border border-violet-500 rounded px-2 py-1 text-base font-bold text-white outline-none"
              />
            ) : (
              <h2
                className="text-lg font-bold truncate cursor-text hover:text-violet-300 transition-colors"
                title="Click to rename"
                onClick={() => setEditingTitle(true)}
              >
                {titleDraft}
                <span className="ml-1.5 text-xs text-gray-600 font-normal">✎</span>
              </h2>
            )}
            <div className="flex items-center gap-2 mt-1 flex-wrap">
              <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${
                opp.classification.type === 'Moonshot'
                  ? 'bg-violet-900 text-violet-300'
                  : 'bg-cyan-900 text-cyan-300'
              }`}>
                {opp.classification.type}
              </span>
              {opp.classification.go_to_market && (
                <span className="text-xs px-2 py-0.5 rounded-full font-semibold bg-gray-800 text-gray-300 border border-gray-700">
                  {opp.classification.go_to_market}
                </span>
              )}
              <span className="text-xs text-gray-500">{opp.classification.industry}</span>
              <span className="text-xs text-gray-500">·</span>
              <span className="text-xs text-gray-500">{opp.classification.category}</span>
            </div>
          </div>
          <div className="text-3xl font-black" style={{ color: scoreToColor(opp.composite_score) }}>
            {Math.round(opp.composite_score)}
          </div>
          <button onClick={onClose} className="ml-2 text-gray-500 hover:text-white text-xl">✕</button>
        </div>

        <div className="px-6 py-4 space-y-6">
          {/* Score breakdown */}
          <section>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Score Breakdown</h3>
            {FACTORS.map(({ key, label, weight }) => (
              <ScoreBar
                key={key}
                label={label}
                score={opp.ratings[key].score}
                weight={weight}
                rationale={opp.ratings[key].rationale}
              />
            ))}
          </section>

          {/* Pain point */}
          <section>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Pain Point</h3>
            <p className="text-sm text-gray-300 leading-relaxed">{opp.research.pain_point_summary}</p>
            {opp.research.affected_segments.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-2">
                {opp.research.affected_segments.map((seg) => (
                  <span key={seg} className="text-xs bg-gray-800 text-gray-400 px-2 py-0.5 rounded">{seg}</span>
                ))}
              </div>
            )}
          </section>

          {/* Market */}
          <section>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Market</h3>
            <div className="grid grid-cols-2 gap-3 mb-3">
              <div className="bg-gray-800 rounded-lg p-3 col-span-2 border border-emerald-900/40">
                <p className="text-xs text-gray-500">Solution TAM <span className="text-gray-600">(direct revenue opportunity)</span></p>
                <p className="text-sm font-bold text-emerald-400 mt-1">
                  {opp.ratings.market_size.solution_tam || opp.research.solution_tam_estimate || '—'}
                </p>
                {(opp.research.tam_derivation) && (
                  <p className="text-xs text-gray-500 mt-1">{opp.research.tam_derivation}</p>
                )}
              </div>
              <div className="bg-gray-800 rounded-lg p-3">
                <p className="text-xs text-gray-500">Industry Size</p>
                <p className="text-sm font-semibold mt-1">
                  {opp.ratings.market_size.industry_size || opp.research.market_size_estimate || '—'}
                </p>
              </div>
              <div className="bg-gray-800 rounded-lg p-3">
                <p className="text-xs text-gray-500">Growth Rate</p>
                <p className="text-sm font-semibold mt-1">{opp.research.market_growth_rate || '—'}</p>
              </div>
            </div>
          </section>

          {/* Competitors */}
          {opp.research.competitors.length > 0 && (
            <section>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                Competitive Landscape ({opp.research.competitors.length})
              </h3>
              <div className="space-y-2">
                {opp.research.competitors.map((c, i) => (
                  <div key={i} className="bg-gray-800 rounded-lg p-3">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold">{c.name}</span>
                      {c.url && (
                        <a href={c.url} target="_blank" rel="noreferrer" className="text-xs text-violet-400 hover:underline">↗</a>
                      )}
                    </div>
                    <p className="text-xs text-gray-400 mt-0.5">{c.weakness}</p>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Monetization */}
          {opp.research.monetization_models.length > 0 && (
            <section>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Monetization Models</h3>
              <ul className="space-y-1">
                {opp.research.monetization_models.map((m, i) => (
                  <li key={i} className="text-sm text-gray-300 flex gap-2">
                    <span className="text-violet-500">›</span>{m}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* Solution hypothesis */}
          {opp.research.solution_hypothesis && (
            <section>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Solution Hypothesis</h3>
              <p className="text-sm text-gray-300 leading-relaxed">{opp.research.solution_hypothesis}</p>
            </section>
          )}

          {/* Devil's Advocate */}
          {opp.devils_advocate && opp.devils_advocate.bear_case && (
            <section>
              <h3 className="text-xs font-semibold text-amber-600 uppercase tracking-wider mb-2">Devil's Advocate</h3>
              <div className="bg-amber-950/20 border border-amber-800/30 rounded-xl p-4 space-y-3">
                <p className="text-sm text-gray-300 leading-relaxed">{opp.devils_advocate.bear_case}</p>
                {opp.devils_advocate.biggest_threat && (
                  <div className="flex gap-2">
                    <span className="text-xs font-semibold text-amber-500 shrink-0 mt-0.5">Biggest threat:</span>
                    <span className="text-xs text-gray-300">{opp.devils_advocate.biggest_threat}</span>
                  </div>
                )}
                {opp.devils_advocate.key_risks.length > 0 && (
                  <ul className="space-y-1.5">
                    {opp.devils_advocate.key_risks.map((risk, i) => (
                      <li key={i} className="flex gap-2 text-xs text-gray-400">
                        <span className="text-amber-700 shrink-0">▲</span>
                        {risk}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </section>
          )}

          {/* Moonshot / Pragmatic justification */}
          {opp.classification.moonshot_justification && (
            <section>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                {opp.classification.type === 'Moonshot' ? '🚀 Moonshot Criteria' : 'Why Pragmatic'}
              </h3>
              <p className="text-sm text-gray-300 leading-relaxed">{opp.classification.moonshot_justification}</p>
            </section>
          )}

          {/* Tags */}
          {opp.classification.tags.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {opp.classification.tags.map((tag) => (
                <span key={tag} className="text-xs bg-gray-800 text-gray-400 px-2 py-0.5 rounded-full">#{tag}</span>
              ))}
            </div>
          )}

          {/* Sources */}
          {opp.research.sources.length > 0 && (
            <section>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Sources</h3>
              <ul className="space-y-1">
                {opp.research.sources.slice(0, 6).map((src, i) => (
                  <li key={i}>
                    <a href={src} target="_blank" rel="noreferrer" className="text-xs text-violet-400 hover:underline break-all">
                      {src}
                    </a>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* Chat */}
          <ChatPanel opp={opp} onOppUpdated={onUpdate} />

          {/* Notes */}
          <section>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Notes</h3>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              placeholder="Add your notes..."
              className="w-full bg-gray-800 border border-gray-700 rounded-lg p-3 text-sm text-gray-200 placeholder-gray-600 resize-none focus:outline-none focus:border-violet-500"
            />
            <button
              onClick={saveNotes}
              disabled={saving}
              className="mt-2 text-xs bg-violet-700 hover:bg-violet-600 text-white px-3 py-1.5 rounded-lg transition-colors disabled:opacity-50"
            >
              {saving ? 'Saving…' : 'Save Notes'}
            </button>
          </section>

          {/* Actions */}
          <div className="flex flex-col gap-2 pt-2 border-t border-gray-800">
            {/* Deep Research */}
            {deepResearchOpen ? (
              <div className="flex flex-col gap-2 bg-gray-800 rounded-lg p-3">
                <p className="text-xs text-gray-400 font-medium">What should we research deeper?</p>
                <textarea
                  value={deepResearchTask}
                  onChange={e => setDeepResearchTask(e.target.value)}
                  rows={2}
                  placeholder="Validate TAM, find more competitors, identify additional monetization models"
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-sm text-gray-200 placeholder-gray-500 resize-none focus:outline-none focus:border-violet-500"
                />
                <div className="flex gap-2">
                  <button
                    onClick={handleDeepResearch}
                    disabled={deepResearchRunning}
                    className="flex-1 text-xs bg-violet-700 hover:bg-violet-600 disabled:opacity-50 text-white px-3 py-1.5 rounded-lg transition-colors"
                  >
                    {deepResearchRunning ? 'Research running…' : '🔍 Start Research'}
                  </button>
                  <button
                    onClick={() => setDeepResearchOpen(false)}
                    className="text-xs text-gray-500 hover:text-gray-300 px-3 py-1.5 rounded-lg transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex gap-3">
                <button
                  onClick={() => setDeepResearchOpen(true)}
                  className="flex-1 text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 px-3 py-2 rounded-lg transition-colors"
                >
                  🔍 Request Deep Research
                </button>
                <button
                  onClick={handleArchive}
                  className="flex-1 text-xs bg-gray-800 hover:bg-red-900 text-gray-400 hover:text-red-300 px-3 py-2 rounded-lg transition-colors"
                >
                  🗃 Archive
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function scoreToColor(score: number): string {
  if (score >= 80) return '#10b981'
  if (score >= 60) return '#facc15'
  if (score >= 40) return '#fb923c'
  return '#f87171'
}
