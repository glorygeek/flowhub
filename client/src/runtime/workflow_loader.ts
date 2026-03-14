import type { WorkflowSpec } from "../types";
import { loadRuntimePlan } from "./plan_loader";

export async function loadWorkflowSpec(filePath: string): Promise<WorkflowSpec> {
  const plan = await loadRuntimePlan(filePath);
  return plan.workflow_spec;
}
