<script lang="ts">
  import { resolve } from '$app/paths';
  import { onMount } from 'svelte';
  import ErrorBanner from '$lib/components/ErrorBanner.svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import TeamBadge from '$lib/components/TeamBadge.svelte';
  import Skeleton from '$lib/components/Skeleton.svelte';
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
  const integer = new Intl.NumberFormat();
  const money = new Intl.NumberFormat(undefined, { style: 'currency', currency: 'USD' });

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

  function toggleRepository(id: string) {
    repositoryIds = repositoryIds.includes(id)
      ? repositoryIds.filter((item) => item !== id)
      : [...repositoryIds, id];
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
    <button class="create-button" onclick={() => void open()}>
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
      <article class="team-card" class:active={team.running_tasks > 0}>
        <header class="card-header">
          <div class="team-identity">
            <div class="team-name">
              <TeamBadge id={team.id} name={team.name} />
              <span
                class:online={team.enabled}
                class="status"
                title={team.enabled ? t('teamsPage.enabled') : t('teamsPage.disabled')}
              ></span>
            </div>
            <span
              class="team-state"
              class:working={team.running_tasks > 0}
              class:disabled={!team.enabled}
            >
              <i></i>{team.running_tasks > 0
                ? t('teamsPage.working')
                : team.enabled
                  ? t('teamsPage.available')
                  : t('teamsPage.disabled')}
            </span>
          </div>
          <div class="capacity">
            <strong>{team.max_concurrent_tasks}</strong>
            <span
              >{team.max_concurrent_tasks === 1
                ? t('teamsPage.taskAtATime')
                : t('teamsPage.parallelTasks')}</span
            >
          </div>
        </header>
        <p class="team-description">{team.description || t('teamsPage.noDescription')}</p>
        <div class="metrics">
          <div class="running-metric">
            <span><i></i>{t('teamsPage.running')}</span><strong>{team.running_tasks}</strong>
          </div>
          <div class="queued-metric">
            <span><i></i>{t('teamsPage.queued')}</span><strong>{team.queued_tasks}</strong>
          </div>
          <div class="completed-metric">
            <span><i></i>{t('teamsPage.completed')}</span><strong>{team.completed_tasks}</strong>
          </div>
        </div>
        <div class="usage" aria-label="Team usage">
          <span title={t('teamsPage.tokensTitle')}
            ><b>{t('teamsPage.tokens')}</b>{integer.format(
              team.total_input_tokens + team.total_output_tokens
            )}</span
          >
          <span title={t('teamsPage.spendTitle')}
            ><b>{t('teamsPage.spend')}</b>{team.estimated_cost_usd === null
              ? t('operations.unavailable')
              : money.format(team.estimated_cost_usd)}</span
          >
          <span title={t('teamsPage.accessTitle')}
            ><b>{t('teamsPage.access')}</b>{team.repository_ids.length
              ? t(
                  team.repository_ids.length === 1
                    ? 'teamsPage.projectCount'
                    : 'teamsPage.projectCountPlural',
                  { count: team.repository_ids.length }
                )
              : t('teamsPage.allProjects')}</span
          >
        </div>
        <footer>
          <a class="workflow-action" href={resolve('/teams/[id]', { id: team.id })}
            ><span>{t('teamsPage.openLifecycle')}</span><b aria-hidden="true">→</b></a
          >
          <div class="operation-actions">
            {#if team.execution_paused}
              <button
                class="edit"
                disabled={busy}
                onclick={async () => {
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
                }}>{t('teamsPage.enableExecution')}</button
              >
            {/if}
            <span
              class="button-help"
              title={team.execution_paused ? t('teamsPage.executionPaused') : t('teamsPage.stopHelp')}
            >
              <button
                class="stop"
                disabled={shuttingDownId === team.id || team.execution_paused}
                onclick={() => void shutdown(team)}
                ><span aria-hidden="true">■</span>{shuttingDownId === team.id
                  ? t('teamsPage.stopping')
                  : t('teamsPage.stopWork')}</button
              >
            </span>
            <button
              class="edit"
              onclick={() => void open(team)}
              aria-label={t('teamsPage.editTeam', { name: team.name })}
              ><span aria-hidden="true">✎</span>
              {t('teamsPage.settings')}</button
            >
            {#if team.id !== '00000000-0000-0000-0000-000000000001'}<button
                class="danger"
                disabled={archivingId === team.id}
                onclick={() => void remove(team)}
                >{archivingId === team.id
                  ? t('teamsPage.archiving')
                  : t('teamsPage.archive')}</button
              >{/if}
          </div>
        </footer>
      </article>
    {/each}
  </section>
</main>

{#if showForm}
  <button class="backdrop" aria-label={t('teamsPage.close')} onclick={() => (showForm = false)}
  ></button>
  <aside class="drawer">
    <header>
      <div>
        <span>{t('teamsPage.configEyebrow')}</span>
        <h2>{editing ? t('teamsPage.editTeam', { name: editing.name }) : t('teamsPage.createTeamTitle')}</h2>
      </div>
      <button onclick={() => (showForm = false)}>×</button>
    </header>
    <div class="body">
      <label
        ><span>{t('teamsPage.name')}</span><input
          bind:value={name}
          placeholder={t('teamsPage.namePlaceholder')}
        /></label
      >
      <label
        ><span>{t('teamsPage.descriptionLabel')}</span><textarea
          bind:value={description}
          rows="4"
          placeholder={t('teamsPage.descriptionPlaceholder')}
        ></textarea></label
      >
      <label
        ><span>{t('teamsPage.parallelTasksLabel')}</span><input
          bind:value={concurrency}
          type="number"
          min="1"
          max="32"
        /><small>{t('teamsPage.parallelTasksHelp')}</small></label
      >
      <fieldset>
        <legend>{t('teamsPage.projectsAccess')}</legend>
        <p>
          {t('teamsPage.projectsAccessDescription')}
        </p>
        <div class="repo-list mb-3">
          <label>
            <input
              type="radio"
              name="repository-scope"
              checked={repositoryIds.length === 0}
              onchange={() => (repositoryIds = [])}
            />
            <span
              ><strong>{t('teamsPage.allImportedRepos')}</strong><small
                >{t('teamsPage.allImportedReposHelp')}</small
              ></span
            >
          </label>
          <label>
            <input
              type="radio"
              name="repository-scope"
              checked={repositoryIds.length > 0}
              onchange={() =>
                (repositoryIds = repositories
                  .filter((repository) => repository.enabled)
                  .map((repository) => repository.id))}
            />
            <span
              ><strong>{t('teamsPage.onlySelectedRepos')}</strong><small
                >{t('teamsPage.onlySelectedReposHelp')}</small
              ></span
            >
          </label>
        </div>
        {#if repositoryIds.length > 0}<div class="repo-list">
            {#each repositories.filter((repo) => repo.enabled) as repository (repository.id)}<label
                ><input
                  type="checkbox"
                  checked={repositoryIds.includes(repository.id)}
                  onchange={() => toggleRepository(repository.id)}
                /><span
                  ><strong>{repository.owner}/{repository.name}</strong><small
                    >{t('teamsPage.repoBranchStatus', {
                      branch: repository.default_branch,
                      status: repository.enabled ? t('teamsPage.enabled') : t('teamsPage.disabled')
                    })}</small
                  ></span
                ></label
              >{/each}
          </div>{/if}
      </fieldset>
      <p>
        {t('teamsPage.postSaveNote')}
      </p>
    </div>
    <footer>
      <button class="cancel" onclick={() => (showForm = false)}>{t('teamsPage.cancel')}</button>
      <div class="save-group">
        <span
          >{editing
            ? t('teamsPage.updateTeamSettings')
            : t('teamsPage.createTeamTitle')}</span
        ><button class="primary" disabled={busy || !name.trim()} onclick={() => void save()}
          >{busy
            ? t('teamsPage.saving')
            : editing
              ? t('teamsPage.saveChanges')
              : t('teamsPage.createTeam')}</button
        >
      </div>
    </footer>
  </aside>
{/if}

<style>
  .primary {
    border-radius: 0.55rem;
    background: var(--color-brand);
    padding: 0.65rem 0.9rem;
    color: white;
    font-size: 0.8rem;
    font-weight: 700;
  }
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
    background: linear-gradient(120deg, var(--color-brand), var(--color-brand-2));
    padding: 0.62rem 0.85rem;
    color: #08050d;
    font-size: 0.76rem;
    font-weight: 800;
    box-shadow: 0 8px 22px color-mix(in srgb, var(--color-brand) 22%, transparent);
    transition:
      filter 150ms ease,
      transform 150ms ease;
  }
  .create-button span {
    font-size: 1rem;
    line-height: 0;
  }
  .create-button:hover {
    filter: brightness(1.08);
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
  .team-card.active::before {
    background: var(--color-accent);
    box-shadow: 0 0 14px color-mix(in srgb, var(--color-accent) 55%, transparent);
  }
  .card-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
  }
  .team-identity {
    display: grid;
    min-width: 0;
    gap: 0.55rem;
  }
  .team-name {
    display: flex;
    align-items: center;
    gap: 0.55rem;
  }
  .team-name :global(.badge) {
    font-size: 0.78rem;
  }
  .status {
    width: 0.55rem;
    height: 0.55rem;
    border-radius: 50%;
    background: var(--color-muted);
  }
  .status.online {
    background: #22a06b;
    box-shadow: 0 0 0 3px color-mix(in srgb, #22a06b 18%, transparent);
  }
  .team-state {
    display: inline-flex;
    width: fit-content;
    align-items: center;
    gap: 0.38rem;
    border: 1px solid color-mix(in srgb, var(--color-accent) 24%, var(--color-line));
    border-radius: 999px;
    background: color-mix(in srgb, var(--color-accent) 6%, transparent);
    padding: 0.22rem 0.5rem;
    color: color-mix(in srgb, var(--color-accent) 78%, var(--color-text));
    font-size: 0.58rem;
    font-weight: 750;
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }
  .team-state i {
    width: 0.38rem;
    height: 0.38rem;
    border-radius: 50%;
    background: currentColor;
  }
  .team-state.working i {
    box-shadow: 0 0 7px currentColor;
  }
  .team-state.disabled {
    border-color: var(--color-line);
    background: transparent;
    color: var(--color-muted);
  }
  .capacity {
    display: grid;
    flex: none;
    min-width: 4.7rem;
    justify-items: end;
    gap: 0.05rem;
    border-left: 1px solid var(--color-line);
    padding-left: 0.9rem;
  }
  .capacity strong {
    color: var(--color-heading);
    font-size: 1.25rem;
    line-height: 1;
  }
  .capacity span {
    color: var(--color-muted);
    font-size: 0.55rem;
    white-space: nowrap;
  }
  .team-description {
    min-height: 2.5rem;
    color: var(--color-muted);
    font-size: 0.8rem;
    line-height: 1.55;
  }
  .metrics {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    overflow: hidden;
    border: 1px solid color-mix(in srgb, var(--color-line) 84%, transparent);
    border-radius: 0.75rem;
    background: color-mix(in srgb, var(--color-surface) 46%, transparent);
  }
  .metrics div {
    display: flex;
    min-width: 0;
    flex-direction: column-reverse;
    gap: 0.3rem;
    padding: 0.72rem;
  }
  .metrics div + div {
    border-left: 1px solid var(--color-line);
  }
  .metrics strong {
    color: var(--color-heading);
    font-size: 1.25rem;
    line-height: 1;
  }
  .metrics span {
    display: flex;
    align-items: center;
    gap: 0.3rem;
    color: var(--color-muted);
    font-size: 0.6rem;
  }
  .metrics i {
    width: 0.34rem;
    height: 0.34rem;
    border-radius: 50%;
    background: var(--color-muted);
  }
  .running-metric i {
    background: var(--color-accent);
  }
  .queued-metric i {
    background: var(--color-warning);
  }
  .completed-metric i {
    background: var(--color-brand-2);
  }
  .usage {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.4rem;
  }
  .usage > span {
    display: grid;
    min-width: 0;
    gap: 0.12rem;
    overflow: hidden;
    border: 1px solid var(--color-line);
    border-radius: 0.5rem;
    padding: 0.48rem 0.52rem;
    color: var(--color-text);
    font: 0.64rem var(--font-mono);
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .usage b {
    color: var(--color-muted);
    font: 700 0.5rem/1.2 var(--font-mono);
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .team-card > footer {
    display: grid;
    gap: 0.65rem;
    border-top: 1px solid var(--color-line);
    padding-top: 1rem;
  }
  .workflow-action {
    display: flex;
    width: 100%;
    align-items: center;
    justify-content: space-between;
    border: 1px solid color-mix(in srgb, var(--color-brand-2) 40%, var(--color-line));
    border-radius: 0.6rem;
    background: color-mix(in srgb, var(--color-brand-2) 9%, var(--color-panel-alt));
    padding: 0.68rem 0.78rem;
    color: var(--color-heading);
    font-size: 0.76rem;
    font-weight: 800;
    transition:
      background 150ms ease,
      border-color 150ms ease;
  }
  .workflow-action b {
    color: var(--color-brand-2);
    font-size: 1rem;
  }
  .workflow-action:hover {
    border-color: var(--color-brand-2);
    background: color-mix(in srgb, var(--color-brand-2) 15%, var(--color-panel-alt));
  }
  .operation-actions {
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }
  .operation-actions button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.32rem;
    border: 1px solid var(--color-line);
    border-radius: 0.5rem;
    padding: 0.48rem 0.58rem;
    color: var(--color-muted);
    font-size: 0.68rem;
    white-space: nowrap;
  }
  .operation-actions button:hover:not(:disabled) {
    border-color: color-mix(in srgb, var(--color-brand-2) 45%, var(--color-line));
    background: color-mix(in srgb, var(--color-brand-2) 7%, transparent);
    color: var(--color-text);
  }
  .button-help {
    display: inline-flex;
  }
  .operation-actions .stop {
    border: 1px solid color-mix(in srgb, var(--color-danger) 45%, var(--color-line));
    color: var(--color-danger);
    font-weight: 700;
  }
  .operation-actions .stop:hover:not(:disabled) {
    background: color-mix(in srgb, var(--color-danger) 9%, transparent);
  }
  .operation-actions button:disabled {
    cursor: not-allowed;
    opacity: 0.42;
  }
  .operation-result {
    border: 1px solid color-mix(in srgb, #22a06b 35%, var(--color-line));
    border-radius: 0.7rem;
    background: color-mix(in srgb, #22a06b 8%, var(--color-panel));
    padding: 0.75rem 0.9rem;
    color: var(--color-text);
    font-size: 0.78rem;
  }
  .operation-actions .danger {
    margin-left: auto;
    border-color: transparent;
    color: var(--color-danger);
  }
  @media (max-width: 460px) {
    .teams-toolbar {
      align-items: stretch;
      flex-direction: column;
    }
    .create-button {
      justify-content: center;
    }
    .operation-actions {
      flex-wrap: wrap;
    }
    .operation-actions .danger {
      margin-left: 0;
    }
  }
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 40;
    width: 100%;
    background: rgb(0 0 0/0.35);
    backdrop-filter: blur(2px);
  }
  .drawer {
    position: fixed;
    top: 50%;
    left: 50%;
    z-index: 50;
    display: grid;
    width: min(620px, calc(100% - 2rem));
    max-height: min(780px, calc(100dvh - 2rem));
    grid-template-rows: auto 1fr auto;
    overflow: hidden;
    transform: translate(-50%, -50%);
    border: 1px solid var(--color-line);
    border-radius: 1rem;
    background: var(--color-bg);
    box-shadow: 0 24px 80px rgb(0 0 0/0.3);
  }
  .drawer > header,
  .drawer > footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid var(--color-line);
    padding: 1.2rem;
  }
  .drawer > footer {
    justify-content: space-between;
    gap: 1rem;
    border-top: 1px solid var(--color-line);
    border-bottom: 0;
  }
  .drawer > footer .cancel {
    color: var(--color-muted);
    font-size: 0.8rem;
    padding: 0.65rem 0.2rem;
  }
  .save-group {
    display: flex;
    align-items: center;
    gap: 0.8rem;
  }
  .save-group > span {
    color: var(--color-muted);
    font-size: 0.68rem;
  }
  @media (max-width: 520px) {
    .save-group > span {
      display: none;
    }
  }
  .drawer header span,
  legend,
  .body > label > span {
    color: var(--color-muted);
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.07em;
    text-transform: uppercase;
  }
  .drawer h2 {
    margin-top: 0.3rem;
    font-size: 1.2rem;
    font-weight: 750;
  }
  .drawer header button {
    font-size: 1.6rem;
  }
  .body {
    display: grid;
    align-content: start;
    gap: 1.2rem;
    min-height: 0;
    overflow-y: auto;
    overscroll-behavior: contain;
    padding: 1.2rem;
  }
  .body > label {
    display: grid;
    gap: 0.4rem;
  }
  .body input,
  .body textarea {
    border: 1px solid var(--color-line);
    border-radius: 0.6rem;
    background: var(--color-panel);
    padding: 0.7rem;
    color: var(--color-text);
  }
  fieldset {
    display: grid;
    gap: 0.7rem;
    border: 1px solid var(--color-line);
    border-radius: 0.75rem;
    padding: 0.9rem;
  }
  .body small,
  fieldset > p {
    color: var(--color-muted);
    font-size: 0.7rem;
  }
  .repo-list {
    display: grid;
    gap: 0.4rem;
    margin-top: 0.7rem;
  }
  .repo-list label {
    display: flex;
    align-items: center;
    gap: 0.7rem;
    border: 1px solid var(--color-line);
    border-radius: 0.6rem;
    padding: 0.65rem;
  }
  .repo-list label span {
    display: grid;
    gap: 0.15rem;
    font-size: 0.78rem;
  }
  .repo-list input {
    width: 1rem;
    height: 1rem;
    padding: 0;
  }
  @media (max-width: 640px) {
    .drawer {
      width: calc(100% - 1rem);
      max-height: calc(100dvh - 1rem);
    }
  }
</style>
