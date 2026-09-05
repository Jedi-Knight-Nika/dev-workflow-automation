import { api } from '$lib/api';
import type { DashboardActivity } from '$lib/types';

export function getDashboardActivity(): Promise<DashboardActivity> {
  return api<DashboardActivity>('/activity');
}
