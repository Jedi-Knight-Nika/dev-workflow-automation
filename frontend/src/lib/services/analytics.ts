import { api } from '$lib/api';
import type { AnalyticsDashboard, CostForecast, TaskAnalytics } from '$lib/types/analytics';
import type { ForecastAccuracy } from '$lib/types/analytics';
export const getForecastAccuracy = () => api<ForecastAccuracy>('/analytics/forecast/accuracy');
export const getAnalytics = (days = 30, teamId?: string) =>
  api<AnalyticsDashboard>(
    `/analytics/ai?days=${days}${teamId ? `&team_id=${encodeURIComponent(teamId)}` : ''}`
  );
export const getTaskAnalytics = (id: string) =>
  api<TaskAnalytics>(`/analytics/tasks/${encodeURIComponent(id)}`);
export const getQueueForecast = (teamId?: string) =>
  api<CostForecast>(
    `/analytics/forecast/queue${teamId ? `?team_id=${encodeURIComponent(teamId)}` : ''}`
  );
export const getPeriodForecast = (days: 7 | 30) =>
  api<CostForecast>(`/analytics/forecast/period?days=${days}`);
