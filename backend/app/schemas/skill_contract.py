from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.common import ExecutionMode, RiskLevel, ReviewStatus


class SkillContractBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    display_name: str = ""
    category: str = Field(min_length=1, max_length=80)
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    input_schema: dict = Field(default_factory=dict)
    output_schema: dict = Field(default_factory=dict)
    execution_mode: ExecutionMode = ExecutionMode.local
    read_only: bool = False
    writes_external_state: bool = False
    risk_level: RiskLevel = RiskLevel.low
    status: ReviewStatus = ReviewStatus.draft
    is_official: bool = False
    source: str = "manual"
    source_slug: str | None = None
    source_url: str | None = None
    owner_handle: str | None = None
    version: str = Field(default="1.0.0", max_length=32)
    summary: str = ""
    stats: dict = Field(default_factory=dict)
    registry_metadata: dict = Field(default_factory=dict)
    source_payload: dict = Field(default_factory=dict)


class SkillContractCreate(SkillContractBase):
    pass


class SkillContractUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    display_name: str | None = None
    category: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = None
    tags: list[str] | None = None
    input_schema: dict | None = None
    output_schema: dict | None = None
    execution_mode: ExecutionMode | None = None
    read_only: bool | None = None
    writes_external_state: bool | None = None
    risk_level: RiskLevel | None = None
    status: ReviewStatus | None = None
    is_official: bool | None = None
    source: str | None = Field(default=None, max_length=32)
    source_slug: str | None = Field(default=None, max_length=160)
    source_url: str | None = Field(default=None, max_length=500)
    owner_handle: str | None = Field(default=None, max_length=120)
    version: str | None = Field(default=None, max_length=32)
    summary: str | None = None
    stats: dict | None = None
    registry_metadata: dict | None = None
    source_payload: dict | None = None


class SkillContractRead(SkillContractBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
    last_synced_at: datetime | None = None
    security_score: float = 0.0
    security_tier: str = "caution"
    security_verdict: str = "manual_review_required"
    security_flags: list[str] = Field(default_factory=list)
