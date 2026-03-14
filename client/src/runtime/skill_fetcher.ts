import { mkdir, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

import type { ClientExecutionGuidance, ClientSkillTarget, FetchedSkillArtifact } from "../types";
import { executeSandboxedHttpRequest, resolveClientToolSandbox } from "./tool_sandbox";

const DEFAULT_REGISTRY_BASE = "https://clawhub.ai";
const MAX_FETCH_ATTEMPTS = 3;
const DEFAULT_RETRY_DELAY_MS = 1500;

function cacheFileName(target: ClientSkillTarget): string {
  const key = target.source_slug || target.name || target.display_name || "skill";
  return `${key.replace(/[^a-zA-Z0-9._-]+/g, "_")}.json`;
}

function resolveFetchUrl(target: ClientSkillTarget, registryBaseUrl: string): string {
  if (target.fetch_strategy === "clawhub_registry" && target.source_slug) {
    return `${registryBaseUrl.replace(/\/+$/, "")}/api/v1/skills/${encodeURIComponent(target.source_slug)}`;
  }
  if (target.source_url) {
    return target.source_url;
  }
  throw new Error(`Cannot resolve fetch URL for ${target.display_name}`);
}

async function fetchJson(url: string): Promise<unknown> {
  let lastError: unknown;
  const sandbox = resolveClientToolSandbox();

  for (let attempt = 1; attempt <= MAX_FETCH_ATTEMPTS; attempt += 1) {
    try {
      const result = await executeSandboxedHttpRequest(
        {
          kind: "http_request",
          method: "GET",
          url,
          headers: { Accept: "application/json" },
          response_format: "json"
        },
        sandbox
      );
      return result.response;
    } catch (error) {
      lastError = error;
      const message = error instanceof Error ? error.message : String(error);
      const rateLimited = message.includes("External HTTP tool 429:");
      if (!rateLimited || attempt === MAX_FETCH_ATTEMPTS) {
        throw error;
      }

      const retryDelayMs = DEFAULT_RETRY_DELAY_MS * attempt;
      await new Promise((resolveDelay) => setTimeout(resolveDelay, retryDelayMs));
    }
  }

  throw lastError;
}

async function readCachedDocument(filePath: string): Promise<{
  fetched_at?: string;
  resolved_url?: string;
  payload: Record<string, unknown> | null;
} | null> {
  try {
    const raw = await readFile(filePath, "utf-8");
    const parsed = JSON.parse(raw) as {
      fetched_at?: string;
      resolved_url?: string;
      payload?: Record<string, unknown> | null;
    };
    return {
      fetched_at: parsed.fetched_at,
      resolved_url: parsed.resolved_url,
      payload: parsed.payload && typeof parsed.payload === "object" ? parsed.payload : null
    };
  } catch {
    return null;
  }
}

function payloadSummary(payload: Record<string, unknown> | null): string | null {
  if (!payload) {
    return null;
  }
  const skill = payload.skill && typeof payload.skill === "object"
    ? (payload.skill as Record<string, unknown>)
    : null;
  const summary =
    payload.summary ??
    payload.description ??
    payload.readme_summary ??
    skill?.summary ??
    skill?.description;
  return typeof summary === "string" && summary.trim() ? summary.trim() : null;
}

function payloadVersion(payload: Record<string, unknown> | null): string | null {
  if (!payload) {
    return null;
  }
  const latestVersion = payload.latestVersion && typeof payload.latestVersion === "object"
    ? (payload.latestVersion as Record<string, unknown>)
    : null;
  const version =
    payload.version ??
    latestVersion?.version ??
    (typeof payload.stats === "object" && payload.stats
      ? (payload.stats as Record<string, unknown>).latestVersion
      : null);
  return typeof version === "string" && version.trim() ? version.trim() : null;
}

function payloadStats(payload: Record<string, unknown> | null): Record<string, unknown> | null {
  if (!payload) {
    return null;
  }
  if (payload.stats && typeof payload.stats === "object") {
    return (payload.stats as Record<string, unknown>) ?? null;
  }
  if (payload.skill && typeof payload.skill === "object") {
    const skill = payload.skill as Record<string, unknown>;
    if (skill.stats && typeof skill.stats === "object") {
      return (skill.stats as Record<string, unknown>) ?? null;
    }
  }
  return null;
}

export async function fetchSkillArtifacts(
  guidance: ClientExecutionGuidance | null | undefined,
  options?: {
    cacheDir?: string;
    registryBaseUrl?: string;
  }
): Promise<FetchedSkillArtifact[]> {
  const skillTargets = Array.isArray(guidance?.skill_targets) ? guidance.skill_targets : [];
  if (skillTargets.length === 0) {
    return [];
  }

  const cacheDir = resolve(process.cwd(), options?.cacheDir || ".flowhub-cache/skills");
  const registryBaseUrl = options?.registryBaseUrl || process.env.FLOWHUB_SKILL_REGISTRY_BASE_URL || DEFAULT_REGISTRY_BASE;
  await mkdir(cacheDir, { recursive: true });

  const fetchedArtifacts: FetchedSkillArtifact[] = [];
  for (const target of skillTargets) {
    const resolvedUrl = resolveFetchUrl(target, registryBaseUrl);
    const filePath = resolve(cacheDir, cacheFileName(target));
    const fetchedAt = new Date().toISOString();
    try {
      const payload = await fetchJson(resolvedUrl);
      await writeFile(
        filePath,
        JSON.stringify(
          {
            fetched_at: fetchedAt,
            resolved_url: resolvedUrl,
            target,
            payload
          },
          null,
          2
        ),
        "utf-8"
      );

      fetchedArtifacts.push({
        name: target.name,
        display_name: target.display_name,
        source: target.source,
        source_slug: target.source_slug,
        source_url: target.source_url,
        fetch_strategy: target.fetch_strategy,
        required: target.required,
        cache_path: filePath,
        fetched_at: fetchedAt,
        resolved_url: resolvedUrl,
        fetch_status: "network",
        fetch_error: null,
        payload_summary: payloadSummary(payload as Record<string, unknown> | null),
        payload_version: payloadVersion(payload as Record<string, unknown> | null),
        payload_stats: payload && typeof payload === "object"
          ? payloadStats(payload as Record<string, unknown>)
          : null
      });
    } catch (error) {
      const cached = await readCachedDocument(filePath);
      if (!cached?.payload) {
        const fetchError = error instanceof Error ? error.message : String(error);
        await writeFile(
          filePath,
          JSON.stringify(
            {
              fetched_at: fetchedAt,
              resolved_url: resolvedUrl,
              target,
              payload: null,
              fetch_error: fetchError
            },
            null,
            2
          ),
          "utf-8"
        );
        fetchedArtifacts.push({
          name: target.name,
          display_name: target.display_name,
          source: target.source,
          source_slug: target.source_slug,
          source_url: target.source_url,
          fetch_strategy: target.fetch_strategy,
          required: target.required,
          cache_path: filePath,
          fetched_at: fetchedAt,
          resolved_url: resolvedUrl,
          fetch_status: "degraded",
          fetch_error: fetchError,
          payload_summary: null,
          payload_version: null,
          payload_stats: null
        });
        continue;
      }
      fetchedArtifacts.push({
        name: target.name,
        display_name: target.display_name,
        source: target.source,
        source_slug: target.source_slug,
        source_url: target.source_url,
        fetch_strategy: target.fetch_strategy,
        required: target.required,
        cache_path: filePath,
        fetched_at: cached.fetched_at || fetchedAt,
        resolved_url: cached.resolved_url || resolvedUrl,
        fetch_status: "cache",
        fetch_error: error instanceof Error ? error.message : String(error),
        payload_summary: payloadSummary(cached.payload),
        payload_version: payloadVersion(cached.payload),
        payload_stats: payloadStats(cached.payload)
      });
    }
  }

  return fetchedArtifacts;
}
