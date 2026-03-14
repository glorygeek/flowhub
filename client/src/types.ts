export type NodeStatus = "success" | "failed" | "skipped";

export type WorkflowNode = {
  id: string;
  name: string;
  skill_ref?: string;
  inputs?: Record<string, unknown>;
};

export type WorkflowEdge = {
  from_node: string;
  to_node: string;
};

export type WorkflowSpec = {
  id: string;
  workflow_id?: number;
  name: string;
  inputs: Record<string, unknown>;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  outputs: Record<string, unknown>;
  retry_policy?: Record<string, unknown>;
  confirm_points?: string[];
  source_recipe_id?: number;
  risk_level: "low" | "medium" | "high";
};

export type ClientSkillTarget = {
  name: string;
  display_name: string;
  source: string;
  source_slug?: string | null;
  source_url?: string | null;
  fetch_strategy: string;
  required: boolean;
};

export type ClientExecutionGuidance = {
  mode: string;
  ai_runtime_owner: string;
  summary: string;
  steps: string[];
  skill_targets: ClientSkillTarget[];
};

export type RuntimePlanBundle = {
  workflow_spec: WorkflowSpec;
  client_execution_guidance?: ClientExecutionGuidance | null;
};

export type FetchedSkillArtifact = {
  name: string;
  display_name: string;
  source: string;
  source_slug?: string | null;
  source_url?: string | null;
  fetch_strategy: string;
  required: boolean;
  cache_path: string;
  fetched_at: string;
  resolved_url: string;
  fetch_status: "network" | "cache" | "degraded";
  fetch_error?: string | null;
  payload_summary?: string | null;
  payload_version?: string | null;
  payload_stats?: Record<string, unknown> | null;
};

export type ResolvedWorkflowNode = {
  id: string;
  name: string;
  skill_ref?: string;
  resolution_status: "resolved" | "unresolved";
  runtime_hint?: string | null;
  matched_skill?: {
    display_name: string;
    source_slug?: string | null;
    source_url?: string | null;
    summary?: string | null;
    version?: string | null;
    fetch_status: "network" | "cache" | "degraded";
    cache_path: string;
    fetch_error?: string | null;
    stats?: Record<string, unknown> | null;
  } | null;
};

export type ResolvedWorkflowBundle = {
  generated_at: string;
  workflow_id?: number;
  workflow_name: string;
  ai_runtime_owner?: string | null;
  guidance_summary?: string | null;
  nodes: ResolvedWorkflowNode[];
};

export type NodeExecutionResult = {
  node_id: string;
  status: NodeStatus;
  output: Record<string, unknown>;
  error?: string;
  retry_count: number;
};

export type ClientAIRuntimeConfig = {
  enabled: boolean;
  base_url: string;
  model: string;
  api_key: string;
  timeout_seconds: number;
  temperature: number;
  thinking_enabled: boolean;
};

export type ClientToolSandboxConfig = {
  enabled: boolean;
  allowed_hosts: string[];
  allowed_methods: string[];
  allowed_commands: string[];
  manifest_path: string;
  manifest_required: boolean;
  manifest_require_release_metadata: boolean;
  manifest_allowed_signers: string[];
  manifest_allowed_fingerprints: string[];
  manifest_allowed_release_batches: string[];
  manifest_current_release_batch: string;
  manifest_previous_release_batches: string[];
  manifest_previous_batch_grace_days: number;
  manifest_enforce_expiration: boolean;
  manifest_require_revocation_audit: boolean;
  allow_sensitive_headers: boolean;
  timeout_seconds: number;
  max_response_bytes: number;
};

export type ClientToolManifestEntry = {
  command: string;
  path: string;
  sha256: string;
  version?: string;
  signer?: string;
  signer_fingerprint?: string | null;
  release_batch?: string | null;
  published_at?: string | null;
  expires_at?: string | null;
  revoked?: boolean;
  revocation_reason?: string | null;
  revoked_by?: string | null;
  revocation_ticket?: string | null;
  description?: string;
};

export type ExternalToolHttpRequest = {
  kind: "http_request";
  method: "GET" | "POST";
  url: string;
  headers?: Record<string, string>;
  body?: unknown;
  timeout_seconds?: number;
  response_format?: "json" | "text";
};

export type ExternalToolShellCommand = {
  kind: "shell_command";
  command: string;
  args: string[];
  cwd?: string;
  timeout_seconds?: number;
};

export type ExternalToolRequest = ExternalToolHttpRequest | ExternalToolShellCommand;

export type ExecutionResult = {
  run_id: string;
  workflow_id?: number;
  workflow_name: string;
  node_results: NodeExecutionResult[];
  summary: {
    total: number;
    success: number;
    failed: number;
    skipped: number;
  };
};
