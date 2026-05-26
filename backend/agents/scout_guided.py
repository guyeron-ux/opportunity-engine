from __future__ import annotations
from backend.agents.base import BaseAgent


class GuidedScoutAgent(BaseAgent):
    """
    Takes a plain-language research prompt and uses the LLM to generate
    targeted search queries, then runs them through Tavily to extract signals.
    """

    def __init__(self):
        super().__init__("scouts")

    def generate_queries(self, prompt: str, n: int = 6) -> list[str]:
        """Ask the LLM to generate n search queries from a plain-language prompt."""
        system = """You are a search query strategist. Given a research directive,
generate concise, specific web search queries that will find relevant articles,
reports, and practitioner discussions. Each query should target a distinct angle.
Return ONLY a JSON array of strings. No explanation."""

        user = f"""Research directive: {prompt}

Generate {n} search queries to find startup opportunity signals related to this topic.
Each query should be 4-8 words, specific enough to return focused results,
covering different angles: market pain, competitive landscape, regulation, technology gaps.

Return a JSON array of {n} strings."""

        try:
            queries = self._call_json(
                [{"role": "user", "content": user}],
                system=system,
                max_tokens=500,
                temperature=0.4,
            )
            if isinstance(queries, list):
                return [str(q).strip() for q in queries if q][:n]
        except Exception as e:
            self._log.error("GuidedScout query generation failed: %s", e)
        return []

    def query_signals_raw(self, query: str, prompt: str) -> list[dict]:
        """Run a single query in the context of a prompt and return signals."""
        results = self.web_search(query, max_results=5)
        if not results:
            return []

        context = "\n\n".join(
            f"Source: {r.get('url', '')}\nTitle: {r.get('title', '')}\n"
            f"Content: {r.get('content', '')[:600]}"
            for r in results
        )
        system = f"You are a startup opportunity scout. Research focus: {prompt}\nSignal strength (1-5): only return >= 3."
        extraction_prompt = f"""Analyze these articles and extract startup opportunity signals relevant to: {prompt}

{context}

Return a JSON array. Each signal:
{{
  "title": "specific opportunity title",
  "pain_point": "specific pain with evidence",
  "affected_segment": "who is affected and scale",
  "signal_strength": 1-5,
  "why_non_obvious": "what makes this easy to overlook",
  "source_urls": ["url1"],
  "query_used": "{query}"
}}

Only include signals with signal_strength >= 3. Return ONLY a valid JSON array."""

        try:
            signals = self._call_json(
                [{"role": "user", "content": extraction_prompt}],
                system=system,
                max_tokens=2000,
                temperature=0.2,
            )
            if isinstance(signals, list):
                return [s for s in signals if s.get("signal_strength", 0) >= 3]
        except Exception as e:
            self._log.error("GuidedScout error for '%s': %s", query[:50], e)
        return []

    def run(self, prompt: str, n_queries: int = 6) -> list[dict]:
        """Generate queries from prompt and extract signals."""
        self._log.info("GuidedScout: generating queries for: %s", prompt[:80])
        queries = self.generate_queries(prompt, n=n_queries)
        if not queries:
            self._log.error("GuidedScout: no queries generated")
            return []

        self._log.info("GuidedScout: running %d queries", len(queries))
        raw_signals: list[dict] = []

        system = f"""You are a startup opportunity scout. Given the research focus below,
extract non-obvious startup opportunity signals from the provided articles.

Research focus: {prompt}

Signal strength (1-5): only return >= 3. Be demanding."""

        for query in queries:
            results = self.web_search(query, max_results=5)
            if not results:
                continue

            context = "\n\n".join(
                f"Source: {r.get('url', '')}\nTitle: {r.get('title', '')}\n"
                f"Content: {r.get('content', '')[:600]}"
                for r in results
            )

            extraction_prompt = f"""Analyze these articles and extract startup opportunity signals relevant to: {prompt}

{context}

Return a JSON array. Each signal:
{{
  "title": "specific opportunity title",
  "pain_point": "specific pain point with evidence",
  "affected_segment": "who is affected and at what scale",
  "signal_strength": 1-5,
  "why_non_obvious": "what makes this easy to overlook",
  "source_urls": ["url1"],
  "query_used": "{query}"
}}

Only include signals with signal_strength >= 3. Return ONLY a valid JSON array."""

            try:
                signals = self._call_json(
                    [{"role": "user", "content": extraction_prompt}],
                    system=system,
                    max_tokens=2000,
                    temperature=0.2,
                )
                if isinstance(signals, list):
                    qualified = [s for s in signals if s.get("signal_strength", 0) >= 3]
                    raw_signals.extend(qualified)
                    self._log.info("GuidedScout query '%s' → %d signals", query[:50], len(qualified))
            except Exception as e:
                self._log.error("GuidedScout extraction error for '%s': %s", query[:50], e)

        self._log.info("GuidedScout: total %d signals", len(raw_signals))
        return raw_signals
