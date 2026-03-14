from app.core.config import get_settings
from app.models.common import ExecutionMode
from app.schemas.planner import CommunicationPreview, PlannerAssistantResponse, SkillRecommendation
from app.schemas.workflow_spec import WorkflowSpec
from app.services.ai_assistant import rewrite_planner_response_with_ai

FREE_USAGE_GUIDE_EXAMPLES = [
    "分析 AAPL 和 NVDA 最近 3 个月走势，并给我一份 markdown 简报。",
    "抓取这个 API 的数据并导出 csv。",
    "总结这篇文章的核心观点，并整理成可发给客户的回复。",
]


def _quality_note(skill: SkillRecommendation) -> str:
    if not skill.trust_signals:
        return ""
    if skill.quality_tier in {"trusted", "strong"}:
        return f"该 Skill 当前可信度为 {skill.quality_tier}，信号包括：{'、'.join(skill.trust_signals[:3])}。"
    return f"该 Skill 当前可信度为 {skill.quality_tier}。"


def build_free_usage_guidance_response(goal: str) -> tuple[PlannerAssistantResponse, CommunicationPreview]:
    usage_steps = [
        "按“动作 + 对象 + 结果形式”描述你的需求。",
        *[f"示例：{example}" for example in FREE_USAGE_GUIDE_EXAMPLES],
    ]
    assistant_response = PlannerAssistantResponse(
        template_key="free_usage_guidance",
        headline="这条消息还不足以生成工作流",
        reply_text="请直接告诉我你要处理什么对象、要执行什么动作，以及希望返回什么结果。",
        usage_steps=usage_steps,
        confirmation_prompt="按上面的任一示例补充后再发送，我会继续为你生成免费版方案。",
        delivery_note="当前没有创建工作流，也没有进入执行确认阶段。",
    )
    communication_preview = CommunicationPreview(
        template_key="free_usage_guidance",
        status="needs_clarification",
        title="请补充有效需求",
        body=f"已收到消息：{goal}。这条消息还不足以生成工作流，请按示例补充你的需求后再发送。",
        usage_steps=usage_steps,
    )
    ai_rewrite = rewrite_planner_response_with_ai(
        template_key="free_usage_guidance",
        goal=goal,
        output_format="markdown",
        execution_mode=ExecutionMode.remote,
        workflow_spec=None,
        selected_skills=[],
        communication_status="needs_clarification",
        default_assistant=assistant_response,
        default_preview=communication_preview,
        settings=get_settings(),
    )
    if ai_rewrite is not None:
        return ai_rewrite
    return assistant_response, communication_preview


def build_free_plan_response_bundle(
    *,
    goal: str,
    output_format: str,
    execution_mode: ExecutionMode,
    workflow_spec: WorkflowSpec,
    selected_skills: list[SkillRecommendation],
    communication_status: str = "pending_confirmation",
) -> tuple[PlannerAssistantResponse, CommunicationPreview]:
    if selected_skills:
        if len(selected_skills) == 1:
            only_skill = selected_skills[0]
            template_key = "free_single_skill_plan"
            headline = "已生成免费版可执行方案"
            reply_text = (
                f"已按免费版规则优先选择 1 个可独立完成任务且高可信优先的 Skill：{only_skill.display_name}。"
                f"当前方案会输出 {output_format.upper()} 结果。"
            )
            usage_steps = [
                "检查目标对象、关键参数和目标输出是否完整。",
                f"确认 {only_skill.display_name} 能覆盖这次需求。",
                _quality_note(only_skill) or "已综合星标、下载、评论反馈和审核信号进行优先排序。",
                "客户端执行时会根据返回的 Skill 信息去官方插件中心或 Skill 中心抓取依赖，并在本地组合。",
                "如果可以直接执行，请明确回复“确认执行”。",
            ]
            delivery_note = "确认后平台会把这套免费版方案回传到用户会话；客户端负责抓取 Skill、在本地组合，并承担 AI 执行算力。"
        else:
            skill_names = " -> ".join(skill.display_name for skill in selected_skills)
            template_key = "free_minimal_combo_plan"
            headline = "已生成免费版最小可行方案"
            reply_text = (
                f"单个 Skill 不足以稳定覆盖当前需求，已按免费版规则组合最小可行方案：{skill_names}。"
                f"当前方案会输出 {output_format.upper()} 结果。"
            )
            usage_steps = [
                "检查目标地址、附加参数和授权信息是否完整。",
                "确认这套最小可行方案符合你的预期结果。",
                "平台已优先按星标、安装量、评论反馈、官方发布者和审核信号选择更可信的 Skill。",
                "客户端执行时会根据返回的 Skill 信息去官方插件中心或 Skill 中心抓取依赖，并在本地组合。",
                "如果可以直接执行，请明确回复“确认执行”。",
            ]
            delivery_note = "确认后平台会把这套免费版方案回传到用户会话；客户端负责抓取 Skill、在本地组合，并承担 AI 执行算力。"
    else:
        template_key = "free_fallback_plan"
        headline = "已生成免费版通用方案"
        reply_text = (
            "当前索引目录里没有足够匹配的已审核 Skill，已先生成一套通用兜底流程，"
            f"用于返回 {output_format.upper()} 结果。"
        )
        usage_steps = [
            "补充更明确的目标地址、API 或预期结果，可以提高命中率。",
            "如果继续执行，客户端仍会按返回信息去官方插件中心或 Skill 中心抓取依赖并在本地组合。",
            "如果接受通用流程，请明确回复“确认执行”。",
            "如果你希望更精准的方案，请先补充上下文后再发送。",
        ]
        delivery_note = "当前方案以兜底流程为主；若继续执行，客户端负责抓取 Skill、在本地组合，并承担 AI 执行算力。"

    if communication_status == "ready_to_send":
        confirmation_prompt = "方案已确认，客户端将抓取所需 Skill 并在本地组合执行，平台会继续回传进度和结果。"
        delivery_note = "当前方案已经确认；客户端负责抓取 Skill 与本地 AI 执行，平台继续承担会话引导和结果回传。"
    else:
        confirmation_prompt = "如果这套免费版方案符合预期，请直接回复“确认执行”。"

    assistant_response = PlannerAssistantResponse(
        template_key=template_key,
        headline=headline,
        reply_text=reply_text,
        usage_steps=usage_steps,
        confirmation_prompt=confirmation_prompt,
        delivery_note=delivery_note,
    )
    communication_preview = CommunicationPreview(
        template_key=template_key,
        status=communication_status,
        title="FlowHub 免费版方案已准备",
        body=f"已收到命令：{goal}。{reply_text} {delivery_note}".strip(),
        usage_steps=usage_steps,
    )
    ai_rewrite = rewrite_planner_response_with_ai(
        template_key=template_key,
        goal=goal,
        output_format=output_format,
        execution_mode=execution_mode,
        workflow_spec=workflow_spec,
        selected_skills=selected_skills,
        communication_status=communication_status,
        default_assistant=assistant_response,
        default_preview=communication_preview,
        settings=get_settings(),
    )
    if ai_rewrite is not None:
        return ai_rewrite
    return assistant_response, communication_preview
