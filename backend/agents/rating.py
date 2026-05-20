from __future__ import annotations
from datetime import datetime
from backend.agents.base import BaseAgent
from backend.models.opportunity import (
    OpportunityEntry, Ratings, RatingFactor, Classification, ResearchData
)
from backend.models.database import generate_opportunity_id, load_db

SYSTEM_PROMPT = """You are a startup opportunity rating specialist. Your job is to score opportunities
on a rigorous 6-factor rubric and classify them.

Scoring rubric (0-100 each):

1. MARKET SIZE (MS) — weight 25%
   Score on the DIRECT SOLUTION TAM — what the proposed platform or product can
   realistically capture as revenue — NOT the total industry spend or GMV.

   Derivation is required: identify the business model, apply realistic penetration
   (typically 1–15% of the addressable segment), and multiply by unit economics.

   Examples of correct derivation:
   - $22B global surrogacy market → E2E platform capturing 5% of deals at 8% take rate = ~$88M TAM → score 45
   - $500B logistics market → SaaS for 200k SMB carriers at $3k/yr = $600M TAM → score 72
   - $4T global payments → infrastructure layer at 0.1% of volume = $4B TAM → score 90

   90-100: Solution TAM $3B+
   70-89:  Solution TAM $500M–$3B
   50-69:  Solution TAM $100M–$500M
   30-49:  Solution TAM $20M–$100M
   0-29:   Solution TAM <$20M or highly speculative

2. PAIN SEVERITY (PS) — weight 25%
   90-100: Critical operational pain at massive scale — entire industries bleeding money or
           time, with no adequate solution. Users are desperate and vocal.
   70-89:  Significant daily friction affecting large segments
   50-69:  Moderate inconvenience
   30-49:  Nice-to-have improvement
   0-29:   Theoretical pain

3. SOLUTION CLARITY (SC) — weight 15%
   90-100: Clear MVP path, known tech stack, defined customer journey
   70-89:  Good direction with some ambiguity
   50-69:  General concept, implementation unclear
   0-49:   Vague or highly complex

4. COMPETITIVE INSIGHT (CI) — weight 15%
   90-100: Fragmented or sleeping-giant market — incumbents are legacy, slow, or mis-aligned.
           A focused challenger can own a defensible position.
   70-89:  Incumbent weaknesses clearly identified
   50-69:  Competitive but with exploitable niches
   0-49:   Dominant players with deep moats

5. MONETIZATION POTENTIAL (MP) — weight 15%
   90-100: Proven models with strong unit economics signals — clear path to $100M+ ARR
   70-89:  Clear path to sustainable revenue
   50-69:  Possible but uncertain
   0-49:   Unclear monetization

6. SIGNAL AUTHORITY (SA) — weight 5%
   90-100: Multiple authoritative sources (VCs actively investing, major industry press,
           regulatory/macro tailwinds)
   70-89:  Mix of authoritative and community signals
   50-69:  Mostly community signals
   0-49:   Single/weak sources

---

CLASSIFICATION — this is a binary judgment, not a score threshold. Apply it carefully:

MOONSHOT (uncommon — roughly 1 in 8 to 1 in 10 opportunities qualify):
  A Moonshot is an opportunity to build a category-defining, infrastructure-level company.
  If it succeeds, the winner owns the platform or standard that an entire industry runs on.

  Consumer examples: Uber (transportation OS), Stripe (payments infrastructure),
  Airbnb (hospitality marketplace), Duolingo (language learning platform).
  B2B/infra examples: Snowflake (data cloud), Twilio (comms infrastructure),
  Palantir (enterprise intelligence), Hugging Face (AI model infrastructure).

  ALL of the following must be true:
  1. TAM is $10B+ AND the market currently lacks a dominant platform or standard
  2. The pain is significant and widespread — affecting a large portion of an industry
     OR systemic within a major vertical (healthcare, finance, logistics, etc.).
     Does NOT need to affect every person on earth — industry-scale suffices.
  3. The solution creates a meaningful shift in HOW work is done or value is delivered —
     not simply automating an existing step or adding a feature layer
  4. A winning company could credibly reach $1B+ valuation by owning the new category
  5. There is a credible path to network effects, proprietary data moats, platform
     lock-in, or defensible infrastructure

  When in doubt, lean Moonshot if 4 of 5 criteria are clearly met and the 5th is
  plausible. Do NOT require certainty on all five — early-stage opportunities are
  inherently uncertain.

PRAGMATIC (the default for solid opportunities):
  A clear, executable business with proven demand and achievable differentiation.
  Strong candidate for a capital-efficient company in the $10M–$500M range.
  Excellent and worth building — but not positioned to own an entire industry category.
"""


class RatingAgent(BaseAgent):
    def __init__(self):
        super().__init__("rating")

    def rate(self, report: dict) -> OpportunityEntry | None:
        title = report.get("title", "Unknown")
        self._log.info("Rating: scoring '%s'", title)

        # Verify completeness
        sources = report.get("sources", [])
        competitors = report.get("competitors", [])
        models = report.get("monetization_models", [])

        if len(sources) < 1:
            self._log.warning("Rating: insufficient sources for '%s' (%d)", title, len(sources))
        if len(competitors) < 1:
            self._log.warning("Rating: insufficient competitors for '%s' (%d)", title, len(competitors))

        scoring_prompt = f"""Score this startup opportunity based on the rubric.

**Opportunity Report:**
Title: {title}
Pain Point: {report.get('pain_point_summary', '')}
Affected Segments: {report.get('affected_segments', [])}
Industry Market Size: {report.get('market_size_estimate', 'Unknown')}
Solution TAM (if pre-derived): {report.get('solution_tam_estimate', 'derive from data')}
Market Growth: {report.get('market_growth_rate', 'Unknown')}
Competitors: {report.get('competitors', [])}
Monetization Models: {models}
Solution Hypothesis: {report.get('solution_hypothesis', '')}
Sources: {sources}

Return a JSON object with these exact keys:
{{
  "market_size": {{
    "score": 0-100,
    "industry_size": "total industry/market size for context",
    "solution_tam": "derived direct TAM for this solution (show calculation)",
    "rationale": "1-2 sentences justifying the score based on solution TAM",
    "evidence": ["key data point 1", "key data point 2"]
  }},
  "pain_severity": {{
    "score": 0-100,
    "rationale": "1-2 sentence justification",
    "evidence": ["evidence 1"]
  }},
  "solution_clarity": {{
    "score": 0-100,
    "rationale": "...",
    "evidence": []
  }},
  "competitive_insight": {{
    "score": 0-100,
    "rationale": "...",
    "evidence": []
  }},
  "monetization_potential": {{
    "score": 0-100,
    "rationale": "...",
    "evidence": []
  }},
  "signal_authority": {{
    "score": 0-100,
    "rationale": "...",
    "evidence": []
  }},
  "classification": {{
    "type": "Moonshot" or "Pragmatic",
    "moonshot_justification": "If Moonshot: which of the 5 criteria are met and why. If Pragmatic: why it does NOT qualify as a Moonshot.",
    "category": "SaaS|Marketplace|API|Platform|Hardware|Consumer|Other",
    "industry": "main industry vertical",
    "go_to_market": "who pays — B2B|B2C|B2G|B2B/B2C|B2B/B2G|B2C/B2G. B2G only when primary customer is government (federal/state/municipal). Use slash for mixed (B2B/B2G = sells to both businesses and govt).",
    "tech_stack": ["relevant tech"],
    "tags": ["3-5 descriptive tags"]
  }}
}}

IMPORTANT on classification: Be conservative. Moonshot is reserved for opportunities that
could genuinely restructure an entire industry and produce a unicorn or hectacorn.
Most strong opportunities are Pragmatic — that is not a lesser designation, it means
excellent and executable. Only classify as Moonshot if ALL five criteria in the system
prompt are clearly met.

Return valid JSON only, no markdown."""

        try:
            scored = self._call_json(
                [{"role": "user", "content": scoring_prompt}],
                system=SYSTEM_PROMPT,
                max_tokens=3000,
            )
        except Exception as e:
            self._log.error("Rating failed for '%s': %s", title, e)
            return None

        # Build OpportunityEntry
        db = load_db()
        opp_id = generate_opportunity_id(db)

        def make_factor(data: dict, extra: dict | None = None) -> RatingFactor:
            f = RatingFactor(
                score=max(0, min(100, int(data.get("score", 0)))),
                rationale=data.get("rationale", ""),
                evidence=data.get("evidence", []),
            )
            if extra:
                for k, v in extra.items():
                    if hasattr(f, k):
                        setattr(f, k, v)
            return f

        ms_data = scored.get("market_size", {})
        ratings = Ratings(
            market_size=make_factor(ms_data, {
                "solution_tam": ms_data.get("solution_tam", ""),
                "industry_size": ms_data.get("industry_size", ""),
            }),
            pain_severity=make_factor(scored.get("pain_severity", {})),
            solution_clarity=make_factor(scored.get("solution_clarity", {})),
            competitive_insight=make_factor(scored.get("competitive_insight", {})),
            monetization_potential=make_factor(scored.get("monetization_potential", {})),
            signal_authority=make_factor(scored.get("signal_authority", {})),
        )

        cls_data = scored.get("classification", {})
        classification = Classification(
            type=cls_data.get("type", "Pragmatic"),
            moonshot_justification=cls_data.get("moonshot_justification", ""),
            category=cls_data.get("category", "SaaS"),
            industry=cls_data.get("industry", "Technology"),
            go_to_market=cls_data.get("go_to_market", "B2B"),
            tech_stack=cls_data.get("tech_stack", []),
            tags=cls_data.get("tags", []),
        )

        research = ResearchData(
            pain_point_summary=report.get("pain_point_summary", ""),
            affected_segments=report.get("affected_segments", []),
            market_size_estimate=report.get("market_size_estimate", ""),
            solution_tam_estimate=report.get("solution_tam_estimate",
                ms_data.get("solution_tam", "")),
            tam_derivation=report.get("tam_derivation",
                ms_data.get("solution_tam", "")),
            market_growth_rate=report.get("market_growth_rate", ""),
            competitors=report.get("competitors", []),
            monetization_models=report.get("monetization_models", []),
            solution_hypothesis=report.get("solution_hypothesis", ""),
            sources=report.get("sources", []),
            signal_sources=report.get("signal_sources", []),
            raw_signals=report.get("raw_signals", []),
        )

        opp = OpportunityEntry(
            id=opp_id,
            title=title,
            composite_score=ratings.composite(),
            ratings=ratings,
            classification=classification,
            research=research,
            cycle_id=datetime.utcnow().strftime("%Y%m%d"),
        )

        self._log.info(
            "Rating: '%s' scored %.1f (type=%s)",
            title, opp.composite_score, classification.type
        )
        return opp
