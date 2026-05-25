#!/usr/bin/env python3
"""
Targeted discovery cycle: Energy (5) + Manufacturing/Supply Chain (5) opportunities scoring >= 75.
Runs iteratively until targets are met.
"""
from __future__ import annotations
import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.agents.base import BaseAgent
from backend.agents.analyst import AnalystAgent
from backend.agents.rating import RatingAgent
from backend.models.database import add_opportunity, get_opportunities, _title_similarity

TARGET_SCORE = 75.0
TARGET_PER_DOMAIN = 5
DUPLICATE_THRESHOLD = 0.60  # slightly looser than global to catch near-duplicates early

# ---------------------------------------------------------------------------
# Domain-specific system prompts for signal extraction
# ---------------------------------------------------------------------------

ENERGY_SYSTEM = """You are a non-obvious startup opportunity scout focused exclusively on ENERGY sector opportunities.

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

Signal strength (1-5): only return >= 3. Be harsh — a 5 requires: quantified pain, real buyers identified, defensible wedge, non-obvious insight."""

MANUFACTURING_SYSTEM = """You are a non-obvious startup opportunity scout focused exclusively on MANUFACTURING and SUPPLY CHAIN opportunities.

Your edge is finding what procurement teams, investors, and generalist analysts overlook:
- Tier 2/3/4 supplier risks invisible to OEM procurement (financial health, geopolitical exposure, concentration)
- Reshoring/nearshoring creating new infrastructure and software gaps that don't yet have solutions
- Legacy factory equipment (10-30 years old) with zero software layer, owned by operators who can't afford full replacements
- Compliance burdens in specialty material supply chains (PFAS, rare earths, conflict minerals, food safety)
- MRO (maintenance, repair, operations) inefficiency: a $700B market with almost no modern software
- Workforce displacement as automation changes required skills but training lags
- Geopolitical fragility in specific supply chains: semiconductors, specialty chemicals, active pharma ingredients
- Contract manufacturers with zero visibility into their own capacity and customers' demand
- Industrial quality control: scrap, rework, warranty costs hidden in P&Ls

NOT looking for:
- Generic supply chain "visibility" platforms (Resilinc, Everstream — already crowded)
- Basic WMS or inventory management
- Generic demand forecasting
- Standard ERP modules
- Broad "Industry 4.0" digital transformation

Signal strength (1-5): only return >= 3. Be harsh — a 5 requires: quantified pain, identified buyer segment, real wedge, non-obvious angle."""

# ---------------------------------------------------------------------------
# Query banks — designed for non-obvious signal extraction
# ---------------------------------------------------------------------------

ENERGY_QUERIES = [
    # Grid / interconnection bottlenecks
    "electric grid interconnection queue permitting backlog software startup opportunity 2025",
    "curtailment renewable energy wasted electricity grid congestion startup solution 2025",
    "distributed energy resource DERMS aggregation small utility cooperative startup 2025",
    # Industrial heat / hard-to-abate
    "industrial process heat decarbonization startup hard-to-abate cement steel chemicals 2025",
    "high temperature heat pump electrification factory industrial startup 2025",
    "green hydrogen electrolyzer operations software maintenance startup 2025",
    # Asset lifecycle
    "battery energy storage BESS degradation warranty asset management startup 2025",
    "offshore wind operations maintenance logistics software remote inspection startup 2025",
    "coal plant decommission repurpose stranded asset energy startup 2025",
    # Nuclear
    "nuclear power plant software modernization aging infrastructure startup 2025",
    "small modular reactor SMR supply chain qualification startup 2025",
    # New market structures
    "energy community virtual net metering peer-to-peer trading startup 2025",
    "carbon border adjustment CBAM compliance manufacturing energy startup 2025",
    "capacity market auction bidding optimization software startup 2025",
    "long duration energy storage flow battery compressed air thermal startup market 2025",
    # Data / intelligence
    "energy data interoperability ESPI Green Button utility API startup 2025",
    "industrial demand response curtailment automation startup C&I customer 2025",
    "power purchase agreement PPA structuring software corporate buyer startup 2025",
]

MANUFACTURING_QUERIES = [
    # Supply chain visibility — non-obvious tiers
    "tier 2 tier 3 supplier mapping financial health monitoring startup OEM 2025",
    "specialty chemical supply chain single source dependency risk startup 2025",
    "rare earth critical mineral supply chain traceability software startup 2025",
    # Reshoring gaps
    "nearshoring reshoring site selection supplier discovery intelligence startup 2025",
    "contract manufacturer capacity visibility demand matching software startup 2025",
    # Legacy factory
    "legacy CNC machine retrofit IoT sensor data capture startup brownfield 2025",
    "predictive quality scrap rework reduction manufacturing AI startup 2025",
    "industrial metrology calibration data management software startup 2025",
    # MRO
    "MRO maintenance repair operations inventory procurement inefficiency startup 2025",
    "industrial spare parts supply chain obsolescence management startup 2025",
    # Compliance
    "PFAS restriction supply chain compliance reporting software manufacturer 2025",
    "conflict minerals responsible sourcing CMRT software automation startup 2025",
    "food safety supply chain traceability FSMA 204 compliance software startup 2025",
    # Workforce
    "manufacturing workforce upskilling automation reskilling gap software startup 2025",
    "frontline worker knowledge capture tribal knowledge manufacturing startup 2025",
    # Specific verticals
    "semiconductor supply chain alternate source qualification startup fabless 2025",
    "cold chain excursion monitoring pharmaceutical biologics logistics startup 2025",
    "active pharmaceutical ingredient API supply chain dependency India China startup 2025",
]


class TargetedScout(BaseAgent):
    """Runs targeted web searches and extracts domain-specific signals."""

    def __init__(self):
        super().__init__("targeted_scout")

    def extract_signals(self, query: str, system_prompt: str, domain: str) -> list[dict]:
        results = self.web_search(query, max_results=5)
        if not results:
            print(f"    [no search results]")
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
Return valid JSON array only, no markdown, no narration."""

        try:
            signals = self._call_json(
                [{"role": "user", "content": prompt}],
                system=system_prompt,
                max_tokens=2000,
                temperature=0.2,
            )
            if isinstance(signals, list):
                return [s for s in signals if s.get("signal_strength", 0) >= 3]
        except Exception as e:
            self._log.error("Signal extraction failed for query '%s': %s", query, e)
        return []


def is_near_duplicate(title: str, existing_titles: list[str], threshold: float = DUPLICATE_THRESHOLD) -> bool:
    return any(_title_similarity(title, t) >= threshold for t in existing_titles)


def run():
    print("=" * 70)
    print("TARGETED CYCLE: Energy (5) + Manufacturing/Supply Chain (5)")
    print(f"Target: score >= {TARGET_SCORE}, {TARGET_PER_DOMAIN} per domain")
    print("=" * 70)

    scout = TargetedScout()
    analyst = AnalystAgent()
    rater = RatingAgent()

    # Track qualifying opportunities per domain
    energy_opps: list = []
    manufacturing_opps: list = []

    # Track all titles seen (to avoid re-processing near-duplicates)
    seen_titles: list[str] = []

    # Seed with existing DB titles to avoid re-generating known opportunities
    existing = get_opportunities(threshold=0)
    existing_titles = [o.title for o in existing]
    print(f"Pre-loaded {len(existing_titles)} existing opportunity titles for dedup\n")

    def process_signal(signal: dict, domain: str) -> tuple[object | None, float]:
        title = signal.get("title", "").strip()
        if not title:
            return None, 0.0

        if is_near_duplicate(title, seen_titles) or is_near_duplicate(title, existing_titles):
            print(f"    [duplicate] {title[:70]}")
            return None, 0.0

        seen_titles.append(title)
        print(f"  → Analyzing: {title[:70]}")

        try:
            report = analyst.analyze(signal)
        except Exception as e:
            print(f"    [analyst error] {e}")
            return None, 0.0

        try:
            opp = rater.rate(report)
        except Exception as e:
            print(f"    [rater error] {e}")
            return None, 0.0

        if opp is None:
            print(f"    [rater returned None]")
            return None, 0.0

        score = opp.composite_score
        print(f"    Score: {score:.1f} {'✓ QUALIFYING' if score >= TARGET_SCORE else '✗ below threshold'}")
        return opp, score

    # --- ENERGY ROUND(S) ---
    print("\n[ENERGY DOMAIN]")
    energy_queries = list(ENERGY_QUERIES)
    query_idx = 0

    while len(energy_opps) < TARGET_PER_DOMAIN and query_idx < len(energy_queries):
        query = energy_queries[query_idx]
        query_idx += 1
        print(f"\nQuery {query_idx}/{len(energy_queries)}: {query[:80]}")

        signals = scout.extract_signals(query, ENERGY_SYSTEM, "Energy")
        print(f"  Signals extracted: {len(signals)}")

        for signal in signals:
            if len(energy_opps) >= TARGET_PER_DOMAIN:
                break
            opp, score = process_signal(signal, "Energy")
            if opp and score >= TARGET_SCORE:
                # Force industry classification to Energy
                if hasattr(opp, 'classification'):
                    opp.classification.industry = "Energy"
                saved = add_opportunity(opp)
                energy_opps.append(opp)
                print(f"    *** SAVED to DB [{score:.1f}] {opp.title[:60]} ***")

        print(f"  Energy qualifying so far: {len(energy_opps)}/{TARGET_PER_DOMAIN}")

    # --- MANUFACTURING ROUND(S) ---
    print("\n\n[MANUFACTURING / SUPPLY CHAIN DOMAIN]")
    manufacturing_queries = list(MANUFACTURING_QUERIES)
    query_idx = 0

    while len(manufacturing_opps) < TARGET_PER_DOMAIN and query_idx < len(manufacturing_queries):
        query = manufacturing_queries[query_idx]
        query_idx += 1
        print(f"\nQuery {query_idx}/{len(manufacturing_queries)}: {query[:80]}")

        signals = scout.extract_signals(query, MANUFACTURING_SYSTEM, "Manufacturing")
        print(f"  Signals extracted: {len(signals)}")

        for signal in signals:
            if len(manufacturing_opps) >= TARGET_PER_DOMAIN:
                break
            opp, score = process_signal(signal, "Manufacturing")
            if opp and score >= TARGET_SCORE:
                if hasattr(opp, 'classification'):
                    opp.classification.industry = "Manufacturing"
                saved = add_opportunity(opp)
                manufacturing_opps.append(opp)
                print(f"    *** SAVED to DB [{score:.1f}] {opp.title[:60]} ***")

        print(f"  Manufacturing qualifying so far: {len(manufacturing_opps)}/{TARGET_PER_DOMAIN}")

    # --- FINAL REPORT ---
    print("\n" + "=" * 70)
    print("FINAL RESULTS")
    print("=" * 70)

    print(f"\nENERGY ({len(energy_opps)}/{TARGET_PER_DOMAIN} qualifying):")
    for opp in energy_opps:
        print(f"  [{opp.composite_score:.1f}] {opp.title}")

    print(f"\nMANUFACTURING ({len(manufacturing_opps)}/{TARGET_PER_DOMAIN} qualifying):")
    for opp in manufacturing_opps:
        print(f"  [{opp.composite_score:.1f}] {opp.title}")

    total = len(energy_opps) + len(manufacturing_opps)
    print(f"\nTotal qualifying: {total}/10")
    if len(energy_opps) < TARGET_PER_DOMAIN or len(manufacturing_opps) < TARGET_PER_DOMAIN:
        print("WARNING: Did not reach target — increase query bank or lower threshold to investigate")

    return energy_opps, manufacturing_opps


if __name__ == "__main__":
    run()
