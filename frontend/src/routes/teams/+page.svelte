<script lang="ts">
  import { resolve } from '$app/paths';
  import { onMount } from 'svelte';
  import ErrorBanner from '$lib/components/ErrorBanner.svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import TeamBadge from '$lib/components/TeamBadge.svelte';
  import { listRepositories } from '$lib/services/repositories';
  import { archiveTeam, createTeam, listTeams, updateTeam } from '$lib/services/teams';
  import type { Repository, Team } from '$lib/types';

  let teams = $state<Team[]>([]),
    repositories = $state<Repository[]>([]);
  let editing = $state<Team | null>(null),
    showForm = $state(false),
    busy = $state(false);
  let error = $state('');
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
    }
  }
  function open(team?: Team) {
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
    if (!confirm(`Archive ${team.name}? Queued assignments will be cancelled.`)) return;
    try {
      await archiveTeam(team.id);
      await load();
    } catch (cause) {
      error = String(cause);
    }
  }
  onMount(load);
</script>

<PageHeader
  eyebrow="AUTONOMOUS DELIVERY"
  title="Engineering teams"
  description="Hire configurable AI teams, scope their codebase access, and run independent task queues in parallel."
/>
<main class="space-y-6 p-4 sm:p-6 md:p-10">
  <ErrorBanner message={error} />
  <div class="flex items-center justify-between">
    <p class="text-muted text-sm">
      Each team works sequentially by default. Teams run independently.
    </p>
    <button class="primary" onclick={() => open()}>Create team</button>
  </div>
  <section class="team-grid">
    {#each teams as team (team.id)}
      <article class="team-card">
        <header>
          <div>
            <TeamBadge id={team.id} name={team.name} />
            <span
              class:online={team.enabled}
              class="status"
              title={team.enabled ? 'Enabled' : 'Disabled'}
            ></span>
          </div>
          <span class="capacity">{team.max_concurrent_tasks} concurrent</span>
        </header>
        <p>{team.description || 'No team description.'}</p>
        <div class="metrics">
          <div><strong>{team.running_tasks}</strong><span>Running</span></div>
          <div><strong>{team.queued_tasks}</strong><span>Queued</span></div>
          <div><strong>{team.completed_tasks}</strong><span>Completed</span></div>
        </div>
        <div class="usage">
          <span>{integer.format(team.total_input_tokens + team.total_output_tokens)} tokens</span
          ><span>{money.format(team.estimated_cost_usd)}</span><span
            >{team.repository_ids.length} projects</span
          >
        </div>
        <footer>
          <!-- eslint-disable-next-line svelte/no-navigation-without-resolve -->
          <a class="primary" href={`${resolve('/agents')}?team=${team.id}`}>Open workflow</a><button
            class="edit"
            onclick={() => open(team)}
            aria-label={`Edit ${team.name}`}><span aria-hidden="true">✎</span> Edit</button
          >{#if team.id !== '00000000-0000-0000-0000-000000000001'}<button
              class="danger"
              onclick={() => void remove(team)}>Archive</button
            >{/if}
        </footer>
      </article>
    {/each}
  </section>
</main>

{#if showForm}
  <button class="backdrop" aria-label="Close" onclick={() => (showForm = false)}></button>
  <aside class="drawer">
    <header>
      <div>
        <span>TEAM CONFIGURATION</span>
        <h2>{editing ? `Edit ${editing.name}` : 'Create a team'}</h2>
      </div>
      <button onclick={() => (showForm = false)}>×</button>
    </header>
    <div class="body">
      <label><span>Name</span><input bind:value={name} placeholder="Payments engineering" /></label>
      <label
        ><span>Description</span><textarea
          bind:value={description}
          rows="4"
          placeholder="What this team owns and delivers…"
        ></textarea></label
      >
      <label
        ><span>Parallel tasks inside this team</span><input
          bind:value={concurrency}
          type="number"
          min="1"
          max="32"
        /><small>Keep this at 1 for strict one-after-another execution.</small></label
      >
      <fieldset>
        <legend>Projects and RAG access</legend>
        <p>
          Tasks from these repositories can be routed here. Configured agents inherit access to
          their indexed code.
        </p>
        <div class="repo-list">
          {#each repositories.filter((repo) => repo.enabled) as repository (repository.id)}<label
              ><input
                type="checkbox"
                checked={repositoryIds.includes(repository.id)}
                onchange={() => toggleRepository(repository.id)}
              /><span
                ><strong>{repository.owner}/{repository.name}</strong><small
                  >{repository.index_status} · {repository.chunk_count} chunks</small
                ></span
              ></label
            >{/each}
        </div>
      </fieldset>
    </div>
    <footer>
      <button class="cancel" onclick={() => (showForm = false)}>Cancel</button>
      <div class="save-group">
        <span>{editing ? 'Update team settings' : 'Create an empty team workflow'}</span><button
          class="primary"
          disabled={busy || !name.trim()}
          onclick={() => void save()}
          >{busy ? 'Saving…' : editing ? 'Save changes' : 'Create team'}</button
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
  .team-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 1rem;
  }
  .team-card {
    display: grid;
    gap: 1rem;
    border: 1px solid var(--color-line);
    border-radius: 1rem;
    background: var(--color-panel);
    padding: 1.1rem;
    box-shadow: 0 2px 10px rgb(0 0 0/0.04);
  }
  .team-card > header {
    display: flex;
    align-items: start;
    justify-content: space-between;
    gap: 1rem;
  }
  .team-card header div {
    display: flex;
    align-items: center;
    gap: 0.55rem;
  }
  .team-card header div :global(.badge) {
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
  .capacity {
    border: 1px solid var(--color-line);
    border-radius: 999px;
    padding: 0.2rem 0.5rem;
    color: var(--color-muted);
    font-size: 0.67rem;
  }
  .team-card > p {
    min-height: 2.5rem;
    color: var(--color-muted);
    font-size: 0.8rem;
    line-height: 1.55;
  }
  .metrics {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    overflow: hidden;
    border: 1px solid var(--color-line);
    border-radius: 0.7rem;
  }
  .metrics div {
    display: grid;
    gap: 0.2rem;
    padding: 0.65rem;
    text-align: center;
  }
  .metrics div + div {
    border-left: 1px solid var(--color-line);
  }
  .metrics strong {
    font-size: 1.15rem;
  }
  .metrics span,
  .usage {
    color: var(--color-muted);
    font-size: 0.66rem;
  }
  .usage {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    gap: 0.5rem;
  }
  .team-card > footer {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    border-top: 1px solid var(--color-line);
    padding-top: 0.9rem;
  }
  .team-card > footer button {
    padding: 0.5rem;
    color: var(--color-muted);
    font-size: 0.75rem;
  }
  .team-card > footer .edit {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    border: 1px solid var(--color-line);
    border-radius: 0.5rem;
    padding: 0.5rem 0.65rem;
  }
  .team-card > footer .edit:hover {
    border-color: var(--color-brand);
    color: var(--color-text);
  }
  .team-card > footer .danger {
    margin-left: auto;
    color: #e5484d;
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
    inset: 0 0 0 auto;
    z-index: 50;
    display: grid;
    width: min(560px, 100%);
    grid-template-rows: auto 1fr auto;
    background: var(--color-bg);
    box-shadow: -20px 0 60px rgb(0 0 0/0.2);
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
    overflow-y: auto;
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
</style>
