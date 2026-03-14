from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.common import ExecutionMode
from app.schemas.planner import (
    ClientExecutionGuidance,
    CommunicationPreview,
    PlannerAssistantResponse,
    SkillRecommendation,
)
from app.schemas.workflow_spec import WorkflowSpec

TargetType = Literal["url", "api", "text"]
OutputFormat = Literal["json", "csv", "xlsx", "pdf", "markdown"]
RunRequestStatus = Literal["planned", "queued", "running", "completed", "failed"]
CredentialKind = Literal["api_key", "token", "cookie", "basic_auth", "other"]


class RunTarget(BaseModel):
    type: TargetType = "url"
    label: str = ""
    value: str = Field(min_length=1)


class CredentialInput(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    kind: CredentialKind = "api_key"
    value: str = Field(min_length=1)
    ephemeral: bool = True


class CredentialDescriptor(BaseModel):
    label: str
    kind: CredentialKind
    preview: str
    ephemeral: bool = True


class RunRequestCreate(BaseModel):
    goal: str = Field(min_length=1, max_length=2000)
    targets: list[RunTarget] = Field(default_factory=list)
    credentials: list[CredentialInput] = Field(default_factory=list)
    output_format: OutputFormat = "json"
    execution_mode: ExecutionMode = ExecutionMode.remote
    user_notes: str = ""


class RunRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    goal: str
    targets: list[RunTarget]
    credential_descriptors: list[CredentialDescriptor]
    output_format: OutputFormat
    execution_mode: ExecutionMode
    user_notes: str
    status: RunRequestStatus
    workflow_spec: WorkflowSpec
    planning_notes: list[str]
    created_at: datetime
    updated_at: datetime


class RunRequestIntakeSummary(BaseModel):
    target_count: int
    credential_count: int
    output_format: OutputFormat
    execution_mode: ExecutionMode


class RunRequestPlanResponse(BaseModel):
    actionable: bool = True
    request: RunRequestRead | None = None
    workflow_spec: WorkflowSpec | None = None
    decision_log: list[str]
    next_steps: list[str]
    intake_summary: RunRequestIntakeSummary
    assistant_response: PlannerAssistantResponse
    selected_skills: list[SkillRecommendation] = Field(default_factory=list)
    communication_preview: CommunicationPreview
    client_execution_guidance: ClientExecutionGuidance | None = None


class RunRequestConfirmResponse(BaseModel):
    request: RunRequestRead
    workflow_spec: WorkflowSpec
    assistant_response: PlannerAssistantResponse
    selected_skills: list[SkillRecommendation] = Field(default_factory=list)
    communication_preview: CommunicationPreview
    client_execution_guidance: ClientExecutionGuidance | None = None
