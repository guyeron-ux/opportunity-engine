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
   90-100: $10B+ TAM with clear, fast-growing trajectory (think payments, logistics, healthcare)
   70-89:  $1B-$10B TAM with strong tailwinds
   50-69:  $100M-$1B TAM
   30-49:  <$100M TAM
   0-29:   Niche/unclear market

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

MOONSHOT (rare — fewer than 1 in 10 opportunities qualify):
  A Moonshot is a once-in-a-decade market opportunity. If it succeeds, it does not just
  build a business — it fundamentally restructures how an entire industry operates.
  Think: Uber reimagined transportation, Stripe rebuilt payments infrastructure,
  Airbnb redefined hospitality, SpaceX reinvented launch.

  ALL of the following must be true to label something a Moonshot:
  1. TAM is $10B+ AND the market is structurally broken or ripe for platform displacement
  2. The pain is industry-wide and systemic — not a segment or workflow problem
  3. The solution requires (or enables) a genuine behavioral or technological shift
     at scale — not just a better UI on existing workflows
  4. If it works, the winner could realistically reach $1B+ valuation (unicorn) and
     potentially $100B+ (hectacorn) by owning the new category
  5. There is a credible path to network effects, platform lock-in, or
     defensible infrastructure that prevents easy replication

  When in doubt, do NOT classify as Moonshot. Reserve it for opportunities that
  genuinely meet all five criteria above.

PRAGMATIC (the default for high-quality opportunities):
  A solid, executable business opportunity. Clear market, proven demand, achievable
  differentiation. An excellent candidate for a capital-efficient, profitable company
  in the $10M–$500M revenue range. Important and worth building — just not
  industry-restructuring.
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
Market Size: {report.get('market_size_estimate', 'Unknown')}
Market Growth: {report.get('market_growth_rate', 'Unknown')}
Competitors: {report.get('competitors', [])}
Monetization Models: {models}
Solution Hypothesis: {report.get('solution_hypothesis', '')}
Sources: {sources}

Return a JSON object with these exact keys:
{{
  "market_size": {{
    "score": 0-100,
    "rationale": "1-2 sentence justification",
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

        def make_factor(data: dict) -> RatingFactor:
            return RatingFactor(
                score=max(0, min(100, int(data.get("score", 0)))),
                rationale=data.get("rationale", ""),
                evidence=data.get("evidence", []),
            )

        ratings = Ratings(
            market_size=make_factor(scored.get("market_size", {})),
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
            tech_stack=cls_data.get("tech_stack", []),
            tags=cls_data.get("tags", []),
        )

        research = ResearchData(
            pain_point_summary=report.get("pain_point_summary", ""),
            affected_segments=report.get("affected_segments", []),
            market_size_estimate=report.get("market_size_estimate", ""),
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
