import type { Opportunity } from '../api'

// ---------------------------------------------------------------------------
// Markdown
// ---------------------------------------------------------------------------

export function opportunityToMarkdown(opp: Opportunity): string {
  const r = opp.ratings
  const cls = opp.classification
  const res = opp.research
  const score = Math.round(opp.composite_score)

  const lines: string[] = [
    `# ${opp.title}`,
    ``,
    `**Score:** ${score} · **${cls.type}** · ${cls.go_to_market} · ${cls.industry} · ${cls.category}`,
    ``,
    `---`,
    ``,
    `## Pain Point`,
    ``,
    res.pain_point_summary,
    ``,
    res.affected_segments.length > 0 ? `**Affected Segments:** ${res.affected_segments.join(', ')}` : '',
    ``,
    `## Market`,
    ``,
    `- **Solution TAM:** ${r.market_size.solution_tam || res.solution_tam_estimate || '—'}`,
    `- **Industry Size:** ${r.market_size.industry_size || res.market_size_estimate || '—'}`,
    `- **Growth Rate:** ${res.market_growth_rate || '—'}`,
    res.tam_derivation ? `- **Derivation:** ${res.tam_derivation}` : '',
    ``,
    `## Score Breakdown`,
    ``,
    `| Factor | Score | Weight | Rationale |`,
    `|--------|------:|------:|-----------|`,
    `| Market Size | ${r.market_size.score} | 25% | ${r.market_size.rationale} |`,
    `| Pain Severity | ${r.pain_severity.score} | 25% | ${r.pain_severity.rationale} |`,
    `| Solution Clarity | ${r.solution_clarity.score} | 15% | ${r.solution_clarity.rationale} |`,
    `| Competitive Insight | ${r.competitive_insight.score} | 15% | ${r.competitive_insight.rationale} |`,
    `| Monetization Potential | ${r.monetization_potential.score} | 15% | ${r.monetization_potential.rationale} |`,
    `| Signal Authority | ${r.signal_authority.score} | 5% | ${r.signal_authority.rationale} |`,
    `| **Composite** | **${score}** | | |`,
    ``,
  ]

  if (res.competitors.length > 0) {
    lines.push(`## Competitive Landscape`, ``)
    res.competitors.forEach(c =>
      lines.push(`- **${c.name}** — ${c.weakness}${c.url ? ` ([↗](${c.url}))` : ''}`)
    )
    lines.push(``)
  }

  if (res.monetization_models.length > 0) {
    lines.push(`## Monetization Models`, ``)
    res.monetization_models.forEach(m => lines.push(`- ${m}`))
    lines.push(``)
  }

  if (res.solution_hypothesis) {
    lines.push(`## Solution Hypothesis`, ``, res.solution_hypothesis, ``)
  }

  if (opp.devils_advocate?.bear_case) {
    const da = opp.devils_advocate
    lines.push(`## Devil's Advocate`, ``)
    lines.push(`**Bear Case:** ${da.bear_case}`, ``)
    if (da.biggest_threat) lines.push(`**Biggest Threat:** ${da.biggest_threat}`, ``)
    if (da.key_risks.length > 0) {
      lines.push(`**Key Risks:**`, ``)
      da.key_risks.forEach(risk => lines.push(`- ${risk}`))
      lines.push(``)
    }
  }

  if (cls.moonshot_justification) {
    lines.push(`## ${cls.type === 'Moonshot' ? 'Moonshot Criteria' : 'Why Pragmatic'}`, ``, cls.moonshot_justification, ``)
  }

  if (cls.tags.length > 0) {
    lines.push(`**Tags:** ${cls.tags.map(t => `#${t}`).join(' ')}`, ``)
  }

  if (res.sources.length > 0) {
    lines.push(`## Sources`, ``)
    res.sources.slice(0, 8).forEach(s => lines.push(`- ${s}`))
    lines.push(``)
  }

  return lines.filter(l => l !== undefined).join('\n')
}

export function exportToMarkdown(opps: Opportunity[]): void {
  const content = opps.map(opportunityToMarkdown).join('\n\n---\n\n')
  const filename =
    opps.length === 1
      ? `${opps[0].title.replace(/[^a-z0-9]+/gi, '-').toLowerCase().slice(0, 60)}.md`
      : `opportunities-export-${new Date().toISOString().slice(0, 10)}.md`
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

// ---------------------------------------------------------------------------
// PDF (HTML → print dialog → Save as PDF)
// ---------------------------------------------------------------------------

function opportunityToHTMLSection(opp: Opportunity): string {
  const r = opp.ratings
  const cls = opp.classification
  const res = opp.research
  const score = Math.round(opp.composite_score)
  const scoreColor = score >= 80 ? '#10b981' : score >= 60 ? '#ca8a04' : '#ef4444'

  const factorRow = (label: string, s: number, w: string, rationale: string) =>
    `<tr><td>${label}</td><td style="text-align:center">${s}</td><td style="text-align:center">${w}</td><td style="color:#555;font-size:0.8rem">${rationale}</td></tr>`

  return `
<div class="opp">
  <div style="display:flex;align-items:baseline;gap:1rem;margin-bottom:0.25rem">
    <span style="font-size:2.5rem;font-weight:900;color:${scoreColor}">${score}</span>
    <h1 style="margin:0;font-size:1.3rem">${opp.title}</h1>
  </div>
  <div style="color:#666;font-size:0.82rem;margin-bottom:1rem">
    ${cls.type} · ${cls.go_to_market} · ${cls.industry} · ${cls.category}
    ${cls.tags.length ? '· ' + cls.tags.map(t => `#${t}`).join(' ') : ''}
  </div>

  <h2>Pain Point</h2>
  <p>${res.pain_point_summary}</p>
  ${res.affected_segments.length ? `<p><strong>Segments:</strong> ${res.affected_segments.join(', ')}</p>` : ''}

  <h2>Market</h2>
  <ul>
    <li><strong>Solution TAM:</strong> ${r.market_size.solution_tam || res.solution_tam_estimate || '—'}</li>
    <li><strong>Industry Size:</strong> ${r.market_size.industry_size || res.market_size_estimate || '—'}</li>
    <li><strong>Growth Rate:</strong> ${res.market_growth_rate || '—'}</li>
    ${res.tam_derivation ? `<li><strong>Derivation:</strong> ${res.tam_derivation}</li>` : ''}
  </ul>

  <h2>Score Breakdown</h2>
  <table>
    <thead><tr><th>Factor</th><th>Score</th><th>Weight</th><th>Rationale</th></tr></thead>
    <tbody>
      ${factorRow('Market Size', r.market_size.score, '25%', r.market_size.rationale)}
      ${factorRow('Pain Severity', r.pain_severity.score, '25%', r.pain_severity.rationale)}
      ${factorRow('Solution Clarity', r.solution_clarity.score, '15%', r.solution_clarity.rationale)}
      ${factorRow('Competitive Insight', r.competitive_insight.score, '15%', r.competitive_insight.rationale)}
      ${factorRow('Monetization', r.monetization_potential.score, '15%', r.monetization_potential.rationale)}
      ${factorRow('Signal Authority', r.signal_authority.score, '5%', r.signal_authority.rationale)}
      <tr style="font-weight:bold"><td>Composite</td><td style="text-align:center">${score}</td><td></td><td></td></tr>
    </tbody>
  </table>

  ${res.competitors.length ? `
  <h2>Competitive Landscape</h2>
  <ul>${res.competitors.map(c => `<li><strong>${c.name}</strong> — ${c.weakness}</li>`).join('')}</ul>
  ` : ''}

  ${res.monetization_models.length ? `
  <h2>Monetization</h2>
  <ul>${res.monetization_models.map(m => `<li>${m}</li>`).join('')}</ul>
  ` : ''}

  ${res.solution_hypothesis ? `<h2>Solution Hypothesis</h2><p>${res.solution_hypothesis}</p>` : ''}

  ${opp.devils_advocate?.bear_case ? `
  <h2>Devil's Advocate</h2>
  <div class="da">
    <p>${opp.devils_advocate.bear_case}</p>
    ${opp.devils_advocate.biggest_threat ? `<p><strong>Biggest Threat:</strong> ${opp.devils_advocate.biggest_threat}</p>` : ''}
    ${opp.devils_advocate.key_risks.length ? `<ul>${opp.devils_advocate.key_risks.map(risk => `<li>${risk}</li>`).join('')}</ul>` : ''}
  </div>
  ` : ''}

  ${cls.moonshot_justification ? `
  <h2>${cls.type === 'Moonshot' ? 'Moonshot Criteria' : 'Why Pragmatic'}</h2>
  <p>${cls.moonshot_justification}</p>
  ` : ''}
</div>`
}

export function exportToPDF(opps: Opportunity[]): void {
  const pageTitle = opps.length === 1 ? opps[0].title : `${opps.length} Opportunities`
  const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>${pageTitle}</title>
<style>
  body { font-family: system-ui, -apple-system, sans-serif; max-width: 960px; margin: 0 auto; padding: 2rem; color: #111; font-size: 0.9rem; line-height: 1.5; }
  h1 { font-size: 1.35rem; margin: 0; }
  h2 { font-size: 0.85rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: #6d28d9; margin: 1.4rem 0 0.4rem; border-bottom: 1px solid #e5e7eb; padding-bottom: 0.2rem; }
  table { width: 100%; border-collapse: collapse; font-size: 0.82rem; margin: 0.5rem 0; }
  th { background: #f5f3ff; text-align: left; padding: 0.35rem 0.5rem; border: 1px solid #ddd; }
  td { padding: 0.35rem 0.5rem; border: 1px solid #ddd; vertical-align: top; }
  ul { padding-left: 1.25rem; margin: 0.4rem 0; }
  li { margin: 0.2rem 0; }
  p { margin: 0.4rem 0; }
  .da { background: #fffbeb; border-left: 4px solid #d97706; padding: 0.75rem 1rem; border-radius: 4px; margin: 0.5rem 0; }
  .opp { margin-bottom: 2rem; }
  .sep { border: none; border-top: 3px solid #e5e7eb; margin: 2.5rem 0; }
  @media print {
    .sep { page-break-after: always; border: none; }
    body { padding: 0; }
  }
</style>
</head>
<body>
${opps.map(opportunityToHTMLSection).join('<hr class="sep">')}
</body>
</html>`

  const win = window.open('', '_blank')
  if (win) {
    win.document.write(html)
    win.document.close()
    setTimeout(() => win.print(), 400)
  }
}
