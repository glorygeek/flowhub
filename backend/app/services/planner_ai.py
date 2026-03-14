import logging
from dataclasses import dataclass, field
from typing import Any

from app.core.config import Settings
from app.models.skill import Skill
from app.services.ai_gateway import request_ai_json
from app.services.skill_quality import summarize_skill_quality

logger = logging.getLogger(__name__)


@dataclass
class AIWorkflowStep:
    skill_slug: str
    name: str | None = None
    inputs: dict[str, Any] = field(default_factory=dict)


@dataclass
class AIPlanningResult:
    workflow_name: str | None
    summary: str | None
    selected_skill_slugs: list[str]
    usage_steps: list[str]
    skill_reasons: dict[str, str]
    workflow_steps: list[AIWorkflowStep]


def plan_skill_chain_with_ai(
    *,
    goal: str,
    targets: list[dict[str, Any]],
    output_format: str,
    execution_mode: str,
    candidates: list[Skill],
    settings: Settings,
) -> AIPlanningResult | None:
    if not candidates:
        return None

    parsed = request_ai_json(
        settings=settings,
        temperature=0.1,
        system_prompt=(
            "You are FlowHub's workflow planner. Pick 1-4 approved skills from the shortlist, "
            "order them into a safe linear workflow, and return only valid JSON. "
            "Use only skills from the shortlist. Prefer high-confidence skills backed by strong "
            "trust signals such as official publisher, stars, installs, community feedback, and "
            "safe moderation. Prefer concise, user-facing explanations."
        ),
        user_payload={
            "task": {
                "goal": goal,
                "targets": targets,
                "output_format": output_format,
                "execution_mode": execution_mode,
            },
            "expected_json_schema": {
                "workflow_name": "string",
                "summary": "string",
                "selected_skill_slugs": ["skill-slug"],
                "usage_steps": ["string"],
                "skill_reasons": {"skill-slug": "string"},
                "workflow_steps": [
                    {
                        "skill_slug": "skill-slug",
                        "name": "string",
                        "inputs": {"optional": "object"},
                    }
                ],
            },
            "skills": [_serialize_candidate(skill) for skill in candidates],
        },
    )
    if parsed is None:
        logger.info("Planner AI unavailable or returned invalid JSON; using fallback planner.")
        return None

    selected_skill_slugs = [
        _normalize_skill_slug(item)
        for item in parsed.get("selected_skill_slugs", [])
        if isinstance(item, str) and _normalize_skill_slug(item)
    ]
    if not selected_skill_slugs:
        return None

    workflow_steps: list[AIWorkflowStep] = []
    raw_steps = parsed.get("workflow_steps", [])
    if isinstance(raw_steps, list):
        for raw_step in raw_steps:
            if not isinstance(raw_step, dict):
                continue
            skill_slug = _normalize_skill_slug(raw_step.get("skill_slug"))
            if not skill_slug:
                continue
            workflow_steps.append(
                AIWorkflowStep(
                    skill_slug=skill_slug,
                    name=str(raw_step.get("name") or "").strip() or None,
                    inputs=raw_step.get("inputs") if isinstance(raw_step.get("inputs"), dict) else {},
                )
            )

    raw_reasons = parsed.get("skill_reasons", {})
    skill_reasons = {
        _normalize_skill_slug(key): str(value).strip()
        for key, value in raw_reasons.items()
        if isinstance(key, str) and isinstance(value, str) and _normalize_skill_slug(key)
    } if isinstance(raw_reasons, dict) else {}

    usage_steps = [
        str(item).strip()
        for item in parsed.get("usage_steps", [])
        if isinstance(item, str) and str(item).strip()
    ]

    return AIPlanningResult(
        workflow_name=str(parsed.get("workflow_name") or "").strip() or None,
        summary=str(parsed.get("summary") or "").strip() or None,
        selected_skill_slugs=selected_skill_slugs,
        usage_steps=usage_steps,
        skill_reasons=skill_reasons,
        workflow_steps=workflow_steps,
    )


def _serialize_candidate(skill: Skill) -> dict[str, Any]:
    quality = summarize_skill_quality(skill)
    return {
        "slug": skill.source_slug or _normalize_skill_slug(skill.name),
        "name": skill.name,
        "display_name": skill.display_name or skill.name,
        "category": skill.category,
        "summary": skill.summary,
        "description": skill.description,
        "tags": skill.tags or [],
        "risk_level": skill.risk_level.value,
        "source_url": skill.source_url,
        "execution_mode": skill.execution_mode.value,
        "quality_score": quality.score,
        "quality_tier": quality.tier,
        "trust_signals": quality.trust_signals,
    }
def _normalize_skill_slug(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if "/" in text:
        return text.split("/", 1)[1]
    return text
