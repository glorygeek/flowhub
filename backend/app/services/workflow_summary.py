from app.schemas.planner import (
    ClientExecutionGuidance,
    PlannerAssistantResponse,
    SkillRecommendation,
    WorkflowSafetyReviewItem,
    WorkflowSummary,
    WorkflowSummaryStep,
)
from app.schemas.workflow_spec import WorkflowSpec


def build_workflow_summary(
    *,
    workflow_spec: WorkflowSpec | None,
    selected_skills: list[SkillRecommendation],
    assistant_response: PlannerAssistantResponse,
    client_execution_guidance: ClientExecutionGuidance | None,
) -> WorkflowSummary | None:
    if workflow_spec is None:
        return None

    skill_lookup = {skill.name: skill for skill in selected_skills}
    steps: list[WorkflowSummaryStep] = []
    formula_parts: list[str] = []
    safety_review_items: list[WorkflowSafetyReviewItem] = []

    for index, node in enumerate(workflow_spec.nodes, start=1):
        skill_ref = node.skill_ref or node.name
        if skill_ref == "output.export":
            format_hint = str(
                (node.inputs or {}).get("format")
                or (workflow_spec.outputs or {}).get("format")
                or ""
            ).strip()
            formula_ref = f"output.export({format_hint})" if format_hint else "output.export"
            steps.append(
                WorkflowSummaryStep(
                    index=index,
                    skill_ref="output.export",
                    display_name=node.name,
                    role="交付最终结果",
                    summary=f"把前序步骤的结果整理为 {format_hint.upper() if format_hint else '目标'} 输出。",
                    planning_status="eligible",
                )
            )
            formula_parts.append(f"{index}#{formula_ref}")
            continue

        skill = skill_lookup.get(skill_ref)
        planning_status = _format_planning_status(skill.security_verdict if skill else None)
        display_name = skill.display_name if skill else node.name
        summary = ""
        if skill is not None:
            summary = skill.summary or skill.description or skill.selection_reason
        if not summary:
            summary = node.name

        steps.append(
            WorkflowSummaryStep(
                index=index,
                skill_ref=skill_ref,
                display_name=display_name,
                role=node.name,
                summary=summary,
                planning_status=planning_status,
                source_url=skill.source_url if skill else None,
            )
        )
        formula_parts.append(f"{index}#{skill_ref}")

        if skill is not None and (
            skill.security_verdict != "safe_to_use" or bool(skill.security_flags)
        ):
            safety_review_items.append(
                WorkflowSafetyReviewItem(
                    skill_ref=skill_ref,
                    display_name=display_name,
                    planning_status=planning_status,
                    security_flags=skill.security_flags,
                    note=_build_security_note(skill),
                )
            )

    plan_type = _resolve_plan_type(selected_skills)
    formula = " + ".join(formula_parts) if formula_parts else "fallback-workflow"
    headline = _build_headline(plan_type=plan_type, workflow_name=workflow_spec.name)
    explanation = _build_explanation(
        plan_type=plan_type,
        workflow_spec=workflow_spec,
        selected_skills=selected_skills,
    )

    safety_guidance = [
        "执行前先核对目标对象、权限范围、输出格式和依赖来源。",
        "优先执行 planning=eligible 的 Skill；遇到 manual_review 或 excluded 时先暂停人工复核。",
        "不要在聊天窗口直接粘贴 API key、token、cookie 或 basic auth 原文。",
        "如当前运行面已安装 flowhub-skill-vetter 或 flowhub-skill-discovery，可先做一轮安全复核再执行。",
    ]
    if safety_review_items:
        safety_guidance.insert(0, "当前工作流中存在需要特别注意的 Skill，请先复核下方安全清单。")
    else:
        safety_guidance.insert(0, "当前工作流未命中明显高风险 Skill，但执行前仍应做最小人工复核。")

    handoff_steps = list(client_execution_guidance.steps) if client_execution_guidance else []

    return WorkflowSummary(
        formula=formula,
        plan_type=plan_type,
        headline=headline,
        explanation=explanation,
        steps=steps,
        usage_steps=list(assistant_response.usage_steps),
        safety_guidance=safety_guidance,
        handoff_steps=handoff_steps,
        safety_review_items=safety_review_items,
    )


def _resolve_plan_type(selected_skills: list[SkillRecommendation]) -> str:
    if not selected_skills:
        return "fallback"
    if len(selected_skills) == 1:
        return "single_skill"
    return "multi_skill"


def _build_headline(*, plan_type: str, workflow_name: str) -> str:
    if plan_type == "single_skill":
        return f"单 Skill 可行性工作流：{workflow_name}"
    if plan_type == "multi_skill":
        return f"组合可行性工作流：{workflow_name}"
    return f"兜底可行性工作流：{workflow_name}"


def _build_explanation(
    *,
    plan_type: str,
    workflow_spec: WorkflowSpec,
    selected_skills: list[SkillRecommendation],
) -> str:
    node_count = len(workflow_spec.nodes)
    output_format = str((workflow_spec.outputs or {}).get("format") or "target").upper()
    if plan_type == "single_skill":
        return (
            f"后端已优先选择 1 个可独立完成需求的 Skill，并补上结果交付步骤。"
            f"当前工作流共有 {node_count} 个节点，目标输出为 {output_format}。"
        )
    if plan_type == "multi_skill":
        return (
            f"后端按当前需求生成了 {len(selected_skills)} 个 Skill 组成的最小可行工作流，"
            f"再附加结果交付步骤。当前工作流共有 {node_count} 个节点，目标输出为 {output_format}。"
        )
    return (
        f"当前索引目录没有足够匹配的已审核 Skill，后端先生成兜底流程以便继续验证链路。"
        f"当前工作流共有 {node_count} 个节点，目标输出为 {output_format}。"
    )


def _format_planning_status(verdict: str | None) -> str:
    if verdict == "block_or_quarantine":
        return "excluded"
    if verdict == "manual_review_required":
        return "manual_review"
    if verdict == "use_with_caution":
        return "caution"
    return "eligible"


def _build_security_note(skill: SkillRecommendation) -> str:
    if skill.security_verdict == "block_or_quarantine":
        return "该 Skill 当前默认不参与安全规划，只有人工放行后才适合执行。"
    if skill.security_verdict == "manual_review_required":
        return "该 Skill 需要人工复核后再执行。"
    if skill.security_verdict == "use_with_caution":
        return "该 Skill 可以执行，但建议先核对权限范围和数据来源。"
    if skill.security_flags:
        return "该 Skill 没有被默认阻断，但仍带有需要关注的安全信号。"
    return "该 Skill 当前可直接参与默认规划。"
