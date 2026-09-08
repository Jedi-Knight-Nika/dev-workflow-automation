export interface UsageTotals {
  cache_write_tokens?: number | null;
  runs: number;
  known_cost_usd: string;
  cost_usd: string | null;
  cost_complete: boolean;
  unknown_cost_runs: number;
  incomplete_usage_runs: number;
  reserved_usd: string;
  failed_spend_usd: string;
  compaction_spend_usd: string;
  input_tokens: number | null;
  output_tokens: number | null;
  cache_read_tokens: number | null;
  reasoning_tokens: number | null;
}
export interface UsageGroup extends UsageTotals {
  key: string;
}
export interface AgentEfficiency extends UsageGroup {
  teams?: string[];
  tokens_per_merged_task?: number | null;
  p90_developer_seconds?: number | null;
  display_name: string;
  tasks_merged: number;
  terminal_tasks: number;
  success_rate: number | null;
  median_cost_usd: number | null;
  p90_cost_usd: number | null;
  median_developer_seconds: number | null;
  human_intervention_rate: number | null;
  review_fix_cycles_per_task: number | null;
  models: string[];
  harnesses: string[];
}
export interface AnalyticsDashboard {
  month_totals?: UsageTotals;
  period_costs?: Record<string, UsageTotals>;
  repository_names?: Record<string, string>;
  reliability?: Record<string, number>;
  local_runs?: LocalRun[];
  sampled_at: string;
  days: number;
  totals: UsageTotals;
  agents: AgentEfficiency[];
  models: UsageGroup[];
  run_kinds: UsageGroup[];
  repositories: UsageGroup[];
  merged_tasks: number;
  complete_merged_tasks: number;
  excluded_incomplete_tasks: number;
  cost_per_merged_task_usd: string | null;
  basis: string;
  daily: UsageGroup[];
}
export interface CostForecast {
  metrics?: Record<string, ForecastMetric>;
  predicted_peak_concurrent_memory_bytes?: number | null;
  queue_drain_seconds?: number | null;
  resource_basis?: string;
  forecast_version: string;
  confidence: string;
  sample_count: number;
  estimate: number | null;
  range: { p50: number | null; p90: number | null } | null;
  basis: string;
  queued_tasks?: number;
  days?: number;
}
export interface TaskAnalytics extends Omit<UsageTotals, 'runs'> {
  runs?: RunUsage[];
  local_runs?: LocalRun[];
  wait_seconds_by_reason?: Record<string, number>;
  phase_seconds?: Record<string, number>;
  provider_active_seconds?: number | null;
  provider_wait_seconds?: number | null;
  time_to_first_edit_seconds?: number | null;
  task_id: string;
  title: string;
  status: string;
  developer_active_seconds: number | null;
  wall_seconds: number | null;
  human_or_external_wait_seconds: number;
  phases: Record<string, number>;
  developer_turns: number;
  compactions: number;
  review_cycles: number;
  validation_failures: number;
  peak_memory_bytes: number | null;
  warnings: string[];
  forecasts: {
    forecast_version: string;
    confidence: string;
    sample_count: number;
    estimate: Record<string, unknown>;
    actuals: Record<string, unknown> | null;
  }[];
}

export interface ForecastMetric {
  estimate: number | null;
  range: { p50: number | null; p90: number | null; p75?: number | null };
  sample_count?: number;
  confidence?: string;
}
export interface LocalRun {
  model: string;
  status: string;
  duration_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  started_at: string;
}
export interface RunUsage {
  id: string;
  model: string;
  harness: string;
  run_kind: string;
  status: string;
  cost: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  cache_read_tokens: number | null;
  cache_write_tokens: number | null;
  reasoning_tokens: number | null;
  started_at: string;
  finished_at: string | null;
  provider_duration_ms: number | null;
}
export interface ForecastAccuracy {
  metrics: Record<
    string,
    {
      sample_count: number;
      median_absolute_percentage_error: number | null;
      p90_coverage: number | null;
      mean_bias: number | null;
    }
  >;
  basis: string;
}
