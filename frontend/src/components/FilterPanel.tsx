interface Filters {
  min_score: number
  types: string[]
  categories: string[]
  industries: string[]
  gtm: string[]
}

interface FilterPanelProps {
  filters: Filters
  onChange: (f: Filters) => void
}

const TYPES = ['Moonshot', 'Pragmatic']
const GTM = ['B2B', 'B2C', 'B2G']
const CATEGORIES = ['SaaS', 'Marketplace', 'API', 'Platform', 'Hardware', 'Consumer', 'Other']
const INDUSTRIES = [
  'Technology', 'Healthcare', 'Finance', 'Education', 'Logistics',
  'Real Estate', 'HR', 'Legal', 'Manufacturing', 'Agriculture',
]

function Toggle({
  label, active, onClick,
}: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`text-xs px-2 py-1 rounded-full border transition-colors ${
        active
          ? 'bg-violet-600 border-violet-500 text-white'
          : 'bg-gray-800 border-gray-700 text-gray-400 hover:border-gray-500'
      }`}
    >
      {label}
    </button>
  )
}

function toggleItem(arr: string[], item: string): string[] {
  return arr.includes(item) ? arr.filter((x) => x !== item) : [...arr, item]
}

export function FilterPanel({ filters, onChange }: FilterPanelProps) {
  return (
    <aside className="w-56 shrink-0 space-y-5">
      {/* Score threshold */}
      <div>
        <div className="flex justify-between text-xs text-gray-400 mb-1">
          <span>Min Score</span>
          <span className="font-bold text-white">{filters.min_score}</span>
        </div>
        <input
          type="range"
          min={0}
          max={100}
          step={5}
          value={filters.min_score}
          onChange={(e) => onChange({ ...filters, min_score: Number(e.target.value) })}
          className="w-full accent-violet-500"
        />
        <div className="flex justify-between text-xs text-gray-600 mt-0.5">
          <span>0</span><span>50</span><span>100</span>
        </div>
      </div>

      {/* Type */}
      <div>
        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Type</h3>
        <div className="flex flex-wrap gap-1.5">
          {TYPES.map((t) => (
            <Toggle
              key={t}
              label={t}
              active={filters.types.includes(t)}
              onClick={() => onChange({ ...filters, types: toggleItem(filters.types, t) })}
            />
          ))}
        </div>
      </div>

      {/* Category */}
      <div>
        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Category</h3>
        <div className="flex flex-wrap gap-1.5">
          {CATEGORIES.map((c) => (
            <Toggle
              key={c}
              label={c}
              active={filters.categories.includes(c)}
              onClick={() => onChange({ ...filters, categories: toggleItem(filters.categories, c) })}
            />
          ))}
        </div>
      </div>

      {/* Industry */}
      <div>
        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Industry</h3>
        <div className="flex flex-wrap gap-1.5">
          {INDUSTRIES.map((ind) => (
            <Toggle
              key={ind}
              label={ind}
              active={filters.industries.includes(ind)}
              onClick={() => onChange({ ...filters, industries: toggleItem(filters.industries, ind) })}
            />
          ))}
        </div>
      </div>

      {/* Go-to-Market */}
      <div>
        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Go-to-Market</h3>
        <div className="flex flex-wrap gap-1.5">
          {GTM.map((g) => (
            <Toggle
              key={g}
              label={g}
              active={filters.gtm.includes(g)}
              onClick={() => onChange({ ...filters, gtm: toggleItem(filters.gtm, g) })}
            />
          ))}
        </div>
      </div>

      {/* Reset */}
      {(filters.types.length > 0 || filters.categories.length > 0 || filters.industries.length > 0 || filters.gtm.length > 0) && (
        <button
          onClick={() => onChange({ min_score: filters.min_score, types: [], categories: [], industries: [], gtm: [] })}
          className="text-xs text-violet-400 hover:text-violet-300 underline"
        >
          Clear filters
        </button>
      )}
    </aside>
  )
}
