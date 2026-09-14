<script lang="ts">
  import { resolve } from '$app/paths';
  import TeamBadge from '$lib/components/TeamBadge.svelte';
  import { t } from '$lib/i18n/index.svelte';
  import type { Team } from '$lib/types';

  let {
    team,
    busy,
    stopping,
    archiving,
    onWake,
    onShutdown,
    onEdit,
    onArchive
  }: {
    team: Team;
    busy: boolean;
    stopping: boolean;
    archiving: boolean;
    onWake: () => void;
    onShutdown: () => void;
    onEdit: () => void;
    onArchive: () => void;
  } = $props();

  const integer = new Intl.NumberFormat();
  const money = new Intl.NumberFormat(undefined, { style: 'currency', currency: 'USD' });
</script>

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
        <button class="edit" disabled={busy} onclick={onWake}
          >{t('teamsPage.enableExecution')}</button
        >
      {/if}
      <span
        class="button-help"
        title={team.execution_paused ? t('teamsPage.executionPaused') : t('teamsPage.stopHelp')}
      >
        <button class="stop" disabled={stopping || team.execution_paused} onclick={onShutdown}
          ><span aria-hidden="true">■</span>{stopping
            ? t('teamsPage.stopping')
            : t('teamsPage.stopWork')}</button
        >
      </span>
      <button class="edit" onclick={onEdit} aria-label={t('teamsPage.editTeam', { name: team.name })}
        ><span aria-hidden="true">✎</span>
        {t('teamsPage.settings')}</button
      >
      {#if team.id !== '00000000-0000-0000-0000-000000000001'}<button
          class="danger"
          disabled={archiving}
          onclick={onArchive}
          >{archiving ? t('teamsPage.archiving') : t('teamsPage.archive')}</button
        >{/if}
    </div>
  </footer>
</article>

<style>
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
  .operation-actions .danger {
    margin-left: auto;
    border-color: transparent;
    color: var(--color-danger);
  }
  @media (max-width: 460px) {
    .operation-actions {
      flex-wrap: wrap;
    }
    .operation-actions .danger {
      margin-left: 0;
    }
  }
</style>
