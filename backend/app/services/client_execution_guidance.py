from app.schemas.planner import ClientExecutionGuidance, ClientSkillTarget, SkillRecommendation
from app.schemas.workflow_spec import WorkflowSpec


def build_client_execution_guidance(
    *,
    workflow_spec: WorkflowSpec | None,
    selected_skills: list[SkillRecommendation],
) -> ClientExecutionGuidance | None:
    if workflow_spec is None:
        return None

    skill_targets = [
        ClientSkillTarget(
            name=skill.name,
            display_name=skill.display_name,
            source=skill.source,
            source_slug=skill.source_slug,
            source_url=skill.source_url,
            fetch_strategy=_resolve_fetch_strategy(skill),
            required=True,
        )
        for skill in selected_skills
    ]

    return ClientExecutionGuidance(
        summary=(
            "客户端应根据返回的 Skill 清单到官方插件中心或 Skill 中心抓取依赖，"
            "在本地组合工作流，并由客户端承担 AI 规划与执行算力。平台负责返回编排结果、"
            "安装线索和会话引导。"
        ),
        steps=[
            "读取返回的 selected_skills 与 workflow_spec。",
            "根据 source_slug / source_url 去官方插件中心或 Skill 中心抓取所需 Skill。",
            "在客户端本地按 workflow_spec 的节点顺序组合这些 Skill。",
            "客户端本地使用自己的 AI 模型或算力完成分析、规划和执行。",
            "执行结果、进度或失败信息再回传到当前用户会话。",
        ],
        skill_targets=skill_targets,
    )


def _resolve_fetch_strategy(skill: SkillRecommendation) -> str:
    if skill.source == "clawhub":
        return "clawhub_registry"
    if skill.source:
        return f"{skill.source}_registry"
    return "registry"
