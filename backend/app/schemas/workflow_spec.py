from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.common import RiskLevel, ReviewStatus
from app.schemas.graph import ensure_acyclic


class WorkflowNode(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    skill_ref: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)


class WorkflowEdge(BaseModel):
    from_node: str
    to_node: str


class WorkflowSpec(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    workflow_id: int | None = None
    name: str = Field(min_length=1, max_length=120)
    inputs: dict[str, Any] = Field(default_factory=dict)
    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)
    outputs: dict[str, Any] = Field(default_factory=dict)
    retry_policy: dict[str, Any] | None = None
    confirm_points: list[str] | None = None
    source_recipe_id: int | None = None
    risk_level: RiskLevel = RiskLevel.low

    @model_validator(mode="after")
    def validate_graph(self):
        node_ids = [node.id for node in self.nodes]
        if node_ids:
            ensure_acyclic(
                node_ids=node_ids,
                edges=[(edge.from_node, edge.to_node) for edge in self.edges],
            )
        return self


class WorkflowBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    inputs: dict[str, Any] = Field(default_factory=dict)
    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)
    outputs: dict[str, Any] = Field(default_factory=dict)
    source_recipe_id: int | None = None
    risk_level: RiskLevel = RiskLevel.low
    status: ReviewStatus = ReviewStatus.draft
    retry_policy: dict[str, Any] | None = None
    confirm_points: list[str] | None = None
    planner_decision_log: list[str] | None = None

    @model_validator(mode="after")
    def validate_dag(self):
        node_ids = [node.id for node in self.nodes]
        if node_ids:
            ensure_acyclic(
                node_ids=node_ids,
                edges=[(edge.from_node, edge.to_node) for edge in self.edges],
            )
        return self


class WorkflowCreate(WorkflowBase):
    pass


class WorkflowUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    inputs: dict[str, Any] | None = None
    nodes: list[WorkflowNode] | None = None
    edges: list[WorkflowEdge] | None = None
    outputs: dict[str, Any] | None = None
    source_recipe_id: int | None = None
    risk_level: RiskLevel | None = None
    status: ReviewStatus | None = None
    retry_policy: dict[str, Any] | None = None
    confirm_points: list[str] | None = None
    planner_decision_log: list[str] | None = None

    @model_validator(mode="after")
    def validate_partial_dag(self):
        if self.nodes is None or self.edges is None:
            return self
        ensure_acyclic(
            node_ids=[node.id for node in self.nodes],
            edges=[(edge.from_node, edge.to_node) for edge in self.edges],
        )
        return self


class WorkflowRead(WorkflowBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
