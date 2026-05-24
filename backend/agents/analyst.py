from __future__ import annotations
from backend.agents.base import BaseAgent

SYSTEM_PROMPT = """You are a startup opportunity analyst with deep domain expertise and a healthy skepticism.
Given a raw pain-point signal, you conduct rigorous multi-step research to produce an honest, comprehensive
opportunity analysis — not a sales pitch.

Your research protocol:
1. Pain validation: corroborate the signal with real evidence; quantify scale and cost where possible
2. Competitive landscape: find ALL relevant players — incumbents, funded startups, AND incumbent AI feature additions
3. Build-vs-buy threat: assess whether enterprises can replicate this with LLM APIs + internal engineering in <3 months
4. Market sizing: derive the direct solution TAM, not the industry GMV
5. Monetization: identify proven models with unit economics

Critical standards:
- "AI-native" is NOT a differentiator in 2025-2026. Every major incumbent is shipping AI features.
  Evaluate the actual wedge: unique data, workflow lock-in, regulatory advantage, domain expertise.
- If a major incumbent (Salesforce, Microsoft, SAP, Workday, etc.) has already shipped an AI product
  in this exact space, that is a category-level threat — say so explicitly.
- If the build-vs-buy path is trivially cheap (<3 months, <$50k), that is a structural weakness —
  say so explicitly.
- Under-researched competitive landscapes are worse than honest uncertainty. Name the real players.
"""


class AnalystAgent(BaseAgent):
    def __init__(self):
        super().__init__("analyst")

    def analyze(self, signal: dict, extra_context: str = "") -> dict:
        raw_title = signal.get("title", "")
        _generic = {"unknown", "unknown opportunity", "untitled", ""}
        title = raw_title if raw_title.lower() not in _generic else signal.get("pain_point_summary", raw_title)[:80]
        pain_point = signal.get("pain_point", signal.get("pain_point_summary", ""))
        segment = signal.get("affected_segment", signal.get("market", ""))
        self._log.info("Analyst: analyzing '%s'", title)

        # Step 1: Validate pain point
        validation_results = self.web_search(
            f"{title} pain point problem {segment} 2025", max_results=5
        )
        corroboration = self.web_search(
            f'"{pain_point[:60]}" problem complaints users 2025', max_results=3
        )

        # Step 2: Competitive landscape — domain-specific, funded startups, gaps
        competitor_results = self.web_search(
            f"{title} competitors alternatives solutions market 2025", max_results=5
        )
        domain_incumbents = self.web_search(
            f"{segment} software vendors platforms market leaders enterprise 2025", max_results=5
        )
        funded_startups = self.web_search(
            f"{segment} startup funding raised series venture capital 2023 2024 2025", max_results=5
        )
        competitor_gaps = self.web_search(
            f"{title} why existing solutions fail limitations gaps 2025", max_results=3
        )

        # Step 2b: Incumbent AI features — what are the big platforms already shipping?
        incumbent_ai = self.web_search(
            f"{segment} AI feature launch Salesforce Microsoft SAP Workday Oracle Adobe 2024 2025", max_results=5
        )

        # Step 2c: Build-vs-buy — can enterprises DIY this with LLM APIs?
        build_vs_buy = self.web_search(
            f"build {title} internal tool LLM API enterprise DIY alternative {segment} 2024 2025", max_results=4
        )

        # Step 3: Market size
        market_results = self.web_search(
            f"{title} market size TAM revenue growth rate 2025", max_results=4
        )

        # Step 4: Monetization
        monetization_results = self.web_search(
            f"{title} business model pricing SaaS subscription revenue 2025", max_results=3
        )

        def fmt(results: list[dict]) -> str:
            return "\n".join(
                f"- [{r.get('title', '')}]({r.get('url', '')}): {r.get('content', '')[:400]}"
                for r in results
            )

        synthesis_prompt = f"""You have completed multi-step research on this startup opportunity.

**Opportunity Signal:**
Title: {title}
Pain Point: {pain_point}
Affected Segment: {segment}

**Research Gathered:**

PAIN POINT VALIDATION:
{fmt(validation_results + corroboration)}

COMPETITIVE LANDSCAPE (domain-specific incumbents + funded startups):
{fmt(competitor_results + domain_incumbents + funded_startups + competitor_gaps)}

INCUMBENT AI FEATURES (what big platforms are already shipping in this space):
{fmt(incumbent_ai)}

BUILD-VS-BUY THREAT (can enterprises DIY this with LLM APIs + internal engineering?):
{fmt(build_vs_buy)}

MARKET DATA:
{fmt(market_results)}

MONETIZATION:
{fmt(monetization_results)}

Synthesize this into a structured analysis. Return a JSON object:
{{
  "title": "specific, descriptive opportunity name (NEVER 'Unknown' — always derive from research)",
  "pain_point_summary": "3-5 sentence summary of the validated pain point with quantified evidence where possible",
  "affected_segments": ["segment1", "segment2"],
  "market_size_estimate": "total industry/market size for context, e.g. '$2.3B global market'",
  "solution_tam_estimate": "direct TAM for this solution (revenue potential, not industry GMV), e.g. '$180M'",
  "tam_derivation": "show calculation: addressable segment × penetration % × unit price, e.g. '50k SMBs × 10% penetration × $3.6k/yr = $18M'",
  "market_growth_rate": "e.g. 18% CAGR",
  "competitors": [
    {{"name": "CompanyX", "raised": "$45M Series B", "weakness": "why it falls short for this specific buyer", "url": "..."}}
  ],
  "incumbent_ai_threat": "2-3 sentences: which major platforms (Salesforce/MS/SAP/etc.) have already shipped AI features in this space, and how serious is that threat",
  "build_vs_buy_risk": "2-3 sentences: honest assessment of whether enterprise buyers could replicate this with Claude/GPT APIs + internal engineering, and at what cost/timeline",
  "monetization_models": ["SaaS subscription $X/mo", "usage-based pricing"],
  "solution_hypothesis": "2-3 sentences on how a startup could win despite competition — must name the specific wedge that survives incumbent AI and DIY risk",
  "sources": ["url1", "url2", "url3"],
  "signal_sources": ["original signal source urls"]
}}

REQUIREMENTS on competitors:
- Name domain-specific software vendors for this exact vertical — NOT generic tools
  Examples: supply chain → Blue Yonder/Kinaxis/o9; logistics → project44/FourKites;
  manufacturing ops → Plex/Arena/Epicor; HR tech → Workday/Rippling; proptech → Yardi/RealPage;
  legal → Clio/Relativity; fintech → Plaid/Stripe; healthcare → Epic/Veeva; etc.
- Include funded startups with their raise amounts ($XM Series Y) if known
- DO NOT list horizontal tools (Monday.com, Asana, Celonis, ServiceNow, generic ERP) unless they
  have a purpose-built product for this specific domain and buyer
- Minimum: 3 domain-specific incumbents + 3 funded startups = 6 minimum, target 8+
- For each: state market position, specific weakness for this buyer, differentiation angle

REQUIREMENTS on incumbent AI threat:
- Explicitly name which large platforms have shipped or announced AI features here
- If multiple have, say so — it raises the competitive bar substantially
- "No incumbent AI threat found" is valid only if you searched and genuinely found none

REQUIREMENTS on build-vs-buy:
- Be honest: if a mid-sized enterprise with a 3-person data team could replicate 80% of this
  in 3 months using Claude API + their existing data, that is a structural risk — say it
- Consider: what proprietary data, workflow integrations, or regulatory requirements make
  a vendor defensible vs. internal build?

NOTE: "AI-native" is not a differentiator — it is table stakes. The question is whether the
startup has something incumbents and DIY teams cannot easily replicate: unique data access,
workflow embedding, regulatory moats, or domain expertise at distribution.

Return valid JSON only, no markdown. Minimum 6 competitors, 2 monetization models."""

        if extra_context:
            synthesis_prompt += f"\n\nADDITIONAL RESEARCH FOCUS:\n{extra_context}"

        try:
            report = self._call_json(
                [{"role": "user", "content": synthesis_prompt}],
                system=SYSTEM_PROMPT,
                max_tokens=6000,
            )
            # Attach original signal data
            report["raw_signals"] = [signal]
            report["signal_sources"] = signal.get("source_urls", [])
            self._log.info("Analyst: completed analysis for '%s'", title)
            return report
        except Exception as e:
            self._log.error("Analyst synthesis failed for '%s': %s", title, e)
            return {
                "title": title,
                "pain_point_summary": pain_point,
                "affected_segments": [segment],
                "market_size_estimate": "Unknown",
                "market_growth_rate": "Unknown",
                "competitors": [],
                "incumbent_ai_threat": "",
                "build_vs_buy_risk": "",
                "monetization_models": [],
                "solution_hypothesis": "",
                "sources": [],
                "signal_sources": signal.get("source_urls", []),
                "raw_signals": [signal],
                "error": str(e),
            }
