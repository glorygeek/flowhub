import { readFile } from "node:fs/promises";

import type { RuntimePlanBundle, WorkflowSpec } from "../types";

function assertString(value: unknown, field: string): asserts value is string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`Invalid workflow field: ${field}`);
  }
}

function validateWorkflowSpec(parsed: Partial<WorkflowSpec>): WorkflowSpec {
  assertString(parsed.id, "id");
  assertString(parsed.name, "name");

  if (!Array.isArray(parsed.nodes)) {
    throw new Error("Invalid workflow field: nodes must be an array");
  }

  if (!Array.isArray(parsed.edges)) {
    throw new Error("Invalid workflow field: edges must be an array");
  }

  for (const node of parsed.nodes) {
    assertString(node.id, "nodes[].id");
    assertString(node.name, "nodes[].name");
  }

  return {
    id: parsed.id,
    workflow_id: parsed.workflow_id,
    name: parsed.name,
    inputs: parsed.inputs ?? {},
    nodes: parsed.nodes,
    edges: parsed.edges,
    outputs: parsed.outputs ?? {},
    retry_policy: parsed.retry_policy,
    confirm_points: parsed.confirm_points,
    source_recipe_id: parsed.source_recipe_id,
    risk_level: parsed.risk_level ?? "low"
  };
}

export async function loadRuntimePlan(filePath: string): Promise<RuntimePlanBundle> {
  const raw = await readFile(filePath, "utf-8");
  const parsed = JSON.parse(raw) as Partial<RuntimePlanBundle & WorkflowSpec>;

  if (parsed.workflow_spec && typeof parsed.workflow_spec === "object") {
    return {
      workflow_spec: validateWorkflowSpec(parsed.workflow_spec as Partial<WorkflowSpec>),
      client_execution_guidance: parsed.client_execution_guidance ?? null
    };
  }

  return {
    workflow_spec: validateWorkflowSpec(parsed as Partial<WorkflowSpec>),
    client_execution_guidance: null
  };
}
