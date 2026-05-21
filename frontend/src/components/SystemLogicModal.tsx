interface Props {
  onClose: () => void
}

const FACTORS = [
  { label: 'Market Size', weight: '25%', desc: 'Direct solution TAM — what this product can realistically capture as revenue, not total industry spend. Requires derivation: addressable segment × penetration × unit economics.' },
  { label: 'Pain Severity', weight: '25%', desc: 'Urgency and scale of the problem. 90+ requires critical operational pain at massive scale with no adequate solution. Scores below 50 indicate theoretical or nice-to-have pain.' },
  { label: 'Solution Clarity', weight: '15%', desc: 'Clear MVP path, known tech stack, defined customer journey. Penalizes vague or highly complex implementation paths.' },
  { label: 'Competitive Insight', weight: '15%', desc: 'Quality of competitive analysis — domain-specific incumbents must be named (e.g., supply chain → Blue Yonder/Kinaxis/o9, not generic ERP tools). Generic-tool-only lists cap at 35.' },
  { label: 'Monetization Potential', weight: '15%', desc: 'Proven business models with strong unit economics. 90+ requires a clear path to $100M+ ARR. Unclear or speculative models score below 50.' },
  { label: 'Signal Authority', weight: '5%', desc: 'Source quality: VC activity, major industry press, regulatory tailwinds (90+) down to single/weak sources (below 50).' },
]

export function SystemLogicModal({ onClose }: Props) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70">
      <div className="w-full max-w-2xl bg-gray-900 border border-gray-700 rounded-2xl shadow-2xl overflow-y-auto max-h-[calc(100vh-2rem)]">
        {/* Header */}
        <div className="sticky top-0 bg-gray-900 border-b border-gray-800 px-6 py-4 flex items-center justify-between">
          <h2 className="font-bold text-lg">How the System Works</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-white text-xl">✕</button>
        </div>

        <div className="px-6 py-5 space-y-7 text-sm">

          {/* Pipeline */}
          <section>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">The Pipeline</h3>
            <div className="space-y-3">
              {[
                { step: '1. Scouts', color: 'text-violet-400', detail: 'Three parallel agents run concurrently: Business (industry news, market reports), Community (Reddit, HN, forums), and Long-form (research papers, newsletters). Each returns structured pain-point signals.' },
                { step: '2. Analyst', color: 'text-cyan-400', detail: 'Each signal goes through multi-step research: pain point validation, competitive landscape (domain-specific incumbents + VC-funded startups), market sizing (TAM derivation), and monetization modeling. Results are synthesized into a structured report.' },
                { step: '3. Rater', color: 'text-emerald-400', detail: 'Scores the report on 6 weighted factors, classifies as Moonshot or Pragmatic, and generates a Devil\'s Advocate analysis. Composite score = weighted average of the 6 factors.' },
              ].map(({ step, color, detail }) => (
                <div key={step} className="flex gap-3">
                  <span className={`font-semibold shrink-0 ${color} w-28`}>{step}</span>
                  <p className="text-gray-400 leading-relaxed">{detail}</p>
                </div>
              ))}
            </div>
          </section>

          {/* Scoring Factors */}
          <section>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Scoring Factors</h3>
            <div className="space-y-3">
              {FACTORS.map(({ label, weight, desc }) => (
                <div key={label} className="bg-gray-800 rounded-lg p-3">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-semibold text-gray-200">{label}</span>
                    <span className="text-xs text-violet-400 font-bold">{weight}</span>
                  </div>
                  <p className="text-xs text-gray-400 leading-relaxed">{desc}</p>
                </div>
              ))}
            </div>
            <p className="text-xs text-gray-600 mt-2">Score range 0–100 per factor. Composite = weighted sum. Strong opportunities composite in the upper 80s; 90+ is rare.</p>
          </section>

          {/* Classification */}
          <section>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Classification</h3>
            <div className="space-y-3">
              <div className="bg-violet-900/20 border border-violet-800/30 rounded-lg p-3">
                <p className="font-semibold text-violet-300 mb-1">Moonshot <span className="text-xs text-gray-500 font-normal">(~1 in 8–10 opportunities)</span></p>
                <p className="text-xs text-gray-400 leading-relaxed">Category-defining, infrastructure-level potential. If it succeeds, the winner owns the platform or standard an entire industry runs on. All five criteria must hold: $10B+ TAM with no dominant platform, widespread pain, fundamental workflow shift, credible $1B+ valuation path, and network effects or data moat potential.</p>
              </div>
              <div className="bg-cyan-900/20 border border-cyan-800/30 rounded-lg p-3">
                <p className="font-semibold text-cyan-300 mb-1">Pragmatic <span className="text-xs text-gray-500 font-normal">(the default)</span></p>
                <p className="text-xs text-gray-400 leading-relaxed">Clear, executable business with proven demand and achievable differentiation. Strong candidate for a capital-efficient company in the $10M–$500M range. Not a lesser designation — Pragmatic means excellent and buildable.</p>
              </div>
            </div>
          </section>

          {/* Chat & Research */}
          <section>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Chat, Research & Rescoring</h3>
            <div className="space-y-2 text-xs text-gray-400 leading-relaxed">
              <p><span className="text-gray-300 font-medium">Chat with Analyst</span> — An experienced VC analyst persona with full opportunity context. Chat history persists across sessions and survives pipeline reruns. The analyst can suggest rerates or edits.</p>
              <p><span className="text-gray-300 font-medium">Rerate with Insights</span> — When the analyst surfaces new information in chat (e.g., missed competitors, revised TAM), clicking "Rerate with these insights" passes the full conversation as evidence. Scores CAN update because new research was introduced.</p>
              <p><span className="text-gray-300 font-medium">Deep Research</span> — Re-runs the Analyst agent with a focused task (e.g., "Find direct competitors in supply chain planning"). Merges new findings into existing research, then full rescores.</p>
              <p><span className="text-gray-300 font-medium">↻ Rerate (bulk)</span> — Classification-only refresh. Scores stay frozen — used to update GTM, category, and tags without introducing variance.</p>
              <p><span className="text-gray-300 font-medium">⚖ Calibrate 75+</span> — Full rescore of all 75+ opportunities with the latest rubric version, including new Devil's Advocate analysis. Use after rubric updates.</p>
            </div>
          </section>

          {/* Devil's Advocate */}
          <section>
            <h3 className="text-xs font-semibold text-amber-600 uppercase tracking-wider mb-3">Devil's Advocate</h3>
            <p className="text-xs text-gray-400 leading-relaxed">Every opportunity gets a counter-analysis: a bear case narrative, up to 5 specific risks (market, competitive, technical, regulatory, execution), and a "biggest threat" — the single most dangerous risk. Generated by the same rater using the full research context, designed to challenge the bull case assumptions.</p>
          </section>

        </div>
      </div>
    </div>
  )
}
