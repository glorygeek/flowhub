import { readFile } from "node:fs/promises";

import type {
  ClientExecutionGuidance,
  FetchedSkillArtifact,
  ResolvedWorkflowBundle,
  WorkflowNode,
  WorkflowSpec
} from "../types";

type CachedSkillDocument = {
  payload?: Record<string, unknown> | null;
};

function normalizeSkillKey(value: string | null | undefined): string {
  return String(value || "")
    .trim()
    .toLowerCase();
}

function summarizePayload(payload: Record<string, unknown> | null | undefined): string | null {
  if (!payload || typeof payload !== "object") {
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

function extractVersion(payload: Record<string, unknown> | null | undefined): string | null {
  if (!payload || typeof payload !== "object") {
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

function extractStats(payload: Record<string, unknown> | null | undefined): Record<string, unknown> | null {
  if (!payload || typeof payload !== "object") {
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

async function readCachedPayload(filePath: string): Promise<Record<string, unknown> | null> {
  const raw = await readFile(filePath, "utf-8");
  const parsed = JSON.parse(raw) as CachedSkillDocument;
  if (!parsed.payload || typeof parsed.payload !== "object") {
    return null;
  }
  return parsed.payload;
}

function buildArtifactLookup(
  artifacts: FetchedSkillArtifact[]
): Map<string, FetchedSkillArtifact> {
  const lookup = new Map<string, FetchedSkillArtifact>();
  for (const artifact of artifacts) {
    const candidates = [
      normalizeSkillKey(artifact.name),
      normalizeSkillKey(artifact.source_slug),
      normalizeSkillKey(artifact.display_name)
    ].filter(Boolean);
    for (const key of candidates) {
      lookup.set(key, artifact);
    }
  }
  return lookup;
}

function resolveArtifactForNode(
  node: WorkflowNode,
  lookup: Map<string, FetchedSkillArtifact>
): FetchedSkillArtifact | null {
  const candidates = [
    normalizeSkillKey(node.skill_ref),
    normalizeSkillKey(node.name)
  ].filter(Boolean);

  for (const key of candidates) {
    if (lookup.has(key)) {
      return lookup.get(key) || null;
    }
    if (key.includes("/")) {
      const slug = key.split("/").pop();
      if (slug && lookup.has(slug)) {
        return lookup.get(slug) || null;
      }
    }
  }

  return null;
}

export async function buildResolvedWorkflowBundle(
  spec: WorkflowSpec,
  guidance: ClientExecutionGuidance | null | undefined,
  artifacts: FetchedSkillArtifact[]
): Promise<ResolvedWorkflowBundle> {
  const artifactLookup = buildArtifactLookup(artifacts);
  const nodes = await Promise.all(
    spec.nodes.map(async (node) => {
      const artifact = resolveArtifactForNode(node, artifactLookup);
      if (!artifact) {
        return {
          id: node.id,
          name: node.name,
          skill_ref: node.skill_ref,
          resolution_status: "unresolved" as const,
          runtime_hint: "No fetched skill metadata matched this node.",
          matched_skill: null
        };
      }

      const payload = await readCachedPayload(artifact.cache_path);
      return {
        id: node.id,
        name: node.name,
        skill_ref: node.skill_ref,
        resolution_status: "resolved" as const,
        runtime_hint:
          artifact.fetch_status === "degraded"
            ? "Skill metadata fetch was unavailable; continuing with unresolved skill details."
            : `Resolved from ${artifact.fetch_status} metadata cache.`,
        matched_skill: {
          display_name: artifact.display_name,
          source_slug: artifact.source_slug,
          source_url: artifact.source_url,
          summary: artifact.payload_summary ?? summarizePayload(payload),
          version: artifact.payload_version ?? extractVersion(payload),
          fetch_status: artifact.fetch_status,
          cache_path: artifact.cache_path,
          fetch_error: artifact.fetch_error ?? null,
          stats: artifact.payload_stats ?? extractStats(payload)
        }
      };
    })
  );

  return {
    generated_at: new Date().toISOString(),
    workflow_id: spec.workflow_id ?? spec.source_recipe_id,
    workflow_name: spec.name,
    ai_runtime_owner: guidance?.ai_runtime_owner ?? null,
    guidance_summary: guidance?.summary ?? null,
    nodes
  };
}
