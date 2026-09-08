export interface ObserverConfiguration {
  enabled: boolean;
  display_name: string;
  local_ai_enabled: boolean;
  model: string;
  memory_reserve_mb: number;
}

export type ObserverScope = {
  page: 'DASHBOARD' | 'TASK' | 'TEAM';
  task_id?: string;
  team_id?: string;
};
export type OrbMode =
  'idle' | 'sleeping' | 'thinking' | 'speaking' | 'warning' | 'critical' | 'offline';
export type FocusMode = 'normal' | 'warnings-only' | 'critical-only' | 'silent';
export interface Evidence {
  key: string;
  text: string;
  source: string;
  measured_at: string | null;
  complete: boolean;
}
export interface AttentionEvent {
  id: string;
  kind: string;
  severity: 'INFO' | 'WARNING' | 'CRITICAL';
  status: 'OPEN' | 'ACKNOWLEDGED' | 'SNOOZED' | 'RESOLVED';
  title: string;
  source: string;
  task_id: string | null;
  team_id: string | null;
  detected_at: string;
  last_seen_at: string;
  notified_at: string | null;
  resolved_at: string | null;
  snoozed_until: string | null;
}
export interface ObserverStatus {
  enabled: boolean;
  ai_available: boolean;
  mode: 'IDLE' | 'SLEEPING';
  highest_severity: 'NONE' | 'WARNING' | 'CRITICAL';
  open_attention_count: number;
  partial_sources: string[];
  reason: string | null;
  sampled_at: string;
  events: AttentionEvent[];
}
export interface Briefing extends ObserverStatus {
  message: string;
  sources: Evidence[];
  changes: Evidence[];
  preferences: { focus: FocusMode; last_seen_at: string | null };
  suggested_questions: string[];
}
export interface ObserverMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources: Evidence[];
}
export interface Conversation {
  id: string;
  title: string;
  scope: ObserverScope;
  updated_at: string;
}
export interface ObserverStreamEvent {
  type: string;
  text?: string;
  tool?: string;
  message?: string;
  answer?: string;
  sources?: Evidence[];
  mode?: 'deterministic' | 'local';
  reason?: string;
}
