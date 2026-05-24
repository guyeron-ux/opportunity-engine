from __future__ import annotations
from backend.agents.base import BaseAgent

SYSTEM_PROMPT = """You are a community signal scout hunting for authentic, under-the-radar startup opportunities
expressed by practitioners — not observers.

Go beyond Reddit and Hacker News. The most valuable signals come from people who do the work:
operators, field technicians, compliance officers, supply chain managers, clinicians, attorneys.
They complain in professional forums, LinkedIn threads, specialized Slack communities, and niche subreddits.

What makes a strong signal:
- A recurring complaint that gets upvoted across multiple threads, months apart
- A workaround so painful that people describe it in detail ("we export to Excel, then manually cross-reference...")
- "I can't believe there's no software for X" in a specific operational context
- A failed product attempt that reveals the pain persisted after the company died
- A job posting that describes a role that should be automated but isn't

What makes a weak signal:
- Generic developer tool frustration (too horizontal)
- Consumer app complaints
- Anything where the commenter links to 3 existing solutions they just haven't tried

Signal strength (1-5): only return >= 3.
"""

SEARCH_QUERIES = [
    # Specific operational subreddits, not just r/startups
    'site:reddit.com (r/operations OR r/supplychain OR r/manufacturing OR r/healthcareit OR r/legaladvice) "wish there was" OR "no software" OR "manually" 2025',
    # Professional frustration with no obvious solution
    '"no tool" OR "no software" OR "still manually" professional workflow enterprise frustration 2025',
    # Indie hackers niche discovery
    "indie hackers niche market underserved no competition validated pain 2025",
    # HN threads where people describe operational pain without finding solutions
    'site:news.ycombinator.com "Ask HN" "no good solution" OR "nothing exists" OR "build this" specific tool 2025',
    # LinkedIn practitioner complaints (often surface domain-specific operational pain)
    "LinkedIn practitioner operator frustrated manual process industry specific 2025",
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
            prompt = f"""Analyze these community posts and extract startup opportunity signals from authentic practitioner pain.

{context}

Look for recurring, specific operational pain described by people who do the work — not observers or journalists.
Ignore complaints where multiple existing solutions are obvious. Focus on the gap between the pain and what's available.

Return a JSON array. Each signal:
{{
  "title": "specific opportunity title — name the domain and the operational gap",
  "pain_point": "the pain in the practitioner's own words if possible — specific, not abstract",
  "affected_segment": "who specifically (job role, industry, company size)",
  "signal_strength": 1-5,
  "recurrence_evidence": "how widespread or repeated this pain appears across sources",
  "source_urls": ["url1"],
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
