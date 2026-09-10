import { api } from '$lib/api';
import type { DashboardSnapshot, HostTelemetry } from '$lib/types';

export function getDashboardSummary(period: 'today' | '7d' | '30d' = 'today') {
  return api<DashboardSnapshot>(`/dashboard/summary?period=${period}`);
}

export function getDashboardTelemetry() {
  return api<HostTelemetry>('/dashboard/telemetry');
}
