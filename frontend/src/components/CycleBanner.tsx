interface CycleBannerProps {
  running: boolean
  startedAt: string | null
  stats: { signals: number; scored: number; total: number }
  lastEvent: string
}

export function CycleBanner({ running, startedAt, stats, lastEvent }: CycleBannerProps) {
  if (!running) return null

  const elapsed = startedAt
    ? Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000)
    : null

  const elapsedStr = elapsed !== null
    ? elapsed < 60 ? `${elapsed}s` : `${Math.floor(elapsed / 60)}m ${elapsed % 60}s`
    : null

  const pct = stats.total > 0 ? Math.round((stats.scored / stats.total) * 100) : null

  return (
    <div className="bg-violet-950 border-b border-violet-800 px-6 py-2.5 flex items-center gap-4">
      {/* Pulsing dot */}
      <span className="relative flex h-2.5 w-2.5 shrink-0">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-violet-400 opacity-75" />
        <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-violet-300" />
      </span>

      <span className="text-sm font-semibold text-violet-200">Discovery cycle running</span>

      {elapsedStr && (
        <span className="text-xs text-violet-400 font-mono">{elapsedStr}</span>
      )}

      <div className="flex items-center gap-3 text-xs text-violet-300">
        {stats.signals > 0 && (
          <span>{stats.signals} signals found</span>
        )}
        {stats.scored > 0 && stats.total > 0 && (
          <>
            <span className="text-violet-600">·</span>
            <span>{stats.scored}/{stats.total} analyzed</span>
          </>
        )}
        {stats.scored > 0 && stats.total === 0 && (
          <>
            <span className="text-violet-600">·</span>
            <span>{stats.scored} scored</span>
          </>
        )}
      </div>

      {/* Progress bar */}
      {pct !== null && (
        <div className="flex-1 max-w-32 bg-violet-900 rounded-full h-1.5">
          <div
            className="bg-violet-400 h-1.5 rounded-full transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
      )}

      {lastEvent && (
        <span className="ml-auto text-xs text-violet-500 truncate max-w-64 hidden lg:block">
          {lastEvent}
        </span>
      )}
    </div>
  )
}
