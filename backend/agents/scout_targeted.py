from __future__ import annotations
from backend.agents.base import BaseAgent

# ---------------------------------------------------------------------------
# Domain definitions: system prompts + query banks
# ---------------------------------------------------------------------------

DOMAINS: dict[str, dict] = {
    "energy": {
        "system": """You are a startup opportunity scout focused on the ENERGY sector.

Look for non-obvious opportunities: grid infrastructure bottlenecks, hard-to-abate industrial decarbonization,
stranded asset transitions, behind-the-meter optimization, clean energy supply chain gaps,
new regulatory frameworks, data layers for grid operators and energy traders.

Signal strength (1-5): only return >= 3. Be demanding — a 5 requires quantified pain, real buyers, defensible wedge.""",

        "queries": [
            "renewable energy interconnection queue risk software developers",
            "industrial heat decarbonization cement steel hard-to-abate software",
            "battery storage BESS asset management degradation warranty",
            "offshore wind operations maintenance logistics software gap",
            "virtual power plant capacity market bidding optimization",
            "carbon border adjustment CBAM compliance software exporters",
            "coal plant decommissioning brownfield repurpose grid connection",
        ],
    },

    "manufacturing": {
        "system": """You are a startup opportunity scout focused on MANUFACTURING and SUPPLY CHAIN.

Look for non-obvious opportunities: sub-tier supplier risks, reshoring gaps, legacy factory equipment with no software layer,
specialty material compliance burdens, MRO inefficiency, geopolitical supply chain fragility,
contract manufacturer visibility gaps, hidden quality control costs.

Signal strength (1-5): only return >= 3. Be demanding — a 5 requires quantified pain, specific buyers, defensible wedge.""",

        "queries": [
            "tier 2 tier 3 supplier financial risk monitoring OEM manufacturing",
            "MRO maintenance repair operations procurement inefficiency manufacturer",
            "reshoring supplier qualification discovery platform manufacturer",
            "legacy factory equipment data capture quality control retrofit",
            "PFAS supply chain compliance chemical substitution manufacturer",
            "contract manufacturer capacity visibility demand planning software",
            "pharmaceutical active ingredient supply chain single source risk",
        ],
    },
}


class TargetedScoutAgent(BaseAgent):
    """Runs targeted domain-specific web searches and extracts opportunity signals."""

    def __init__(self):
        super().__init__("scouts")

    def query_signals(self, query: str, domain: str) -> list[dict]:
        """Run a single query for a domain and return extracted signals."""
        config = DOMAINS.get(domain)
        if not config:
            return []
        system = config["system"]

        results = self.web_search(query, max_results=5)
        if not results:
            return []

        context = "\n\n".join(
            f"Source: {r.get('url', '')}\nTitle: {r.get('title', '')}\n"
            f"Content: {r.get('content', '')[:800]}"
            for r in results
        )

        prompt = f"""Analyze these articles and extract non-obvious startup opportunity signals in the {domain} sector.

{context}

Return a JSON array. Each signal:
{{
  "title": "specific opportunity title — name the exact niche and wedge",
  "pain_point": "specific pain point with quantified evidence where possible",
  "affected_segment": "who exactly is affected and estimated economic scale",
  "signal_strength": 1-5,
  "why_non_obvious": "what makes this easy to overlook or underestimate",
  "source_urls": ["url1"],
  "query_used": "{query}"
}}

Only include signals with signal_strength >= 3. Be demanding about quality.
Return ONLY a valid JSON array. No narration, no markdown, no explanation before or after."""

        try:
            signals = self._call_json(
                [{"role": "user", "content": prompt}],
                system=system,
                max_tokens=2000,
                temperature=0.2,
            )
            if isinstance(signals, list):
                qualified = [s for s in signals if s.get("signal_strength", 0) >= 3]
                self._log.info("TargetedScout[%s] '%s...' → %d signals", domain, query[:50], len(qualified))
                return qualified
        except Exception as e:
            self._log.error("TargetedScout[%s] error for '%s': %s", domain, query[:50], e)
        return []

    def get_queries(self, domain: str) -> list[str]:
        return DOMAINS.get(domain, {}).get("queries", [])
