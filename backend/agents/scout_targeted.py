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
            "electric grid interconnection queue permitting backlog software startup opportunity 2025",
            "curtailment renewable energy wasted electricity grid congestion startup solution 2025",
            "distributed energy resource DERMS aggregation small utility cooperative startup 2025",
            "industrial process heat decarbonization startup hard-to-abate cement steel chemicals 2025",
            "high temperature heat pump electrification factory industrial startup 2025",
            "green hydrogen electrolyzer operations software maintenance startup 2025",
            "battery energy storage BESS degradation warranty asset management startup 2025",
            "offshore wind operations maintenance logistics software remote inspection startup 2025",
            "coal plant decommission repurpose stranded asset brownfield energy startup 2025",
            "nuclear power plant software modernization aging infrastructure startup 2025",
            "small modular reactor SMR supply chain qualification startup 2025",
            "energy community virtual net metering peer-to-peer trading software startup 2025",
            "carbon border adjustment CBAM compliance manufacturing energy startup 2025",
            "capacity market auction bidding optimization software startup 2025",
            "long duration energy storage flow battery compressed air thermal startup market 2025",
            "industrial demand response curtailment automation startup commercial industrial 2025",
            "power purchase agreement PPA structuring software corporate buyer startup 2025",
            "grid interconnection study software automation renewable developer startup 2025",
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
            "tier 2 tier 3 supplier mapping financial health monitoring startup OEM risk 2025",
            "specialty chemical supply chain single source dependency concentration risk startup 2025",
            "rare earth critical mineral supply chain traceability software startup manufacturer 2025",
            "nearshoring reshoring site selection supplier discovery intelligence startup 2025",
            "contract manufacturer capacity visibility demand matching software startup 2025",
            "legacy CNC machine retrofit IoT sensor data brownfield manufacturing startup 2025",
            "predictive quality scrap rework reduction manufacturing AI startup 2025",
            "industrial metrology calibration data management software startup factory 2025",
            "MRO maintenance repair operations inventory procurement inefficiency startup 2025",
            "industrial spare parts supply chain obsolescence management startup manufacturer 2025",
            "PFAS restriction chemical supply chain compliance reporting software manufacturer 2025",
            "conflict minerals responsible sourcing CMRT automation startup 2025",
            "food safety supply chain traceability FSMA 204 compliance software startup 2025",
            "manufacturing workforce upskilling automation reskilling gap software startup 2025",
            "frontline worker knowledge capture tribal knowledge manufacturing startup 2025",
            "semiconductor supply chain alternate source qualification startup fabless 2025",
            "cold chain excursion monitoring pharmaceutical biologics logistics startup 2025",
            "active pharmaceutical ingredient API supply chain risk China India dependency startup 2025",
        ],
    },
}


class TargetedScoutAgent(BaseAgent):
    """Runs targeted domain-specific web searches and extracts opportunity signals."""

    def __init__(self):
        super().__init__("scouts")

    def run_domain(self, domain: str) -> list[dict]:
        """Run all queries for a domain and return extracted signals."""
        config = DOMAINS.get(domain)
        if not config:
            self._log.error("Unknown domain: %s", domain)
            return []

        system = config["system"]
        queries = config["queries"]
        raw_signals: list[dict] = []

        self._log.info("TargetedScout[%s]: running %d queries", domain, len(queries))

        for query in queries:
            results = self.web_search(query, max_results=5)
            if not results:
                continue

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
                    raw_signals.extend(qualified)
                    self._log.info("TargetedScout[%s] query '%s...' → %d signals", domain, query[:50], len(qualified))
            except Exception as e:
                self._log.error("TargetedScout[%s] extraction error for '%s': %s", domain, query[:50], e)

        self._log.info("TargetedScout[%s]: total %d raw signals", domain, len(raw_signals))
        return raw_signals
