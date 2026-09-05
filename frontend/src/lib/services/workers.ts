import { api } from '$lib/api';
import type { WorkerNode } from '$lib/types';

export function listWorkers(): Promise<WorkerNode[]> {
  return api<WorkerNode[]>('/workers');
}
