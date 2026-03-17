from typing import Any

from pydantic import BaseModel, Field

from app.models.common import RiskLevel
from app.schemas.workflow_spec import WorkflowSpec


class PlannerPlanRequest(BaseModel):
    request_text: str = Field(min_length=1)
    client_capabilities: dict[str, Any] = Field(default_factory=dict)
    risk_tolerance: RiskLevel | None = None


class SkillRecommendation(BaseModel):
    skill_id: int
    name: str
    display_name: str
    category: str
    source: str = ""
    source_slug: str | None = None
    summary: str = ""
    description: str = ""
    source_url: str | None = None
    usage_hint: str
    selection_reason: str
    quality_score: float = 0.0
    quality_tier: str = "basic"
    trust_signals: list[str] = Field(default_factory=list)
    security_score: float = 0.0
    security_tier: str = "caution"
    security_verdict: str = "manual_review_required"
    security_flags: list[str] = Field(default_factory=list)


class ClientSkillTarget(BaseModel):
    name: str
    display_name: str
    source: str = ""
    source_slug: str | None = None
    source_url: str | None = None
    fetch_strategy: str = "registry"
    required: bool = True


class ClientExecutionGuidance(BaseModel):
    mode: str = "client_fetch_and_compose"
    ai_runtime_owner: str = "client"
    summary: str
    steps: list[str] = Field(default_factory=list)
    skill_targets: list[ClientSkillTarget] = Field(default_factory=list)


class ClientInstallTarget(BaseModel):
    name: str
    display_name: str
    source: str = ""
    source_slug: str | None = None
    source_url: str | None = None
    fetch_strategy: str = "registry"
    required: bool = True
    install_command: str | None = None
    install_command_windows: str | None = None


class ClientInstallGuidance(BaseModel):
    mode: str = "client_managed"
    install_requested: bool = False
    status: str = "deferred"
    summary: str
    steps: list[str] = Field(default_factory=list)
    items: list[ClientInstallTarget] = Field(default_factory=list)
    note: str = ""


class WorkflowSummaryStep(BaseModel):
    index: int
    skill_ref: str
    display_name: str
    role: str
    summary: str = ""
    planning_status: str = "eligible"
    source_url: str | None = None


class WorkflowSafetyReviewItem(BaseModel):
    skill_ref: str
    display_name: str
    planning_status: str = "eligible"
    security_flags: list[str] = Field(default_factory=list)
    note: str = ""


class WorkflowSummary(BaseModel):
    formula: str
    plan_type: str = "fallback"
    headline: str
    explanation: str
    steps: list[WorkflowSummaryStep] = Field(default_factory=list)
    usage_steps: list[str] = Field(default_factory=list)
    safety_guidance: list[str] = Field(default_factory=list)
    handoff_steps: list[str] = Field(default_factory=list)
    safety_review_items: list[WorkflowSafetyReviewItem] = Field(default_factory=list)


class PlannerAssistantResponse(BaseModel):
    template_key: str = ""
    headline: str
    reply_text: str
    usage_steps: list[str] = Field(default_factory=list)
    confirmation_prompt: str = ""
    delivery_note: str = ""


class CommunicationPreview(BaseModel):
    channel: str = "user_inbox"
    template_key: str = ""
    status: str = "pending_confirmation"
    title: str
    body: str
    usage_steps: list[str] = Field(default_factory=list)


class PlannerPlanResponse(BaseModel):
    actionable: bool = True
    workflow_spec: WorkflowSpec | None = None
    decision_log: list[str]
    estimated_risk: RiskLevel | None = None
    assistant_response: PlannerAssistantResponse
    selected_skills: list[SkillRecommendation] = Field(default_factory=list)
    communication_preview: CommunicationPreview
    client_execution_guidance: ClientExecutionGuidance | None = None
    client_install_guidance: ClientInstallGuidance | None = None
    workflow_summary: WorkflowSummary | None = None
