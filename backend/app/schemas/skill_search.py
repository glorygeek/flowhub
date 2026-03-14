from pydantic import BaseModel, Field

from app.schemas.skill_contract import SkillContractRead


class SkillSearchResultRead(BaseModel):
    skill: SkillContractRead
    search_score: float
    retrieval_source: str
    official_score: float | None = None
    quality_score: float = 0.0
    quality_tier: str = "basic"
    trust_signals: list[str] = Field(default_factory=list)
    security_score: float = 0.0
    security_tier: str = "caution"
    security_verdict: str = "manual_review_required"
    security_flags: list[str] = Field(default_factory=list)
    matched_terms: list[str] = Field(default_factory=list)
    matched_tags: list[str] = Field(default_factory=list)
    ranking_reasons: list[str] = Field(default_factory=list)
