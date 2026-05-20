import type { Opportunity } from '../api'

interface Props {
  opportunities: Opportunity[]
  onSelect: (opp: Opportunity) => void
  loading: boolean
}

function ScoreBadge({ score }: { score: number }) {
  const color =
    score >= 80 ? 'bg-emerald-900 text-emerald-300' :
    score >= 60 ? 'bg-yellow-900 text-yellow-300' :
    score >= 40 ? 'bg-orange-900 text-orange-300' :
    'bg-red-900 text-red-300'
  return (
    <span className={`inline-block font-mono font-bold text-sm px-2 py-0.5 rounded ${color}`}>
      {Math.round(score)}
    </span>
  )
}

function TypeBadge({ type }: { type: string }) {
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${
      type === 'Moonshot' ? 'bg-violet-900 text-violet-300' : 'bg-cyan-900 text-cyan-300'
    }`}>
      {type}
    </span>
  )
}

function latestCycleId(opportunities: Opportunity[]): string {
  return opportunities.reduce((max, o) => (o.cycle_id > max ? o.cycle_id : max), '')
}

export function OpportunityTable({ opportunities, onSelect, loading }: Props) {
  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-500">
        <span className="animate-pulse text-sm">Loading opportunities…</span>
      </div>
    )
  }

  if (opportunities.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-gray-600 gap-3">
        <span className="text-4xl">📡</span>
        <p className="text-sm">No opportunities yet. Trigger a discovery cycle to get started.</p>
      </div>
    )
  }

  const newestCycleId = latestCycleId(opportunities)

  return (
    <div className="flex-1 overflow-auto">
      {/* Desktop table */}
      <table className="w-full text-sm hidden md:table">
        <thead>
          <tr className="border-b border-gray-800 text-xs text-gray-500 text-left">
            <th className="py-3 px-4 w-8">#</th>
            <th className="py-3 px-4">Opportunity</th>
            <th className="py-3 px-4 w-20">Score</th>
            <th className="py-3 px-4 w-28">Type</th>
            <th className="py-3 px-4 w-32">Industry</th>
            <th className="py-3 px-4 w-24">Added</th>
            <th className="py-3 px-4">Tags</th>
          </tr>
        </thead>
        <tbody>
          {opportunities.map((opp, i) => {
            const isNew = newestCycleId && opp.cycle_id === newestCycleId
            return (
            <tr
              key={opp.id}
              onClick={() => onSelect(opp)}
              className={`border-b cursor-pointer transition-colors ${
                isNew
                  ? 'border-violet-900/40 bg-violet-950/25 hover:bg-violet-950/40'
                  : 'border-gray-800/50 hover:bg-gray-800/40'
              }`}
            >
              <td className="py-3 px-4 text-gray-600 font-mono">{i + 1}</td>
              <td className="py-3 px-4">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-gray-100 leading-tight">{opp.title}</span>
                  {isNew && (
                    <span className="shrink-0 text-xs font-semibold px-1.5 py-0.5 rounded-full bg-violet-800/60 text-violet-300 border border-violet-700/50">
                      new
                    </span>
                  )}
                </div>
                <div className="text-xs text-gray-500 mt-0.5 line-clamp-1">
                  {opp.research.pain_point_summary}
                </div>
              </td>
              <td className="py-3 px-4">
                <ScoreBadge score={opp.composite_score} />
              </td>
              <td className="py-3 px-4">
                <div className="flex items-center gap-1.5 flex-wrap">
                  <TypeBadge type={opp.classification.type} />
                  {opp.classification.go_to_market && (
                    <span className="text-xs px-1.5 py-0.5 rounded font-mono bg-gray-800 text-gray-400 border border-gray-700">
                      {opp.classification.go_to_market}
                    </span>
                  )}
                </div>
              </td>
              <td className="py-3 px-4 text-gray-400 text-xs">{opp.classification.industry}</td>
              <td className="py-3 px-4 text-gray-500 text-xs whitespace-nowrap">
                {new Date(opp.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
              </td>
              <td className="py-3 px-4">
                <div className="flex flex-wrap gap-1">
                  {opp.classification.tags.slice(0, 3).map((tag) => (
                    <span key={tag} className="text-xs bg-gray-800 text-gray-500 px-1.5 py-0.5 rounded">
                      {tag}
                    </span>
                  ))}
                </div>
              </td>
            </tr>
          )})}
        </tbody>
      </table>

      {/* Mobile card list */}
      <div className="md:hidden space-y-2 p-2">
        {opportunities.map((opp) => {
          const isNew = newestCycleId && opp.cycle_id === newestCycleId
          return (
          <div
            key={opp.id}
            onClick={() => onSelect(opp)}
            className={`rounded-xl p-4 cursor-pointer transition-colors ${
              isNew
                ? 'bg-violet-950/40 hover:bg-violet-950/60 border border-violet-900/40'
                : 'bg-gray-800/60 hover:bg-gray-800'
            }`}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-sm truncate">{opp.title}</span>
                  {isNew && (
                    <span className="shrink-0 text-xs font-semibold px-1.5 py-0.5 rounded-full bg-violet-800/60 text-violet-300 border border-violet-700/50">
                      new
                    </span>
                  )}
                </div>
                <div className="text-xs text-gray-500 mt-0.5">{opp.classification.industry}</div>
              </div>
              <div className="flex items-center gap-2 shrink-0 flex-wrap justify-end">
                <ScoreBadge score={opp.composite_score} />
                <TypeBadge type={opp.classification.type} />
                {opp.classification.go_to_market && (
                  <span className="text-xs px-1.5 py-0.5 rounded font-mono bg-gray-800 text-gray-400 border border-gray-700">
                    {opp.classification.go_to_market}
                  </span>
                )}
              </div>
            </div>
            <p className="text-xs text-gray-500 mt-2 line-clamp-2">{opp.research.pain_point_summary}</p>
          </div>
        )})}
      </div>
    </div>
  )
}
