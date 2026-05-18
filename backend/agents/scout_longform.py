from __future__ import annotations
from backend.agents.base import BaseAgent

SYSTEM_PROMPT = """You are a long-form content scout specialized in extracting startup opportunity signals
from in-depth analysis, research reports, and thought leadership content.

Your task is to analyze articles from Medium, TechCrunch, VentureBeat, Substack newsletters,
CB Insights reports, a16z blog, and similar long-form sources.

Look for:
- Detailed market analysis identifying gaps
- Industry expert opinions on emerging needs
- Deep dives into specific sector pain points
- Research-backed market opportunity identification
- "White space" analyses by investors/analysts

Signal strength (1-5): prioritize signals with data backing and expert authority.
Only return signals with signal_strength >= 3.
"""

SEARCH_QUERIES = [
    "TechCrunch VentureBeat market opportunity startup gap analysis 2025",
    "a16z andreessen horowitz market thesis opportunity 2025",
    "CB Insights emerging market gap disruption report 2025",
    "Substack newsletter startup opportunity whitespace 2025",
    "Medium deep dive market analysis unmet need B2B 2025",
]


class ScoutLongformAgent(BaseAgent):
    def __init__(self):
        super().__init__("scouts")

    def run(self, since_hours: int = 24) -> list[dict]:
        self._log.info("LongformScout: starting scan (last %dh)", since_hours)
        raw_signals: list[dict] = []

        for query in SEARCH_QUERIES:
            results = self.web_search(query, max_results=5)
            if not results:
                continue
            context = "\n\n".join(
                f"Source: {r.get('url', '')}\nTitle: {r.get('title', '')}\nContent: {r.get('content', '')[:800]}"
                for r in results
            )
            prompt = f"""Analyze these long-form articles and extract startup opportunity signals supported by research or expert analysis.

{context}

Return a JSON array. Each signal:
{{
  "title": "brief opportunity title",
  "pain_point": "specific pain point with evidence",
  "affected_segment": "who is affected and estimated size",
  "signal_strength": 1-5,
  "source_urls": ["url1"],
  "data_points": ["any stats or research cited"],
  "expert_signals": "any VC/analyst endorsement",
  "query_used": "{query}"
}}

Only include signals with signal_strength >= 3. Return [] if none qualify.
Return valid JSON array only, no markdown."""

            try:
                signals = self._call_json(
                    [{"role": "user", "content": prompt}],
                    system=SYSTEM_PROMPT,
                )
                if isinstance(signals, list):
                    raw_signals.extend(signals)
            except Exception as e:
                self._log.error("LongformScout extraction error: %s", e)

        filtered = [s for s in raw_signals if s.get("signal_strength", 0) >= 3]
        self._log.info("LongformScout: found %d qualifying signals", len(filtered))
        return filtered
