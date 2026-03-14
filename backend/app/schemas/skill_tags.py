from datetime import datetime

from pydantic import BaseModel, Field


class SkillTagRead(BaseModel):
    id: int
    name: str
    label: str
    category: str
    source: str
    description: str
    active: bool
    usage_count: int
    created_at: datetime
    updated_at: datetime


class SkillLinkedTagRead(SkillTagRead):
    link_source: str
    confidence: str


class SkillTagAssignmentUpdate(BaseModel):
    tag_names: list[str] = Field(default_factory=list)
    change_note: str | None = None
    actor: str | None = None


class SkillTagDefinitionUpdate(BaseModel):
    label: str | None = None
    description: str | None = None
    active: bool | None = None
    change_note: str | None = None
    actor: str | None = None
