from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


SecurityDecision = Literal[
    "safe_to_use",
    "use_with_caution",
    "manual_review_required",
    "block_or_quarantine",
]


class SkillSecurityOverrideRead(BaseModel):
    decision: SecurityDecision
    actor: str | None = None
    note: str | None = None
    updated_at: datetime | None = None


class SkillSecurityOverrideUpdate(BaseModel):
    decision: SecurityDecision | Literal["clear_override"]
    change_note: str | None = None
    actor: str | None = None


class SkillSecurityReviewRead(BaseModel):
    security_score: float = 0.0
    security_tier: str = "caution"
    security_verdict: str = "manual_review_required"
    security_flags: list[str] = Field(default_factory=list)
    permission_profile: dict[str, bool] = Field(default_factory=dict)
    moderation_verdict: str | None = None
    operator_override: SkillSecurityOverrideRead | None = None
