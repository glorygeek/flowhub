from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SearchPolicyRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    intent_key: str
    description: str
    reason: str
    conditions: dict
    score_delta: float
    priority: int
    active: bool
    created_at: datetime
    updated_at: datetime


class SearchPolicyRuleUpdate(BaseModel):
    description: str | None = None
    reason: str | None = None
    conditions: dict | None = None
    score_delta: float | None = None
    priority: int | None = Field(default=None, ge=0, le=1000)
    active: bool | None = None
    change_note: str | None = None
    actor: str | None = None


class SearchPolicyRollbackRequest(BaseModel):
    change_note: str | None = None
    actor: str | None = None
