from __future__ import annotations
from backend.agents.base import BaseAgent

# ---------------------------------------------------------------------------
# Domain definitions: system prompts + query banks
# ---------------------------------------------------------------------------

DOMAINS: dict[str, dict] = {
    "energy": {
        "system": """You are a non-obvious startup opportunity scout focused exclusively on ENERGY sector opportunities.

Your edge is finding what most VCs and generalist analysts miss:
- Grid infrastructure bottlenecks that enable software plays (interconnection queue, permitting, curtailment)
- Industrial decarbonization in hard-to-abate sectors: cement, steel, chemicals, shipping, agriculture
- Stranded fossil asset transitions and brownfield repurposing (coal plants → storage/data centers)
- Behind-the-meter optimization for C&I customers with complex load profiles
- Supply chain gaps in the clean energy buildout: offshore wind, long-duration storage, nuclear SMRs
- Regulatory arbitrage from new policy frameworks (IRA tax credits, CBAM, capacity markets, clean hydrogen standards)
- Data and intelligence layers for grid operators, IPPs, and energy traders
- Water-energy nexus: industrial water treatment, cooling, desalination

NOT looking for:
- Basic solar/wind project development or EPC
- Generic "energy management" dashboards (crowded)
- EV charging networks (oversaturated)
- Carbon offset marketplaces
- Generic ESG reporting tools

Signal strength (1-5): only return >= 3. Be demanding — a 5 requires: quantified pain, real buyers identified, defensible wedge, non-obvious insight.""",

        "queries": [
            # Grid interconnection: 2,000+ GW stuck in queues, developers flying blind on withdrawal risk
            "renewable energy interconnection queue position risk modeling software developer",
            # Industrial heat: 20% of global energy use, almost no software addresses it
            "industrial process heat decarbonization cement steel glass hard-to-abate software gap",
            # BESS lifecycle: $50B+ deployed with no purpose-built asset management stack
            "battery energy storage system BESS degradation warranty revenue optimization software",
            # Offshore wind O&M: logistics nightmare, ~$25B/yr cost, no dominant software player
            "offshore wind operations maintenance vessel scheduling technician dispatch software",
            # Capacity markets: VPPs and aggregators losing revenue to manual bidding errors
            "virtual power plant capacity market ancillary services bidding optimization software",
            # CBAM: EU carbon border tax forces US/Asian exporters to quantify embedded carbon
            "carbon border adjustment mechanism CBAM embedded carbon calculation compliance software",
            # Brownfield: 250+ US coal plants closing, grid connections worth $millions, no repurposing software
            "coal plant decommissioning brownfield repurpose grid connection valuation software",
        ],
    },

    "manufacturing": {
        "system": """You are a non-obvious startup opportunity scout focused exclusively on MANUFACTURING and SUPPLY CHAIN opportunities.

Your edge is finding what procurement teams, investors, and generalist analysts overlook:
- Tier 2/3/4 supplier risks invisible to OEM procurement (financial health, geopolitical exposure, single-source concentration)
- Reshoring/nearshoring creating infrastructure and software gaps with no existing solutions
- Legacy factory equipment (10-30 years old) with zero software layer, owned by operators who can't afford full replacements
- Compliance burdens in specialty material supply chains (PFAS, rare earths, conflict minerals, food safety)
- MRO (maintenance, repair, operations) inefficiency: $700B+ market with almost no modern software
- Workforce displacement gaps as automation changes required skills but training lags
- Geopolitical fragility in specific supply chains: semiconductors, specialty chemicals, active pharma ingredients
- Contract manufacturers with zero visibility into their own capacity and customers' demand
- Industrial quality control hidden costs: scrap, rework, warranty buried in P&Ls

NOT looking for:
- Generic supply chain "visibility" platforms (already crowded)
- Basic WMS or inventory management
- Generic demand forecasting or ERP modules
- Standard "Industry 4.0" digital transformation pitches

Signal strength (1-5): only return >= 3. Be demanding — a 5 requires: quantified pain, specific buyer segment, real defensible wedge, non-obvious angle.""",

        "queries": [
            # Sub-tier supplier risk: OEMs only watch tier-1; tier-2/3 failures cause the actual disruptions
            "tier 2 tier 3 supplier financial distress early warning monitoring OEM manufacturing",
            # MRO: $700B market, 60%+ unplanned spend, almost no modern procurement software
            "MRO maintenance repair operations unplanned spend procurement optimization manufacturer",
            # Reshoring gap: manufacturers moving from China can't find qualified alternative suppliers
            "reshoring nearshoring supplier qualification discovery platform manufacturer US Mexico",
            # Legacy machine data: 80% of factory equipment has no connectivity, operators can't see quality data
            "legacy factory equipment brownfield data capture quality scrap retrofit manufacturer",
            # PFAS compliance: EPA PFAS rules forcing manufacturers to trace chemicals through supply chain
            "PFAS forever chemicals supply chain compliance material substitution manufacturer",
            # Contract mfg visibility: CMOs have no software to share capacity; customers can't plan
            "contract manufacturer capacity planning visibility demand signal sharing software",
            # API pharma: 80%+ of active pharma ingredients sourced from China/India, no monitoring tool
            "active pharmaceutical ingredient API supply chain single source risk monitoring software",
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
