from __future__ import annotations
from backend.agents.base import BaseAgent

SYSTEM_PROMPT = """You are a long-form content scout specialized in identifying non-obvious startup opportunities
from deep research, investor theses, and cross-domain analysis.

Your edge is connecting dots others miss:
- A technology platform maturing in one sector that could be the wedge in a totally different one
- A macro or demographic shift that changes cost structures or creates a new buyer with new budget
- A regulatory change that makes a previously unviable business model newly viable
- Academic or R&D advances 12-24 months from commercial application
- A VC thesis that names an emerging category before it's obvious
- An industry segment that is economically outsized relative to its software investment

You are NOT looking for:
- Already-crowded AI categories (AI writing, AI customer support, AI coding assistants)
- Opportunities where a16z or Sequoia has already announced a thesis and funded 5 companies
- Generic "digital transformation" of any horizontal process

Signal quality beats quantity. One sharp, non-obvious signal is worth ten obvious ones.
Signal strength (1-5): only return >= 3.
"""

SEARCH_QUERIES = [
    # VC investment in unusual, niche verticals — signals validated pain
    "venture capital investment niche vertical underrated overlooked sector 2026",
    # Cross-industry technology transfer analyses by researchers or analysts
    "technology transfer methodology from one industry applied another sector startup 2026",
    # Macro/regulatory shifts opening new market windows
    "policy change regulation opens new market category startup opportunity 2026",
    # Sectors large in economic weight, small in software penetration
    "large industry low software penetration digital gap opportunity 2026",
    # Emerging research nearing commercial inflection
    "research commercialize near-term application startup technology 2026",
    # Infrastructure shifts that remove historical barriers
    "infrastructure cost collapse enables new business model previously impossible 2026",
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
            prompt = f"""Analyze these long-form articles and extract non-obvious startup opportunity signals.

{context}

Ask: does this signal connect trends or technology from one domain with pain from another?
Is there a cross-industry insight here that most generalist analysts would miss?

Return a JSON array. Each signal:
{{
  "title": "specific opportunity title — name the domain and the cross-domain wedge if applicable",
  "pain_point": "specific pain point with evidence, ideally quantified",
  "affected_segment": "who is affected and estimated economic scale",
  "signal_strength": 1-5,
  "cross_domain_angle": "what insight from another domain or sector applies here (if any)",
  "source_urls": ["url1"],
  "data_points": ["any stats or research cited"],
  "expert_signals": "any VC/analyst/researcher endorsement",
  "query_used": "{query}"
}}

Only include signals with signal_strength >= 3. Return [] if none qualify.
Return valid JSON array only, no markdown."""

            try:
                signals = self._call_json(
                    [{"role": "user", "content": prompt}],
                    system=SYSTEM_PROMPT,
                    max_tokens=2000,
                )
                if isinstance(signals, list):
                    raw_signals.extend(signals)
            except Exception as e:
                self._log.error("LongformScout extraction error: %s", e)

        filtered = [s for s in raw_signals if s.get("signal_strength", 0) >= 3]
        self._log.info("LongformScout: found %d qualifying signals", len(filtered))
        return filtered
