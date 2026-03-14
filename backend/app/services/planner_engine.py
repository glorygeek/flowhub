import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.common import ExecutionMode, RiskLevel, ReviewStatus
from app.models.recipe import Recipe
from app.models.skill import Skill
from app.schemas.planner import (
    CommunicationPreview,
    PlannerAssistantResponse,
    SkillRecommendation,
)
from app.schemas.workflow_spec import WorkflowEdge, WorkflowNode, WorkflowSpec
from app.services.ai_assistant import assess_request_actionability_with_ai
from app.services.free_tier_chat_templates import (
    build_free_plan_response_bundle,
    build_free_usage_guidance_response,
)
from app.services.planner_ai import AIPlanningResult, plan_skill_chain_with_ai
from app.services.skill_quality import summarize_skill_quality
from app.services.skill_security import summarize_skill_security
from app.services.skill_search import search_skills as search_indexed_skills

NOISE_TOKENS = {
    "http",
    "https",
    "www",
    "com",
    "org",
    "net",
    "io",
    "html",
    "htm",
    "example",
}
GENERIC_TOKENS = {
    "api",
    "app",
    "tool",
    "service",
    "latest",
    "web",
    "data",
    "cloud",
    "docs",
    "documentation",
}
TOKEN_ALIASES = {
    "抓取": {"fetch", "collect", "scrape"},
    "爬取": {"fetch", "collect", "scrape"},
    "提取": {"extract", "collect"},
    "总结": {"summary", "report"},
    "摘要": {"summary", "report"},
    "简报": {"summary", "brief", "report"},
    "状态": {"status"},
    "客户": {"customer"},
    "通知": {"notify", "message"},
    "网站": {"web", "page", "site"},
    "接口": {"api", "endpoint"},
    "表格": {"csv", "excel", "sheet"},
    "日报": {"daily", "report", "summary"},
    "周报": {"weekly", "report", "summary"},
    "月报": {"monthly", "report", "summary"},
}
COLLECTOR_KEYWORDS = {"fetch", "collect", "scrape", "crawl", "request", "api", "web", "extract", "rss"}
PRESENTER_KEYWORDS = {
    "summary",
    "summarize",
    "brief",
    "report",
    "markdown",
    "export",
    "output",
    "notify",
    "message",
    "status",
}
PRESENTER_SIGNAL_KEYWORDS = {
    "summary",
    "summarize",
    "brief",
    "markdown",
    "export",
    "output",
    "notify",
    "message",
    "report generation",
    "investment report",
    "customer-facing",
}
ACTION_KEYWORDS = {
    "analyze",
    "analysis",
    "compare",
    "collect",
    "crawl",
    "clean",
    "export",
    "extract",
    "fetch",
    "generate",
    "monitor",
    "notify",
    "report",
    "research",
    "review",
    "scrape",
    "summarize",
    "summary",
    "track",
    "translate",
    "write",
    "分析",
    "比较",
    "抓取",
    "爬取",
    "提取",
    "导出",
    "整理",
    "总结",
    "摘要",
    "监控",
    "通知",
    "翻译",
}
OBJECT_HINT_KEYWORDS = {
    "api",
    "article",
    "chart",
    "csv",
    "customer",
    "document",
    "earnings",
    "endpoint",
    "equity",
    "file",
    "finance",
    "incident",
    "index",
    "link",
    "market",
    "news",
    "pdf",
    "price",
    "report",
    "stock",
    "stocks",
    "table",
    "text",
    "ticker",
    "url",
    "website",
    "客户",
    "报告",
    "接口",
    "文档",
    "文章",
    "新闻",
    "链接",
    "表格",
    "股票",
    "行情",
    "财报",
}
SELF_CONTAINED_KEYWORDS = {
    "all-in-one",
    "all in one",
    "comprehensive",
    "complete",
    "end-to-end",
    "end to end",
    "full",
    "one-shot",
    "one shot",
    "single request",
    "standalone",
    "report generation",
    "investment report",
    "综合",
    "完整",
    "全面",
    "报告生成",
    "一站式",
    "一键",
}
SMALL_TALK_PATTERNS = (
    re.compile(r"^(hi|hello|hey|yo|sup|thanks|thank you)[!,. ]*$"),
    re.compile(r"^(你好|您好|在吗|哈喽|嗨|谢谢)[!！,.，。 ]*$"),
)
@dataclass
class PlanBuildResult:
    actionable: bool
    workflow_spec: WorkflowSpec | None
    decision_log: list[str]
    estimated_risk: RiskLevel | None
    assistant_response: PlannerAssistantResponse
    selected_skills: list[SkillRecommendation]
    communication_preview: CommunicationPreview


@dataclass
class RankedSkillMatch:
    skill: Skill
    score: float
    quality_score: float
    quality_tier: str
    trust_signals: list[str]
    security_score: float
    security_tier: str
    security_verdict: str
    security_flags: list[str]
    matched_tokens: list[str]
    selection_reason: str


def risk_rank(level: RiskLevel) -> int:
    mapping = {RiskLevel.low: 1, RiskLevel.medium: 2, RiskLevel.high: 3}
    return mapping[level]


def clamp_risk(risk: RiskLevel, tolerance: RiskLevel | None) -> RiskLevel:
    if tolerance is None:
        return risk
    if risk_rank(risk) <= risk_rank(tolerance):
        return risk
    return tolerance


def normalize_skill_identifier(value: str | None) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if "/" in text:
        return text.split("/", 1)[1]
    return text


def build_skill_haystack(skill: Skill) -> str:
    return " ".join(
        [
            skill.name or "",
            skill.display_name or "",
            skill.category or "",
            skill.description or "",
            skill.summary or "",
            " ".join(skill.tags or []),
            skill.source_slug or "",
        ]
    ).lower()


def tokenize_request_text(goal: str, targets: list[dict[str, Any]]) -> set[str]:
    text_parts = [goal]
    for target in targets:
        text_parts.append(str(target.get("label") or ""))
        text_parts.append(str(target.get("value") or ""))

        value = str(target.get("value") or "")
        parsed = urlparse(value)
        if parsed.netloc:
            text_parts.append(parsed.netloc.replace(".", " "))
        if parsed.path:
            text_parts.append(parsed.path.replace("/", " "))

    text = " ".join(text_parts).lower()
    raw_tokens = re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z0-9_\-]+", text)
    tokens: set[str] = set()
    for token in raw_tokens:
        normalized = token.strip("-_")
        if not normalized or normalized in NOISE_TOKENS:
            continue
        tokens.add(normalized)
        if normalized.endswith("s") and len(normalized) > 4:
            tokens.add(normalized[:-1])
        for phrase, aliases in TOKEN_ALIASES.items():
            if phrase in normalized:
                tokens.update(aliases)
    return tokens


def recipe_match_score(recipe: Recipe, request_tokens: set[str]) -> int:
    haystack = " ".join(
        [
            recipe.name or "",
            recipe.scenario or "",
            recipe.description or "",
            " ".join(recipe.tags or []),
            " ".join(recipe.recommended_skill_categories or []),
        ]
    ).lower()
    return sum(1 for token in request_tokens if token and token in haystack)


def skill_match_score(skill: Skill, request_tokens: set[str]) -> tuple[int, list[str]]:
    haystack = build_skill_haystack(skill)
    matched_tokens = sorted({token for token in request_tokens if token and token in haystack})
    specific_tokens = [token for token in matched_tokens if token not in GENERIC_TOKENS]
    generic_tokens = [token for token in matched_tokens if token in GENERIC_TOKENS]
    score = len(specific_tokens) * 3 + len(generic_tokens)
    if score == 0:
        return 0, []
    if skill.is_official:
        score += 2
    if skill.execution_mode == ExecutionMode.remote:
        score += 1
    if skill.risk_level == RiskLevel.low:
        score += 1
    return score, matched_tokens


def build_nodes_from_recipe(recipe: Recipe, goal: str) -> tuple[list[WorkflowNode], list[WorkflowEdge]]:
    nodes: list[WorkflowNode] = []
    for index, raw_node in enumerate(recipe.node_skeleton or [], start=1):
        skill_category = (raw_node or {}).get("skill_category") or "generic"
        config = dict((raw_node or {}).get("config") or {})
        name = (raw_node or {}).get("name") or skill_category.replace("-", " ")
        skill_ref = (raw_node or {}).get("skill_ref") or f"{skill_category}.execute"
        nodes.append(
            WorkflowNode(
                id=(raw_node or {}).get("id") or f"step_{index}",
                name=name,
                skill_ref=skill_ref,
                inputs={
                    "request_text": goal,
                    **config,
                },
            )
        )

    edges = [
        WorkflowEdge(from_node=edge.get("from_node"), to_node=edge.get("to_node"))
        for edge in (recipe.edges or [])
    ]
    return nodes, edges


def infer_target_step(targets: list[dict[str, Any]]) -> WorkflowNode:
    if not targets:
        return WorkflowNode(
            id="step_2",
            name="Collect source data",
            skill_ref="generic.collect",
            inputs={},
        )

    first_target = targets[0]
    target_type = first_target.get("type")
    target_value = first_target.get("value")
    if target_type == "url":
        return WorkflowNode(
            id="step_2",
            name="Fetch target page",
            skill_ref="web.fetch",
            inputs={"url": target_value},
        )
    if target_type == "api":
        return WorkflowNode(
            id="step_2",
            name="Call target API",
            skill_ref="api.request",
            inputs={"endpoint": target_value},
        )
    return WorkflowNode(
        id="step_2",
        name="Process provided content",
        skill_ref="generic.process",
        inputs={"source": target_value},
    )


def build_fallback_workflow(
    goal: str,
    targets: list[dict[str, Any]],
    output_format: str,
) -> tuple[list[WorkflowNode], list[WorkflowEdge]]:
    nodes = [
        WorkflowNode(
            id="step_1",
            name="Interpret request",
            skill_ref="planner.analyze",
            inputs={"request_text": goal},
        ),
        infer_target_step(targets),
        WorkflowNode(
            id="step_3",
            name="Prepare result package",
            skill_ref="output.export",
            inputs={"format": output_format},
        ),
    ]
    edges = [
        WorkflowEdge(from_node="step_1", to_node="step_2"),
        WorkflowEdge(from_node="step_2", to_node="step_3"),
    ]
    return nodes, edges


def select_skill_candidates(
    *,
    db: Session,
    query_text: str,
    request_tokens: set[str],
    limit: int,
) -> list[RankedSkillMatch]:
    search_hits = search_indexed_skills(
        db=db,
        query_text=query_text,
        limit=limit,
    )
    if search_hits:
        ranked_hits: list[RankedSkillMatch] = []
        for hit in search_hits:
            matched_tokens = sorted(dict.fromkeys(hit.matched_terms + hit.matched_tags))
            reasons = hit.ranking_reasons or ["Matched by quick skill search."]
            ranked_hits.append(
                RankedSkillMatch(
                    skill=hit.skill,
                    score=hit.score,
                    quality_score=hit.quality_score,
                    quality_tier=hit.quality_tier,
                    trust_signals=hit.trust_signals,
                    security_score=hit.security_score,
                    security_tier=hit.security_tier,
                    security_verdict=hit.security_verdict,
                    security_flags=hit.security_flags,
                    matched_tokens=matched_tokens,
                    selection_reason=" ".join(reasons[:3]),
                )
            )
        return _filter_plannable_skill_matches(ranked_hits, limit=limit)

    approved_skills = list(
        db.scalars(select(Skill).where(Skill.status == ReviewStatus.approved)).all()
    )

    ranked: list[RankedSkillMatch] = []
    for skill in approved_skills:
        raw_score, matched_tokens = skill_match_score(skill=skill, request_tokens=request_tokens)
        if raw_score <= 0:
            continue
        quality = summarize_skill_quality(skill)
        security = summarize_skill_security(skill)
        score = raw_score * 2 + quality.score
        token_summary = ", ".join(matched_tokens[:5]) if matched_tokens else skill.category
        trust_note = f"可信度={quality.tier}" if quality.tier else "可信度=basic"
        ranked.append(
            RankedSkillMatch(
                skill=skill,
                score=score,
                quality_score=quality.score,
                quality_tier=quality.tier,
                trust_signals=quality.trust_signals,
                security_score=security.score,
                security_tier=security.tier,
                security_verdict=security.verdict,
                security_flags=security.flags,
                matched_tokens=matched_tokens,
                selection_reason=f"Matched request intent via: {token_summary}. {trust_note}.",
            )
        )

    ranked.sort(
        key=lambda item: (
            -item.score,
            item.skill.risk_level != RiskLevel.low,
            not item.skill.is_official,
            item.skill.display_name or item.skill.name,
        )
    )
    deduped: list[RankedSkillMatch] = []
    seen_names: set[str] = set()
    for item in ranked:
        display_key = (item.skill.display_name or item.skill.name).strip().lower()
        if display_key in seen_names:
            continue
        seen_names.add(display_key)
        deduped.append(item)
        if len(deduped) >= limit:
            break
    return _filter_plannable_skill_matches(deduped, limit=limit)


def _filter_plannable_skill_matches(candidates: list[RankedSkillMatch], *, limit: int) -> list[RankedSkillMatch]:
    non_blocked = [candidate for candidate in candidates if candidate.security_verdict != "block_or_quarantine"]
    preferred = [candidate for candidate in non_blocked if candidate.security_verdict != "manual_review_required"]
    filtered = preferred or non_blocked
    return filtered[:limit]


def infer_skill_roles(skill: Skill) -> set[str]:
    haystack = build_skill_haystack(skill)
    roles: set[str] = set()
    if any(keyword in haystack for keyword in COLLECTOR_KEYWORDS):
        roles.add("collector")
    if has_presenter_signal(haystack):
        roles.add("presenter")
    return roles


def has_presenter_signal(haystack: str) -> bool:
    if any(keyword in haystack for keyword in PRESENTER_SIGNAL_KEYWORDS):
        return True
    if "report" in haystack and any(keyword in haystack for keyword in {"generate", "generation", "deliver"}):
        return True
    return False


def assess_request_actionability(
    *,
    goal: str,
    targets: list[dict[str, Any]],
    request_tokens: set[str],
) -> tuple[bool, list[str]]:
    normalized_goal = goal.strip().lower()
    for pattern in SMALL_TALK_PATTERNS:
        if pattern.fullmatch(normalized_goal):
            return False, ["Message matched a greeting or small-talk pattern."]

    specific_tokens = {
        token
        for token in request_tokens
        if token not in GENERIC_TOKENS and token not in NOISE_TOKENS and len(token) > 1
    }
    action_tokens = request_tokens & ACTION_KEYWORDS
    object_hint_tokens = request_tokens & OBJECT_HINT_KEYWORDS
    has_targets = any(str(target.get("value") or "").strip() for target in targets)
    has_structured_hint = bool(
        re.search(r"https?://|www\.|[A-Z]{2,5}(?:\s*,\s*[A-Z]{2,5})+", goal)
        or re.search(r"\b(api|url|link|ticker|pdf|csv|markdown)\b", normalized_goal)
    )

    score = 0
    if action_tokens:
        score += 2
    if has_targets:
        score += 2
    if object_hint_tokens:
        score += 1
    if len(specific_tokens) >= 3:
        score += 1
    if has_structured_hint:
        score += 1

    decision_log = [
        f"Actionability signals: action_tokens={len(action_tokens)}, targets={int(has_targets)}, "
        f"object_hints={len(object_hint_tokens)}, specific_tokens={len(specific_tokens)}, "
        f"structured_hint={int(has_structured_hint)}."
    ]
    actionable = score >= 2 and (bool(action_tokens) or has_targets or has_structured_hint)
    if not actionable:
        decision_log.append("Message did not include enough task intent or target context for planning.")
    return actionable, decision_log


def build_usage_guidance_response(goal: str) -> tuple[PlannerAssistantResponse, CommunicationPreview]:
    return build_free_usage_guidance_response(goal)


def is_self_contained_skill(
    *,
    candidate: RankedSkillMatch,
    target_tokens: set[str],
    output_format: str,
) -> bool:
    haystack = build_skill_haystack(candidate.skill)
    roles = infer_skill_roles(candidate.skill)
    target_matches = len((set(candidate.matched_tokens) & target_tokens) - GENERIC_TOKENS)
    output_capable = output_format.lower() in haystack or has_presenter_signal(haystack)

    if "collector" in roles and "presenter" in roles and target_matches >= 1:
        return True
    if any(keyword in haystack for keyword in SELF_CONTAINED_KEYWORDS) and output_capable:
        return True
    if (
        candidate.skill.category in {"automation", "analysis", "data", "web"}
        and output_capable
        and target_matches >= 2
        and candidate.score >= 8
    ):
        return True
    return False


def choose_free_skill_plan(
    *,
    candidates: list[RankedSkillMatch],
    target_tokens: set[str],
    output_format: str,
) -> list[RankedSkillMatch]:
    for candidate in candidates:
        if is_self_contained_skill(
            candidate=candidate,
            target_tokens=target_tokens,
            output_format=output_format,
        ):
            return [candidate]
    return choose_local_skill_mix(
        candidates=candidates,
        target_tokens=target_tokens,
        output_format=output_format,
    )


def choose_ai_guided_free_plan(
    *,
    candidates: list[RankedSkillMatch],
    target_tokens: set[str],
    output_format: str,
) -> list[RankedSkillMatch]:
    if not candidates:
        return []

    first = candidates[0]
    if is_self_contained_skill(candidate=first, target_tokens=target_tokens, output_format=output_format):
        return [first]

    selected: list[RankedSkillMatch] = []
    covered_roles: set[str] = set()
    for candidate in candidates:
        roles = infer_skill_roles(candidate.skill)
        if not roles:
            continue
        selected.append(candidate)
        covered_roles.update(roles)
        if "collector" in covered_roles and "presenter" in covered_roles:
            return selected[:4]

    return choose_free_skill_plan(
        candidates=candidates,
        target_tokens=target_tokens,
        output_format=output_format,
    )


def choose_local_skill_mix(
    *,
    candidates: list[RankedSkillMatch],
    target_tokens: set[str],
    output_format: str,
) -> list[RankedSkillMatch]:
    collector_choice: RankedSkillMatch | None = None
    presenter_choice: RankedSkillMatch | None = None
    primary_choice: RankedSkillMatch | None = candidates[0] if candidates else None
    collector_score = -1
    presenter_score = -1

    for candidate in candidates:
        roles = infer_skill_roles(candidate.skill)
        matched = set(candidate.matched_tokens)
        target_bonus = len((matched & target_tokens) - GENERIC_TOKENS) * 2
        output_bonus = len(matched & (PRESENTER_KEYWORDS | {output_format.lower()}))

        if "collector" in roles:
            score = candidate.score + target_bonus
            if score > collector_score:
                collector_choice = candidate
                collector_score = score

        if "presenter" in roles:
            score = candidate.score + output_bonus
            if score > presenter_score:
                presenter_choice = candidate
                presenter_score = score

    selected: list[RankedSkillMatch] = []
    if collector_choice:
        selected.append(collector_choice)
    elif primary_choice:
        selected.append(primary_choice)

    if presenter_choice and (not selected or presenter_choice.skill.id != selected[0].skill.id):
        selected.append(presenter_choice)

    if not selected:
        return candidates[: min(2, len(candidates))]
    if len(selected) == 1:
        for candidate in candidates:
            if candidate.skill.id != selected[0].skill.id:
                selected.append(candidate)
                break
    return selected[:2]


def select_skills_via_ai(
    *,
    goal: str,
    targets: list[dict[str, Any]],
    output_format: str,
    execution_mode: ExecutionMode,
    candidates: list[RankedSkillMatch],
    db: Session,
) -> tuple[list[RankedSkillMatch], AIPlanningResult | None]:
    settings = get_settings()
    ai_plan = plan_skill_chain_with_ai(
        goal=goal,
        targets=targets,
        output_format=output_format,
        execution_mode=execution_mode.value,
        candidates=[candidate.skill for candidate in candidates],
        settings=settings,
    )
    if ai_plan is None:
        return [], None

    candidate_lookup: dict[str, RankedSkillMatch] = {}
    for candidate in candidates:
        for identifier in {
            normalize_skill_identifier(candidate.skill.source_slug),
            normalize_skill_identifier(candidate.skill.name),
        }:
            if identifier:
                candidate_lookup[identifier] = candidate

    selected_by_slug: dict[str, RankedSkillMatch] = {}
    ordered_slugs: list[str] = []
    missing_slugs: list[str] = []
    for slug in ai_plan.selected_skill_slugs:
        normalized_slug = normalize_skill_identifier(slug)
        if not normalized_slug or normalized_slug in ordered_slugs:
            continue
        ordered_slugs.append(normalized_slug)
        candidate = candidate_lookup.get(normalized_slug)
        if not candidate:
            missing_slugs.append(normalized_slug)
            continue
        selected_by_slug[normalized_slug] = RankedSkillMatch(
            skill=candidate.skill,
            score=candidate.score,
            quality_score=candidate.quality_score,
            quality_tier=candidate.quality_tier,
            trust_signals=candidate.trust_signals,
            security_score=candidate.security_score,
            security_tier=candidate.security_tier,
            security_verdict=candidate.security_verdict,
            security_flags=candidate.security_flags,
            matched_tokens=candidate.matched_tokens,
            selection_reason=ai_plan.skill_reasons.get(normalized_slug)
            or candidate.selection_reason,
        )

    if missing_slugs:
        fallback_names = {slug for slug in missing_slugs if slug}
        fallback_names.update({f"clawhub/{slug}" for slug in missing_slugs if slug})
        resolved_skills = db.scalars(
            select(Skill).where(
                Skill.status == ReviewStatus.approved,
                or_(Skill.source_slug.in_(missing_slugs), Skill.name.in_(fallback_names)),
            )
        ).all()
        resolved_lookup = {
            normalize_skill_identifier(skill.source_slug or skill.name): skill
            for skill in resolved_skills
        }
        for slug in missing_slugs:
            skill = resolved_lookup.get(slug)
            if skill is None or slug in selected_by_slug:
                continue
            quality = summarize_skill_quality(skill)
            security = summarize_skill_security(skill)
            selected_by_slug[slug] = RankedSkillMatch(
                skill=skill,
                score=0,
                quality_score=quality.score,
                quality_tier=quality.tier,
                trust_signals=quality.trust_signals,
                security_score=security.score,
                security_tier=security.tier,
                security_verdict=security.verdict,
                security_flags=security.flags,
                matched_tokens=[],
                selection_reason=ai_plan.skill_reasons.get(slug)
                or "Selected by planner AI outside the initial shortlist.",
            )
    selected = [selected_by_slug[slug] for slug in ordered_slugs if slug in selected_by_slug]
    return selected, ai_plan


def build_nodes_from_skills(
    *,
    skills: list[RankedSkillMatch],
    goal: str,
    targets: list[dict[str, Any]],
    output_format: str,
    ai_plan: AIPlanningResult | None,
) -> tuple[list[WorkflowNode], list[WorkflowEdge]]:
    nodes: list[WorkflowNode] = []
    step_lookup = {}
    if ai_plan:
        step_lookup = {
            normalize_skill_identifier(step.skill_slug): step
            for step in ai_plan.workflow_steps
        }

    for index, ranked_skill in enumerate(skills, start=1):
        skill = ranked_skill.skill
        normalized_slug = normalize_skill_identifier(skill.source_slug or skill.name)
        ai_step = step_lookup.get(normalized_slug)
        inputs: dict[str, Any] = {
            "request_text": goal,
            "targets": targets,
            "output_format": output_format,
        }
        if targets:
            inputs["primary_target"] = targets[0].get("value")
        if ai_step:
            inputs.update(ai_step.inputs)
        nodes.append(
            WorkflowNode(
                id=f"step_{index}",
                name=ai_step.name if ai_step and ai_step.name else skill.display_name or skill.name,
                skill_ref=skill.name,
                inputs=inputs,
            )
        )

    nodes.append(
        WorkflowNode(
            id=f"step_{len(nodes) + 1}",
            name=f"Deliver {output_format.upper()} result",
            skill_ref="output.export",
            inputs={"format": output_format},
        )
    )

    edges = [
        WorkflowEdge(from_node=nodes[index].id, to_node=nodes[index + 1].id)
        for index in range(len(nodes) - 1)
    ]
    return nodes, edges


def build_skill_recommendations(
    *,
    ranked_skills: list[RankedSkillMatch],
    output_format: str,
    reason_override: str | None = None,
) -> list[SkillRecommendation]:
    recommendations: list[SkillRecommendation] = []
    for index, ranked_skill in enumerate(ranked_skills, start=1):
        skill = ranked_skill.skill
        usage_parts = [
            f"第 {index} 步调用该 Skill",
            "读取本次命令与目标参数并把结果继续传给下一步",
            f"最终工作流会输出 {output_format.upper()} 结果",
        ]
        if skill.source_url:
            usage_parts.append(f"详情: {skill.source_url}")
        recommendations.append(
            SkillRecommendation(
                skill_id=skill.id,
                name=skill.name,
                display_name=skill.display_name or skill.name,
                category=skill.category,
                source=skill.source,
                source_slug=skill.source_slug,
                summary=skill.summary,
                description=skill.description,
                source_url=skill.source_url,
                usage_hint="；".join(usage_parts),
                selection_reason=reason_override or ranked_skill.selection_reason,
                quality_score=ranked_skill.quality_score,
                quality_tier=ranked_skill.quality_tier,
                trust_signals=ranked_skill.trust_signals,
                security_score=ranked_skill.security_score,
                security_tier=ranked_skill.security_tier,
                security_verdict=ranked_skill.security_verdict,
                security_flags=ranked_skill.security_flags,
            )
        )
    return recommendations


def build_response_bundle(
    *,
    goal: str,
    output_format: str,
    execution_mode: ExecutionMode,
    workflow_spec: WorkflowSpec,
    selected_skills: list[SkillRecommendation],
    ai_summary: str | None = None,
    ai_usage_steps: list[str] | None = None,
    communication_status: str = "pending_confirmation",
) -> tuple[PlannerAssistantResponse, CommunicationPreview]:
    _ = ai_summary
    _ = ai_usage_steps
    return build_free_plan_response_bundle(
        goal=goal,
        output_format=output_format,
        execution_mode=execution_mode,
        workflow_spec=workflow_spec,
        selected_skills=selected_skills,
        communication_status=communication_status,
    )


def resolve_workflow_skill_recommendations(
    *,
    workflow_spec: WorkflowSpec,
    output_format: str,
    db: Session,
) -> list[SkillRecommendation]:
    ordered_refs: list[str] = []
    seen_refs: set[str] = set()
    for node in workflow_spec.nodes:
        skill_ref = node.skill_ref
        if not skill_ref or "/" not in skill_ref or skill_ref == "output.export":
            continue
        if skill_ref in seen_refs:
            continue
        seen_refs.add(skill_ref)
        ordered_refs.append(skill_ref)

    if not ordered_refs:
        return []

    skills = {
        skill.name: skill
        for skill in db.scalars(select(Skill).where(Skill.name.in_(ordered_refs))).all()
    }
    ranked_skills: list[RankedSkillMatch] = []
    for skill_ref in ordered_refs:
        skill = skills.get(skill_ref)
        if skill is None:
            continue
        quality = summarize_skill_quality(skill)
        security = summarize_skill_security(skill)
        ranked_skills.append(
            RankedSkillMatch(
                skill=skill,
                score=0,
                quality_score=quality.score,
                quality_tier=quality.tier,
                trust_signals=quality.trust_signals,
                security_score=security.score,
                security_tier=security.tier,
                security_verdict=security.verdict,
                security_flags=security.flags,
                matched_tokens=[],
                selection_reason="Included in the generated workflow.",
            )
        )
    return build_skill_recommendations(
        ranked_skills=ranked_skills,
        output_format=output_format,
        reason_override="Included in the generated workflow.",
    )


def build_plan(
    *,
    goal: str,
    targets: list[dict[str, Any]] | None,
    output_format: str,
    execution_mode: ExecutionMode,
    risk_tolerance: RiskLevel | None,
    client_capabilities: dict[str, Any] | None,
    db: Session,
) -> PlanBuildResult:
    settings = get_settings()
    normalized_targets = targets or []
    request_tokens = tokenize_request_text(
        goal=f"{goal} {output_format}",
        targets=normalized_targets,
    )
    search_query_text = " ".join(
        [
            goal,
            output_format,
            *[
                " ".join(
                    str(part or "")
                    for part in (target.get("label"), target.get("value"))
                    if str(part or "").strip()
                )
                for target in normalized_targets
            ],
        ]
    )
    target_tokens = tokenize_request_text(goal="", targets=normalized_targets)
    decision_log: list[str] = []
    ai_actionability = assess_request_actionability_with_ai(
        goal=goal,
        targets=normalized_targets,
        output_format=output_format,
        execution_mode=execution_mode,
        settings=settings,
    )
    if ai_actionability is not None:
        actionable = ai_actionability.actionable
        decision_log.append(
            f"AI analyzed the intake and marked actionable={int(actionable)}: {ai_actionability.reason}"
        )
        if ai_actionability.missing_information:
            decision_log.append(
                "AI flagged missing information: " + ", ".join(ai_actionability.missing_information[:4]) + "."
            )
    else:
        actionable, actionability_log = assess_request_actionability(
            goal=goal,
            targets=normalized_targets,
            request_tokens=request_tokens,
        )
        decision_log.extend(actionability_log)
    capability_note = client_capabilities or {}

    if not actionable:
        if capability_note:
            decision_log.append(f"Client capabilities considered: {capability_note}.")
        assistant_response, communication_preview = build_usage_guidance_response(goal)
        return PlanBuildResult(
            actionable=False,
            workflow_spec=None,
            decision_log=decision_log,
            estimated_risk=None,
            assistant_response=assistant_response,
            selected_skills=[],
            communication_preview=communication_preview,
        )

    approved_recipes = list(
        db.scalars(select(Recipe).where(Recipe.status == ReviewStatus.approved)).all()
    )

    selected_recipe: Recipe | None = None
    best_score = 0
    for recipe in approved_recipes:
        score = recipe_match_score(recipe=recipe, request_tokens=request_tokens)
        if score > best_score:
            selected_recipe = recipe
            best_score = score

    source_recipe_id: int | None = None
    estimated_risk = RiskLevel.low
    selected_skill_matches: list[RankedSkillMatch] = []
    ai_plan: AIPlanningResult | None = None
    candidate_limit = max(settings.planner_ai_max_candidates, 1)
    skill_candidates = select_skill_candidates(
        db=db,
        query_text=search_query_text,
        request_tokens=request_tokens,
        limit=candidate_limit,
    )
    if skill_candidates:
        ai_selected_skills, ai_plan = select_skills_via_ai(
            goal=goal,
            targets=normalized_targets,
            output_format=output_format,
            execution_mode=execution_mode,
            candidates=skill_candidates,
            db=db,
        )
        if ai_selected_skills:
            selected_skill_matches = choose_ai_guided_free_plan(
                candidates=ai_selected_skills[:4],
                target_tokens=target_tokens,
                output_format=output_format,
            )
            if len(selected_skill_matches) == 1 and len(ai_selected_skills) > 1:
                decision_log.append(
                    "Planner AI shortlisted multiple indexed skills; free tier kept the strongest "
                    "single-skill plan."
                )
            else:
                decision_log.append(
                    f"Planner AI selected {len(selected_skill_matches)} indexed skill(s) from "
                    f"{len(skill_candidates)} candidate(s)."
                )
        else:
            selected_skill_matches = choose_free_skill_plan(
                candidates=skill_candidates,
                target_tokens=target_tokens,
                output_format=output_format,
            )
            if len(selected_skill_matches) == 1:
                decision_log.append("Free tier selected a single indexed skill using local ranking.")
            else:
                decision_log.append(
                    f"Selected {len(selected_skill_matches)} indexed skill(s) using local ranking."
                )

    if selected_recipe and not selected_skill_matches:
        source_recipe_id = selected_recipe.id
        estimated_risk = clamp_risk(selected_recipe.risk_level, risk_tolerance)
        nodes, edges = build_nodes_from_recipe(recipe=selected_recipe, goal=goal)
        decision_log.append(
            f"Matched approved recipe '{selected_recipe.name}' with score={best_score}."
        )
        if not nodes:
            nodes, edges = build_fallback_workflow(
                goal=goal,
                targets=normalized_targets,
                output_format=output_format,
            )
            decision_log.append("Recipe had no reusable node skeleton, generated fallback steps.")
    elif selected_skill_matches:
        if selected_recipe:
            decision_log.append(
                f"Skipped recipe '{selected_recipe.name}' because indexed Skill composition was available."
            )
        nodes, edges = build_nodes_from_skills(
            skills=selected_skill_matches,
            goal=goal,
            targets=normalized_targets,
            output_format=output_format,
            ai_plan=ai_plan,
        )
        highest_risk = max(
            (ranked.skill.risk_level for ranked in selected_skill_matches),
            key=risk_rank,
            default=RiskLevel.low,
        )
        estimated_risk = clamp_risk(highest_risk, risk_tolerance)
    else:
        nodes, edges = build_fallback_workflow(
            goal=goal,
            targets=normalized_targets,
            output_format=output_format,
        )
        estimated_risk = clamp_risk(RiskLevel.low, risk_tolerance)
        decision_log.append(
            "No approved recipe or indexed skill matched; generated a default 3-step workflow."
        )

    if normalized_targets:
        decision_log.append(f"Captured {len(normalized_targets)} target input(s) for execution.")

    if risk_tolerance:
        decision_log.append(f"Applied risk tolerance filter: {risk_tolerance.value}.")

    decision_log.append(f"Prepared output format: {output_format}.")
    decision_log.append(f"Preferred execution mode: {execution_mode.value}.")

    if capability_note:
        decision_log.append(f"Client capabilities considered: {capability_note}.")

    selected_skills = build_skill_recommendations(
        ranked_skills=selected_skill_matches,
        output_format=output_format,
    )
    workflow_name = ai_plan.workflow_name if ai_plan and ai_plan.workflow_name else f"Run request: {goal[:60]}"
    workflow_spec = WorkflowSpec(
        name=workflow_name[:120],
        inputs={
            "request_text": goal,
            "targets": normalized_targets,
            "execution_mode": execution_mode.value,
        },
        nodes=nodes,
        edges=edges,
        outputs={
            "result": "object",
            "format": output_format,
        },
        source_recipe_id=source_recipe_id,
        retry_policy={"max_retries": 1, "strategy": "simple"},
        confirm_points=[nodes[0].id] if nodes else None,
        risk_level=estimated_risk,
    )
    assistant_response, communication_preview = build_response_bundle(
        goal=goal,
        output_format=output_format,
        execution_mode=execution_mode,
        workflow_spec=workflow_spec,
        selected_skills=selected_skills,
        ai_summary=ai_plan.summary if ai_plan else None,
        ai_usage_steps=ai_plan.usage_steps if ai_plan else None,
    )

    return PlanBuildResult(
        actionable=True,
        workflow_spec=workflow_spec,
        decision_log=decision_log,
        estimated_risk=estimated_risk,
        assistant_response=assistant_response,
        selected_skills=selected_skills,
        communication_preview=communication_preview,
    )
