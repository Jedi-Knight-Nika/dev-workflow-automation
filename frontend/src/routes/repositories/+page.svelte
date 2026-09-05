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
    queueRepositoryIndex,
    setRepositoryEnabled,
    searchRepositoryKnowledge
  } from '$lib/services/repositories';
  import { t } from '$lib/i18n/index.svelte';
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
  let busyRepository = '';
  let showManualForm = false;
  let githubAccount: GitHubInstallationAccount | null = null;
  const date = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' });
  const githubConnected = () =>
    integrationsResource.data.some(
      (integration) => integration.provider_name === 'github' && integration.status === 'CONNECTED'
    );
  const imported = (repository: DiscoveredRepository) =>
    repositoriesResource.data.some(
      (item) => item.provider === 'github' && item.external_repo_id === repository.external_repo_id
    );
  function knowledgeLabel(repository: Repository) {
    if (repository.index_status === 'READY') return t('repositories.aiReadyLabel');
    if (['QUEUED', 'INDEXING'].includes(repository.index_status))
      return t('repositories.embeddingLabel');
    if (repository.index_status === 'FAILED') return t('repositories.failedLabel');
    return t('repositories.notReadyLabel');
  }
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
  async function selectRepository(repository: DiscoveredRepository) {
    busyRepository = repository.external_repo_id;
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
    } finally {
      busyRepository = '';
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
  async function removeRepository(repository: Repository) {
    if (
      !window.confirm(
        t('repositories.confirmRemove', { name: `${repository.owner}/${repository.name}` })
      )
    ) {
      return;
    }
    busyRepository = repository.id;
    error = '';
    try {
      await deleteRepository(repository.id);
      if (searchingRepository === repository.id) searchingRepository = '';
      await repositoriesResource.refresh();
    } catch (cause) {
      error = String(cause);
    } finally {
      busyRepository = '';
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
  <section class="grid gap-3 md:grid-cols-3">
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
          <span class="font-mono text-[10px] {githubConnected() ? 'text-accent' : 'text-warning'}">
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
          {githubConnected() ? t('repositories.manageConnection') : t('repositories.connectGithub')}
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
            <span class="text-sm"
              >{repository.full_name} {repository.private ? '· private' : ''}</span
            >
            {#if imported(repository)}
              <span class="font-mono text-[10px] text-accent">{t('repositories.imported')}</span>
            {:else}
              <Button
                variant="primary"
                disabled={busyRepository === repository.external_repo_id}
                onclick={() => selectRepository(repository)}
              >
                {busyRepository === repository.external_repo_id
                  ? t('repositories.importing')
                  : t('repositories.importPlusEmbed')}
              </Button>
            {/if}
          </div>{/each}
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
                  : 'text-muted'}"
                >{repository.enabled ? t('repositories.enabled') : t('repositories.disabled')}</span
              >
            </div>
            <p class="text-muted mt-1 text-xs break-all">
              {repository.default_branch} · {repository.clone_url}
            </p>
            <div class="mt-3 rounded-lg border border-line bg-panel-alt p-3">
              <div class="flex items-center justify-between gap-3">
                <strong class="text-xs">{t('repositories.aiKnowledge')}</strong>
                <span
                  class="font-mono text-[10px] {repository.index_status === 'READY'
                    ? 'text-accent'
                    : repository.index_status === 'FAILED'
                      ? 'text-danger'
                      : 'text-warning'}"
                >
                  {knowledgeLabel(repository)}
                </span>
              </div>
              <p class="text-muted mt-1 text-xs">{knowledgeDescription(repository)}</p>
            </div>
            <div class="text-muted mt-3 grid gap-1 font-mono text-[10px] sm:grid-cols-2">
              <span>{t('repositories.clone')}: {repository.clone_status.replaceAll('_', ' ')}</span>
              <span>{t('repositories.chunks')}: {repository.chunk_count}</span>
              <span
                >{t('repositories.remote')}: {repository.latest_sha?.slice(0, 12) ||
                  t('repositories.notFetched')}</span
              >
              <span
                >{t('repositories.indexed')}: {repository.indexed_sha?.slice(0, 12) ||
                  t('repositories.never')}</span
              >
              <span class="sm:col-span-2"
                >{t('repositories.lastSuccessfulPreparation')}: {repository.indexed_at
                  ? date.format(new Date(repository.indexed_at))
                  : t('repositories.never')}</span
              >
            </div>
            {#if repository.index_error}<p class="mt-1 max-w-xl text-xs text-danger">
                {repository.index_error}
              </p>{/if}
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              disabled={!repository.enabled ||
                ['QUEUED', 'INDEXING'].includes(repository.index_status)}
              onclick={() => queueIndex(repository)}
              >{repository.index_status === 'READY'
                ? t('repositories.reEmbed')
                : t('repositories.prepareKnowledge')}</Button
            >
            <Button
              size="sm"
              disabled={repository.index_status !== 'READY'}
              onclick={() => {
                searchingRepository = repository.id;
                results = [];
              }}>{t('repositories.search')}</Button
            >
            <Button size="sm" onclick={() => toggleRepository(repository)}
              >{repository.enabled
                ? t('repositories.disable')
                : t('repositories.enableAndIndex')}</Button
            >
            <Button
              variant="danger"
              size="sm"
              disabled={busyRepository === repository.id}
              onclick={() => removeRepository(repository)}
            >
              {busyRepository === repository.id
                ? t('repositories.removing')
                : t('repositories.remove')}
            </Button>
          </div>
        </article>{:else}<EmptyState message={t('repositories.empty')} />{/each}
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
</main>
