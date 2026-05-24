from __future__ import annotations
import json
import re
from typing import Iterator

from backend.agents.base import BaseAgent


SYSTEM_TEMPLATE = """You are a senior VC analyst and trusted advisor — not an assistant. \
You have deep expertise in startups, go-to-market strategy, competitive dynamics, and market sizing.

Your job is to give your honest, unfiltered read on this opportunity. When the user challenges \
your analysis, engage seriously: defend your position with logic and evidence if you believe you're \
right, concede and update if their point is valid, or acknowledge genuine uncertainty where it exists. \
Never capitulate just to be agreeable, and never push back just to seem rigorous. \
The goal is to reach the most accurate assessment — not to satisfy, not to provoke.

Think of this as a peer conversation between two experienced investors stress-testing an analysis. \
You have a strong point of view. You are willing to be wrong, but you need to be convinced.

--- OPPORTUNITY CONTEXT ---
{context}
--- END CONTEXT ---

At the END of your reply only, append action tags when relevant:
- Append `[SUGGEST_RERATE]` when ANY of the following is true:
  • The user explicitly asks to rerate or rescore
  • The conversation has surfaced new facts that would materially change a score
  • You and the user have converged on a view that the current score is meaningfully off
  Do NOT wait for certainty — if the user asked for a rerate, always append it.
  Rerates go in whichever direction the evidence warrants — up or down. In practice,
  deeper scrutiny tends to surface overlooked risks and pull scores down, but a rerate
  that uncovers a missed strength or an under-appreciated market should move the score up.
- Append `[SUGGEST_EDIT:{{"field": "value"}}]` to suggest a specific field change (e.g., title, notes).

Be extremely concise. Default to 2-4 sentences. Bullets only for 3+ items.
No preamble, no restatement, no sign-off. Lead with the substance.
Expand only if the user asks."""


class ChatAgent(BaseAgent):
    def __init__(self):
        super().__init__("chat")

    def _build_context(self, opp) -> str:
        r = opp.ratings
        c = opp.classification
        res = opp.research
        competitors = ", ".join(
            f"{comp.get('name', '')} ({comp.get('weakness', '')})"
            for comp in res.competitors[:5]
        ) or "None identified"
        monetization = ", ".join(res.monetization_models[:4]) or "None identified"
        tags = ", ".join(c.tags[:8]) or "None"
        return f"""Title: {opp.title}
Composite Score: {opp.composite_score:.1f}/100
Type: {c.type} | GTM: {c.go_to_market} | Category: {c.category} | Industry: {c.industry}

SCORES:
- Market Size: {r.market_size.score}/100 — {r.market_size.rationale}
  Solution TAM: {r.market_size.solution_tam or res.solution_tam_estimate}
  TAM Derivation: {res.tam_derivation}
- Pain Severity: {r.pain_severity.score}/100 — {r.pain_severity.rationale}
- Solution Clarity: {r.solution_clarity.score}/100 — {r.solution_clarity.rationale}
- Competitive Insight: {r.competitive_insight.score}/100 — {r.competitive_insight.rationale}
- Monetization Potential: {r.monetization_potential.score}/100 — {r.monetization_potential.rationale}
- Startup Viability: {r.startup_viability.score}/100 — {r.startup_viability.rationale}
  (Capital Efficiency: {r.startup_viability.capital_efficiency}, Time to Revenue: {r.startup_viability.time_to_revenue}, Execution Accessibility: {r.startup_viability.execution_accessibility})
- Signal Authority: {r.signal_authority.score}/100 — {r.signal_authority.rationale}

PAIN POINT: {res.pain_point_summary}
AFFECTED SEGMENTS: {', '.join(res.affected_segments)}
MARKET SIZE: {res.market_size_estimate} | GROWTH: {res.market_growth_rate}
COMPETITORS: {competitors}
MONETIZATION: {monetization}
SOLUTION HYPOTHESIS: {res.solution_hypothesis}
TAGS: {tags}
NOTES: {opp.user.notes or 'None'}"""

    def stream_chat(self, opp, messages: list[dict]) -> Iterator[str]:
        system = SYSTEM_TEMPLATE.format(context=self._build_context(opp))
        yield from self._stream(messages, system=system)

    def parse_actions(self, text: str) -> tuple[str, list[dict]]:
        """Strip action tags from text and return (clean_text, actions)."""
        actions: list[dict] = []

        # Extract [SUGGEST_RERATE]
        if "[SUGGEST_RERATE]" in text:
            actions.append({"type": "rerate"})
            text = text.replace("[SUGGEST_RERATE]", "").strip()

        # Extract [SUGGEST_EDIT:{...}]
        edit_pattern = re.compile(r"\[SUGGEST_EDIT:(\{.*?\})\]", re.DOTALL)
        for match in edit_pattern.finditer(text):
            try:
                data = json.loads(match.group(1))
                actions.append({"type": "edit", "data": data})
            except json.JSONDecodeError:
                pass
        text = edit_pattern.sub("", text).strip()

        return text, actions
