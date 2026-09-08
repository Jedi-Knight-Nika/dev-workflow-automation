export type Task = {
  id: string;
  external_key: string | null;
  title: string;
  description: string;
  priority: number;
  status: string;
  stage: string;
  wait_reason: string;
  lifecycle_version: number;
  requirement_version: number;
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
  latest_sha: string | null;
  updated_at: string;
  archived_at: string | null;
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
  security: {
    secret_masking_enabled: boolean;
    resume_native_session: boolean;
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

export type Job = {
  id: string;
  task_id: string;
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

export type TaskRoleMetrics = {
  role: string;
  provider: string;
  model: string;
  attempts: number;
  input_tokens: number;
  output_tokens: number;
  duration_ms: number;
};
export type TaskMetrics = {
  native_turns?: number;
  attempts: number;
  input_tokens: number;
  output_tokens: number;
  missing_usage_attempts: number;
  duration_ms: number;
  estimated_cost_usd: number | null;
  roles: TaskRoleMetrics[];
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
  active_workers?: NonNullable<DashboardSnapshot['active_worker']>[];
  running_jobs?: number;
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
    action?: string;
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

export type TaskMessage = {
  id: number;
  task_id: string;
  job_id: string | null;
  reply_to_id: number | null;
  author_type: 'USER' | 'AGENT' | 'SYSTEM';
  author_name: string;
  author_role: string | null;
  kind: 'COMMENT' | 'STATUS_UPDATE' | string;
  body: string;
  context: Record<string, unknown>;
  created_at: string;
};

export type TaskMessagePage = {
  items: TaskMessage[];
  next_before_id: number | null;
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
  exit_code: number | null;
  output_tail: string;
  finished_at: string | null;
};

export type NativeRun = {
  id: string;
  role_kind: string;
  provider: string;
  model: string;
  harness: string | null;
  status: string;
  input_tokens: number | null;
  output_tokens: number | null;
  cache_read_tokens: number | null;
  cost_usd: string | null;
  usage_complete: boolean;
  artifact: string | null;
  failure_code: string | null;
  started_at: string;
  finished_at: string | null;
  requirement_version: number;
};

export type LiveExecution = {
  id: string;
  role_kind: string;
  provider: string;
  model: string;
  harness: string | null;
  status: string;
  started_at: string;
  finished_at: string | null;
  telemetry: {
    input_tokens_observed?: number | null;
    active_context_estimate?: number | null;
    phase_label?: string | null;
    tool_call_count?: number;
    diff_changes?: number;
    source_read_count?: number;
    targeted_check_improvements?: number;
    tokens_since_last_progress?: number | null;
    warnings?: string[];
    stop_reason?: string | null;
  } | null;
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
  execution_paused: boolean;
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
  estimated_cost_usd: number | null;
  created_at: string;
  updated_at: string;
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
