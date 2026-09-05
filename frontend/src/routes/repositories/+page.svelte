<script lang="ts">
  import { onMount } from 'svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import Button from '$lib/components/Button.svelte';
  import EmptyState from '$lib/components/EmptyState.svelte';
  import TextField from '$lib/components/TextField.svelte';
  import { repositoriesResource } from '$lib/stores/repositories.svelte';
  import {
    addRepository,
    discoverGithubRepositories,
    queueRepositoryIndex,
    setRepositoryEnabled,
    searchRepositoryKnowledge
  } from '$lib/services/repositories';
  import type { DiscoveredRepository, KnowledgeResult, Repository } from '$lib/types';
  let discovered: DiscoveredRepository[] = [];
  let discovering = false;
  let owner = '';
  let name = '';
  let cloneUrl = '';
  let error = '';
  let query = '';
  let searchingRepository = '';
  let results: KnowledgeResult[] = [];
  const date = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' });
  async function add(event: SubmitEvent) {
    event.preventDefault();
    try {
      await addRepository({
        provider: 'github',
        external_repo_id: `${owner}/${name}`,
        owner,
        name,
        clone_url: cloneUrl,
        default_branch: 'main'
      });
      owner = '';
      name = '';
      cloneUrl = '';
      await repositoriesResource.refresh();
    } catch (cause) {
      error = String(cause);
    }
  }
  async function discover() {
    discovering = true;
    error = '';
    try {
      discovered = await discoverGithubRepositories();
    } catch (cause) {
      error = String(cause);
    } finally {
      discovering = false;
    }
  }
  async function selectRepository(repository: DiscoveredRepository) {
    try {
      await addRepository({
        provider: 'github',
        external_repo_id: repository.external_repo_id,
        owner: repository.owner,
        name: repository.name,
        clone_url: repository.clone_url,
        default_branch: repository.default_branch
      });
      discovered = discovered.filter(
        (item) => item.external_repo_id !== repository.external_repo_id
      );
      await repositoriesResource.refresh();
    } catch (cause) {
      error = String(cause);
    }
  }
  async function queueIndex(repository: Repository) {
    error = '';
    try {
      await queueRepositoryIndex(repository.id);
      await repositoriesResource.refresh();
    } catch (cause) {
      error = String(cause);
    }
  }
  async function toggleRepository(repository: Repository) {
    try {
      await setRepositoryEnabled(repository.id, !repository.enabled);
      await repositoriesResource.refresh();
    } catch (cause) {
      error = String(cause);
    }
  }
  async function search(repository: Repository) {
    if (!query.trim()) return;
    searchingRepository = repository.id;
    error = '';
    try {
      results = await searchRepositoryKnowledge(repository.id, query);
    } catch (cause) {
      error = String(cause);
    }
  }
  onMount(() => {
    repositoriesResource.load();
    const refresh = window.setInterval(() => {
      if (
        repositoriesResource.data.some((repository) =>
          ['QUEUED', 'INDEXING'].includes(repository.index_status)
        )
      ) {
        repositoriesResource.refresh();
      }
    }, 2000);
    return () => window.clearInterval(refresh);
  });
</script>

<PageHeader
  eyebrow="SOURCE CONTROL"
  title="Repositories"
  description="Repositories available to the worker and their knowledge-index status."
/>
<main class="grid gap-6 p-4 sm:p-6 md:p-10 xl:grid-cols-[1fr_360px]">
  <section class="border-line overflow-hidden rounded-xl border">
    <div class="border-line flex flex-wrap items-center justify-between gap-3 border-b p-4">
      <div>
        <strong>GitHub discovery</strong>
        <p class="text-muted text-xs">
          Select a GitHub repository to add it and automatically queue its knowledge index.
        </p>
      </div>
      <Button onclick={discover} disabled={discovering}
        >{discovering ? 'Loading…' : 'Discover'}</Button
      >
    </div>
    {#if discovered.length}<div class="border-brand border-b">
        <p class="bg-panel-alt px-4 py-2 font-mono text-[10px] text-brand">AVAILABLE FROM GITHUB</p>
        {#each discovered as repository, index (repository.external_repo_id)}<div
            class="border-line flex flex-wrap items-center justify-between gap-3 border-t p-3 motion-safe:animate-fade-in-up"
            style="animation-delay: {Math.min(index, 10) * 30}ms"
          >
            <span class="text-sm"
              >{repository.full_name} {repository.private ? '· private' : ''}</span
            >
            <Button variant="primary" onclick={() => selectRepository(repository)}>Select</Button>
          </div>{/each}
      </div>{/if}
    {#each repositoriesResource.data as repository, index (repository.id)}<article
        class="border-line grid gap-4 rounded-xl border p-4 card-hover motion-safe:animate-fade-in-up lg:grid-cols-[1fr_auto]"
        style="animation-delay: {Math.min(index, 10) * 30}ms"
      >
        <div>
          <div class="flex items-center gap-3">
            <strong>{repository.owner}/{repository.name}</strong>
            <span
              class="rounded-full border border-line px-2 py-0.5 font-mono text-[10px] {repository.enabled
                ? 'border-accent/40 text-accent'
                : 'text-muted'}">{repository.enabled ? 'ENABLED' : 'DISABLED'}</span
            >
          </div>
          <p class="text-muted mt-1 text-xs break-all">
            {repository.default_branch} · {repository.clone_url}
          </p>
          <div class="text-muted mt-3 grid gap-1 font-mono text-[10px] sm:grid-cols-2">
            <span>Clone: {repository.clone_status.replaceAll('_', ' ')}</span>
            <span>Chunks: {repository.chunk_count}</span>
            <span>Remote: {repository.latest_sha?.slice(0, 12) || 'not fetched'}</span>
            <span>Indexed: {repository.indexed_sha?.slice(0, 12) || 'never'}</span>
            <span class="sm:col-span-2"
              >Last successful index: {repository.indexed_at
                ? date.format(new Date(repository.indexed_at))
                : 'never'}</span
            >
          </div>
          {#if repository.index_error}<p class="mt-1 max-w-xl text-xs text-danger">
              {repository.index_error}
            </p>{/if}
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <span
            class="font-mono text-[10px] text-muted {['QUEUED', 'INDEXING'].includes(
              repository.index_status
            )
              ? 'motion-safe:animate-pulse'
              : ''}">{repository.index_status.replaceAll('_', ' ')}</span
          >
          <Button size="sm" disabled={!repository.enabled} onclick={() => queueIndex(repository)}
            >Index</Button
          >
          <Button
            size="sm"
            disabled={repository.index_status !== 'READY'}
            onclick={() => {
              searchingRepository = repository.id;
              results = [];
            }}>Search</Button
          >
          <Button size="sm" onclick={() => toggleRepository(repository)}
            >{repository.enabled ? 'Disable' : 'Enable + index'}</Button
          >
        </div>
      </article>{:else}<EmptyState message="No repositories selected." />{/each}
    {#if searchingRepository}<form
        class="border-line border-t p-4"
        onsubmit={(event) => {
          event.preventDefault();
          const repository = repositoriesResource.data.find(
            (item) => item.id === searchingRepository
          );
          if (repository) search(repository);
        }}
      >
        <div class="flex flex-col gap-2 sm:flex-row">
          <TextField bind:value={query} placeholder="Semantic repository search" />
          <Button variant="primary" type="submit" class="sm:w-auto">Search</Button>
        </div>
        {#each results as result (`${result.file_path}-${result.chunk_index}`)}<article
            class="border-line mt-3 rounded-lg border p-3"
          >
            <div class="flex justify-between gap-3 text-xs">
              <strong>{result.file_path}</strong><span>{result.score.toFixed(3)}</span>
            </div>
            <pre
              class="text-muted mt-2 max-h-40 overflow-auto text-xs whitespace-pre-wrap">{result.content}</pre>
          </article>{/each}
      </form>{/if}
  </section>
  <form class="border-line bg-panel h-fit rounded-xl border p-5" onsubmit={add}>
    <h2 class="mb-4 font-semibold">Add repository</h2>
    {#if error || repositoriesResource.error}<p class="mb-3 text-xs text-danger">
        {error || repositoriesResource.error}
      </p>{/if}
    <div class="mb-2.5 space-y-2.5">
      <TextField bind:value={owner} placeholder="Owner" required />
      <TextField bind:value={name} placeholder="Repository name" required />
      <TextField bind:value={cloneUrl} placeholder="Clone URL" required />
    </div>
    <Button variant="primary" size="lg" type="submit" class="w-full">Add repository</Button>
  </form>
</main>
