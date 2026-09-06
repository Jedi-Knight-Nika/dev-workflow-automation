<script lang="ts">
  import { onMount } from 'svelte';
  import { resolve } from '$app/paths';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import Button from '$lib/components/Button.svelte';
  import EmptyState from '$lib/components/EmptyState.svelte';
  import TextField from '$lib/components/TextField.svelte';
  import Skeleton from '$lib/components/Skeleton.svelte';
  import Spinner from '$lib/components/Spinner.svelte';
  import { repositoriesResource } from '$lib/stores/repositories.svelte';
  import { integrationsResource } from '$lib/stores/integrations.svelte';
  import { getGithubAppManageUrl, getGithubInstallationAccount } from '$lib/services/integrations';
  import {
    addRepository,
    deleteRepository,
    discoverGithubRepositories,
    getRepositoryDependencies,
    importRepositories,
    listRepositories,
    queueRepositoryIndex,
    setRepositoryArchived,
    setRepositoryEnabled,
    searchRepositoryKnowledge
  } from '$lib/services/repositories';
  import { t } from '$lib/i18n/index.svelte';
  import ResourceDetailDrawer from '$lib/components/resources/ResourceDetailDrawer.svelte';
  import ResourceStatus, {
    type ResourceState
  } from '$lib/components/resources/ResourceStatus.svelte';
  import type { RepositoryDependencies } from '$lib/services/repositories';
  import type {
    DiscoveredRepository,
    GitHubInstallationAccount,
    KnowledgeResult,
    Repository
  } from '$lib/types';
  let discovered: DiscoveredRepository[] = [];
  let discovering = false;
  let discoveryCompleted = false;
  let owner = '';
  let name = '';
  let cloneUrl = '';
  let error = '';
  let query = '';
  let searchingRepository = '';
  let results: KnowledgeResult[] = [];
  let showManualForm = false;
  let githubAccount: GitHubInstallationAccount | null = null;
  let selectedRepositoryIds: string[] = [];
  let prepareKnowledge = true;
  let selectedRepository: Repository | null = null;
  let dependencies: RepositoryDependencies | null = null;
  let showArchived = false;
  let archivedRepositories: Repository[] = [];
  const date = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' });
  const githubConnected = () =>
    integrationsResource.data.some(
      (integration) => integration.provider_name === 'github' && integration.status === 'CONNECTED'
    );
  const imported = (repository: DiscoveredRepository) =>
    repositoriesResource.data.some(
      (item) => item.provider === 'github' && item.external_repo_id === repository.external_repo_id
    );
  function knowledgeDescription(repository: Repository) {
    if (repository.index_status === 'READY') {
      return t('repositories.knowledgeChunksSearchable', { count: repository.chunk_count });
    }
    if (['QUEUED', 'INDEXING'].includes(repository.index_status)) {
      return t('repositories.beingClonedChunkedEmbedded');
    }
    if (repository.index_status === 'FAILED')
      return repository.index_error || t('repositories.embeddingFailed');
    return t('repositories.createIndexBeforeAssigning');
  }
  function resourceState(value: string): ResourceState {
    if (value === 'READY') return 'READY';
    if (['UPDATING', 'INDEXING', 'QUEUED'].includes(value)) return 'WORKING';
    if (['FAILED', 'CANNOT_FETCH', 'OUT_OF_DATE'].includes(value)) return 'NEEDS_ATTENTION';
    if (value === 'DISABLED') return 'DISABLED';
    return 'NOT_CONFIGURED';
  }
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
      discoveryCompleted = true;
    } catch (cause) {
      error = String(cause);
    } finally {
      discovering = false;
    }
  }
  async function manageGithubAccess() {
    error = '';
    try {
      const result = await getGithubAppManageUrl();
      window.location.assign(result.url);
    } catch (cause) {
      error = String(cause);
    }
  }
  async function loadGithubAccount() {
    try {
      githubAccount = await getGithubInstallationAccount();
    } catch {
      githubAccount = null;
    }
  }
  function toggleDiscovered(id: string, checked: boolean) {
    selectedRepositoryIds = checked
      ? Array.from(new Set([...selectedRepositoryIds, id]))
      : selectedRepositoryIds.filter((value) => value !== id);
  }
  async function importSelected() {
    const selection = discovered.filter((item) =>
      selectedRepositoryIds.includes(item.external_repo_id)
    );
    if (!selection.length) return;
    error = '';
    try {
      await importRepositories(
        selection.map((repository) => ({
          provider: 'github',
          external_repo_id: repository.external_repo_id,
          owner: repository.owner,
          name: repository.name,
          clone_url: repository.clone_url,
          default_branch: repository.default_branch
        })),
        prepareKnowledge
      );
      discovered = discovered.filter(
        (item) => !selectedRepositoryIds.includes(item.external_repo_id)
      );
      selectedRepositoryIds = [];
      await repositoriesResource.refresh();
    } catch (cause) {
      error = String(cause);
    }
  }
  async function openRepository(repository: Repository) {
    selectedRepository = repository;
    dependencies = null;
    try {
      dependencies = await getRepositoryDependencies(repository.id);
    } catch (cause) {
      error = String(cause);
    }
  }
  async function archiveRepository(repository: Repository, archived: boolean) {
    error = '';
    try {
      await setRepositoryArchived(repository.id, archived);
      selectedRepository = null;
      await repositoriesResource.refresh();
      if (showArchived) archivedRepositories = await listRepositories(true);
    } catch (cause) {
      error = String(cause);
    }
  }
  async function toggleArchivedView() {
    showArchived = !showArchived;
    if (showArchived) archivedRepositories = await listRepositories(true);
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
  async function removeRepository(repository: Repository) {
    const usage = dependencies || (await getRepositoryDependencies(repository.id));
    if (
      !window.confirm(
        `${t('repositories.confirmRemove', { name: `${repository.owner}/${repository.name}` })}\n\nUsed by ${usage.teams.length} teams, ${usage.active_tasks} active tasks, ${usage.active_workspaces} workspaces, and ${usage.task_sources.length} task sources.`
      )
    ) {
      return;
    }
    error = '';
    try {
      await deleteRepository(repository.id);
      if (searchingRepository === repository.id) searchingRepository = '';
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
    integrationsResource.load();
    repositoriesResource.load();
    loadGithubAccount();
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
  eyebrow={t('repositories.eyebrow')}
  title={t('repositories.newTitle')}
  description={t('repositories.newDescription')}
/>
<main class="space-y-6 p-4 sm:p-6 md:p-10">
  {#if repositoriesResource.data.length === 0}<section class="grid gap-3 md:grid-cols-3">
      <article class="border-line bg-panel rounded-xl border p-4">
        <p class="font-mono text-[10px] text-brand">{t('repositories.step1Eyebrow')}</p>
        <strong class="mt-2 block">{t('repositories.connectGithub')}</strong>
        <p class="text-muted mt-1 text-xs">
          {t('repositories.connectGithubDescription')}
        </p>
        <div class="mt-4 flex items-center justify-between gap-2">
          <span class="flex items-center gap-2">
            {#if githubAccount}<img
                class="h-6 w-6 rounded-full"
                src={githubAccount.avatar_url}
                alt=""
              />{/if}
            <span
              class="font-mono text-[10px] {githubConnected() ? 'text-accent' : 'text-warning'}"
            >
              {githubAccount
                ? `@${githubAccount.login}`
                : githubConnected()
                  ? t('repositories.connected')
                  : t('repositories.notConnected')}
            </span>
          </span>
          <a
            class="border-line rounded-lg border px-3 py-2 text-xs hover:border-brand hover:text-brand"
            href={resolve('/integrations')}
          >
            {githubConnected()
              ? t('repositories.manageConnection')
              : t('repositories.connectGithub')}
          </a>
        </div>
      </article>
      <article
        class="border-line bg-panel rounded-xl border p-4 {githubConnected() ? '' : 'opacity-50'}"
      >
        <p class="font-mono text-[10px] text-brand">{t('repositories.step2Eyebrow')}</p>
        <strong class="mt-2 block">{t('repositories.chooseRepositories')}</strong>
        <p class="text-muted mt-1 text-xs">{t('repositories.onlyImportedCanBeUsed')}</p>
        <p class="mt-4 font-mono text-[10px]">
          {t('repositories.selectedCount', { count: repositoriesResource.data.length })}
        </p>
      </article>
      <article class="border-line bg-panel rounded-xl border p-4">
        <p class="font-mono text-[10px] text-brand">{t('repositories.step3Eyebrow')}</p>
        <strong class="mt-2 block">{t('repositories.buildAiKnowledge')}</strong>
        <p class="text-muted mt-1 text-xs">
          {t('repositories.importingAutomaticallyClones')}
        </p>
        <p class="mt-4 font-mono text-[10px] text-accent">
          {t('repositories.aiReadyCount', {
            count: repositoriesResource.data.filter(
              (repository) => repository.index_status === 'READY'
            ).length
          })}
        </p>
      </article>
    </section>
  {:else}
    <section
      class="border-line bg-panel flex flex-wrap items-center justify-between gap-4 rounded-xl border p-4"
    >
      <div>
        <strong>{repositoriesResource.data.length} repositories</strong>
        <p class="text-muted mt-1 text-xs">
          {repositoriesResource.data.filter((item) => item.knowledge_status === 'READY').length} AI Ready
          ·
          {repositoriesResource.data.filter((item) => item.knowledge_status === 'INDEXING').length} indexing
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <span class="text-muted text-xs">
          GitHub · {githubAccount ? `@${githubAccount.login}` : 'not connected'}
        </span>
        <a
          class="border-line rounded-lg border px-3 py-2 text-xs hover:text-brand"
          href={resolve('/integrations')}>Manage GitHub</a
        >
        <Button variant="primary" onclick={discover} disabled={discovering || !githubConnected()}
          >+ Add Repository</Button
        >
        <Button size="sm" onclick={toggleArchivedView}
          >{showArchived ? 'Hide archived' : 'Show archived'}</Button
        >
      </div>
    </section>
  {/if}

  {#if error || repositoriesResource.error || integrationsResource.error}
    <p
      class="border-danger/40 bg-danger/5 overflow-hidden rounded-lg border p-3 text-xs break-words text-danger"
    >
      {error || repositoriesResource.error || integrationsResource.error}
    </p>
  {/if}

  <section class="border-line overflow-hidden rounded-xl border">
    <div class="border-line flex flex-wrap items-center justify-between gap-3 border-b p-4">
      <div>
        <strong>{t('repositories.selectFromGithub')}</strong>
        <p class="text-muted text-xs">
          {t('repositories.importingGrantsAccess')}
        </p>
      </div>
      <Button variant="primary" onclick={discover} disabled={discovering || !githubConnected()}>
        <span class="flex items-center gap-2">
          {#if discovering}<Spinner class="size-3.5" />{/if}
          {discovering ? t('common.loading') : t('repositories.chooseRepositoriesButton')}
        </span>
      </Button>
    </div>
    {#if !githubConnected()}
      <div class="bg-panel-alt p-5 text-center">
        <p class="text-sm">{t('repositories.connectGithubBeforeChoosing')}</p>
        <a
          class="mt-3 inline-block text-xs text-brand hover:underline"
          href={resolve('/integrations')}>{t('repositories.goToGithubConnection')}</a
        >
      </div>
    {/if}
    {#if githubConnected() && discoveryCompleted && discovered.length === 0}
      <div class="bg-panel-alt border-line border-b p-5 text-center">
        <strong class="text-sm">{t('repositories.noReposGrantedTitle')}</strong>
        <p class="text-muted mx-auto mt-1 max-w-xl text-xs">
          {t('repositories.noReposGrantedDescription')}
        </p>
        <Button class="mt-3" variant="primary" onclick={manageGithubAccess}>
          {t('repositories.manageRepositoryAccess')}
        </Button>
      </div>
    {/if}
    {#if discovered.length}<div class="border-brand border-b">
        <p class="bg-panel-alt px-4 py-2 font-mono text-[10px] text-brand">
          {t('repositories.availableFromGithub')}
        </p>
        {#each discovered as repository, index (repository.external_repo_id)}<div
            class="border-line flex flex-wrap items-center justify-between gap-3 border-t p-3 motion-safe:animate-fade-in-up"
            style="animation-delay: {Math.min(index, 10) * 30}ms"
          >
            <label class="flex items-center gap-3 text-sm">
              <input
                type="checkbox"
                checked={selectedRepositoryIds.includes(repository.external_repo_id)}
                disabled={imported(repository)}
                onchange={(event) =>
                  toggleDiscovered(repository.external_repo_id, event.currentTarget.checked)}
              />
              {repository.full_name}
              {repository.private ? '· private' : ''}
            </label>
            {#if imported(repository)}
              <span class="font-mono text-[10px] text-accent">{t('repositories.imported')}</span>
            {:else}
              <span class="text-muted text-[10px]">Available</span>
            {/if}
          </div>{/each}
        <div class="border-line flex flex-wrap items-center justify-between gap-3 border-t p-4">
          <label class="flex items-center gap-2 text-xs">
            <input type="checkbox" bind:checked={prepareKnowledge} /> Prepare AI Knowledge
          </label>
          <Button
            variant="primary"
            disabled={!selectedRepositoryIds.length}
            onclick={importSelected}>Import {selectedRepositoryIds.length} selected</Button
          >
        </div>
      </div>{/if}
    {#if repositoriesResource.loading && repositoriesResource.data.length === 0}
      <div class="grid gap-4 p-4" aria-busy="true">
        <!-- eslint-disable-next-line @typescript-eslint/no-unused-vars -->
        {#each Array(3) as _, index (index)}
          <article class="border-line grid gap-3 rounded-xl border p-4 lg:grid-cols-[1fr_auto]">
            <div>
              <Skeleton class="h-4 w-48" />
              <Skeleton class="mt-2 h-3 w-64" />
              <Skeleton class="mt-3 h-16 w-full rounded-lg" />
              <Skeleton class="mt-3 h-3 w-full" />
            </div>
            <div class="flex flex-wrap items-center gap-2">
              <Skeleton class="h-8 w-24" />
              <Skeleton class="h-8 w-20" />
              <Skeleton class="h-8 w-20" />
            </div>
          </article>
        {/each}
      </div>
    {:else}
      <div
        class="hidden border-line bg-panel-alt grid-cols-[minmax(15rem,2fr)_8rem_9rem_9rem_9rem_7rem] gap-4 border-b px-4 py-2 font-mono text-[10px] text-muted uppercase lg:grid"
      >
        <span>Repository</span><span>Source</span><span>Code access</span><span>AI Knowledge</span
        ><span>Used by</span><span>Activity</span>
      </div>
      {#each showArchived ? archivedRepositories : repositoriesResource.data as repository, index (repository.id)}<button
          type="button"
          class="border-line hover:bg-panel-alt grid w-full gap-3 border-b p-4 text-left motion-safe:animate-fade-in-up lg:grid-cols-[minmax(15rem,2fr)_8rem_9rem_9rem_9rem_7rem] lg:items-center"
          style="animation-delay: {Math.min(index, 10) * 30}ms"
          onclick={() => openRepository(repository)}
        >
          <span>
            <strong class="block">{repository.owner}/{repository.name}</strong>
            <span class="text-muted mt-1 block text-xs">{repository.default_branch}</span>
            {#if repository.archived_at}<span class="text-muted text-[10px]">Archived</span>{/if}
          </span>
          <span class="text-xs capitalize">{repository.provider}</span>
          <span><ResourceStatus state={resourceState(repository.code_status)} /></span>
          <span><ResourceStatus state={resourceState(repository.knowledge_status)} /></span>
          <span class="text-xs"
            >{repository.teams_count} teams · {repository.active_tasks_count} tasks</span
          >
          <span class="text-muted text-xs"
            >{repository.last_activity_at
              ? date.format(new Date(repository.last_activity_at))
              : 'Never'}</span
          >
        </button>{:else}<EmptyState message={t('repositories.empty')} />{/each}
    {/if}
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
          <TextField bind:value={query} placeholder={t('repositories.searchPlaceholder')} />
          <Button variant="primary" type="submit" class="sm:w-auto"
            >{t('repositories.search')}</Button
          >
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
    <div class="border-line border-t p-4">
      <button
        class="text-xs text-muted hover:text-brand"
        type="button"
        onclick={() => (showManualForm = !showManualForm)}
      >
        {showManualForm ? t('repositories.hideManualImport') : t('repositories.cantFindRepository')}
      </button>
      {#if showManualForm}
        <form class="mt-4 grid gap-2 md:grid-cols-[1fr_1fr_2fr_auto]" onsubmit={add}>
          <TextField bind:value={owner} placeholder={t('repositories.owner')} required />
          <TextField bind:value={name} placeholder={t('repositories.repositoryName')} required />
          <TextField bind:value={cloneUrl} placeholder={t('repositories.cloneUrl')} required />
          <Button variant="primary" type="submit">{t('repositories.importPlusEmbed')}</Button>
        </form>
      {/if}
    </div>
  </section>
  {#if selectedRepository}
    {@const repository = selectedRepository}
    <ResourceDetailDrawer
      title={`${repository.owner}/${repository.name}`}
      description={`${repository.provider} · ${repository.default_branch}`}
      onClose={() => (selectedRepository = null)}
    >
      <div class="space-y-5">
        <section class="grid grid-cols-2 gap-3">
          <div class="border-line bg-panel-alt rounded-lg border p-3">
            <p class="text-muted text-[10px] uppercase">Code access</p>
            <div class="mt-2"><ResourceStatus state={resourceState(repository.code_status)} /></div>
            <p class="text-muted mt-2 text-xs">
              Latest {repository.latest_sha?.slice(0, 12) || 'not fetched'}
            </p>
          </div>
          <div class="border-line bg-panel-alt rounded-lg border p-3">
            <p class="text-muted text-[10px] uppercase">AI Knowledge</p>
            <div class="mt-2">
              <ResourceStatus state={resourceState(repository.knowledge_status)} />
            </div>
            <p class="text-muted mt-2 text-xs">{repository.chunk_count} searchable chunks</p>
          </div>
        </section>
        <section class="border-line rounded-lg border p-4">
          <h3 class="font-semibold">Usage</h3>
          <div class="text-muted mt-3 grid grid-cols-2 gap-2 text-xs">
            <span>Teams</span><strong>{dependencies?.teams.length ?? repository.teams_count}</strong
            >
            <span>Active Tasks</span><strong
              >{dependencies?.active_tasks ?? repository.active_tasks_count}</strong
            >
            <span>Workspaces</span><strong
              >{dependencies?.active_workspaces ?? repository.active_workspaces_count}</strong
            >
            <span>Task Sources</span><strong
              >{dependencies?.task_sources.join(', ') || 'None'}</strong
            >
          </div>
        </section>
        <section class="border-line rounded-lg border p-4">
          <h3 class="font-semibold">AI Knowledge</h3>
          <p class="text-muted mt-2 text-xs">{knowledgeDescription(repository)}</p>
          {#if repository.index_error}<p class="mt-2 text-xs text-danger">
              {repository.index_error}
            </p>{/if}
          <div class="mt-3 flex flex-wrap gap-2">
            <Button
              size="sm"
              disabled={!repository.enabled ||
                ['QUEUED', 'INDEXING'].includes(repository.index_status)}
              onclick={() => queueIndex(repository)}>Update Knowledge</Button
            >
            <Button
              size="sm"
              disabled={repository.index_status !== 'READY'}
              onclick={() => {
                searchingRepository = repository.id;
                results = [];
                selectedRepository = null;
              }}>Search Knowledge</Button
            >
          </div>
        </section>
        <section class="border-line rounded-lg border p-4">
          <h3 class="font-semibold">Lifecycle</h3>
          <div class="mt-3 flex flex-wrap gap-2">
            {#if repository.archived_at}
              <Button onclick={() => archiveRepository(repository, false)}>Restore</Button>
            {:else}
              <Button onclick={() => toggleRepository(repository)}
                >{repository.enabled ? 'Disable' : 'Enable and Index'}</Button
              >
              <Button onclick={() => archiveRepository(repository, true)}>Archive</Button>
            {/if}
            <Button variant="danger" onclick={() => removeRepository(repository)}
              >Remove Permanently</Button
            >
          </div>
          <p class="text-muted mt-2 text-[10px]">
            Removal is blocked while Teams, active Tasks, workspaces, or task-source integrations
            depend on this repository.
          </p>
        </section>
      </div>
    </ResourceDetailDrawer>
  {/if}
</main>
