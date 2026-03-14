import { randomUUID } from "node:crypto";

import type {
  ExecutionResult,
  NodeExecutionResult,
  ResolvedWorkflowBundle,
  ResolvedWorkflowNode,
  WorkflowSpec
} from "../types";
import {
  canUseClientAi,
  parseClientAiJson,
  requestClientAiChat,
  resolveClientAiRuntime
} from "./client_ai";
import {
  executeSandboxedExternalTool,
  parseExternalToolRequest,
  resolveClientToolSandbox
} from "./tool_sandbox";

function topologicalSort(spec: WorkflowSpec): string[] {
  const indegree = new Map<string, number>();
  const adjacency = new Map<string, string[]>();

  for (const node of spec.nodes) {
    indegree.set(node.id, 0);
    adjacency.set(node.id, []);
  }

  for (const edge of spec.edges) {
    if (!indegree.has(edge.from_node) || !indegree.has(edge.to_node)) {
      throw new Error(`Unknown node reference in edge ${edge.from_node} -> ${edge.to_node}`);
    }
    adjacency.get(edge.from_node)?.push(edge.to_node);
    indegree.set(edge.to_node, (indegree.get(edge.to_node) || 0) + 1);
  }

  const queue: string[] = [];
  for (const [nodeId, count] of indegree.entries()) {
    if (count === 0) {
      queue.push(nodeId);
    }
  }

  const sorted: string[] = [];
  while (queue.length) {
    const current = queue.shift() as string;
    sorted.push(current);

    for (const next of adjacency.get(current) || []) {
      const remain = (indegree.get(next) || 0) - 1;
      indegree.set(next, remain);
      if (remain === 0) {
        queue.push(next);
      }
    }
  }

  if (sorted.length !== spec.nodes.length) {
    throw new Error("Workflow graph has a cycle");
  }

  return sorted;
}

async function simulateNodeExecution(node: WorkflowSpec["nodes"][number]): Promise<NodeExecutionResult> {
  const maxRetries = Number((node.inputs?.max_retries as number | undefined) ?? 0);
  let retries = 0;

  while (retries <= maxRetries) {
    const shouldFail = Boolean(node.inputs?.simulate_fail) && retries < maxRetries;

    if (shouldFail) {
      retries += 1;
      continue;
    }

    if (Boolean(node.inputs?.simulate_permanent_fail)) {
      return {
        node_id: node.id,
        status: "failed",
        output: {},
        error: `Node ${node.id} failed permanently`,
        retry_count: retries
      };
    }

    return {
      node_id: node.id,
      status: "success",
      output: {
        message: `Executed ${node.name}`,
        skill_ref: node.skill_ref || "n/a"
      },
      retry_count: retries
    };
  }

  return {
    node_id: node.id,
    status: "failed",
    output: {},
    error: `Node ${node.id} exhausted retries`,
    retry_count: retries
  };
}

function findResolvedNode(
  resolvedWorkflow: ResolvedWorkflowBundle | null | undefined,
  nodeId: string
): ResolvedWorkflowNode | null {
  if (!resolvedWorkflow) {
    return null;
  }
  return resolvedWorkflow.nodes.find((item) => item.id === nodeId) ?? null;
}

function summarizePreviousResults(results: NodeExecutionResult[]): Array<Record<string, unknown>> {
  return results.slice(-3).map((item) => ({
    node_id: item.node_id,
    status: item.status,
    output: item.output,
    error: item.error ?? null
  }));
}

function buildNodePayload(
  spec: WorkflowSpec,
  node: WorkflowSpec["nodes"][number],
  previousResults: NodeExecutionResult[],
  resolvedNode: ResolvedWorkflowNode | null
): Record<string, unknown> {
  return {
    workflow: {
      id: spec.id,
      name: spec.name,
      risk_level: spec.risk_level,
      inputs: spec.inputs,
      outputs: spec.outputs
    },
    node: {
      id: node.id,
      name: node.name,
      skill_ref: node.skill_ref || null,
      inputs: node.inputs || {}
    },
    resolved_skill: resolvedNode?.matched_skill ?? null,
    previous_results: summarizePreviousResults(previousResults)
  };
}

async function executeNodeWithClientAi(
  spec: WorkflowSpec,
  node: WorkflowSpec["nodes"][number],
  previousResults: NodeExecutionResult[],
  resolvedNode: ResolvedWorkflowNode | null
): Promise<NodeExecutionResult | null> {
  const runtime = resolveClientAiRuntime();
  if (!canUseClientAi(runtime)) {
    return null;
  }

  const systemPrompt =
    "You are the FlowHub client runtime. Execute one workflow node using only the provided context. " +
    "Do not invent live web requests, API fetches, or external data access unless the context already includes them. " +
    "Return strict JSON with keys: message (string), result (object), notes (array of strings), confidence (string).";
  const userPayload = buildNodePayload(spec, node, previousResults, resolvedNode);

  try {
    const aiResult = await requestClientAiChat(runtime, [
      { role: "system", content: systemPrompt },
      { role: "user", content: JSON.stringify(userPayload, null, 2) }
    ]);
    const parsed = parseClientAiJson(aiResult.content);
    return {
      node_id: node.id,
      status: "success",
      output: {
        runtime: "client_ai",
        provider: aiResult.provider,
        model: aiResult.model,
        matched_skill: resolvedNode?.matched_skill ?? null,
        message: parsed.message ?? `Client AI executed ${node.name}`,
        result: parsed.result ?? {},
        notes: Array.isArray(parsed.notes) ? parsed.notes : [],
        confidence: parsed.confidence ?? "medium",
        reasoning_content: aiResult.reasoning_content
      },
      retry_count: 0
    };
  } catch (error) {
    return {
      node_id: node.id,
      status: "failed",
      output: {
        runtime: "client_ai",
        matched_skill: resolvedNode?.matched_skill ?? null
      },
      error: error instanceof Error ? error.message : String(error),
      retry_count: 0
    };
  }
}

async function executeNodeWithExternalTool(
  node: WorkflowSpec["nodes"][number]
): Promise<NodeExecutionResult | null> {
  const toolPayload = node.inputs?.external_tool;
  if (!toolPayload) {
    return null;
  }

  try {
    const sandbox = resolveClientToolSandbox();
    const request = parseExternalToolRequest(toolPayload);
    if (!request) {
      return null;
    }
    const output = await executeSandboxedExternalTool(request, sandbox);
    return {
      node_id: node.id,
      status: "success",
      output,
      retry_count: 0
    };
  } catch (error) {
    return {
      node_id: node.id,
      status: "failed",
      output: {
        runtime: "external_tool",
        tool_kind: typeof toolPayload === "object" && toolPayload && "kind" in toolPayload
          ? String((toolPayload as Record<string, unknown>).kind || "unknown")
          : "unknown"
      },
      error: error instanceof Error ? error.message : String(error),
      retry_count: 0
    };
  }
}

export async function executeWorkflow(
  spec: WorkflowSpec,
  options?: { resolvedWorkflow?: ResolvedWorkflowBundle | null }
): Promise<ExecutionResult> {
  const order = topologicalSort(spec);
  const nodeMap = new Map(spec.nodes.map((node) => [node.id, node]));

  const results: NodeExecutionResult[] = [];
  let hasFailure = false;

  for (const nodeId of order) {
    const node = nodeMap.get(nodeId);
    if (!node) {
      throw new Error(`Missing node ${nodeId}`);
    }

    if (hasFailure) {
      results.push({
        node_id: node.id,
        status: "skipped",
        output: {},
        retry_count: 0
      });
      continue;
    }

    const resolvedNode = findResolvedNode(options?.resolvedWorkflow, node.id);
    let result = await executeNodeWithExternalTool(node);
    if (!result) {
      result = await executeNodeWithClientAi(spec, node, results, resolvedNode);
    }
    if (result?.status === "failed") {
      const clientAiError = result.error;
      if (result.output.runtime === "external_tool") {
        results.push(result);
        hasFailure = true;
        continue;
      }
      result = await simulateNodeExecution(node);
      result.output = {
        ...result.output,
        fallback_from: "client_ai",
        fallback_reason: "Client AI execution failed; fell back to simulated runtime.",
        client_ai_error: clientAiError,
        matched_skill: resolvedNode?.matched_skill ?? null
      };
    }
    if (!result) {
      result = await simulateNodeExecution(node);
      result.output = {
        ...result.output,
        runtime: "simulated",
        matched_skill: resolvedNode?.matched_skill ?? null
      };
    }
    results.push(result);
    if (result.status === "failed") {
      hasFailure = true;
    }
  }

  const summary = {
    total: results.length,
    success: results.filter((item) => item.status === "success").length,
    failed: results.filter((item) => item.status === "failed").length,
    skipped: results.filter((item) => item.status === "skipped").length
  };

  return {
    run_id: randomUUID(),
    workflow_id: spec.workflow_id ?? spec.source_recipe_id,
    workflow_name: spec.name,
    node_results: results,
    summary
  };
}
