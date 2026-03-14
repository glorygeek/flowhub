import type { ClientAIRuntimeConfig } from "../types";
import { envFlag, resolveEnvValue } from "./runtime_env";

type ClientAIChatResult = {
  provider: string;
  model: string;
  content: string;
  reasoning_content: string | null;
};

function detectProvider(baseUrl: string, model: string): string {
  const loweredBase = String(baseUrl || "").toLowerCase();
  const loweredModel = String(model || "").toLowerCase();
  if (loweredBase.includes("deepseek.com") || loweredModel.startsWith("deepseek-")) {
    return "deepseek";
  }
  return "openai-compatible";
}

export function resolveClientAiRuntime(): ClientAIRuntimeConfig {
  const enabled = envFlag("CLIENT_AI_ENABLED", envFlag("AI_ENABLED", false));
  return {
    enabled,
    base_url: resolveEnvValue("CLIENT_AI_BASE_URL") || resolveEnvValue("AI_BASE_URL"),
    model: resolveEnvValue("CLIENT_AI_MODEL") || resolveEnvValue("AI_MODEL"),
    api_key: resolveEnvValue("CLIENT_AI_API_KEY") || resolveEnvValue("AI_API_KEY"),
    timeout_seconds: Number(resolveEnvValue("CLIENT_AI_TIMEOUT_SECONDS") || resolveEnvValue("AI_TIMEOUT_SECONDS") || 30),
    temperature: Number(
      resolveEnvValue("CLIENT_AI_TEMPERATURE") || resolveEnvValue("AI_DEFAULT_TEMPERATURE") || 0.2
    ),
    thinking_enabled: envFlag(
      "CLIENT_AI_THINKING_ENABLED",
      envFlag("AI_THINKING_ENABLED", false)
    )
  };
}

export function canUseClientAi(runtime: ClientAIRuntimeConfig): boolean {
  return Boolean(runtime.enabled && runtime.base_url && runtime.model && runtime.api_key);
}

function buildChatPayload(
  runtime: ClientAIRuntimeConfig,
  messages: Array<{ role: "system" | "user" | "assistant"; content: string }>
): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    model: runtime.model,
    temperature: runtime.temperature,
    messages
  };
  const provider = detectProvider(runtime.base_url, runtime.model);
  if (
    provider === "deepseek" &&
    runtime.thinking_enabled &&
    runtime.model.trim().toLowerCase() === "deepseek-chat"
  ) {
    payload.thinking = { type: "enabled" };
  }
  return payload;
}

function extractTextField(value: unknown): string | null {
  if (typeof value === "string" && value.trim()) {
    return value.trim();
  }
  if (Array.isArray(value)) {
    const parts = value
      .map((item) => {
        if (
          item &&
          typeof item === "object" &&
          (item as Record<string, unknown>).type === "text" &&
          typeof (item as Record<string, unknown>).text === "string"
        ) {
          return ((item as Record<string, unknown>).text as string).trim();
        }
        return "";
      })
      .filter(Boolean);
    if (parts.length > 0) {
      return parts.join("\n");
    }
  }
  return null;
}

function stripJsonFence(content: string): string {
  const trimmed = content.trim();
  if (!trimmed.startsWith("```")) {
    return trimmed;
  }
  const withoutTicks = trimmed.replace(/^```(?:json)?/i, "").replace(/```$/i, "");
  return withoutTicks.trim();
}

function extractJsonObject(content: string): string | null {
  const cleaned = stripJsonFence(content);
  const start = cleaned.indexOf("{");
  if (start < 0) {
    return null;
  }

  let depth = 0;
  let inString = false;
  let escaped = false;
  for (let index = start; index < cleaned.length; index += 1) {
    const char = cleaned[index];
    if (inString) {
      if (escaped) {
        escaped = false;
      } else if (char === "\\") {
        escaped = true;
      } else if (char === "\"") {
        inString = false;
      }
      continue;
    }

    if (char === "\"") {
      inString = true;
      continue;
    }
    if (char === "{") {
      depth += 1;
    } else if (char === "}") {
      depth -= 1;
      if (depth === 0) {
        return cleaned.slice(start, index + 1);
      }
    }
  }

  return null;
}

export function parseClientAiJson(content: string): Record<string, unknown> {
  const cleaned = stripJsonFence(content);
  try {
    return JSON.parse(cleaned) as Record<string, unknown>;
  } catch {
    const objectBlob = extractJsonObject(cleaned);
    if (objectBlob) {
      try {
        return JSON.parse(objectBlob) as Record<string, unknown>;
      } catch {
        // Fall through to raw text mode.
      }
    }
  }

  return {
    message: cleaned,
    result: {
      raw_text: cleaned
    },
    notes: ["Model response was stored as raw text because strict JSON parsing failed."],
    confidence: "low"
  };
}

export async function requestClientAiChat(
  runtime: ClientAIRuntimeConfig,
  messages: Array<{ role: "system" | "user" | "assistant"; content: string }>
): Promise<ClientAIChatResult> {
  const endpoint = `${runtime.base_url.replace(/\/+$/, "")}/chat/completions`;
  const payload = buildChatPayload(runtime, messages);
  const provider = detectProvider(runtime.base_url, runtime.model);
  const timeoutMs =
    provider === "deepseek" && runtime.thinking_enabled
      ? Math.max(runtime.timeout_seconds * 1000, 90000)
      : runtime.timeout_seconds * 1000;
  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${runtime.api_key}`
    },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(timeoutMs)
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Client AI ${response.status}: ${text}`);
  }

  const raw = (await response.json()) as {
    model?: string;
    choices?: Array<{ message?: { content?: unknown; reasoning_content?: unknown } }>;
  };
  const message = raw.choices?.[0]?.message;
  const content = extractTextField(message?.content);
  if (!content) {
    throw new Error("Client AI returned no content");
  }

  return {
    provider,
    model: String(raw.model || runtime.model),
    content,
    reasoning_content: extractTextField(message?.reasoning_content)
  };
}
