export interface MetricSeries {
  labels: Record<string, string>;
  samples: [number, number | null][];
}
export interface MetricResult {
  status: string;
  series: MetricSeries[];
  sampled_at: string | null;
  reason: string | null;
}
export interface ResourceSummary {
  metrics_complete: boolean;
  sample_coverage_ratio: number | null;
  values: Record<string, number | null>;
  calculated_at: string;
}
export interface RunnerResource {
  container_id: string;
  task_title?: string | null;
  task_key?: string | null;
  profile_name?: string | null;
  harness?: string | null;
  model?: string | null;
  known_cost_usd?: string;
  unknown_cost_runs?: number;
  input_tokens?: number | null;
  output_tokens?: number | null;
  ai_active_seconds?: number | null;
  developer_active_seconds?: number | null;
  wall_seconds?: number;
  resources?: ServiceResource | null;
  runner_run_id: string;
  task_id: string | null;
  team_id: string | null;
  agent_profile_id: string | null;
  container_name: string;
  service_kind: string;
  phase: string | null;
  started_at: string;
  stopped_at: string | null;
  exit_code: number | null;
  oom_killed: boolean | null;
  summary: ResourceSummary | null;
}
export interface ServiceResource {
  memory_peak?: number | null;
  network_rx_rate?: number | null;
  network_tx_rate?: number | null;
  block_read_rate?: number | null;
  block_write_rate?: number | null;
  throttled_rate?: number | null;
  memory_ratio?: number | null;
  memory_failures?: number | null;
  pids?: number | null;
  uptime_seconds?: number | null;
  restart_count?: number | null;
  oom_count?: number | null;
  exit_code?: number | null;
  state?: string;
  health?: string;
  id: string;
  name: string | null;
  service: string | null;
  cpu?: number | null;
  memory?: number | null;
  memory_limit?: number | null;
  last_seen?: number | null;
}
export interface LiveMetrics {
  events?: InfrastructureEvent[];
  status: string;
  sampled_at: string | null;
  data_freshness_seconds: number | null;
  host: Record<string, number | null>;
  services: ServiceResource[];
  active_runners: RunnerResource[];
  availability: MetricResult;
  targets: MetricResult;
  cpu_definition: string;
}
export interface Incident {
  id: string;
  service_key: string;
  kind: string;
  severity: string;
  opened_at: string;
  closed_at: string | null;
  source: string;
  summary: string;
}
export interface MonitoringSettings {
  monthly_budget_usd?: number | null;
  forecast_horizon_days?: number;
  enabled: boolean;
  retention_days: number;
  retention_size: string;
  refresh_seconds: number;
  forecasts_enabled: boolean;
  forecast_min_samples: number;
  cpu_warning: number;
  ram_warning: number;
  disk_warning: number;
  queue_warning_seconds: number;
  alertmanager_enabled: boolean;
  deployment_managed: boolean;
}

export interface InfrastructureEvent {
  id: string;
  occurred_at: string;
  container_id: string;
  service_name: string;
  event_type: string;
  runner_run_id: string | null;
  exit_code: number | null;
}
export interface Availability {
  status: string;
  days: number;
  services: {
    service: string;
    uptime_ratio: number | null;
    sample_coverage_ratio: number;
    valid_samples: number;
    samples: [number, number | null][];
  }[];
  basis: string;
}
