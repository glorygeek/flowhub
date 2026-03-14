const DEFAULT_TIMEOUT_MS = 20000;
const DEFAULT_EXECUTION_MODE = "remote";
const DEFAULT_OUTPUT_FORMAT = "markdown";
const TARGET_TYPES = new Set(["url", "api", "text"]);
const CREDENTIAL_KINDS = new Set(["api_key", "token", "cookie", "basic_auth", "other"]);

function getConfig(api) {
  const cfg = api.config || {};
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

  return lines;
}

function wrapBlock(label, text) {
  return `${label}:\n<<<\n${String(text || "").trim()}\n>>>`;
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

  if (!actionable) {
    return [
      headline,
      replyText,
      "你可以这样描述需求：",
      ...usageSteps.map((step, index) => `${index + 1}. ${step}`)
    ].join("\n");
  }

  const lines = [headline, replyText];
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

function buildSuggestedConfirmReply(result) {
  return (
    result?.communication_preview?.body ||
    "方案已确认，平台会继续把执行进度和结果回传到当前会话。"
  );
}

function buildPlanText(result) {
  const actionable = result?.actionable !== false;
  const requestId = result?.request?.id ?? "n/a";
  const workflowId = result?.workflow_spec?.workflow_id ?? "n/a";
  const templateKey =
    result?.assistant_response?.template_key || result?.communication_preview?.template_key || "unknown";
  const headline = result?.assistant_response?.headline || "Plan created";
  const replyText = result?.assistant_response?.reply_text || "";
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
    ...formatSelectedSkills(result?.selected_skills),
    ...formatUsageSteps(result?.assistant_response?.usage_steps),
    `communication_status: ${communicationStatus}`,
    `confirmation_prompt: ${confirmationPrompt}`,
    ...formatClientExecutionGuidance(result?.client_execution_guidance),
    wrapBlock("suggested_chat_reply", buildSuggestedPlanReply(result)),
    "next_action: wait for explicit user confirmation, then call flowhub_confirm_request."
  ].join("\n");
}

function buildConfirmText(result) {
  const requestId = result?.request?.id ?? "n/a";
  const requestStatus = result?.request?.status || "unknown";
  const templateKey =
    result?.assistant_response?.template_key || result?.communication_preview?.template_key || "unknown";
  const communicationStatus = result?.communication_preview?.status || "unknown";
  const communicationBody = result?.communication_preview?.body || "";

  return [
    "FLOWHUB_CONFIRM_READY",
    `template_key: ${templateKey}`,
    `request_id: ${requestId}`,
    `request_status: ${requestStatus}`,
    `communication_status: ${communicationStatus}`,
    `customer_reply: ${communicationBody}`,
    ...formatClientExecutionGuidance(result?.client_execution_guidance),
    wrapBlock("suggested_customer_reply", buildSuggestedConfirmReply(result))
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
      name: "flowhub_search_skills",
      description:
        "Search FlowHub's indexed skill catalog and return trusted candidate skills ranked by relevance and registry trust signals. Use this for discovery-only chat requests before workflow planning.",
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
    },
    { optional: true }
  );

  api.registerTool(
    {
      name: "flowhub_plan_command",
      description:
        "Create a FlowHub run request from a user's natural-language automation command. Use this to plan a workflow, return selected skills, and ask for confirmation in the same chat.",
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
    },
    { optional: true }
  );

  api.registerTool(
    {
      name: "flowhub_confirm_request",
      description:
        "Confirm a previously planned FlowHub request after the user explicitly approves it. Returns the customer-facing reply payload that should be sent in the same chat.",
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

        return {
          content: [
            {
              type: "text",
              text: buildConfirmText(result)
            }
          ]
        };
      }
    },
    { optional: true }
  );
}
