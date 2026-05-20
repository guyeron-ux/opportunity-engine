from __future__ import annotations
from backend.agents.base import BaseAgent

SYSTEM_PROMPT = """You are a startup opportunity analyst. Given a raw pain-point signal, you conduct
deep multi-step research to produce a comprehensive opportunity analysis.

Your research protocol:
1. Initial research: validate the pain point, find corroborating evidence
2. Competitive landscape: identify all current solutions and their gaps
3. Market deep-dive: TAM/SAM/SOM estimates, growth rates, key segments
4. Monetization: viable business models, pricing benchmarks, unit economics hints
5. Synthesis: structured analysis output

Be rigorous. Cite sources. Identify at least 3 corroborating sources, 5 competitors,
and 2 monetization models minimum.
"""


class AnalystAgent(BaseAgent):
    def __init__(self):
        super().__init__("analyst")

    def analyze(self, signal: dict, extra_context: str = "") -> dict:
        raw_title = signal.get("title", "")
        _generic = {"unknown", "unknown opportunity", "untitled", ""}
        title = raw_title if raw_title.lower() not in _generic else signal.get("pain_point_summary", raw_title)[:80]
        pain_point = signal.get("pain_point", signal.get("pain_point_summary", ""))
        segment = signal.get("affected_segment", signal.get("market", ""))
        self._log.info("Analyst: analyzing '%s'", title)

        # Step 1: Validate pain point
        validation_results = self.web_search(
            f"{title} pain point problem {segment} 2025", max_results=5
        )
        corroboration = self.web_search(
            f'"{pain_point[:60]}" problem complaints users 2025', max_results=3
        )

        # Step 2: Competitive landscape
        competitor_results = self.web_search(
            f"{title} competitors alternatives solutions market 2025", max_results=6
        )
        competitor_gaps = self.web_search(
            f"{title} why existing solutions fail limitations 2025", max_results=3
        )

        # Step 3: Market size
        market_results = self.web_search(
            f"{title} market size TAM revenue growth rate 2025", max_results=4
        )

        # Step 4: Monetization
        monetization_results = self.web_search(
            f"{title} business model pricing SaaS subscription revenue 2025", max_results=3
        )

        def fmt(results: list[dict]) -> str:
            return "\n".join(
                f"- [{r.get('title', '')}]({r.get('url', '')}): {r.get('content', '')[:400]}"
                for r in results
            )

        synthesis_prompt = f"""You have completed multi-step research on this startup opportunity.

**Opportunity Signal:**
Title: {title}
Pain Point: {pain_point}
Affected Segment: {segment}

**Research Gathered:**

PAIN POINT VALIDATION:
{fmt(validation_results + corroboration)}

COMPETITIVE LANDSCAPE:
{fmt(competitor_results + competitor_gaps)}

MARKET DATA:
{fmt(market_results)}

MONETIZATION:
{fmt(monetization_results)}

Now synthesize this into a structured analysis. Return a JSON object:
{{
  "title": "specific, descriptive opportunity name (NEVER 'Unknown' — always derive from research)",
  "pain_point_summary": "3-5 sentence summary of the validated pain point",
  "affected_segments": ["segment1", "segment2"],
  "market_size_estimate": "total industry/market size for context, e.g. '$2.3B global market'",
  "solution_tam_estimate": "direct TAM for this solution (revenue potential, not industry GMV), e.g. '$180M'",
  "tam_derivation": "show calculation: addressable segment × penetration % × unit price, e.g. '50k SMBs × 10% penetration × $3.6k/yr = $18M'",
  "market_growth_rate": "e.g. 18% CAGR",
  "competitors": [
    {{"name": "CompanyX", "weakness": "why it falls short", "url": "..."}}
  ],
  "monetization_models": ["SaaS subscription $X/mo", "usage-based pricing"],
  "solution_hypothesis": "2-3 sentences on how a startup could win this market",
  "sources": ["url1", "url2", "url3"],
  "signal_sources": ["original signal source urls"]
}}

Return valid JSON only, no markdown. Include at least 5 competitors and 2 monetization models."""

        if extra_context:
            synthesis_prompt += f"\n\nADDITIONAL RESEARCH FOCUS:\n{extra_context}"

        try:
            report = self._call_json(
                [{"role": "user", "content": synthesis_prompt}],
                system=SYSTEM_PROMPT,
                max_tokens=6000,
            )
            # Attach original signal data
            report["raw_signals"] = [signal]
            report["signal_sources"] = signal.get("source_urls", [])
            self._log.info("Analyst: completed analysis for '%s'", title)
            return report
        except Exception as e:
            self._log.error("Analyst synthesis failed for '%s': %s", title, e)
            return {
                "title": title,
                "pain_point_summary": pain_point,
                "affected_segments": [segment],
                "market_size_estimate": "Unknown",
                "market_growth_rate": "Unknown",
                "competitors": [],
                "monetization_models": [],
                "solution_hypothesis": "",
                "sources": [],
                "signal_sources": signal.get("source_urls", []),
                "raw_signals": [signal],
                "error": str(e),
            }
