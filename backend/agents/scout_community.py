from __future__ import annotations
from backend.agents.base import BaseAgent

SYSTEM_PROMPT = """You are a community signal scout specialized in finding authentic startup opportunities
from developer and entrepreneur communities.

Your task is to scan Reddit, Hacker News, Indie Hackers, Product Hunt, and similar forums to find
genuine pain points expressed by real users — especially recurring complaints, "I wish someone would
build X" requests, and failed product attempts that reveal persistent unmet needs.

Assess each signal:
1. How often / strongly is this pain expressed?
2. Is the affected segment large enough to build a business?
3. Are existing solutions clearly inadequate?
4. Signal strength (1-5)

Only return signals with signal_strength >= 3.
"""

SEARCH_QUERIES = [
    'site:reddit.com "I wish there was" OR "why doesn\'t someone build" startup tool 2025',
    "site:news.ycombinator.com ask HN pain point problem software 2025",
    "indie hackers problem validation market gap 2025",
    "reddit developer frustration tool missing workflow 2025",
    "product hunt failed startup gap opportunity 2025",
]


class ScoutCommunityAgent(BaseAgent):
    def __init__(self):
        super().__init__("scouts")

    def run(self, since_hours: int = 24) -> list[dict]:
        self._log.info("CommunityScout: starting scan (last %dh)", since_hours)
        raw_signals: list[dict] = []

        for query in SEARCH_QUERIES:
            results = self.web_search(query, max_results=5)
            if not results:
                continue
            context = "\n\n".join(
                f"Source: {r.get('url', '')}\nTitle: {r.get('title', '')}\nContent: {r.get('content', '')[:600]}"
                for r in results
            )
            prompt = f"""Analyze these community posts and extract startup opportunity signals from authentic user pain points.

{context}

Return a JSON array. Each signal:
{{
  "title": "brief opportunity title",
  "pain_point": "specific pain point in user's own words",
  "affected_segment": "who is affected",
  "signal_strength": 1-5,
  "source_urls": ["url1"],
  "community_evidence": "how widespread/frequent this pain appears",
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
                self._log.error("CommunityScout extraction error: %s", e)

        filtered = [s for s in raw_signals if s.get("signal_strength", 0) >= 3]
        self._log.info("CommunityScout: found %d qualifying signals", len(filtered))
        return filtered
