<script lang="ts">
  import { onMount } from 'svelte';
  import ErrorBanner from '$lib/components/ErrorBanner.svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import Skeleton from '$lib/components/Skeleton.svelte';
  import TeamCard from '$lib/components/teams/TeamCard.svelte';
  import TeamFormDrawer from '$lib/components/teams/TeamFormDrawer.svelte';
  import { t } from '$lib/i18n/index.svelte';
  import { listRepositories } from '$lib/services/repositories';
  import {
    archiveTeam,
    createTeam,
    listTeams,
    shutdownTeam,
    wakeTeam,
    updateTeam
  } from '$lib/services/teams';
  import type { Repository, Team } from '$lib/types';

  let teams = $state<Team[]>([]),
    repositories = $state<Repository[]>([]);
  let editing = $state<Team | null>(null),
    showForm = $state(false),
    busy = $state(false);
  let error = $state(''),
    loading = $state(true);
  let archivingId = $state(''),
    shuttingDownId = $state(''),
    statusMessage = $state('');
  let name = $state(''),
    description = $state(''),
    concurrency = $state(1);
  let repositoryIds = $state<string[]>([]);

  async function load() {
    try {
      [teams, repositories] = await Promise.all([listTeams(), listRepositories()]);
    } catch (cause) {
      error = String(cause);
    } finally {
      loading = false;
    }
  }
  async function open(team?: Team) {
    editing = team ?? null;
    name = team?.name ?? '';
    description = team?.description ?? '';
    concurrency = team?.max_concurrent_tasks ?? 1;
    repositoryIds = [...(team?.repository_ids ?? [])];
    showForm = true;
  }
  async function save() {
    if (!name.trim()) return;
    busy = true;
    error = '';
    const input = {
      name: name.trim(),
      description: description.trim(),
      enabled: editing?.enabled ?? true,
      max_concurrent_tasks: concurrency,
      repository_ids: repositoryIds
    };
    try {
      if (editing) await updateTeam(editing.id, input);
      else await createTeam(input);
      showForm = false;
      await load();
    } catch (cause) {
      error = String(cause);
    } finally {
      busy = false;
    }
  }
  async function remove(team: Team) {
    if (!confirm(t('teamsPage.confirmArchive', { name: team.name }))) return;
    archivingId = team.id;
    try {
      await archiveTeam(team.id);
      await load();
    } catch (cause) {
      error = String(cause);
    } finally {
      archivingId = '';
    }
  }
  async function shutdown(team: Team) {
    if (!confirm(t('teamsPage.confirmStop', { name: team.name }))) return;
    shuttingDownId = team.id;
    error = '';
    try {
      const result = await shutdownTeam(team.id);
      statusMessage = t('teamsPage.shutdownResult', {
        name: team.name,
        jobs: result.cancelled_jobs,
        tasks: result.paused_tasks
      });
      await load();
    } catch (cause) {
      error = String(cause);
    } finally {
      shuttingDownId = '';
    }
  }
  async function wake(team: Team) {
    busy = true;
    try {
      await wakeTeam(team.id);
      await load();
      statusMessage = t('teamsPage.executionResumed');
    } catch (cause) {
      error = String(cause);
    } finally {
      busy = false;
    }
  }
  onMount(load);
</script>

<PageHeader
  eyebrow={t('teamsPage.eyebrow')}
  title={t('teamsPage.title')}
  description={t('teamsPage.description')}
/>
<main class="space-y-6 p-4 sm:p-6 md:p-10">
  <ErrorBanner message={error} />
  {#if statusMessage}<p class="operation-result" role="status">{statusMessage}</p>{/if}
  <div class="teams-toolbar">
    <div>
      <strong>{t('teamsPage.independentLanes')}</strong>
      <p>{t('teamsPage.independentLanesDescription')}</p>
    </div>
    <button class="create-button accent-action" onclick={() => void open()}>
      <span aria-hidden="true">+</span>
      {t('teamsPage.createTeam')}
    </button>
  </div>
  <section class="team-grid" aria-busy={loading}>
    {#if loading}
      <!-- eslint-disable-next-line @typescript-eslint/no-unused-vars -->
      {#each Array(3) as _, index (index)}
        <article class="team-card">
          <header>
            <div>
              <Skeleton class="h-6 w-6 rounded-full" />
              <Skeleton class="h-4 w-24" />
            </div>
            <Skeleton class="h-5 w-20 rounded-full" />
          </header>
          <Skeleton class="h-10 w-full" />
          <Skeleton class="h-14 w-full rounded-[0.7rem]" />
          <Skeleton class="h-4 w-full" />
        </article>
      {/each}
    {/if}
    {#each teams as team (team.id)}
      <TeamCard
        {team}
        {busy}
        stopping={shuttingDownId === team.id}
        archiving={archivingId === team.id}
        onWake={() => void wake(team)}
        onShutdown={() => void shutdown(team)}
        onEdit={() => void open(team)}
        onArchive={() => void remove(team)}
      />
    {/each}
  </section>
</main>

{#if showForm}
  <TeamFormDrawer
    {editing}
    bind:name
    bind:description
    bind:concurrency
    bind:repositoryIds
    {repositories}
    {busy}
    onSave={() => void save()}
    onClose={() => (showForm = false)}
  />
{/if}

<style>
  .teams-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    border: 1px solid var(--color-line);
    border-radius: 0.85rem;
    background: color-mix(in srgb, var(--color-panel) 76%, transparent);
    padding: 0.85rem 0.9rem 0.85rem 1rem;
  }
  .teams-toolbar strong {
    color: var(--color-heading);
    font-size: 0.8rem;
  }
  .teams-toolbar p {
    margin-top: 0.15rem;
    color: var(--color-muted);
    font-size: 0.72rem;
  }
  .create-button {
    display: inline-flex;
    flex: none;
    align-items: center;
    gap: 0.5rem;
    border: 1px solid color-mix(in srgb, var(--color-brand-2) 45%, var(--color-brand));
    border-radius: 0.6rem;
    background: linear-gradient(120deg in srgb, var(--color-action-start), var(--color-action-end));
    padding: 0.62rem 0.85rem;
    color: var(--color-on-brand);
    font-size: 0.76rem;
    font-weight: 800;
    box-shadow: 0 8px 22px color-mix(in srgb, var(--color-brand) 22%, transparent);
    transition:
      box-shadow 150ms ease,
      transform 150ms ease;
  }
  .create-button span {
    font-size: 1rem;
    line-height: 0;
  }
  .create-button:hover {
    box-shadow: 0 8px 24px color-mix(in srgb, var(--color-brand) 40%, transparent);
    transform: translateY(-1px);
  }
  .team-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(min(360px, 100%), 440px));
    gap: 1.15rem;
    justify-content: start;
  }
  .team-card {
    position: relative;
    display: grid;
    align-content: start;
    gap: 1.05rem;
    overflow: hidden;
    border: 1px solid color-mix(in srgb, var(--color-brand-2) 16%, var(--color-line));
    border-radius: 1rem;
    background:
      radial-gradient(
        circle at 100% 0,
        color-mix(in srgb, var(--color-brand) 8%, transparent),
        transparent 35%
      ),
      var(--color-panel);
    padding: 1.15rem;
    box-shadow:
      inset 0 1px 0 rgb(255 255 255 / 4%),
      0 14px 36px rgb(0 0 0 / 18%);
    transition:
      border-color 160ms ease,
      box-shadow 160ms ease,
      transform 160ms ease;
  }
  .team-card::before {
    position: absolute;
    inset: 0 auto 0 0;
    width: 3px;
    background: color-mix(in srgb, var(--color-brand-2) 55%, var(--color-line));
    content: '';
  }
  .team-card:hover {
    border-color: color-mix(in srgb, var(--color-brand-2) 38%, var(--color-line));
    box-shadow:
      inset 0 1px 0 rgb(255 255 255 / 6%),
      0 18px 42px rgb(0 0 0 / 26%);
    transform: translateY(-2px);
  }
  .operation-result {
    border: 1px solid color-mix(in srgb, #22a06b 35%, var(--color-line));
    border-radius: 0.7rem;
    background: color-mix(in srgb, #22a06b 8%, var(--color-panel));
    padding: 0.75rem 0.9rem;
    color: var(--color-text);
    font-size: 0.78rem;
  }
  @media (max-width: 460px) {
    .teams-toolbar {
      align-items: stretch;
      flex-direction: column;
    }
    .create-button {
      justify-content: center;
    }
  }
</style>
