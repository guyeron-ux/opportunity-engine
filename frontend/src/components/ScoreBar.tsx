interface ScoreBarProps {
  label: string
  score: number
  weight?: number
  rationale?: string
}

function scoreColor(score: number): string {
  if (score >= 80) return 'bg-emerald-500'
  if (score >= 60) return 'bg-yellow-400'
  if (score >= 40) return 'bg-orange-400'
  return 'bg-red-500'
}

export function ScoreBar({ label, score, weight, rationale }: ScoreBarProps) {
  const filled = Math.round(score / 10)
  const bars = '█'.repeat(filled) + '░'.repeat(10 - filled)

  return (
    <div className="mb-2">
      <div className="flex items-center justify-between text-xs mb-1">
        <span className="text-gray-400 font-mono">
          {label}
          {weight !== undefined && (
            <span className="text-gray-600 ml-1">({(weight * 100).toFixed(0)}%)</span>
          )}
        </span>
        <span className="font-bold text-white">{score}</span>
      </div>
      <div className={`font-mono text-sm tracking-widest ${scoreColor(score).replace('bg-', 'text-')}`}>
        {bars}
      </div>
      {rationale && <p className="text-xs text-gray-500 mt-0.5">{rationale}</p>}
    </div>
  )
}
