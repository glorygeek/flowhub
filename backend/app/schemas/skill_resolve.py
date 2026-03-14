from pydantic import BaseModel

from app.schemas.skill_contract import SkillContractRead


class SkillResolveRead(BaseModel):
    requested_ref: str
    matched_by: str | None = None
    skill: SkillContractRead | None = None
