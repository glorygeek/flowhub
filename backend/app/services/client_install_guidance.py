from app.schemas.planner import (
    ClientInstallGuidance,
    ClientInstallTarget,
    SkillRecommendation,
)


def build_client_install_guidance(
    *,
    selected_skills: list[SkillRecommendation],
    install_requested: bool = False,
) -> ClientInstallGuidance:
    install_targets: list[ClientInstallTarget] = []
    seen: set[tuple[str, str]] = set()

    for skill in selected_skills:
        slug = _normalize_slug(skill.source_slug or skill.name)
        dedupe_key = (skill.source or "", slug or skill.name)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        install_command = None
        install_command_windows = None
        if skill.source == "clawhub" and slug:
            install_command = f"clawhub install {slug}"
            install_command_windows = f"clawhub.cmd install {slug}"

        install_targets.append(
            ClientInstallTarget(
                name=skill.name,
                display_name=skill.display_name,
                source=skill.source,
                source_slug=skill.source_slug,
                source_url=skill.source_url,
                fetch_strategy=_resolve_fetch_strategy(skill),
                required=True,
                install_command=install_command,
                install_command_windows=install_command_windows,
            )
        )

    if not install_targets:
        return ClientInstallGuidance(
            mode="client_managed",
            install_requested=install_requested,
            status="not_required",
            summary="当前工作流没有需要额外安装的 registry Skill；客户端只需要按返回结果继续执行。",
            steps=[
                "当前方案没有额外的 Skill 安装动作。",
                "客户端仍应先核对 workflow_summary、security_flags 与 planning 状态，再决定是否继续执行。",
            ],
            items=[],
            note="FlowHub 只返回工作流和执行线索，不会替不同客户端执行本地安装。",
        )

    return ClientInstallGuidance(
        mode="client_managed",
        install_requested=install_requested,
        status="pending_client_action" if install_requested else "deferred",
        summary=(
            "FlowHub 只返回安装线索和命令模板。只有当最终用户明确提出下载/安装指令时，"
            "才应由当前客户端 OpenClaw 在本地执行安装。"
        ),
        steps=[
            "先核对 selected_skills、workflow_summary 和 safety_guidance，确认当前方案确实需要这些依赖。",
            "只有当最终用户明确提出“下载”或“安装”指令时，才由当前客户端执行安装命令。",
            "若当前 Skill 来自 ClawHub registry，可优先使用 `clawhub install <slug>`；Windows 可用 `clawhub.cmd install <slug>`。",
            "安装完成后，再由当前客户端按 workflow_spec 在本地组合并继续执行；FlowHub 服务端不代装。",
            "遇到 manual_review_required 或 block_or_quarantine 时，先暂停并做人工复核。",
        ],
        items=install_targets,
        note="这份安装指导适用于不同配置的 OpenClaw 客户端；是否执行安装，由客户端在用户明确授权后自行决定。",
    )


def _resolve_fetch_strategy(skill: SkillRecommendation) -> str:
    if skill.source == "clawhub":
        return "clawhub_registry"
    if skill.source:
        return f"{skill.source}_registry"
    return "registry"


def _normalize_slug(value: str | None) -> str:
    return str(value or "").strip().removeprefix("clawhub/")
