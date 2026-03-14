import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

import { executeWorkflow } from "./runtime/executor";
import { canUseClientAi, resolveClientAiRuntime } from "./runtime/client_ai";
import { loadRuntimePlan } from "./runtime/plan_loader";
import { buildResolvedWorkflowBundle } from "./runtime/resolved_bundle";
import { fetchSkillArtifacts } from "./runtime/skill_fetcher";
import { resolveClientToolSandbox } from "./runtime/tool_sandbox";

function argValue(args: string[], key: string, fallback: string): string {
  const index = args.indexOf(key);
  if (index >= 0 && args[index + 1]) {
    return args[index + 1];
  }
  return fallback;
}

function hasFlag(args: string[], key: string): boolean {
  return args.includes(key);
}

async function postTelemetryWithRetry(
  url: string,
  payload: Record<string, unknown>,
  apiKey: string
): Promise<Response> {
  let lastError: unknown;

  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": apiKey
        },
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(`Telemetry API ${res.status}: ${text}`);
      }

      return res;
    } catch (error) {
      lastError = error;
      if (attempt === 1) {
        throw error;
      }
    }
  }

  throw lastError;
}

async function main() {
  const args = process.argv.slice(2);
  const planFile = argValue(args, "--plan", argValue(args, "--spec", "./sample-workflow.json"));
  const cacheDir = argValue(args, "--cache-dir", "./.flowhub-cache/skills");
  const resolvedPlanOut = argValue(args, "--resolved-plan-out", "./.flowhub-cache/resolved-workflow.json");
  const registryBaseUrl = argValue(
    args,
    "--registry-base",
    process.env.FLOWHUB_SKILL_REGISTRY_BASE_URL || "https://clawhub.ai"
  );
  const skipTelemetry = hasFlag(args, "--skip-telemetry");
  const apiBase =
    argValue(args, "--api-base", process.env.FLOWHUB_API_BASE_URL || "http://localhost:8000/api/v1") +
    "/telemetry/events";
  const apiKey = argValue(args, "--api-key", process.env.FLOWHUB_API_KEY || "dev-flowhub-key");

  const planPath = resolve(process.cwd(), planFile);
  const plan = await loadRuntimePlan(planPath);
  const clientAiRuntime = resolveClientAiRuntime();
  const clientToolSandbox = resolveClientToolSandbox();
  const fetchedSkills = await fetchSkillArtifacts(plan.client_execution_guidance, {
    cacheDir,
    registryBaseUrl
  });
  const resolvedWorkflow = await buildResolvedWorkflowBundle(
    plan.workflow_spec,
    plan.client_execution_guidance,
    fetchedSkills
  );
  const resolvedPlanPath = resolve(process.cwd(), resolvedPlanOut);
  await mkdir(dirname(resolvedPlanPath), { recursive: true });
  await writeFile(resolvedPlanPath, JSON.stringify(resolvedWorkflow, null, 2), "utf-8");
  const execution = await executeWorkflow(plan.workflow_spec, {
    resolvedWorkflow
  });

  const telemetryPayload = {
    workflow_id: execution.workflow_id ?? null,
    run_id: execution.run_id,
    node_results: execution.node_results,
    summary: execution.summary,
    client_meta: {
      runtime: "tauri-ts-mvp",
      workflow_name: execution.workflow_name,
      timestamp: new Date().toISOString(),
      fetched_skills: fetchedSkills,
      resolved_workflow_path: resolvedPlanPath
    }
  };

  if (skipTelemetry) {
    console.log(
      JSON.stringify(
        {
          run_id: execution.run_id,
          summary: execution.summary,
          node_results: execution.node_results,
          client_ai_runtime: {
            enabled: clientAiRuntime.enabled,
            configured: canUseClientAi(clientAiRuntime),
            base_url: clientAiRuntime.base_url || null,
            model: clientAiRuntime.model || null,
            thinking_enabled: clientAiRuntime.thinking_enabled
          },
          client_tool_sandbox: clientToolSandbox,
          fetched_skills: fetchedSkills,
          resolved_workflow: resolvedWorkflow,
          resolved_workflow_path: resolvedPlanPath,
          telemetry_skipped: true
        },
        null,
        2
      )
    );
    return;
  }

  const response = await postTelemetryWithRetry(apiBase, telemetryPayload, apiKey);
  const ack = (await response.json()) as { accepted: boolean; ingested_at: string };

  console.log(
    JSON.stringify(
      {
        run_id: execution.run_id,
        summary: execution.summary,
        node_results: execution.node_results,
        client_ai_runtime: {
          enabled: clientAiRuntime.enabled,
          configured: canUseClientAi(clientAiRuntime),
          base_url: clientAiRuntime.base_url || null,
          model: clientAiRuntime.model || null,
          thinking_enabled: clientAiRuntime.thinking_enabled
        },
        client_tool_sandbox: clientToolSandbox,
        fetched_skills: fetchedSkills,
        resolved_workflow: resolvedWorkflow,
        resolved_workflow_path: resolvedPlanPath,
        telemetry_ack: ack
      },
      null,
      2
    )
  );
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
