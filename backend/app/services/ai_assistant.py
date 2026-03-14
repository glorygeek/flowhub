from dataclasses import dataclass
from typing import Any

from app.core.config import Settings
from app.models.common import ExecutionMode
from app.schemas.planner import CommunicationPreview, PlannerAssistantResponse, SkillRecommendation
from app.schemas.workflow_spec import WorkflowSpec
from app.services.ai_gateway import request_ai_json


@dataclass
class AIActionabilityAssessment:
    actionable: bool
    reason: str
    missing_information: list[str]


def assess_request_actionability_with_ai(
    *,
    goal: str,
    targets: list[dict[str, Any]],
    output_format: str,
    execution_mode: ExecutionMode,
    settings: Settings,
) -> AIActionabilityAssessment | None:
    payload = request_ai_json(
        settings=settings,
        temperature=0.0,
        system_prompt=(
            "You are FlowHub's intake classifier. Decide whether a chat message contains an actionable automation "
            "request. Return JSON only with keys actionable, reason, missing_information. "
            "Mark actionable=false for greetings, vague chatter, or requests without enough task intent."
        ),
        user_payload={
            "goal": goal,
            "targets": targets,
            "output_format": output_format,
            "execution_mode": execution_mode.value,
            "expected_json_schema": {
                "actionable": True,
                "reason": "string",
                "missing_information": ["string"],
            },
        },
    )
    if payload is None:
        return None

    actionable = bool(payload.get("actionable"))
    reason = str(payload.get("reason") or "").strip()
    missing_information = [
        str(item).strip()
        for item in payload.get("missing_information", [])
        if isinstance(item, str) and str(item).strip()
    ] if isinstance(payload.get("missing_information"), list) else []
    if not reason:
        return None

    return AIActionabilityAssessment(
        actionable=actionable,
        reason=reason,
        missing_information=missing_information,
    )


def rewrite_planner_response_with_ai(
    *,
    template_key: str,
    goal: str,
    output_format: str,
    execution_mode: ExecutionMode,
    workflow_spec: WorkflowSpec | None,
    selected_skills: list[SkillRecommendation],
    communication_status: str,
    default_assistant: PlannerAssistantResponse,
    default_preview: CommunicationPreview,
    settings: Settings,
) -> tuple[PlannerAssistantResponse, CommunicationPreview] | None:
    payload = request_ai_json(
        settings=settings,
        temperature=0.2,
        system_prompt=(
            "You are FlowHub's customer-facing reply writer. Rewrite the default workflow reply into concise, clear "
            "Chinese for a chat bot. Preserve the business meaning, stay in free-tier mode, and return JSON only. "
            "Do not mention paid plans, subscriptions, or hidden capabilities."
        ),
        user_payload={
            "template_key": template_key,
            "goal": goal,
            "output_format": output_format,
            "execution_mode": execution_mode.value,
            "communication_status": communication_status,
            "workflow": {
                "name": workflow_spec.name if workflow_spec else "",
                "node_count": len(workflow_spec.nodes) if workflow_spec else 0,
                "risk_level": workflow_spec.risk_level.value if workflow_spec else "low",
            },
            "selected_skills": [
                {
                    "display_name": skill.display_name,
                    "category": skill.category,
                    "summary": skill.summary,
                    "description": skill.description,
                    "quality_tier": skill.quality_tier,
                    "trust_signals": skill.trust_signals,
                }
                for skill in selected_skills
            ],
            "defaults": {
                "assistant_response": {
                    "headline": default_assistant.headline,
                    "reply_text": default_assistant.reply_text,
                    "usage_steps": default_assistant.usage_steps,
                    "confirmation_prompt": default_assistant.confirmation_prompt,
                    "delivery_note": default_assistant.delivery_note,
                },
                "communication_preview": {
                    "title": default_preview.title,
                    "body": default_preview.body,
                    "usage_steps": default_preview.usage_steps,
                },
            },
            "expected_json_schema": {
                "headline": "string",
                "reply_text": "string",
                "usage_steps": ["string"],
                "confirmation_prompt": "string",
                "delivery_note": "string",
                "title": "string",
                "body": "string",
            },
        },
    )
    if payload is None:
        return None

    headline = str(payload.get("headline") or "").strip()
    reply_text = str(payload.get("reply_text") or "").strip()
    confirmation_prompt = str(payload.get("confirmation_prompt") or "").strip()
    delivery_note = str(payload.get("delivery_note") or "").strip()
    title = str(payload.get("title") or "").strip()
    body = str(payload.get("body") or "").strip()
    usage_steps = [
        str(item).strip()
        for item in payload.get("usage_steps", [])
        if isinstance(item, str) and str(item).strip()
    ] if isinstance(payload.get("usage_steps"), list) else []

    if not all([headline, reply_text, confirmation_prompt, delivery_note, title, body]) or not usage_steps:
        return None

    assistant_response = PlannerAssistantResponse(
        template_key=template_key,
        headline=headline,
        reply_text=reply_text,
        usage_steps=usage_steps,
        confirmation_prompt=confirmation_prompt,
        delivery_note=delivery_note,
    )
    communication_preview = CommunicationPreview(
        channel=default_preview.channel,
        template_key=template_key,
        status=communication_status,
        title=title,
        body=body,
        usage_steps=usage_steps,
    )
    return assistant_response, communication_preview
