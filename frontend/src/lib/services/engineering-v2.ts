import { api } from '$lib/api';

export type RoleKind = 'INTERPRETER' | 'DEVELOPER' | 'THINKER' | 'REVIEWER';
export type AgentProfile = {
  id: string;
  team_id: string;
  version: number;
  role_kind: RoleKind;
  display_name: string;
  avatar: string;
  enabled: boolean;
  provider: string;
  model: string;
  harness: string | null;
  effort: string;
  supplemental_instructions: string;
  prompt_version: string;
  soft_budget_usd: string | number | null;
  hard_budget_usd: string | number | null;
};
export type EngineeringTask = {
  id: string;
  title: string;
  priority: number;
  execution_version: number;
  legacy_state: string;
  status: string | null;
  stage: string | null;
  wait_reason: string | null;
  requirement_version: number;
  pull_request_url: string | null;
};
export type TeamActivity = {
  team_id: string;
  team_name: string;
  enabled: boolean;
  tasks: EngineeringTask[];
  milestones: {
    id: string;
    task_id: string;
    stage: string;
    status: string;
    actor: string;
    started_at: string;
    finished_at: string | null;
  }[];
};
export const STAGES = [
  'INTAKE',
  'PLANNING',
  'DEVELOPING',
  'VALIDATING',
  'PUBLISHING',
  'REVIEWING',
  'FIXING',
  'MERGING',
  'COMPLETE'
] as const;
export const listProfiles = (id: string) => api<AgentProfile[]>(`/v2/teams/${id}/profiles`);
export const initializeProfiles = (id: string) =>
  api<AgentProfile[]>(`/v2/teams/${id}/profiles/initialize`, { method: 'POST' });
export function profileInput(profile: AgentProfile) {
  return {
    version: profile.version,
    display_name: profile.display_name,
    avatar: profile.avatar,
    enabled: profile.enabled,
    provider: profile.provider,
    model: profile.model,
    harness: profile.harness,
    effort: profile.effort,
    supplemental_instructions: profile.supplemental_instructions,
    soft_budget_usd: profile.soft_budget_usd,
    hard_budget_usd: profile.hard_budget_usd
  };
}
export const saveProfile = (profile: AgentProfile) =>
  api<AgentProfile>(`/v2/teams/${profile.team_id}/profiles/${profile.role_kind}`, {
    method: 'PUT',
    body: JSON.stringify(profileInput(profile))
  });
export const getTeamActivity = (id: string) => api<TeamActivity>(`/v2/teams/${id}/activity`);

export type AutomationPolicy = {
  version: number;
  enrollment_enabled: boolean;
  auto_merge: boolean;
  repository_ids: string[];
  authorized_reviewer_ids: string[];
  required_checks: string[];
  task_budget_usd: string | number;
  team_budget_usd: string | number;
  require_formal_approval: boolean;
};
export const getAutomation = (id: string) => api<AutomationPolicy>(`/v2/teams/${id}/automation`);
export const saveAutomation = (id: string, policy: AutomationPolicy) =>
  api<{ version: number }>(`/v2/teams/${id}/automation`, {
    method: 'PUT',
    body: JSON.stringify(policy)
  });
export const enrollTask = (id: string) =>
  api<{ status: string }>(`/v2/tasks/${id}/enroll`, { method: 'POST' });

export type SessionChangeMode = 'keep_native' | 'handoff';
export type DeveloperSessionView = {
  session_id: string;
  generation: number;
  has_native_session: boolean;
  harness: string;
  provider: string;
  model: string;
  state: string;
  task_status: string;
  lifecycle_version: number;
  profile_version: number;
  target_harness: string;
  target_provider: string;
  target_model: string;
  keep_native_available: boolean;
  blocker: string | null;
};
export const getDeveloperSession = (id: string) =>
  api<DeveloperSessionView | null>(`/v2/tasks/${id}/session`);

export function sessionChangeInput(
  session: DeveloperSessionView,
  mode: SessionChangeMode,
  reason: string
) {
  return {
    session_id: session.session_id,
    lifecycle_version: session.lifecycle_version,
    profile_version: session.profile_version,
    mode,
    reason
  };
}

export const changeDeveloperSession = (
  id: string,
  session: DeveloperSessionView,
  mode: SessionChangeMode,
  reason: string
) =>
  api<DeveloperSessionView>(`/v2/tasks/${id}/session/change`, {
    method: 'POST',
    body: JSON.stringify(sessionChangeInput(session, mode, reason))
  });

export type V2Statistics = {
  scope: string;
  days: number;
  cloud_runs: {
    role: string;
    provider: string;
    model: string;
    attempts: number;
    input_tokens: number | null;
    output_tokens: number | null;
    cost_usd: string | null;
    incomplete_usage_runs: number;
    provider_time_ms: number | null;
    compactions: number;
  }[];
  local_runs: { model: string; attempts: number; duration_ms: number; failed: number }[];
  phases: {
    stage: string;
    status: string;
    count: number;
    finished_duration_seconds: number | null;
  }[];
};
export const getV2Statistics = (teamId?: string) =>
  api<V2Statistics>(
    `/v2/statistics?days=30${teamId ? `&team_id=${encodeURIComponent(teamId)}` : ''}`
  );
