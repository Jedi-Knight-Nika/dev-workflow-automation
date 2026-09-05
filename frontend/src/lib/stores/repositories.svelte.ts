import { createResource } from './resource.svelte';
import { listRepositories } from '$lib/services/repositories';
import type { Repository } from '$lib/types';

export const repositoriesResource = createResource<Repository[]>(listRepositories, []);
