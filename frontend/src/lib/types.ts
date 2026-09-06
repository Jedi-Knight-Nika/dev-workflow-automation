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
  repository_name?: string | null;
  due_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  source?: ExternalTaskSource | null;
  team_id?: string | null;
  team_name?: string | null;
  project_name?: string | null;
  labels?: string[];
  estimate?: number | null;
  repository_scopes?: Array<{
    repository_id: string;
    repository_name: string;
    selected_by: string;
    reason: string;
    confidence: number | null;
    is_primary: boolean;
    changed: boolean;
    branch_name: string | null;
    current_revision: string | null;
    pull_request_number: number | null;
    pull_request_url: string | null;
  }>;
};

export type ExternalTaskSource = {
  provider: string;
  external_id: string;
  identifier: string;
  url: string | null;
  state_id: string | null;
  state_name: string | null;
  assignee_id: string | null;
  assignee_name: string | null;
  assignee_email: string | null;
  creator_name: string | null;
  team_name: string | null;
  team_key: string | null;
  project_name: string | null;
  labels: string[];
  estimate: number | null;
  due_date: string | null;
  provider_created_at: string | null;
  provider_updated_at: string | null;
  raw_payload: Record<string, unknown>;
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
  archived_at: string | null;
  code_status: 'READY' | 'UPDATING' | 'CANNOT_FETCH' | 'NOT_PREPARED' | 'DISABLED';
  knowledge_status: 'READY' | 'INDEXING' | 'OUT_OF_DATE' | 'FAILED' | 'NOT_PREPARED' | 'DISABLED';
  teams_count: number;
  active_tasks_count: number;
  active_workspaces_count: number;
  last_activity_at: string | null;
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
  sync_status: string;
  last_synced_at: string | null;
  updated_at: string;
  display_status: 'READY' | 'WORKING' | 'NEEDS_ATTENTION' | 'NOT_CONFIGURED' | 'DISABLED';
  usage: {
    agents_count?: number;
    teams_count?: number;
    repositories_count?: number;
    active_tasks_count?: number;
    waiting_jobs_count?: number;
    workflow_nodes_count?: number;
  };
};

export type TrelloBoard = { id: string; name: string; url: string };
export type TrelloList = { id: string; name: string; closed: boolean };

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

export type AccountSettings = {
  general: {
    display_name: string;
    timezone: string;
    date_format: 'YYYY-MM-DD' | 'DD/MM/YYYY' | 'MM/DD/YYYY';
    time_format: '12H' | '24H';
    default_landing_page: 'dashboard' | 'tasks' | 'teams';
    default_task_view: 'board' | 'list';
    appearance: 'system' | 'light' | 'dark';
    compact_dashboard: boolean;
  };
  ai: {
    default_provider_id: string | null;
    default_model: string | null;
    default_reasoning_level: 'default' | 'low' | 'medium' | 'high' | 'max';
    default_max_output_tokens: number | null;
    provider_failure_behavior: 'PAUSE_AND_NOTIFY' | 'USE_CONFIGURED_FALLBACK';
    structured_output_retry_limit: number;
  };
  execution: {
    default_execution_mode: 'CONSERVATIVE' | 'AUTONOMOUS' | 'CUSTOM';
    default_worker_runtime: 'LOCAL_PROCESS' | 'DOCKER' | 'WSL2';
    max_concurrent_workers: number;
    default_job_timeout_seconds: number;
  };
  safety: {
    default_merge_policy: PolicyChoice;
    default_unknown_network_policy: PolicyChoice;
    default_dependency_install_policy: PolicyChoice;
    default_push_task_branch_policy: PolicyChoice;
  };
  knowledge: {
    auto_index_repositories: boolean;
    incremental_index_after_merge: boolean;
    index_source_code: boolean;
    index_tests: boolean;
    index_documentation: boolean;
    ignore_generated_files: boolean;
    context_strategy: 'MINIMAL' | 'BALANCED' | 'DEEP';
  };
  storage: {
    completed_workspace_retention_days: number;
    failed_workspace_retention_days: number;
    worker_log_retention_days: number;
    audit_event_retention_days: number;
    monthly_cost_warning: number | null;
    monthly_cost_hard_stop: number | null;
  };
  security: {
    secret_masking_enabled: boolean;
    fresh_session_per_job: boolean;
    locked_rules: Array<{
      key: string;
      effective_value: 'DENY';
      source: 'PLATFORM';
      editable: false;
    }>;
  };
  settings_version: number;
  updated_at: string;
};

export type PolicyChoice = 'ALLOW' | 'DENY' | 'REQUIRE_HUMAN';

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
  integration_mode: string;
  poll_interval_seconds: number;
  filter_assignee_id: string;
  filter_state_ids: string[];
  integration_sync_status: string;
  integration_sync_error: string | null;
  integration_last_synced_at: string | null;
  reasoning_effort: 'default' | 'low' | 'medium' | 'high' | 'max';
  max_output_tokens: number | null;
  temperature: number | null;
  timeout_minutes: number;
  max_retries: number;
  max_review_cycles: number;
  context_depth: 'low' | 'normal' | 'deep';
  rag_retrieval_depth: 'low' | 'normal' | 'deep';
  fallback_provider: string | null;
  fallback_model: string | null;
  agent_id: string | null;
  node_type: 'AGENT' | 'SYSTEM_GATE' | 'TERMINAL' | 'HUMAN_APPROVAL' | 'EXTERNAL_WAIT';
  system_node_type: string | null;
};

export type WorkflowEdge = {
  id: string;
  source_node_id: string;
  target_node_id: string;
  outcome: string;
  required: boolean;
  job_type: string | null;
  internal_task_state: string | null;
  external_status_key: string | null;
  priority_override: number | null;
  configuration: Record<string, unknown>;
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

export type DashboardUsageBucket = {
  key: string;
  input_tokens: number;
  output_tokens: number;
  estimated_cost: number | null;
};

export type DashboardTimeBucket = {
  period: string;
  completed: number;
  failed: number;
  human_assisted: number;
  input_tokens: number;
  output_tokens: number;
};

export type DashboardSnapshot = {
  period: 'today' | '7d' | '30d';
  generated_at: string;
  system_status: string;
  health_score: number;
  active_tasks: number;
  queued_jobs: number;
  ready_to_merge: number;
  needs_human: number;
  completed: number;
  failed: number;
  tokens: number;
  estimated_cost: number | null;
  autonomy_rate: number | null;
  active_worker: null | {
    job_id: string;
    task_id: string;
    task_label: string;
    team_id: string | null;
    team_name: string | null;
    agent_name: string | null;
    role: string;
    provider: string | null;
    model: string | null;
    started_at: string | null;
    input_tokens: number;
    output_tokens: number;
  };
  queue: Array<{
    job_id: string;
    task_id: string;
    task_label: string;
    team_id: string | null;
    team_name: string | null;
    role: string;
    action: string;
    priority: number;
    state: string;
    created_at: string;
  }>;
  teams: Array<{
    team_id: string;
    name: string;
    status: string;
    current_task_id: string | null;
    current_task_label: string | null;
    agent_name: string | null;
    role: string | null;
    provider: string | null;
    model: string | null;
    queued_jobs: number;
    open_pull_requests: number;
    ready_to_merge: number;
    tokens: number;
  }>;
  recent_events: Array<{
    id: string;
    timestamp: string;
    team_id: string | null;
    team_name: string | null;
    task_id: string;
    task_label: string;
    source: string;
    severity: string;
    event_type: string;
    summary: string;
  }>;
  usage_by_role: DashboardUsageBucket[];
  usage_by_provider: DashboardUsageBucket[];
  usage_by_team: DashboardUsageBucket[];
  throughput: DashboardTimeBucket[];
  token_history: DashboardTimeBucket[];
  health: Array<{
    name: string;
    status: string;
    message: string;
    last_success_at: string | null;
    last_failure_at: string | null;
  }>;
};

export type HostTelemetry = {
  cpu_percent: number;
  memory_used_bytes: number;
  memory_total_bytes: number;
  memory_percent: number;
  disk_used_bytes: number;
  disk_total_bytes: number;
  disk_percent: number;
  load_average: [number, number, number] | null;
  uptime_seconds: number;
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

export type LinearMember = {
  id: string;
  name: string;
  email: string;
  active: boolean;
};

export type Team = {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  max_concurrent_tasks: number;
  repository_ids: string[];
  queued_tasks: number;
  running_tasks: number;
  completed_tasks: number;
  total_input_tokens: number;
  total_output_tokens: number;
  estimated_cost_usd: number;
  created_at: string;
  updated_at: string;
};

export type ExecutionPolicy = {
  mode: 'CONSERVATIVE' | 'AUTONOMOUS' | 'CUSTOM';
  settings: Record<string, 'ALLOW' | 'DENY' | 'REQUIRE_HUMAN'>;
  approved_hosts: string[];
  max_command_timeout_seconds: number;
  max_output_bytes: number;
  isolation_level: string;
  execution_environment: string;
};

export type ApprovalRequest = {
  id: string;
  team_id: string;
  task_id: string;
  job_id: string;
  agent_id: string | null;
  tool: string;
  action: string;
  arguments: Record<string, unknown>;
  reason: string;
  state: string;
  created_at: string;
  expires_at: string;
};

export type AppNotification = {
  id: string;
  incident_id: string | null;
  type: string;
  severity: 'INFO' | 'WARNING' | 'ACTION_REQUIRED' | 'CRITICAL';
  title: string;
  message: string;
  status: 'UNREAD' | 'READ' | 'ACKNOWLEDGED' | 'RESOLVED';
  task_id: string | null;
  action_target: string | null;
  created_at: string;
};

export type TelegramStatus = {
  configured: boolean;
  connected: boolean;
  username: string | null;
  last_delivery_at: string | null;
  last_delivery_error: string | null;
  webhook_configured: boolean;
};

export type TaskMemory = {
  task_id: string;
  goal: string;
  known_facts: string[];
  decisions: string[];
  rejected_approaches: { approach: string; reason: string }[];
  invariants: string[];
  important_files: string[];
  important_symbols: string[];
  open_questions: string[];
  open_finding_ids: string[];
  resolved_finding_summaries: string[];
  current_plan_job_id: string | null;
  current_sha: string | null;
  version: number;
};

export type AgentCheckpoint = {
  id: string;
  job_id: string;
  role: string;
  repository_sha: string | null;
  summary: string;
  structured_data: Record<string, unknown>;
  token_estimate: number | null;
  created_at: string;
};

export type Role = {
  id: string;
  name: string;
  category: string;
  description: string;
  system_instructions: string;
  capabilities: string[];
  permissions: string[];
  allowed_results: string[];
  knowledge_collection_ids: string[];
  default_provider: string | null;
  default_model: string | null;
  default_reasoning_effort: string;
  default_timeout_minutes: number;
  default_max_retries: number;
  runtime_profile: RoleRuntimeProfile;
  override_policy: Record<string, string>;
  enabled: boolean;
  built_in: boolean;
  version: number;
  active_agents: number;
  inactive_agents: number;
  total_agents: number;
  created_at: string;
  updated_at: string;
};

export type RoleRuntimeProfile = {
  reasoning_default: 'PROVIDER_DEFAULT' | 'MINIMAL' | 'LOW' | 'MEDIUM' | 'HIGH' | 'MAX';
  reasoning_min: 'PROVIDER_DEFAULT' | 'MINIMAL' | 'LOW' | 'MEDIUM' | 'HIGH' | 'MAX';
  reasoning_max: 'PROVIDER_DEFAULT' | 'MINIMAL' | 'LOW' | 'MEDIUM' | 'HIGH' | 'MAX';
  dynamic_reasoning_allowed: boolean;
  max_output_tokens: number | null;
  temperature: number | null;
  context_strategy: 'MINIMAL' | 'BALANCED' | 'DEEP';
  max_tool_calls: number;
  job_timeout_seconds: number;
  max_job_attempts: number;
  max_model_turns: number;
  structured_output_mode: 'REQUIRED' | 'PREFERRED' | 'NONE';
};

export type AgentRuntimeView = {
  agent_id: string;
  role_id: string;
  role_name: string;
  config_version: number;
  versions: {
    role: number;
    agent: number;
    capabilities: string;
    strategy: string;
  };
  overrides: Record<string, unknown>;
  override_policy: Record<string, string>;
  effective: {
    provider: string;
    model: string;
    reasoning_level: string;
    max_output_tokens: number;
    temperature: number | null;
    context_strategy: string;
    max_tool_calls: number;
    job_timeout_seconds: number;
    max_job_attempts: number;
    max_model_turns: number;
    structured_output_mode: string;
    capability_version: string;
    strategy_version: string;
  };
  effective_hash: string;
  sources: Record<string, 'ROLE' | 'AGENT'>;
};

export type ModelCapabilities = {
  provider: string;
  model: string;
  context_window: number | null;
  max_output_tokens: number | null;
  reasoning_supported: boolean;
  reasoning_levels: string[];
  temperature_supported: boolean;
  structured_output_supported: boolean;
  tools_supported: boolean;
  parallel_tool_calls_supported: boolean;
  capability_version: string;
};

export type TaskAssignment = {
  id: string;
  task_id: string;
  team_id: string;
  status: string;
  queue_position: number;
  reason: string;
  assigned_at: string;
  started_at: string | null;
  completed_at: string | null;
};
