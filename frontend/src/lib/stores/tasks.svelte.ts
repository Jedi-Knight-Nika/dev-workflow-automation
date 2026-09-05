import { createResource } from './resource.svelte';
import { listTasks } from '$lib/services/tasks';
import type { Task } from '$lib/types';

export const tasksResource = createResource<Task[]>(listTasks, []);
