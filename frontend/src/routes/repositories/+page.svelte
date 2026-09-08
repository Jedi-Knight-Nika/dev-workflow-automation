<script lang="ts">
  import { onMount } from 'svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import ErrorBanner from '$lib/components/ErrorBanner.svelte';
  import {
    listRepositories,
    discoverGithubRepositories,
    importRepositories,
    setRepositoryEnabled,
    setRepositoryArchived,
    deleteRepository,
    getRepositoryDependencies
  } from '$lib/services/repositories';
  import type { Repository, DiscoveredRepository } from '$lib/types';
  let rows = $state<Repository[]>([]),
    discovered = $state<DiscoveredRepository[]>([]);
  let selected = $state<string[]>([]),
    loading = $state(true),
    busy = $state(false),
    error = $state('');
  let includeArchived = $state(false);
  async function refresh() {
    try {
      rows = await listRepositories(includeArchived);
    } catch (cause) {
      error = String(cause);
    } finally {
      loading = false;
    }
  }
  async function perform(action: () => Promise<unknown>) {
    busy = true;
    error = '';
    try {
      await action();
      await refresh();
    } catch (cause) {
      error = String(cause);
    } finally {
      busy = false;
    }
  }
  async function discover() {
    await perform(async () => {
      discovered = await discoverGithubRepositories();
      selected = [];
    });
  }
  async function importSelected() {
    await perform(async () => {
      await importRepositories(
        discovered
          .filter((repo) => selected.includes(repo.external_repo_id))
          .map((repo) => ({ ...repo, provider: 'github' }))
      );
      discovered = [];
      selected = [];
    });
  }
  async function remove(repo: Repository) {
    await perform(async () => {
      const dependencies = await getRepositoryDependencies(repo.id);
      if (dependencies.teams.length || dependencies.active_tasks || dependencies.active_workspaces)
        throw new Error(
          'Unassign Teams and finish or archive dependent tasks before deleting this repository.'
        );
      if (
        confirm(
          'Delete the repository registration for ' +
            repo.owner +
            '/' +
            repo.name +
            '? This does not delete the remote repository.'
        )
      )
        await deleteRepository(repo.id);
    });
  }
  onMount(() => {
    void refresh();
  });
</script>

<PageHeader
  eyebrow="Resources"
  title="Repositories"
  description="Register source repositories and assign them to Teams. Native sessions read their isolated checkout directly."
/>
<main class="space-y-5 p-4 sm:p-6 md:p-10">
  {#if error}<ErrorBanner message={error} />{/if}
  <div class="flex flex-wrap items-center gap-4">
    <button class="btn-primary" disabled={busy} onclick={() => void discover()}
      >Import from GitHub</button
    >
    <button class="btn-secondary" disabled={busy} onclick={() => void refresh()}>Refresh</button>
    <label class="flex items-center gap-2"
      ><input
        type="checkbox"
        bind:checked={includeArchived}
        onchange={() => void refresh()}
      />Include archived</label
    >
  </div>
  <p class="text-muted text-sm">
    New task workspaces start from the repository's current default branch. An existing task keeps
    its branch and native session. No repository indexing or embedding requests are required.
  </p>
  {#if discovered.length}
    <section class="border-line space-y-3 rounded-xl border p-5">
      <h2 class="font-semibold">Available GitHub repositories</h2>
      {#each discovered as repo (repo.external_repo_id)}
        <label class="flex gap-2"
          ><input
            type="checkbox"
            value={repo.external_repo_id}
            bind:group={selected}
            disabled={rows.some((row) => row.external_repo_id === repo.external_repo_id)}
          />{repo.full_name}{repo.private ? ' · private' : ''}</label
        >
      {/each}
      <button
        class="btn-primary"
        disabled={busy || !selected.length}
        onclick={() => void importSelected()}>Import selected ({selected.length})</button
      >
      <button
        class="btn-secondary"
        disabled={busy}
        onclick={() => {
          discovered = [];
        }}>Cancel</button
      >
    </section>
  {/if}
  {#if loading}<p>Loading repositories…</p>{:else if !rows.length}<p class="text-muted">
      No repositories registered.
    </p>{/if}
  <div class="grid gap-4 lg:grid-cols-2">
    {#each rows as repo (repo.id)}
      <section class="border-line space-y-3 rounded-xl border bg-panel p-5">
        <h2 class="font-semibold">{repo.owner}/{repo.name}</h2>
        <p class="text-muted text-sm">
          {repo.default_branch} · {repo.archived_at
            ? 'Archived'
            : repo.enabled
              ? 'Enabled'
              : 'Disabled'}
        </p>
        <p class="text-sm">
          {repo.teams_count} Teams · {repo.active_tasks_count} active tasks · {repo.active_workspaces_count}
          workspaces
        </p>
        <div class="flex flex-wrap gap-2">
          <button
            class="btn-secondary"
            disabled={busy || !!repo.archived_at}
            onclick={() => void perform(() => setRepositoryEnabled(repo.id, !repo.enabled))}
            >{repo.enabled ? 'Disable new work' : 'Enable'}</button
          >
          <button
            class="btn-secondary"
            disabled={busy}
            onclick={() => void perform(() => setRepositoryArchived(repo.id, !repo.archived_at))}
            >{repo.archived_at ? 'Restore' : 'Archive'}</button
          >
          <button
            class="btn-secondary text-danger"
            disabled={busy}
            onclick={() => void remove(repo)}>Delete registration</button
          >
        </div>
      </section>
    {/each}
  </div>
</main>
