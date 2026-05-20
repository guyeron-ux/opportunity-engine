from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class RatingFactor(BaseModel):
    score: int = Field(ge=0, le=100)
    rationale: str = ""
    evidence: list[str] = []


class Ratings(BaseModel):
    market_size: RatingFactor = Field(default_factory=lambda: RatingFactor(score=0))
    pain_severity: RatingFactor = Field(default_factory=lambda: RatingFactor(score=0))
    solution_clarity: RatingFactor = Field(default_factory=lambda: RatingFactor(score=0))
    competitive_insight: RatingFactor = Field(default_factory=lambda: RatingFactor(score=0))
    monetization_potential: RatingFactor = Field(default_factory=lambda: RatingFactor(score=0))
    signal_authority: RatingFactor = Field(default_factory=lambda: RatingFactor(score=0))

    def composite(self) -> float:
        return (
            self.market_size.score * 0.25
            + self.pain_severity.score * 0.25
            + self.solution_clarity.score * 0.15
            + self.competitive_insight.score * 0.15
            + self.monetization_potential.score * 0.15
            + self.signal_authority.score * 0.05
        )


class Classification(BaseModel):
    type: str = ""          # "Moonshot" | "Pragmatic"
    moonshot_justification: str = ""
    category: str = ""      # e.g. "SaaS", "Marketplace", "API"
    industry: str = ""
    tech_stack: list[str] = []
    tags: list[str] = []


class ResearchData(BaseModel):
    pain_point_summary: str = ""
    affected_segments: list[str] = []
    market_size_estimate: str = ""
    market_growth_rate: str = ""
    competitors: list[dict] = []
    monetization_models: list[str] = []
    solution_hypothesis: str = ""
    sources: list[str] = []
    signal_sources: list[str] = []
    raw_signals: list[dict] = []


class UserInteraction(BaseModel):
    notes: str = ""
    archived: bool = False
    archived_at: Optional[datetime] = None
    deeper_research_requested: bool = False
    last_viewed: Optional[datetime] = None


class OpportunityEntry(BaseModel):
    id: str
    title: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    composite_score: float = 0.0
    ratings: Ratings = Field(default_factory=Ratings)
    classification: Classification = Field(default_factory=Classification)
    research: ResearchData = Field(default_factory=ResearchData)
    user: UserInteraction = Field(default_factory=UserInteraction)
    cycle_id: str = ""


class ImportRecord(BaseModel):
    id: str
    filename: str
    imported_at: datetime = Field(default_factory=datetime.utcnow)
    signals_extracted: int = 0
    opportunities_added: int = 0


class DatabaseModel(BaseModel):
    opportunities: list[OpportunityEntry] = []
    archived_opportunities: list[OpportunityEntry] = []
    imports: list[ImportRecord] = []
    settings: dict = Field(default_factory=lambda: {
        "score_threshold": 70,
        "cycle_running": False,
        "last_cycle_run": None,
        "last_cycle_summary": None,
    })
    user_preferences: dict = Field(default_factory=lambda: {
        "filters": {},
        "notifications_enabled": True,
    })
