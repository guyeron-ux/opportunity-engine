from __future__ import annotations
import json
from backend.agents.base import BaseAgent

SYSTEM_PROMPT = """You are a business intelligence scout hunting for non-obvious startup opportunities.

Your mandate is to surface signals most analysts would miss — NOT the obvious "AI-native X" plays
every accelerator cohort is already building. The best signals connect a technology trend or
infrastructure shift from one domain with an unsolved operational pain in another.

What you're looking for:
- Regulatory or policy shifts that create a forced new software category
- An industry that is economically large but digitally embarrassingly primitive
- A technology proven at scale in one vertical (finance, logistics, defense) not yet applied elsewhere
- Post-M&A / post-consolidation gaps where a buyer segment is suddenly underserved
- Manual workflows so expensive that incumbents can't fix them without disrupting their own margins
- Infrastructure or API commoditization that removes a historical barrier and opens a new application layer

What you are NOT looking for:
- Any "AI wrapper" on an existing category with 3+ funded competitors
- Generic productivity or workflow tools that work across all industries
- Anything already described in TechCrunch as a hot category

Signal strength (1-5): only return >= 3. Ask yourself — would a smart person say "oh wow, I never thought of that"?
If the answer is no, it's a 2.
"""

SEARCH_QUERIES = [
    # Regulatory/compliance shifts forcing new software categories
    "new regulation compliance requirement enterprise software gap 2025 2026",
    # Industries economically large but digitally primitive
    "industry still uses spreadsheets fax paper manual process costly 2025",
    # Cross-sector technology transfer
    "technology methodology proven finance defense aerospace applied new industry sector 2025",
    # Post-acquisition gaps — underserved buyers after vendor consolidation
    "enterprise software vendor acquisition customers abandoned gap underserved 2025",
    # Infrastructure commoditization enabling new application layers
    "infrastructure API now commodity enables new startup application category 2025",
    # Skilled labor shortage forcing software to absorb expertise
    "skilled labor shortage expert knowledge workforce crisis software solution 2025",
    # Operational data trapped with no action loop
    "operational data collected unused siloed no software acts on it industry 2025",
]


class ScoutBusinessAgent(BaseAgent):
    def __init__(self):
        super().__init__("scouts")

    def run(self, since_hours: int = 24) -> list[dict]:
        self._log.info("BusinessScout: starting scan (last %dh)", since_hours)
        raw_signals: list[dict] = []

        for query in SEARCH_QUERIES:
            results = self.web_search(query, max_results=5)
            if not results:
                continue
            context = "\n\n".join(
                f"Source: {r.get('url', '')}\nTitle: {r.get('title', '')}\nContent: {r.get('content', '')[:600]}"
                for r in results
            )
            prompt = f"""Analyze these articles and extract non-obvious startup opportunity signals.

{context}

First ask: is this already being actively built by multiple funded startups? If yes, skip it.
Prefer signals that connect an underused technology with an overlooked industry pain point.

Return a JSON array. Each signal:
{{
  "title": "specific opportunity title — name the domain AND the wedge, never generic",
  "pain_point": "who bleeds money or time, and exactly why no existing solution fixes it",
  "affected_segment": "specific segment and rough economic scale",
  "signal_strength": 1-5,
  "why_non_obvious": "what makes this easy to overlook or underestimate",
  "source_urls": ["url1"],
  "market_hint": "any market size or growth data mentioned",
  "query_used": "{query}"
}}

Only include signals with signal_strength >= 3. Skip anything already crowded with funded players.
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
                self._log.error("BusinessScout extraction error: %s", e)

        filtered = [s for s in raw_signals if s.get("signal_strength", 0) >= 3]
        self._log.info("BusinessScout: found %d qualifying signals", len(filtered))
        return filtered
