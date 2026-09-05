<script lang="ts">
  import { onMount } from 'svelte';
  import PageHeader from '$lib/PageHeader.svelte';
  import { api } from '$lib/api';
  import type { DiscoveredRepository, KnowledgeResult, Repository } from '$lib/types';
  let repositories: Repository[] = [];
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
  async function load() {
    repositories = await api<Repository[]>('/repositories');
  }
  async function add(event: SubmitEvent) {
    event.preventDefault();
    try {
      await api('/repositories', {
        method: 'POST',
        body: JSON.stringify({
          provider: 'github',
          external_repo_id: `${owner}/${name}`,
          owner,
          name,
          clone_url: cloneUrl,
          default_branch: 'main'
        })
      });
      owner = '';
      name = '';
      cloneUrl = '';
      await load();
    } catch (cause) {
      error = String(cause);
    }
  }
  async function discover() {
    discovering = true;
    error = '';
    try {
      discovered = await api<DiscoveredRepository[]>('/github/repositories');
    } catch (cause) {
      error = String(cause);
    } finally {
      discovering = false;
    }
  }
  async function selectRepository(repository: DiscoveredRepository) {
    try {
      await api('/repositories', {
        method: 'POST',
        body: JSON.stringify({
          provider: 'github',
          external_repo_id: repository.external_repo_id,
          owner: repository.owner,
          name: repository.name,
          clone_url: repository.clone_url,
          default_branch: repository.default_branch
        })
      });
      discovered = discovered.filter(
        (item) => item.external_repo_id !== repository.external_repo_id
      );
      await load();
    } catch (cause) {
      error = String(cause);
    }
  }
  async function queueIndex(repository: Repository) {
    error = '';
    try {
      await api(`/repositories/${repository.id}/index`, { method: 'POST' });
      await load();
    } catch (cause) {
      error = String(cause);
    }
  }
  async function toggleRepository(repository: Repository) {
    try {
      await api(`/repositories/${repository.id}/enabled?enabled=${!repository.enabled}`, {
        method: 'PATCH'
      });
      await load();
    } catch (cause) {
      error = String(cause);
    }
  }
  async function search(repository: Repository) {
    if (!query.trim()) return;
    searchingRepository = repository.id;
    error = '';
    try {
      results = await api<KnowledgeResult[]>(
        `/repositories/${repository.id}/search?query=${encodeURIComponent(query)}`
      );
    } catch (cause) {
      error = String(cause);
    }
  }
  onMount(() => {
    load().catch((cause) => {
      error = String(cause);
    });
    const refresh = window.setInterval(() => {
      if (
        repositories.some((repository) => ['QUEUED', 'INDEXING'].includes(repository.index_status))
      ) {
        load().catch((cause) => {
          error = String(cause);
        });
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
<main class="grid gap-6 p-6 md:p-10 xl:grid-cols-[1fr_360px]">
  <section class="border-line border">
    <div class="border-line flex items-center justify-between border-b p-4">
      <div>
        <strong>GitHub discovery</strong>
        <p class="text-muted text-xs">
          Select a GitHub repository to add it and automatically queue its knowledge index.
        </p>
      </div>
      <button class="border-line border px-3 py-2 text-xs" onclick={discover} disabled={discovering}
        >{discovering ? 'Loading…' : 'Discover'}</button
      >
    </div>
    {#if discovered.length}<div class="border-accent border-b">
        <p class="bg-[#102218] px-4 py-2 font-mono text-[10px] text-accent">
          AVAILABLE FROM GITHUB
        </p>
        {#each discovered as repository (repository.external_repo_id)}<div
            class="border-line flex items-center justify-between border-t p-3"
          >
            <span class="text-sm"
              >{repository.full_name} {repository.private ? '· private' : ''}</span
            ><button
              class="bg-accent px-3 py-1.5 text-xs font-bold text-[#07100a]"
              onclick={() => selectRepository(repository)}>Select</button
            >
          </div>{/each}
      </div>{/if}
    {#each repositories as repository (repository.id)}<article
        class="border-line grid gap-4 border-b p-4 lg:grid-cols-[1fr_auto]"
      >
        <div>
          <div class="flex items-center gap-3">
            <strong>{repository.owner}/{repository.name}</strong>
            <span class="font-mono text-[10px] {repository.enabled ? 'text-accent' : 'text-muted'}"
              >{repository.enabled ? 'ENABLED' : 'DISABLED'}</span
            >
          </div>
          <p class="text-muted mt-1 text-xs">
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
          {#if repository.index_error}<p class="mt-1 max-w-xl text-xs text-red-300">
              {repository.index_error}
            </p>{/if}
        </div>
        <div class="flex items-center gap-2">
          <span class="font-mono text-[10px] text-[#a4afa7]"
            >{repository.index_status.replaceAll('_', ' ')}</span
          >
          <button
            class="border-line border px-2 py-1 text-xs"
            disabled={!repository.enabled}
            onclick={() => queueIndex(repository)}>Index</button
          >
          <button
            class="border-line border px-2 py-1 text-xs disabled:opacity-30"
            disabled={repository.index_status !== 'READY'}
            onclick={() => {
              searchingRepository = repository.id;
              results = [];
            }}>Search</button
          >
          <button
            class="border-line border px-2 py-1 text-xs"
            onclick={() => toggleRepository(repository)}
            >{repository.enabled ? 'Disable' : 'Enable + index'}</button
          >
        </div>
      </article>{:else}<p class="text-muted p-8 text-center">No repositories selected.</p>{/each}
    {#if searchingRepository}<form
        class="border-line border-t p-4"
        onsubmit={(event) => {
          event.preventDefault();
          const repository = repositories.find((item) => item.id === searchingRepository);
          if (repository) search(repository);
        }}
      >
        <div class="flex gap-2">
          <input
            class="border-line w-full border bg-[#090c0a] p-3 outline-none focus:border-accent"
            bind:value={query}
            placeholder="Semantic repository search"
          />
          <button class="bg-accent cursor-pointer px-5 font-bold text-[#07100a]" type="submit"
            >Search</button
          >
        </div>
        {#each results as result (`${result.file_path}-${result.chunk_index}`)}<article
            class="border-line mt-3 border p-3"
          >
            <div class="flex justify-between gap-3 text-xs">
              <strong>{result.file_path}</strong><span>{result.score.toFixed(3)}</span>
            </div>
            <pre
              class="text-muted mt-2 max-h-40 overflow-auto text-xs whitespace-pre-wrap">{result.content}</pre>
          </article>{/each}
      </form>{/if}
  </section>
  <form class="border-line bg-panel h-fit border p-5" onsubmit={add}>
    <h2 class="mb-4 font-semibold">Add repository</h2>
    {#if error}<p class="mb-3 text-xs text-red-300">{error}</p>{/if}<input
      class="border-line mb-2.5 w-full border bg-[#090c0a] p-3 outline-none focus:border-accent"
      bind:value={owner}
      placeholder="Owner"
      required
    /><input
      class="border-line mb-2.5 w-full border bg-[#090c0a] p-3 outline-none focus:border-accent"
      bind:value={name}
      placeholder="Repository name"
      required
    /><input
      class="border-line mb-2.5 w-full border bg-[#090c0a] p-3 outline-none focus:border-accent"
      bind:value={cloneUrl}
      placeholder="Clone URL"
      required
    /><button class="bg-accent w-full cursor-pointer p-3 font-bold text-[#07100a]" type="submit"
      >Add repository</button
    >
  </form>
</main>
