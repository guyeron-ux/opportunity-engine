from __future__ import annotations
import json
from backend.agents.base import BaseAgent

SYSTEM_PROMPT = """You are a business intelligence scout specialized in identifying startup opportunities.
Your task is to analyze recent business news, financial reports, and industry publications to identify
genuine pain points and market gaps that represent viable startup opportunities.

Focus on sources: Bloomberg, Forbes, CNBC, Financial Times, Entrepreneur, Business Insider,
Wall Street Journal, Harvard Business Review.

For each opportunity signal you find, assess:
1. What specific problem or pain point is described?
2. Who is affected (segment, size)?
3. Why existing solutions are inadequate?
4. Signal strength (1-5 scale, where 5 = very strong evidence)

Return ONLY signals with signal_strength >= 3.
"""

SEARCH_QUERIES = [
    "startup opportunity market gap 2025 business",
    "enterprise pain point inefficiency solution 2025",
    "industry disruption unmet need market 2025",
    "SMB problem workflow automation opportunity",
    "B2B SaaS market gap underserved segment 2025",
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
            prompt = f"""Analyze these recent business articles and extract startup opportunity signals.

{context}

Return a JSON array of opportunity signals. Each signal must have:
{{
  "title": "brief opportunity title",
  "pain_point": "specific pain point description",
  "affected_segment": "who is affected",
  "signal_strength": 1-5,
  "source_urls": ["url1", "url2"],
  "market_hint": "any market size or growth hints mentioned",
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
                self._log.error("BusinessScout extraction error: %s", e)

        filtered = [s for s in raw_signals if s.get("signal_strength", 0) >= 3]
        self._log.info("BusinessScout: found %d qualifying signals", len(filtered))
        return filtered
