export type RiskLevel = "low" | "medium" | "high";
export type ReviewStatus = "draft" | "pending" | "approved" | "rejected" | "archived";
export type ExecutionMode = "local" | "remote";
export type TargetType = "url" | "api" | "text";
export type OutputFormat = "json" | "csv" | "xlsx" | "pdf" | "markdown";
export type CredentialKind = "api_key" | "token" | "cookie" | "basic_auth" | "other";
export type RunRequestStatus = "planned" | "queued" | "running" | "completed" | "failed";
export type NodeExecutionStatus = "pending" | "running" | "success" | "failed" | "skipped";

export type Skill = {
  id: number;
  name: string;
  display_name: string;
  category: string;
  description: string;
  summary: string;
  tags: string[];
  risk_level: RiskLevel;
  status: ReviewStatus;
  execution_mode: "local" | "remote";
  source: string;
  source_slug?: string | null;
  source_url?: string | null;
  is_official: boolean;
  owner_handle?: string | null;
  version: string;
  stats: Record<string, unknown>;
  registry_metadata: Record<string, unknown>;
  security_score: number;
  security_tier: string;
  security_verdict: string;
  security_flags: string[];
  last_synced_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type SkillTag = {
  id: number;
  name: string;
  label: string;
  category: string;
  source: string;
  description: string;
  active: boolean;
  usage_count: number;
  created_at: string;
  updated_at: string;
};

export type SearchPolicyRule = {
  id: number;
  name: string;
  intent_key: string;
  description: string;
  reason: string;
  conditions: Record<string, unknown>;
  score_delta: number;
  priority: number;
  active: boolean;
  created_at: string;
  updated_at: string;
};

export type OperatorChangeLog = {
  id: number;
  entity_type: string;
  entity_id: number;
  action: string;
  actor: string;
  note: string;
  before_state: Record<string, unknown>;
  after_state: Record<string, unknown>;
  created_at: string;
};

export type SkillLinkedTag = SkillTag & {
  link_source: string;
  confidence: string;
};

export type SkillSearchResult = {
  skill: Skill;
  search_score: number;
  retrieval_source: string;
  official_score?: number | null;
  quality_score: number;
  quality_tier: string;
  trust_signals: string[];
  security_score: number;
  security_tier: string;
  security_verdict: string;
  security_flags: string[];
  matched_terms: string[];
  matched_tags: string[];
  ranking_reasons: string[];
};

export type SkillSecurityOverride = {
  decision: "safe_to_use" | "use_with_caution" | "manual_review_required" | "block_or_quarantine";
  actor?: string | null;
  note?: string | null;
  updated_at?: string | null;
};

export type SkillSecurityReview = {
  security_score: number;
  security_tier: string;
  security_verdict: string;
  security_flags: string[];
  permission_profile: Record<string, boolean>;
  moderation_verdict?: string | null;
  operator_override?: SkillSecurityOverride | null;
};

export type ResolvedSkillRef = {
  requested_ref: string;
  matched_by?: string | null;
  skill?: Skill | null;
};

export type RecipeNode = {
  id: string;
  skill_category?: string;
  config?: Record<string, unknown>;
};

export type RecipeEdge = {
  from_node: string;
  to_node: string;
};

export type Recipe = {
  id: number;
  name: string;
  scenario: string;
  description: string;
  tags: string[];
  node_skeleton: RecipeNode[];
  edges: RecipeEdge[];
  risk_level: RiskLevel;
  status: ReviewStatus;
  created_at: string;
};

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

export type Workflow = {
  id: number;
  name: string;
  description: string;
  inputs: Record<string, unknown>;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  outputs: Record<string, unknown>;
  source_recipe_id?: number;
  risk_level: RiskLevel;
  status: ReviewStatus;
  created_at: string;
};

export type SkillRecommendation = {
  skill_id: number;
  name: string;
  display_name: string;
  category: string;
  source: string;
  source_slug?: string | null;
  summary: string;
  description: string;
  source_url?: string | null;
  usage_hint: string;
  selection_reason: string;
  quality_score: number;
  quality_tier: string;
  trust_signals: string[];
  security_score: number;
  security_tier: string;
  security_verdict: string;
  security_flags: string[];
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

export type ClientInstallTarget = {
  name: string;
  display_name: string;
  source: string;
  source_slug?: string | null;
  source_url?: string | null;
  fetch_strategy: string;
  required: boolean;
  install_command?: string | null;
  install_command_windows?: string | null;
};

export type ClientInstallGuidance = {
  mode: string;
  install_requested: boolean;
  status: string;
  summary: string;
  steps: string[];
  items: ClientInstallTarget[];
  note: string;
};

export type WorkflowSummaryStep = {
  index: number;
  skill_ref: string;
  display_name: string;
  role: string;
  summary: string;
  planning_status: string;
  source_url?: string | null;
};

export type WorkflowSafetyReviewItem = {
  skill_ref: string;
  display_name: string;
  planning_status: string;
  security_flags: string[];
  note: string;
};

export type WorkflowSummary = {
  formula: string;
  plan_type: string;
  headline: string;
  explanation: string;
  steps: WorkflowSummaryStep[];
  usage_steps: string[];
  safety_guidance: string[];
  handoff_steps: string[];
  safety_review_items: WorkflowSafetyReviewItem[];
};

export type AssistantResponse = {
  template_key: string;
  headline: string;
  reply_text: string;
  usage_steps: string[];
  confirmation_prompt: string;
  delivery_note: string;
};

export type CommunicationPreview = {
  channel: string;
  template_key: string;
  status: "pending_confirmation" | "ready_to_send" | string;
  title: string;
  body: string;
  usage_steps: string[];
};

export type PlannedWorkflow = {
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
  risk_level: RiskLevel;
};

export type RunTarget = {
  type: TargetType;
  label: string;
  value: string;
};

export type CredentialDescriptor = {
  label: string;
  kind: CredentialKind;
  preview: string;
  ephemeral: boolean;
};

export type RunRequest = {
  id: number;
  goal: string;
  targets: RunTarget[];
  credential_descriptors: CredentialDescriptor[];
  output_format: OutputFormat;
  execution_mode: ExecutionMode;
  user_notes: string;
  status: RunRequestStatus;
  workflow_spec: PlannedWorkflow;
  planning_notes: string[];
  created_at: string;
  updated_at: string;
};

export type NodeExecutionResult = {
  node_id: string;
  status: NodeExecutionStatus;
  output: Record<string, unknown>;
  error?: string | null;
  retry_count: number;
};

export type TelemetryEvent = {
  id: number;
  workflow_id?: number | null;
  run_id: string;
  node_results: NodeExecutionResult[];
  summary: Record<string, unknown>;
  client_meta: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type AuditAlertDelivery = {
  id: number;
  telemetry_event_id: number;
  workflow_id?: number | null;
  run_id: string;
  destination: string;
  status: string;
  attempt_count: number;
  response_status_code?: number | null;
  response_body_preview: string;
  error_message: string;
  payload: Record<string, unknown>;
  delivered_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type TelemetryAnomaly = {
  event_id: number;
  workflow_id?: number | null;
  run_id: string;
  failed_node_count: number;
  failed_node_ids: string[];
  summary: Record<string, unknown>;
  client_meta: Record<string, unknown>;
  created_at: string;
};

export type RunRequestPlanResponse = {
  actionable: boolean;
  request?: RunRequest | null;
  workflow_spec?: PlannedWorkflow | null;
  decision_log: string[];
  next_steps: string[];
  assistant_response: AssistantResponse;
  selected_skills: SkillRecommendation[];
  communication_preview: CommunicationPreview;
  client_execution_guidance?: ClientExecutionGuidance | null;
  client_install_guidance?: ClientInstallGuidance | null;
  workflow_summary?: WorkflowSummary | null;
  intake_summary: {
    target_count: number;
    credential_count: number;
    output_format: OutputFormat;
    execution_mode: ExecutionMode;
  };
};

export type RunRequestConfirmResponse = {
  request: RunRequest;
  workflow_spec: PlannedWorkflow;
  assistant_response: AssistantResponse;
  selected_skills: SkillRecommendation[];
  communication_preview: CommunicationPreview;
  client_execution_guidance?: ClientExecutionGuidance | null;
  client_install_guidance?: ClientInstallGuidance | null;
  workflow_summary?: WorkflowSummary | null;
};
