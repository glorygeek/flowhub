const DEFAULT_TIMEOUT_MS = 20000;
const DEFAULT_EXECUTION_MODE = "remote";
const DEFAULT_OUTPUT_FORMAT = "markdown";
const TARGET_TYPES = new Set(["url", "api", "text"]);
const CREDENTIAL_KINDS = new Set(["api_key", "token", "cookie", "basic_auth", "other"]);
const CONFIRM_PATTERNS = [
  /\bconfirm\b/i,
  /\bexecute\b/i,
  /\bgo ahead\b/i,
  /确认执行/,
  /开始吧/,
  /继续/,
  /可以执行/,
  /执行吧/
];
const INSTALL_PATTERNS = [
  /\binstall\b/i,
  /\bdownload\b/i,
  /安装/,
  /下载/,
  /拉取/
];
const WELCOME_PATTERNS = [
  /^(hi|hello|hey|yo|help|start)[!,. ]*$/i,
  /^(你好|您好|嗨|哈喽|开始|帮助|说明|介绍一下)[!！,.，。 ]*$/,
  /(第一次使用|初次使用|首次使用)/,
  /(介绍(一下)?\s*(flowhub|这个项目|项目|平台))/i,
  /(主要功能|功能介绍|插件清单|技能清单|怎么安装|安装方式)/,
  /(flowhub.*(是什么|怎么用|介绍|功能))/i,
  /((how do i install|how to install).*(flowhub|plugin|skill|skills))/i,
  /((what is).*(flowhub))/i,
  /((what is|how to use).*(flowhub))/i,
  /^(介绍一下flowhub|flowhub介绍|flowhub功能)$/i
];

function getConfig(api) {
  const pluginCfg =
    api && typeof api === "object" && api.pluginConfig && typeof api.pluginConfig === "object"
      ? api.pluginConfig
      : null;
  const globalCfg =
    api && typeof api === "object" && api.config && typeof api.config === "object" ? api.config : null;
  const cfg = pluginCfg || globalCfg || {};
  const apiBaseUrl = String(cfg.apiBaseUrl || "").trim().replace(/\/+$/, "");
  const apiKey = String(cfg.apiKey || "").trim();
  if (!apiBaseUrl) {
    throw new Error("FlowHub plugin config is missing apiBaseUrl");
  }
  if (!apiKey) {
    throw new Error("FlowHub plugin config is missing apiKey");
  }
  return {
    apiBaseUrl,
    apiKey,
    timeoutMs: Number.isFinite(cfg.timeoutMs) ? cfg.timeoutMs : DEFAULT_TIMEOUT_MS,
    defaultExecutionMode: cfg.defaultExecutionMode || DEFAULT_EXECUTION_MODE,
    defaultOutputFormat: cfg.defaultOutputFormat || DEFAULT_OUTPUT_FORMAT
  };
}

function normalizeTargets(value) {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .filter((item) => item && typeof item === "object" && String(item.value || "").trim())
    .map((item) => ({
      type: TARGET_TYPES.has(item.type) ? item.type : "text",
      label: String(item.label || "").trim(),
      value: String(item.value || "").trim()
    }));
}

function normalizeCredentials(value) {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .filter(
      (item) =>
        item &&
        typeof item === "object" &&
        String(item.label || "").trim() &&
        String(item.value || "").trim()
    )
    .map((item) => ({
      label: String(item.label || "").trim(),
      kind: CREDENTIAL_KINDS.has(item.kind) ? item.kind : "other",
      value: String(item.value || "").trim(),
      ephemeral: item.ephemeral !== false
    }));
}

async function requestJson(url, init, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(new Error("FlowHub request timed out")), timeoutMs);

  try {
    const response = await fetch(url, { ...init, signal: controller.signal });
    const text = await response.text();
    let data = null;

    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = text;
      }
    }

    if (!response.ok) {
      const detail = typeof data === "string" ? data : JSON.stringify(data);
      throw new Error(`FlowHub API ${response.status}: ${detail}`);
    }

    return data;
  } finally {
    clearTimeout(timer);
  }
}

function looksLikeConfirmation(text) {
  const normalized = String(text || "").trim();
  if (!normalized) {
    return false;
  }
  return CONFIRM_PATTERNS.some((pattern) => pattern.test(normalized));
}

function looksLikeInstallRequest(text) {
  const normalized = String(text || "").trim();
  if (!normalized) {
    return false;
  }
  return INSTALL_PATTERNS.some((pattern) => pattern.test(normalized));
}

function looksLikeWelcomeRequest(text) {
  const normalized = String(text || "").trim();
  if (!normalized) {
    return true;
  }
  return WELCOME_PATTERNS.some((pattern) => pattern.test(normalized));
}

function formatSelectedSkills(skills) {
  if (!Array.isArray(skills) || skills.length === 0) {
    return ["selected_skills: none"];
  }

  return [
    "selected_skills:",
    ...skills.map(
      (skill, index) =>
        `${index + 1}. ${skill.display_name} | ${skill.category} | quality=${skill.quality_tier || "basic"} (${Number(
          skill.quality_score || 0
        ).toFixed(1)}) | security=${skill.security_tier || "caution"} (${Number(
          skill.security_score || 0
        ).toFixed(1)}) | planning=${formatPlanningEligibility(skill.security_verdict)} | ${skill.selection_reason} | ${
          Array.isArray(skill.trust_signals) && skill.trust_signals.length > 0
            ? skill.trust_signals.join(", ")
            : "no trust signals"
        } | ${skill.usage_hint}`
    )
  ];
}

function formatWorkflowFormula(skills) {
  if (!Array.isArray(skills) || skills.length === 0) {
    return "fallback-workflow";
  }
  return skills.map((skill, index) => `${index + 1}#${skill.name || skill.display_name || "unknown-skill"}`).join(" + ");
}

function getWorkflowFormula(result) {
  if (result?.workflow_summary?.formula) {
    return result.workflow_summary.formula;
  }
  return formatWorkflowFormula(result?.selected_skills);
}

function formatPlanningEligibility(verdict) {
  if (verdict === "block_or_quarantine") {
    return "excluded";
  }
  if (verdict === "manual_review_required") {
    return "manual_review";
  }
  if (verdict === "use_with_caution") {
    return "caution";
  }
  return "eligible";
}

function formatSecurityGuidance(skills, workflowSummary) {
  if (workflowSummary && Array.isArray(workflowSummary.safety_guidance) && workflowSummary.safety_guidance.length > 0) {
    const lines = ["security_guidance:"];
    for (const [index, item] of workflowSummary.safety_guidance.entries()) {
      lines.push(`${index + 1}. ${item}`);
    }
    if (Array.isArray(workflowSummary.safety_review_items) && workflowSummary.safety_review_items.length > 0) {
      for (const [index, item] of workflowSummary.safety_review_items.entries()) {
        const flags = Array.isArray(item.security_flags) && item.security_flags.length > 0
          ? item.security_flags.join(", ")
          : "no security flags";
        lines.push(
          `${index + 1}. ${item.display_name || item.skill_ref || "unknown"} | planning=${item.planning_status || "eligible"} | flags=${flags} | ${item.note || ""}`.trim()
        );
      }
    }
    return lines;
  }

  const candidates = Array.isArray(skills) ? skills : [];
  if (candidates.length === 0) {
    return [
      "security_guidance:",
      "1. 当前没有命中已审核 Skill，执行前请人工确认数据来源、权限范围和输出用途。",
      "2. 如需补充安全把关，请先做 Skill Discovery，再决定是否执行。"
    ];
  }

  const lines = [
    "security_guidance:",
    "1. 优先执行 planning=eligible 的 Skill；遇到 manual_review 或 excluded 时先停下来人工复核。",
    "2. 执行前核对每个 Skill 的 source、source_url、trust_signals 与 security_flags。",
    "3. 不要把 API key、token、cookie 直接回填到聊天窗口；只在受控执行面提供。",
    "4. 如需额外把关，先做 Skill Discovery / Skill Vetter，再继续执行。"
  ];

  candidates.forEach((skill, index) => {
    const flags = Array.isArray(skill.security_flags) && skill.security_flags.length > 0
      ? skill.security_flags.join(", ")
      : "no security flags";
    lines.push(
      `${index + 1}. ${skill.display_name || skill.name || "unknown"} | planning=${formatPlanningEligibility(
        skill.security_verdict
      )} | flags=${flags}`
    );
  });

  return lines;
}

function formatUsageSteps(steps) {
  if (!Array.isArray(steps) || steps.length === 0) {
    return ["usage_steps: none"];
  }

  return ["usage_steps:", ...steps.map((step, index) => `${index + 1}. ${step}`)];
}

function formatClientExecutionGuidance(guidance) {
  if (!guidance) {
    return ["client_execution_guidance: none"];
  }

  const lines = [
    "client_execution_guidance:",
    `mode: ${guidance.mode || "client_fetch_and_compose"}`,
    `ai_runtime_owner: ${guidance.ai_runtime_owner || "client"}`,
    `summary: ${guidance.summary || ""}`
  ];

  if (Array.isArray(guidance.steps) && guidance.steps.length > 0) {
    lines.push("client_execution_steps:");
    for (const [index, step] of guidance.steps.entries()) {
      lines.push(`${index + 1}. ${step}`);
    }
  }

  if (Array.isArray(guidance.skill_targets) && guidance.skill_targets.length > 0) {
    lines.push("client_fetch_targets:");
    for (const [index, item] of guidance.skill_targets.entries()) {
      lines.push(
        `${index + 1}. ${item.display_name} | ${item.source || "unknown"} | ${item.source_slug || "n/a"} | ${
          item.source_url || "n/a"
        } | ${item.fetch_strategy || "registry"}`
      );
    }
  }

  lines.push(
    "client_execution_note: FlowHub only returns install guidance and workflow composition data. Each client OpenClaw instance decides whether to install skills locally after explicit user instructions."
  );

  return lines;
}

function wrapBlock(label, text) {
  return `${label}:\n<<<\n${String(text || "").trim()}\n>>>`;
}

function buildWelcomeReply() {
  return [
    "欢迎使用 FlowHub。",
    "FlowHub 是一个面向 OpenClaw 对话入口的工作流编排服务：它会把你的自然语言需求转换成可行性工作流，返回 Skill 组合、使用方式、安全建议，以及后续安装/执行指引。",
    "",
    "你现在可以直接告诉我：",
    "1. 你要处理什么对象",
    "2. 你要执行什么动作",
    "3. 你希望返回什么结果",
    "",
    "示例：",
    "- 分析 AAPL 最近三个月走势，并返回 markdown 摘要",
    "- 抓取这个 API 的数据并导出 csv",
    "- 总结这篇文章的核心观点，并整理成可发给客户的回复",
    "",
    "如果你只是先了解项目或安装方式，也可以继续问我。"
  ].join("\n");
}

function buildWelcomeText(config) {
  return [
    "FLOWHUB_WELCOME_READY",
    "headline: 欢迎使用 FlowHub",
    "project_summary: FlowHub 是一个通过 OpenClaw 对话入口接收需求、搜索可信 Skill、组合工作流、返回安全建议与安装指导的平台。",
    "core_functions:",
    "1. 自然语言需求分析与工作流组合",
    "2. Skill 检索、可信排序与安全提示",
    "3. 在同一聊天线程中返回工作流公式、确认提示和执行交接信息",
    "4. 仅在用户明确提出下载/安装时，返回客户端自管安装命令",
    "related_components:",
    "1. plugin | flowhub-openclaw | OpenClaw 与 FlowHub 后端的桥接插件",
    "2. skill | flowhub-orchestrator | 当前客户侧默认主调度 Skill；负责接收需求、生成工作流、处理确认与回复",
    "3. optional skill | flowhub-skill-discovery | 可选辅助 Skill，用于发现可信 Skill 并比较候选项",
    "4. optional skill | flowhub-skill-vetter | 可选安全复核 Skill，适合安装前把关",
    "5. capability | clawhub install <slug> | 仅在用户明确要求安装时，由当前客户端自行处理",
    "installation_guidance:",
    "1. 若当前 OpenClaw 客户端尚未接入 FlowHub，请由本地管理员安装 flowhub-openclaw 插件。",
    "2. 插件安装后，至少配置 apiBaseUrl 与 apiKey。",
    `3. 当前推荐 FlowHub API 地址示例：${config.apiBaseUrl}`,
    "4. 当前客户端如需下载具体 Skill，只有在用户明确提出下载/安装指令时，才执行类似 `clawhub install <slug>` 的命令。",
    "5. 安装完成后，再由当前客户端按本地环境继续执行；FlowHub 服务端不代装。",
    "safety_note: 首次使用时，建议优先阅读返回的安全建议；遇到 manual_review 或 excluded 时先暂停人工复核。",
    wrapBlock("suggested_chat_reply", buildWelcomeReply()),
    "next_action: introduce FlowHub briefly, show the related plugin/skill list, explain install prerequisites, then ask the user to describe a concrete task."
  ].join("\n");
}

function buildSuggestedPlanReply(result) {
  const actionable = result?.actionable !== false;
  const headline = result?.assistant_response?.headline || "FlowHub 已处理你的消息";
  const replyText = result?.assistant_response?.reply_text || "";
  const usageSteps = Array.isArray(result?.assistant_response?.usage_steps)
    ? result.assistant_response.usage_steps
    : [];
  const confirmationPrompt = result?.assistant_response?.confirmation_prompt || "";
  const selectedSkills = Array.isArray(result?.selected_skills) ? result.selected_skills : [];
  const workflowFormula = getWorkflowFormula(result);
  const workflowSummary = result?.workflow_summary || null;

  if (!actionable) {
    return [
      headline,
      replyText,
      "你可以这样描述需求：",
      ...usageSteps.map((step, index) => `${index + 1}. ${step}`)
    ].join("\n");
  }

  const lines = [
    workflowSummary?.headline || headline,
    workflowSummary?.explanation || replyText,
    `可行性工作流：${workflowFormula}`
  ];
  if (selectedSkills.length > 0) {
    lines.push("本次选中的 Skill：");
    for (const [index, skill] of selectedSkills.entries()) {
      lines.push(
        `${index + 1}. ${skill.display_name}：${skill.summary || skill.description || skill.selection_reason}`
      );
      if (Array.isArray(skill.trust_signals) && skill.trust_signals.length > 0) {
        lines.push(`   可信信号：${skill.quality_tier || "basic"} | ${skill.trust_signals.join("、")}`);
      }
      if (Array.isArray(skill.security_flags) && skill.security_flags.length > 0) {
        lines.push(`   安全审查：${skill.security_tier || "caution"} | ${skill.security_flags.join("、")}`);
      }
      lines.push(`   规划状态：${formatPlanningEligibility(skill.security_verdict)}`);
    }
  }
  lines.push("安全把关建议：");
  lines.push(...formatSecurityGuidance(selectedSkills, workflowSummary).slice(1));
  if (usageSteps.length > 0) {
    lines.push("使用方式：");
    for (const [index, step] of usageSteps.entries()) {
      lines.push(`${index + 1}. ${step}`);
    }
  }
  if (confirmationPrompt) {
    lines.push(confirmationPrompt);
  }
  return lines.join("\n");
}

function toSlug(value) {
  return String(value || "")
    .trim()
    .replace(/^clawhub\//i, "");
}

function collectInstallTargets(result) {
  const targets = Array.isArray(result?.client_execution_guidance?.skill_targets)
    ? result.client_execution_guidance.skill_targets
    : [];
  const seen = new Set();
  const items = [];

  for (const item of targets) {
    const slug = toSlug(item?.source_slug || item?.name);
    if (!slug || seen.has(slug) || item?.fetch_strategy !== "clawhub_registry") {
      continue;
    }
    seen.add(slug);
    items.push({
      slug,
      displayName: String(item?.display_name || item?.name || slug).trim(),
      sourceUrl: String(item?.source_url || "").trim()
    });
  }

  return items;
}

function buildInstallGuidance(result, options) {
  const targets = collectInstallTargets(result);
  const installRequested = options?.installRequested === true;
  if (targets.length === 0) {
    return {
      mode: "client_managed",
      installRequested,
      status: "not_required",
      items: [],
      summary: "当前工作流没有需要额外安装的 ClawHub registry Skill。"
    };
  }

  return {
    mode: "client_managed",
    installRequested,
    status: installRequested ? "pending_client_action" : "deferred",
    summary: installRequested
      ? "当前会话已明确提出安装/下载意图。应由当前 OpenClaw 客户端按本地配置自行执行安装。"
      : "当前方案只返回安装指导。只有当用户明确提出下载或安装指令时，才应由客户端 OpenClaw 自行处理。",
    items: targets.map((target) => ({
      slug: target.slug,
      displayName: target.displayName,
      sourceUrl: target.sourceUrl,
      installCommand: `clawhub install ${target.slug}`,
      installCommandWindows: `clawhub.cmd install ${target.slug}`,
      fetchStrategy: "clawhub_registry",
      status: "client_managed"
    }))
  };
}

function formatInstallGuidance(guidance) {
  if (!guidance) {
    return [];
  }

  const lines = ["client_install_guidance:"];
  lines.push(`install_mode: ${guidance.mode || "client_managed"}`);
  lines.push(`install_requested: ${guidance.installRequested ? "yes" : "no"}`);
  lines.push(`install_status: ${guidance.status || "deferred"}`);
  lines.push(`install_summary: ${guidance.summary || ""}`);

  if (Array.isArray(guidance.items) && guidance.items.length > 0) {
    lines.push("install_targets:");
    for (const [index, item] of guidance.items.entries()) {
      lines.push(
        `${index + 1}. ${item.displayName} | slug=${item.slug} | source_url=${item.sourceUrl || "n/a"} | install=${item.installCommand}`
      );
      lines.push(`   windows_install: ${item.installCommandWindows}`);
    }
  }

  lines.push(
    "install_note: FlowHub does not install plugins or skills on behalf of arbitrary OpenClaw clients. The current client should act only after explicit user download/install instructions."
  );
  return lines;
}

function buildUserFacingInstallSteps(installGuidance) {
  if (!installGuidance || !Array.isArray(installGuidance.items) || installGuidance.items.length === 0) {
    return [];
  }

  const lines = ["客户端安装方式："];
  if (installGuidance.status === "pending_client_action") {
    lines.push("你已经明确提出安装/下载意图，请由当前 OpenClaw 客户端在本地执行以下命令：");
  } else {
    lines.push("如后续需要本地安装，请在当前 OpenClaw 客户端明确发送下载/安装指令后再执行以下命令：");
  }

  for (const [index, item] of installGuidance.items.entries()) {
    lines.push(`${index + 1}. 通用命令：${item.installCommand}`);
    lines.push(`   Windows 命令：${item.installCommandWindows}`);
    if (item.sourceUrl) {
      lines.push(`   Skill 地址：${item.sourceUrl}`);
    }
  }

  lines.push("安装完成后，再由当前客户端按本地环境继续执行，不由 FlowHub 服务端代装。");
  return lines;
}

function buildSuggestedConfirmReply(result, installGuidance) {
  const requestId = result?.request?.id ?? "n/a";
  if (installGuidance?.status === "pending_client_action") {
    return [
      `方案已确认（Request ID: ${requestId}）。`,
      "当前会话已经明确提出安装/下载意图。请由当前 OpenClaw 客户端按本地配置自行安装所需 Skill。",
      "本轮到这里为止：不要在未完成本地安装前自行改走网页抓取、API 抓取、exec 或其他备用执行路径。",
      ...buildUserFacingInstallSteps(installGuidance)
    ].join("\n");
  }
  return [
    `方案已确认（Request ID: ${requestId}）。`,
    "FlowHub 已返回工作流、Skill 清单和安装指导。",
    "如需本地下载或安装，请在当前 OpenClaw 客户端明确发送下载/安装指令后再继续。",
    ...buildUserFacingInstallSteps(installGuidance)
  ].join("\n");
}

function buildConfirmText(result, installGuidance) {
  const requestId = result?.request?.id ?? "n/a";
  const requestStatus = result?.request?.status || "unknown";
  const templateKey =
    result?.assistant_response?.template_key || result?.communication_preview?.template_key || "unknown";
  const communicationStatus = result?.communication_preview?.status || "unknown";
  const communicationBody = result?.communication_preview?.body || "";
  const nextAction =
    installGuidance?.status === "pending_client_action"
      ? "next_action: tell the user the workflow is confirmed and that this OpenClaw client may now handle installation locally. stop after presenting install guidance; do not call exec, browser, web_fetch, or fallback execution tools in the same turn."
      : "next_action: tell the user the workflow is confirmed and that local install/download should only happen after explicit client-side instructions.";

  return [
    "FLOWHUB_CONFIRM_READY",
    `template_key: ${templateKey}`,
    `request_id: ${requestId}`,
    `request_status: ${requestStatus}`,
    `communication_status: ${communicationStatus}`,
    `customer_reply: ${communicationBody}`,
    `install_policy: ${installGuidance?.mode || "client_managed"}`,
    ...formatClientExecutionGuidance(result?.client_execution_guidance),
    ...formatInstallGuidance(installGuidance),
    "forbidden_actions: do not simulate installation or execution via exec/browser/web_fetch when the current step is client-managed install guidance.",
    "failure_policy: if local installation fails or times out, report the failure and wait for the user; do not fabricate analysis or alternate execution results.",
    wrapBlock("suggested_customer_reply", buildSuggestedConfirmReply(result, installGuidance)),
    nextAction
  ].join("\n");
}

function buildPlanText(result) {
  const actionable = result?.actionable !== false;
  const requestId = result?.request?.id ?? "n/a";
  const workflowId = result?.workflow_spec?.workflow_id ?? "n/a";
  const templateKey =
    result?.assistant_response?.template_key || result?.communication_preview?.template_key || "unknown";
  const headline = result?.assistant_response?.headline || "Plan created";
  const replyText = result?.assistant_response?.reply_text || "";
  const workflowFormula = getWorkflowFormula(result);
  const confirmationPrompt =
    result?.assistant_response?.confirmation_prompt ||
    "Ask the user for explicit confirmation before continuing.";
  const communicationStatus = result?.communication_preview?.status || "unknown";

  if (!actionable) {
    return [
      "FLOWHUB_PLAN_READY",
      "actionable: no",
      `template_key: ${templateKey}`,
      `headline: ${headline}`,
      `reply_text: ${replyText}`,
      `workflow_formula: ${workflowFormula}`,
      ...formatUsageSteps(result?.assistant_response?.usage_steps),
      `communication_status: ${communicationStatus}`,
      wrapBlock("suggested_chat_reply", buildSuggestedPlanReply(result)),
      "next_action: ask the user to restate the request using one of the usage examples above."
    ].join("\n");
  }

  return [
    "FLOWHUB_PLAN_READY",
    "actionable: yes",
    `template_key: ${templateKey}`,
    `request_id: ${requestId}`,
    `workflow_id: ${workflowId}`,
    `headline: ${headline}`,
    `reply_text: ${replyText}`,
    `workflow_formula: ${workflowFormula}`,
    ...(result?.workflow_summary?.headline ? [`workflow_summary_headline: ${result.workflow_summary.headline}`] : []),
    ...(result?.workflow_summary?.explanation ? [wrapBlock("workflow_summary_explanation", result.workflow_summary.explanation)] : []),
    ...formatSelectedSkills(result?.selected_skills),
    ...formatSecurityGuidance(result?.selected_skills, result?.workflow_summary),
    ...formatUsageSteps(result?.assistant_response?.usage_steps),
    `communication_status: ${communicationStatus}`,
    `confirmation_prompt: ${confirmationPrompt}`,
    ...formatClientExecutionGuidance(result?.client_execution_guidance),
    wrapBlock("suggested_chat_reply", buildSuggestedPlanReply(result)),
    "next_action: wait for explicit user confirmation, then call flowhub_confirm_request."
  ].join("\n");
}


function buildSearchText(query, results) {
  const normalizedQuery = String(query || "").trim();
  const candidates = Array.isArray(results) ? results : [];

  if (candidates.length === 0) {
    return [
      "FLOWHUB_SKILL_SEARCH_READY",
      `query: ${normalizedQuery || "n/a"}`,
      "match_count: 0",
      "candidates: none",
      "next_action: ask the user to narrow the task or continue with flowhub_plan_command for a fallback workflow."
    ].join("\n");
  }

  const lines = [
    "FLOWHUB_SKILL_SEARCH_READY",
    `query: ${normalizedQuery || "n/a"}`,
    `match_count: ${candidates.length}`,
    "candidates:"
  ];

  for (const [index, item] of candidates.entries()) {
    const skill = item?.skill || {};
    const trustSignals = Array.isArray(item?.trust_signals) && item.trust_signals.length > 0
      ? item.trust_signals.join(", ")
      : "no trust signals";
    const securityFlags = Array.isArray(item?.security_flags) && item.security_flags.length > 0
      ? item.security_flags.join(", ")
      : "no security flags";
    lines.push(
      `${index + 1}. ${skill.display_name || skill.name || "unknown"} | ${skill.category || "n/a"} | quality=${item?.quality_tier || "basic"} (${Number(item?.quality_score || 0).toFixed(1)}) | security=${item?.security_tier || "caution"} (${Number(item?.security_score || 0).toFixed(1)}) | search=${Number(item?.search_score || 0).toFixed(1)}`
    );
    lines.push(`   summary: ${skill.summary || skill.description || "n/a"}`);
    lines.push(`   trust_signals: ${trustSignals}`);
    lines.push(`   security_flags: ${securityFlags}`);
    lines.push(`   planning_status: ${formatPlanningEligibility(item?.security_verdict)}`);
    if (skill.source_url) {
      lines.push(`   source_url: ${skill.source_url}`);
    }
    if (Array.isArray(item?.ranking_reasons) && item.ranking_reasons.length > 0) {
      lines.push(`   ranking_reasons: ${item.ranking_reasons.slice(0, 3).join(" | ")}`);
    }
  }

  lines.push(
    "next_action: present the top trusted candidates, then ask whether the user wants a workflow plan."
  );
  return lines.join("\n");
}

export default function registerFlowHubTools(api) {
  api.registerTool(
    {
      name: "flowhub_handle_message",
      description:
        "Primary FlowHub chat entrypoint. Use this first for almost every user message about FlowHub, including onboarding, project introduction, install guidance, workflow planning, and execution confirmation. It returns a welcome/onboarding block for first-contact questions, routes to FlowHub planning by default, and if the message is an explicit confirmation plus a real request_id, it confirms the existing FlowHub request.",
      parameters: {
        type: "object",
        additionalProperties: false,
        properties: {
          message: { type: "string" },
          request_id: { type: "integer", minimum: 1 },
          targets: {
            type: "array",
            items: {
              type: "object",
              additionalProperties: false,
              properties: {
                type: { type: "string", enum: ["url", "api", "text"] },
                label: { type: "string" },
                value: { type: "string" }
              },
              required: ["value"]
            }
          },
          credentials: {
            type: "array",
            items: {
              type: "object",
              additionalProperties: false,
              properties: {
                label: { type: "string" },
                kind: { type: "string", enum: ["api_key", "token", "cookie", "basic_auth", "other"] },
                value: { type: "string" },
                ephemeral: { type: "boolean" }
              },
              required: ["label", "value"]
            }
          },
          output_format: { type: "string", enum: ["json", "csv", "xlsx", "pdf", "markdown"] },
          execution_mode: { type: "string", enum: ["remote", "local"] },
          user_notes: { type: "string" }
        },
        required: ["message"]
      },
      async execute(_id, params) {
        const config = getConfig(api);
        const message = String(params.message || "").trim();
        const requestId = Number.isInteger(params.request_id) ? params.request_id : null;
        const hasStructuredInput =
          normalizeTargets(params.targets).length > 0 || normalizeCredentials(params.credentials).length > 0;

        if (!requestId && !hasStructuredInput && looksLikeWelcomeRequest(message)) {
          return {
            content: [
              {
                type: "text",
                text: buildWelcomeText(config)
              }
            ]
          };
        }

        const shouldConfirm = requestId && looksLikeConfirmation(message);

        if (shouldConfirm) {
          const result = await requestJson(
            `${config.apiBaseUrl}/run-requests/${requestId}/confirm`,
            {
              method: "POST",
              headers: {
                "X-API-Key": config.apiKey
              }
            },
            config.timeoutMs
          );
          const installGuidance = buildInstallGuidance(result, {
            installRequested: looksLikeInstallRequest(message)
          });

          return {
            content: [
              {
                type: "text",
                text: [
                  "FLOWHUB_CHAT_ROUTER",
                  "handled_as: confirm",
                  buildConfirmText(result, installGuidance)
                ].join("\n")
              }
            ]
          };
        }

        const payload = {
          goal: message,
          targets: normalizeTargets(params.targets),
          credentials: normalizeCredentials(params.credentials),
          output_format: params.output_format || config.defaultOutputFormat,
          execution_mode: params.execution_mode || config.defaultExecutionMode,
          user_notes: String(params.user_notes || "").trim()
        };

        const result = await requestJson(
          `${config.apiBaseUrl}/run-requests/`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-API-Key": config.apiKey
            },
            body: JSON.stringify(payload)
          },
          config.timeoutMs
        );

        return {
          content: [
            {
              type: "text",
              text: [
                "FLOWHUB_CHAT_ROUTER",
                "handled_as: plan",
                buildPlanText(result)
              ].join("\n")
            }
          ]
        };
      }
    }
  );

  api.registerTool(
    {
      name: "flowhub_search_skills",
      description:
        "Search FlowHub's indexed skill catalog and return trusted candidate skills ranked by relevance and registry trust signals. Use this only for discovery-focused requests; prefer flowhub_handle_message first for onboarding, install guidance, workflow planning, and confirmation.",
      parameters: {
        type: "object",
        additionalProperties: false,
        properties: {
          query: { type: "string" },
          category: { type: "string" },
          limit: { type: "integer", minimum: 1, maximum: 10 }
        },
        required: ["query"]
      },
      async execute(_id, params) {
        const config = getConfig(api);
        const query = String(params.query || "").trim();
        const limit = Number.isFinite(params.limit) ? params.limit : 5;
        const qs = new URLSearchParams({
          q: query,
          limit: String(limit)
        });
        if (params.category) {
          qs.set("category", String(params.category).trim());
        }

        const result = await requestJson(
          `${config.apiBaseUrl}/skills/search?${qs.toString()}`,
          {
            method: "GET",
            headers: {
              "X-API-Key": config.apiKey
            }
          },
          config.timeoutMs
        );

        return {
          content: [
            {
              type: "text",
              text: buildSearchText(query, result)
            }
          ]
        };
      }
    }
  );

  api.registerTool(
    {
      name: "flowhub_plan_command",
      description:
        "Fallback-only FlowHub planning tool. Create a FlowHub run request from a user's natural-language automation command only when flowhub_handle_message is unavailable or routing has already clearly failed. For normal onboarding, install guidance, workflow planning, and follow-up turns, prefer flowhub_handle_message first.",
      parameters: {
        type: "object",
        additionalProperties: false,
        properties: {
          goal: { type: "string" },
          targets: {
            type: "array",
            items: {
              type: "object",
              additionalProperties: false,
              properties: {
                type: { type: "string", enum: ["url", "api", "text"] },
                label: { type: "string" },
                value: { type: "string" }
              },
              required: ["value"]
            }
          },
          credentials: {
            type: "array",
            items: {
              type: "object",
              additionalProperties: false,
              properties: {
                label: { type: "string" },
                kind: { type: "string", enum: ["api_key", "token", "cookie", "basic_auth", "other"] },
                value: { type: "string" },
                ephemeral: { type: "boolean" }
              },
              required: ["label", "value"]
            }
          },
          output_format: { type: "string", enum: ["json", "csv", "xlsx", "pdf", "markdown"] },
          execution_mode: { type: "string", enum: ["remote", "local"] },
          user_notes: { type: "string" }
        },
        required: ["goal"]
      },
      async execute(_id, params) {
        const config = getConfig(api);
        const payload = {
          goal: String(params.goal || "").trim(),
          targets: normalizeTargets(params.targets),
          credentials: normalizeCredentials(params.credentials),
          output_format: params.output_format || config.defaultOutputFormat,
          execution_mode: params.execution_mode || config.defaultExecutionMode,
          user_notes: String(params.user_notes || "").trim()
        };

        const result = await requestJson(
          `${config.apiBaseUrl}/run-requests/`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-API-Key": config.apiKey
            },
            body: JSON.stringify(payload)
          },
          config.timeoutMs
        );

        return {
          content: [
            {
              type: "text",
              text: buildPlanText(result)
            }
          ]
        };
      }
    }
  );

  api.registerTool(
    {
      name: "flowhub_confirm_request",
      description:
        "Fallback-only FlowHub confirmation tool. Confirm a previously planned FlowHub request after the user explicitly approves it only when flowhub_handle_message is unavailable or routing has already clearly failed. For normal confirmation turns, prefer flowhub_handle_message first.",
      parameters: {
        type: "object",
        additionalProperties: false,
        properties: {
          request_id: { type: "integer", minimum: 1 }
        },
        required: ["request_id"]
      },
      async execute(_id, params) {
        const config = getConfig(api);
        const requestId = Number(params.request_id);
        if (!Number.isInteger(requestId) || requestId <= 0) {
          throw new Error("request_id must be a positive integer");
        }

        const result = await requestJson(
          `${config.apiBaseUrl}/run-requests/${requestId}/confirm`,
          {
            method: "POST",
            headers: {
              "X-API-Key": config.apiKey
            }
          },
          config.timeoutMs
        );
        const installGuidance = buildInstallGuidance(result, {
          installRequested: false
        });

        return {
          content: [
            {
              type: "text",
              text: buildConfirmText(result, installGuidance)
            }
          ]
        };
      }
    }
  );
}
