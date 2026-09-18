export type Scope = {
  type: 'workspace' | 'project' | 'team' | 'task' | 'repository';
  id?: string | null;
};
export type ViewMode = 'flow' | 'workspace' | 'code';
export type FileChange = {
  repository_id: string;
  operation: 'A' | 'M' | 'D' | 'R';
  path: string;
  previous_path: string | null;
  lines_added: number | null;
  lines_deleted: number | null;
};
export type ActivityEvent = {
  sequence: number;
  id: string;
  kind: string;
  occurred_at: string;
  recorded_at: string;
  task_id: string;
  task_title: string;
  task_key: string | null;
  team_id: string | null;
  team_name: string | null;
  project: string | null;
  actor_type: string;
  actor: string;
  correlation_id: string | null;
  payload: Record<string, unknown>;
  files: FileChange[];
  parents?: RelatedActivity[];
  unresolved_parents?: number;
  file_status?: string | null;
};
export type RelatedActivity = Pick<
  ActivityEvent,
  'sequence' | 'kind' | 'occurred_at' | 'actor' | 'actor_type' | 'task_id' | 'payload'
> & { relationship?: string };
export type FileHistory = {
  counts: Record<string, number>;
  incomplete: boolean;
  sampled: boolean;
  collection_enabled?: boolean;
};
export type ActivityAggregate = {
  unit: 'hour' | 'day';
  events: number;
  through_sequence: number;
  buckets: {
    at: string;
    events: number;
    tasks: number;
    validation_passed: number;
    validation_failed: number;
    reviews: number;
    human_responses: number;
  }[];
};
export type Inspection = {
  event: ActivityEvent;
  children: RelatedActivity[];
  checks: RelatedActivity[];
  truncated: boolean;
  file_status: string | null;
  file_attempts: number;
  file_retry_at: string | null;
};
export type TaskState = {
  id: string;
  title: string;
  key: string | null;
  team_id: string | null;
  team_name: string | null;
  project: string | null;
  status: string;
  stage: string;
  wait_reason: string;
  version: number;
  dependency_ids?: string[];
};
export type Preflight = {
  scope: Scope;
  from: string;
  to: string;
  through_sequence: number;
  estimated_events: number;
  tasks: number;
  max_events: number;
  max_files: number;
  file_changes: number;
  max_tasks: number;
  too_large: boolean;
  delayed: boolean;
  last_projected_at: string | null;
  warnings: string[];
  live_available: boolean;
  file_history?: FileHistory;
  capacity?: CapacityEvidence;
};
export type CapacityEvidence = {
  as_of?: string;
  through_sequence?: number;
  truncated: boolean;
  teams: {
    id: string;
    name: string;
    limits: { at: string; capacity: number }[];
    jobs: { id: string; task_id: string; start: string; end: string | null; complete: boolean }[];
  }[];
};
export type Frame = {
  tasks: TaskState[];
  index: number;
  count: number;
  at: number;
  playing: boolean;
  cost: number;
  unknownCosts: number;
  incompleteUsage: number;
  inputTokens: number;
  outputTokens: number;
  activeMs: number;
  waitingMs: number;
  selected: ActivityEvent | null;
  process: import('./process-metrics').ProcessMetrics;
  economics: import('./economics').Economics;
  bottlenecks: import('./bottlenecks').Bottlenecks;
  workPlans: WorkPlanSnapshot[];
  deployments: ReturnType<typeof import('$lib/delivery/metrics').deploymentMetrics>;
};
export type WorkPlan = {
  revision: number;
  units: { id: string; depends_on: number[]; status: string }[];
};
export type WorkPlanSnapshot = { runId: string; task: string; at: string; plans: WorkPlan[] };
export type Filters = { actor: string; kind: string; team: string; communication: boolean };
export type ReplayConfig = {
  events: ActivityEvent[];
  tasks: TaskState[];
  start: number;
  mode: ViewMode;
  live: boolean;
  maxEvents: number;
  maxTasks: number;
  capacity?: CapacityEvidence;
};
export type RendererCommand =
  | { type: 'LOAD'; config: ReplayConfig }
  | { type: 'APPEND'; events: ActivityEvent[] }
  | { type: 'CAPACITY'; evidence: CapacityEvidence }
  | { type: 'PLAY' | 'PAUSE' | 'DISPOSE' }
  | { type: 'SEEK'; index: number }
  | { type: 'SPEED'; speed: number; realGaps: boolean }
  | { type: 'MODE'; mode: ViewMode }
  | { type: 'FILTER'; filters: Filters }
  | { type: 'RESIZE'; width: number; height: number; dpr: number }
  | { type: 'SELECT'; x: number; y: number }
  | { type: 'PAN'; x: number; y: number }
  | { type: 'ZOOM'; factor: number }
  | { type: 'RESET_CAMERA' }
  | { type: 'INIT'; canvas: OffscreenCanvas };

export type RendererMessage =
  | { type: 'FRAME'; frame: Frame; renderMs?: number }
  | { type: 'ERROR'; message: string; code?: 'worker_crash' | 'graphics_unavailable' | 'limit' };
