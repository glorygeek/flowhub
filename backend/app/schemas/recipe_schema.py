from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.common import RiskLevel, ReviewStatus
from app.schemas.graph import ensure_acyclic


class RecipeNode(BaseModel):
    id: str = Field(min_length=1)
    skill_category: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class RecipeEdge(BaseModel):
    from_node: str
    to_node: str


class RecipeBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    scenario: str = Field(min_length=1, max_length=120)
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    node_skeleton: list[RecipeNode] = Field(default_factory=list)
    edges: list[RecipeEdge] = Field(default_factory=list)
    param_mappings: dict[str, Any] = Field(default_factory=dict)
    recommended_skill_categories: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.low
    status: ReviewStatus = ReviewStatus.draft

    @model_validator(mode="after")
    def validate_dag(self):
        node_ids = [node.id for node in self.node_skeleton]
        if node_ids:
            ensure_acyclic(
                node_ids=node_ids,
                edges=[(edge.from_node, edge.to_node) for edge in self.edges],
            )
        return self


class RecipeCreate(RecipeBase):
    pass


class RecipeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    scenario: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    tags: list[str] | None = None
    node_skeleton: list[RecipeNode] | None = None
    edges: list[RecipeEdge] | None = None
    param_mappings: dict[str, Any] | None = None
    recommended_skill_categories: list[str] | None = None
    risk_level: RiskLevel | None = None
    status: ReviewStatus | None = None

    @model_validator(mode="after")
    def validate_partial_dag(self):
        if self.node_skeleton is None or self.edges is None:
            return self
        ensure_acyclic(
            node_ids=[node.id for node in self.node_skeleton],
            edges=[(edge.from_node, edge.to_node) for edge in self.edges],
        )
        return self


class RecipeRead(RecipeBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
