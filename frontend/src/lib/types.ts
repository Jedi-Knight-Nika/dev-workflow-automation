export type Task = {
  id: string;
  external_key: string | null;
  title: string;
  description: string;
  priority: number;
  state: string;
  current_revision: string | null;
  repository_id: string | null;
  branch_name: string | null;
  workspace_path: string | null;
  pull_request_number: number | null;
  pull_request_url: string | null;
  manual_takeover: boolean;
  created_at: string;
  updated_at: string;
};

export type Repository = {
  id: string;
  provider: string;
  external_repo_id: string;
  owner: string;
  name: string;
  clone_url: string;
  default_branch: string;
  enabled: boolean;
  local_path: string | null;
  index_status: string;
  index_error: string | null;
  latest_sha: string | null;
  indexed_sha: string | null;
  indexed_at: string | null;
  updated_at: string;
  clone_status: string;
  chunk_count: number;
};

export type DiscoveredRepository = {
  external_repo_id: string;
  owner: string;
  name: string;
  full_name: string;
  clone_url: string;
  default_branch: string;
  private: boolean;
};

export type Integration = {
  id: string;
  provider_type: string;
  provider_name: string;
  status: string;
  configuration: Record<string, unknown>;
  has_credentials: boolean;
  last_error: string | null;
  updated_at: string;
};

export type GitHubInstallationAccount = {
  login: string;
  account_type: string;
  avatar_url: string;
  profile_url: string;
};

export type WebhookHealth = {
  provider: string;
  pending: number;
  failed: number;
  last_delivery_at: string | null;
  last_processed_at: string | null;
  last_error: string | null;
};

export type AgentConfig = {
  role: string;
  enabled: boolean;
  provider: string;
  model: string;
  configuration: Record<string, unknown>;
  updated_at: string;
  status: string;
  active_jobs: number;
  total_runs: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_estimated_cost_usd: number;
  last_run_at: string | null;
  last_duration_ms: number | null;
  last_provider: string | null;
  last_model: string | null;
  active_task_id: string | null;
  active_task_manual_takeover: boolean;
  active_task_has_workspace: boolean;
};

export type TerminalAccess = {
  session_id: string;
  token: string;
  status: string;
  cols: number;
  rows: number;
};

export type AgentKnowledge = {
  id: string;
  role: string;
  title: string;
  chunk_count: number;
  created_at: string;
};

export type WorkflowNode = {
  id: string;
  role: string;
  label: string;
  position_x: number;
  position_y: number;
  enabled: boolean;
  activation_policy: string;
  batch_window_seconds: number;
  integration_ids: string[];
  repository_ids: string[];
  provider: string;
  model: string;
  system_prompt: string;
  model_validation_status: string;
  model_validation_message: string | null;
  model_validated_at: string | null;
};

export type WorkflowEdge = {
  id: string;
  source_node_id: string;
  target_node_id: string;
  outcome: string;
  required: boolean;
};

export type WorkflowGraph = {
  version: number;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
};

export type ProviderCatalog = {
  provider: string;
  capabilities: Record<string, boolean>;
  models: Array<{ id: string; display_name: string }>;
};

export type Job = {
  id: string;
  task_id: string;
  role: string;
  action: string;
  state: string;
  attempt: number;
  priority: number;
  payload: Record<string, unknown>;
  result: {
    protocol_version: number;
    job_id: string;
    task_id: string;
    role: string;
    result: string;
    summary: string;
    data: Record<string, unknown>;
  } | null;
  worker_id: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  failure_reason: string | null;
  retry_not_before: string | null;
};

export type DashboardActivity = {
  active_job: Job | null;
  queued_jobs: Job[];
};

export type TaskEvent = {
  id: number;
  task_id: string;
  source: string;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type ValidationRecord = {
  id: string;
  provider: string;
  kind: string;
  name: string;
  status: string;
  revision: string;
  details_url: string | null;
  created_at: string;
};

export type KnowledgeResult = {
  file_path: string;
  chunk_index: number;
  content: string;
  commit_sha: string;
  score: number;
};

export type ReviewFinding = {
  id: string;
  reviewer_job_id: string;
  workspace_fingerprint: string;
  finding_fingerprint: string | null;
  occurrence_count: number;
  severity: string;
  file_path: string | null;
  line: number | null;
  message: string;
  status: string;
  created_at: string;
  last_seen_at: string | null;
  resolved_at: string | null;
};

export type WorkerNode = {
  id: string;
  hostname: string;
  process_id: number;
  status: string;
  online: boolean;
  capabilities: string[];
  started_at: string;
  last_heartbeat: string;
  stopped_at: string | null;
};

export type LinearWorkflowState = {
  id: string;
  name: string;
  type: string;
  team_id: string;
  team_name: string;
  team_key: string;
};
