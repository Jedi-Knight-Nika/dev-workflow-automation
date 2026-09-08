import { api } from '$lib/api';
import type {
  Availability,
  InfrastructureEvent,
  Incident,
  LiveMetrics,
  MetricResult,
  MonitoringSettings,
  RunnerResource
} from '$lib/types/observability';
export const getLiveMetrics = (signal?: AbortSignal) =>
  api<LiveMetrics>('/observability/live', { signal });
export const getServiceHistory = (service: string, metric: string, hours = 1) => {
  const end = new Date(),
    start = new Date(end.getTime() - hours * 3600000);
  return api<MetricResult>(
    `/observability/services/${encodeURIComponent(service)}/history?metric=${encodeURIComponent(metric)}&from=${start.toISOString()}&to=${end.toISOString()}&step=${Math.max(10, Math.ceil((hours * 3600) / 2000))}`
  );
};
export const getMonitoringSettings = () => api<MonitoringSettings>('/observability/settings');
export const getIncidents = () => api<Incident[]>('/observability/incidents');
export const getAvailability = (days = 30) =>
  api<Availability>(`/observability/availability?days=${days}`);
export const getTaskResources = (id: string) =>
  api<{ runners: RunnerResource[]; events: InfrastructureEvent[] }>(
    `/observability/tasks/${encodeURIComponent(id)}/resources`
  );
export const getRunnerHistory = (id: string, metric: 'memory' | 'cpu') =>
  api<MetricResult>(`/observability/runners/${encodeURIComponent(id)}/history?metric=${metric}`);
