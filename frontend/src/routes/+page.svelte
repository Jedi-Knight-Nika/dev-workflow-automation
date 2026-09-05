<script lang="ts">
  import { resolve } from '$app/paths';
  import { onMount } from 'svelte';
  import { API_URL } from '$lib/api';
  import ErrorBanner from '$lib/components/ErrorBanner.svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import { getDashboardSummary, getDashboardTelemetry } from '$lib/services/dashboard';
  import type { DashboardSnapshot, DashboardUsageBucket, HostTelemetry } from '$lib/types';

  let dashboard = $state<DashboardSnapshot | null>(null);
  let period = $state<'today' | '7d' | '30d'>('today');
  let error = $state(''),
    live = $state(false),
    loading = $state(true);
  let telemetry = $state<HostTelemetry | null>(null);
  let refreshTimer: ReturnType<typeof setTimeout> | undefined;
  const compact = new Intl.NumberFormat(undefined, {
    notation: 'compact',
    maximumFractionDigits: 1
  });
  const time = new Intl.DateTimeFormat(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  });
  const total = (item: DashboardUsageBucket) => item.input_tokens + item.output_tokens;
  const maxUsage = (items: DashboardUsageBucket[]) => Math.max(1, ...items.map(total));

  async function load() {
    try {
      [dashboard, telemetry] = await Promise.all([
        getDashboardSummary(period),
        getDashboardTelemetry()
      ]);
      error = '';
    } catch (cause) {
      error = cause instanceof Error ? cause.message : String(cause);
    } finally {
      loading = false;
    }
  }
  async function selectPeriod(value: typeof period) {
    period = value;
    loading = true;
    await load();
  }
  function scheduleRefresh() {
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(() => void load(), 250);
  }
  function elapsed(startedAt: string | null) {
    if (!startedAt) return 'STARTING';
    const seconds = Math.max(0, Math.floor((Date.now() - Date.parse(startedAt)) / 1000));
    return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
  }
  onMount(() => {
    void load();
    const stream = new EventSource(`${API_URL}/api/v1/events/stream`);
    const telemetryTimer = setInterval(() => {
      void getDashboardTelemetry().then((value) => (telemetry = value));
    }, 5000);
    stream.onopen = () => (live = true);
    stream.addEventListener('update', scheduleRefresh);
    stream.onerror = () => {
      live = false;
      error = 'Live connection interrupted; reconnecting.';
    };
    return () => {
      stream.close();
      clearTimeout(refreshTimer);
      clearInterval(telemetryTimer);
    };
  });
</script>

<svelte:head><title>Engineering Control Center</title></svelte:head>
<PageHeader
  eyebrow="AI ENGINEERING OPERATIONS"
  title="Control center"
  description="Live workflow, team, usage, repository, and infrastructure state."
/>
<main class="cockpit">
  <div class="toolbar">
    <span class="live"><i class:connected={live}></i>{live ? 'LIVE' : 'RECONNECTING'}</span>
    <div class="periods">
      {#each [['today', 'Today'], ['7d', '7 days'], ['30d', '30 days']] as item (item[0])}<button
          class:active={period === item[0]}
          onclick={() => void selectPeriod(item[0] as typeof period)}>{item[1]}</button
        >{/each}
    </div>
  </div>
  <ErrorBanner message={error} />
  {#if loading && !dashboard}<div class="empty">INITIALIZING CONTROL SURFACE…</div>
  {:else if dashboard}
    <section class="metrics">
      <article class="health">
        <div class="gauge" style={`--value:${dashboard.health_score * 3.6}deg`}>
          <span><b>{dashboard.health_score}%</b>{dashboard.system_status}</span>
        </div>
        <small>SYSTEM HEALTH</small>
      </article>
      {#each [['ACTIVE TASKS', dashboard.active_tasks, 'violet'], ['QUEUE', dashboard.queued_jobs, 'cyan'], ['READY TO MERGE', dashboard.ready_to_merge, 'green'], ['TOKENS', compact.format(dashboard.tokens), 'violet'], ['HUMAN NEEDED', dashboard.needs_human, dashboard.needs_human ? 'danger' : '']] as metric (metric[0])}<article
          class="metric {metric[2]}"
        >
          <span>{metric[0]}</span><strong>{metric[1]}</strong><small
            >{metric[0] === 'TOKENS'
              ? dashboard.estimated_cost === null
                ? 'Cost unavailable'
                : `$${dashboard.estimated_cost.toFixed(2)} estimated`
              : period}</small
          >
        </article>{/each}
    </section>

    <section class="split">
      <article class="worker panel">
        <header><span>ACTIVE WORKER</span><i class:running={dashboard.active_worker}></i></header>
        {#if dashboard.active_worker}<div class="worker-core">
            <div class="orb">{dashboard.active_worker.role.slice(0, 2)}</div>
            <small>{dashboard.active_worker.role}</small>
            <h2>{dashboard.active_worker.agent_name || dashboard.active_worker.role}</h2>
            <p>
              {dashboard.active_worker.provider || 'provider'} / {dashboard.active_worker.model ||
                'model pending'}
            </p>
          </div>
          <a href={resolve('/tasks/[id]', { id: dashboard.active_worker.task_id })}
            ><small>{dashboard.active_worker.team_name || 'Unassigned'}</small><b
              >{dashboard.active_worker.task_label}</b
            ></a
          >
          <footer>
            <div><span>ELAPSED</span><b>{elapsed(dashboard.active_worker.started_at)}</b></div>
            <div>
              <span>TOKENS</span><b
                >{compact.format(
                  dashboard.active_worker.input_tokens + dashboard.active_worker.output_tokens
                )}</b
              >
            </div>
            <div><span>STATE</span><b class="cyan-text">RUNNING</b></div>
          </footer>{:else}<div class="worker-core idle">
            <div class="orb">—</div>
            <h2>Execution lane idle</h2>
            <p>Scheduler ready for the next job.</p>
          </div>{/if}
      </article>
      <article class="feed panel">
        <header>
          <div>
            <span>LIVE ACTIVITY</span>
            <h2>Operational timeline</h2>
          </div>
          <small>{dashboard.recent_events.length} RECENT</small>
        </header>
        <div class="events">
          {#each dashboard.recent_events as event (event.id)}<a
              href={resolve('/tasks/[id]', { id: event.task_id })}
              ><time>{time.format(new Date(event.timestamp))}</time><i
                class:error={event.severity === 'ERROR'}
                class:warning={event.severity === 'WARNING'}
              ></i>
              <div>
                <b>{event.event_type.replaceAll('_', ' ')}</b>
                <p>{event.team_name ? `${event.team_name} · ` : ''}{event.task_label}</p>
                <small>{event.summary}</small>
              </div></a
            >{:else}<div class="empty">No persisted activity yet.</div>{/each}
        </div>
      </article>
    </section>

    <div class="section-title">
      <div>
        <span>TEAMS</span>
        <h2>Engineering organization</h2>
      </div>
      <a href={resolve('/teams')}>MANAGE →</a>
    </div>
    <section class="teams">
      {#each dashboard.teams as team (team.team_id)}<article class="team">
          <header>
            <div class="avatar">{team.name.slice(0, 2).toUpperCase()}</div>
            <div>
              <h3>{team.name}</h3>
              <span class={team.status.toLowerCase()}>{team.status.replaceAll('_', ' ')}</span>
            </div>
          </header>
          <div class="current">
            <small>CURRENT TASK</small><b>{team.current_task_label || 'No active task'}</b
            >{#if team.agent_name}<span
                >{team.agent_name} · {team.role}<br />{team.provider} / {team.model}</span
              >{/if}
          </div>
          <div class="team-stats">
            <div><b>{compact.format(team.tokens)}</b><small>tokens</small></div>
            <div><b>{team.queued_jobs}</b><small>queued</small></div>
            <div><b>{team.open_pull_requests}</b><small>open PRs</small></div>
            <div><b>{team.ready_to_merge}</b><small>merge ready</small></div>
          </div>
          <!-- eslint-disable-next-line svelte/no-navigation-without-resolve -->
          <a href={`${resolve('/agents')}?team=${team.team_id}`}>VIEW TEAM →</a>
        </article>{/each}
    </section>

    <section class="split analytics">
      <article class="panel chart">
        <header>
          <div>
            <span>THROUGHPUT</span>
            <h2>Task outcomes</h2>
          </div>
          <small
            >AUTONOMY {dashboard.autonomy_rate === null
              ? '—'
              : `${dashboard.autonomy_rate}%`}</small
          >
        </header>
        <div class="bars">
          {#each dashboard.throughput as point (point.period)}{@const peak = Math.max(
              1,
              ...dashboard.throughput.map((value) => value.completed + value.failed)
            )}
            <div>
              <div>
                <i class="failed" style={`height:${(point.failed / peak) * 100}%`}></i><i
                  class="done"
                  style={`height:${(point.completed / peak) * 100}%`}
                ></i>
              </div>
              <small>{point.period.slice(5)}</small>
            </div>{/each}
        </div>
        <footer>
          <span>● Completed {dashboard.completed}</span><span class="red"
            >● Failed {dashboard.failed}</span
          >
        </footer>
      </article>
      <article class="panel usage">
        <header>
          <div>
            <span>AI USAGE</span>
            <h2>Tokens by role</h2>
          </div>
          <b>{compact.format(dashboard.tokens)}</b>
        </header>
        <div>
          {#each dashboard.usage_by_role as item (item.key)}<div class="usage-row">
              <span>{item.key}</span>
              <div>
                <i style={`width:${(total(item) / maxUsage(dashboard.usage_by_role)) * 100}%`}></i>
              </div>
              <b>{compact.format(total(item))}</b>
            </div>{:else}<div class="empty">Usage appears after model calls.</div>{/each}
        </div>
      </article>
    </section>

    <section class="split bottom">
      <article class="panel queue">
        <header>
          <div>
            <span>SCHEDULER</span>
            <h2>Execution queue</h2>
          </div>
          <b>{dashboard.queue.length}</b>
        </header>
        {#each dashboard.queue.slice(0, 8) as job, index (job.job_id)}<a
            href={resolve('/tasks/[id]', { id: job.task_id })}
            ><b>{index ? String(index + 1).padStart(2, '0') : 'NEXT'}</b><i>P{job.priority}</i>
            <div>
              <strong>{job.task_label}</strong><small
                >{job.team_name || 'Unassigned'} · {job.role} · {job.action.replaceAll(
                  '_',
                  ' '
                )}</small
              >
            </div></a
          >{:else}<div class="empty">No queued work.</div>{/each}
      </article>
      <article class="panel dependencies">
        <header>
          <div>
            <span>DEPENDENCIES</span>
            <h2>System health</h2>
          </div>
        </header>
        <div>
          {#each dashboard.health as check (check.name)}<article>
              <i class={check.status.toLowerCase()}></i>
              <div><b>{check.name}</b><small>{check.message}</small></div>
              <span>{check.status.replaceAll('_', ' ')}</span>
            </article>{/each}
        </div>
      </article>
    </section>
    {#if telemetry}
      <section class="panel telemetry">
        <header>
          <div>
            <span>SERVER TELEMETRY</span>
            <h2>Runtime resources</h2>
          </div>
          <small>5 SECOND LIVE SAMPLE</small>
        </header>
        <div>
          {#each [['CPU', telemetry.cpu_percent], ['MEMORY', telemetry.memory_percent], ['DISK', telemetry.disk_percent]] as meter (meter[0])}
            <article>
              <div class="telemetry-ring" style={`--meter:${Number(meter[1]) * 3.6}deg`}>
                <b>{Number(meter[1]).toFixed(0)}%</b>
              </div>
              <span>{meter[0]}</span>{#if meter[0] === 'MEMORY'}<small
                  >{compact.format(telemetry.memory_used_bytes)} / {compact.format(
                    telemetry.memory_total_bytes
                  )}</small
                >{:else if meter[0] === 'DISK'}<small
                  >{compact.format(telemetry.disk_used_bytes)} / {compact.format(
                    telemetry.disk_total_bytes
                  )}</small
                >{:else}<small>Load {telemetry.load_average?.[0].toFixed(2) ?? '—'}</small>{/if}
            </article>
          {/each}
        </div>
      </section>
    {/if}
  {/if}
</main>

<style>
  .cockpit {
    max-width: 1500px;
    margin: auto;
    padding: 1.25rem;
    display: grid;
    gap: 1.25rem;
  }
  .toolbar,
  .section-title,
  .panel > header,
  .worker > header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .live {
    font: 700 0.65rem var(--font-mono);
    letter-spacing: 0.14em;
    color: var(--color-muted);
  }
  .live i {
    display: inline-block;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #ef4444;
    margin-right: 0.5rem;
  }
  .live i.connected {
    background: #4ade80;
    box-shadow: 0 0 10px #4ade80;
  }
  .periods {
    display: flex;
    border: 1px solid var(--color-line);
    padding: 0.2rem;
    border-radius: 0.6rem;
  }
  .periods button {
    padding: 0.4rem 0.65rem;
    border-radius: 0.4rem;
    font-size: 0.7rem;
    color: var(--color-muted);
  }
  .periods .active {
    background: var(--color-brand);
    color: white;
  }
  .panel,
  .metric,
  .health,
  .team {
    border: 1px solid var(--color-line);
    border-radius: 1rem;
    background: var(--color-panel);
  }
  .metrics {
    display: grid;
    grid-template-columns: 1.2fr repeat(5, 1fr);
    gap: 0.7rem;
  }
  .metric {
    min-height: 122px;
    padding: 1rem;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
  }
  .metric span,
  .panel header span,
  .section-title span {
    font: 700 0.6rem var(--font-mono);
    letter-spacing: 0.13em;
    color: var(--color-muted);
  }
  .metric strong {
    font: 700 2rem var(--font-mono);
  }
  .metric small {
    font-size: 0.6rem;
    color: var(--color-muted);
  }
  .metric.green strong {
    color: #4ade80;
  }
  .metric.cyan strong,
  .cyan-text {
    color: #3fd8ff;
  }
  .metric.danger {
    border-color: #ef444477;
  }
  .health {
    padding: 0.8rem;
    display: flex;
    align-items: center;
    gap: 0.8rem;
  }
  .health > small {
    writing-mode: vertical-rl;
    font: 700 0.55rem var(--font-mono);
    color: var(--color-muted);
  }
  .gauge {
    --value: 0deg;
    width: 88px;
    aspect-ratio: 1;
    border-radius: 50%;
    display: grid;
    place-items: center;
    background: conic-gradient(#4ade80 var(--value), var(--color-line) 0);
    position: relative;
  }
  .gauge:before {
    content: '';
    position: absolute;
    inset: 7px;
    background: var(--color-panel);
    border-radius: 50%;
  }
  .gauge span {
    z-index: 1;
    text-align: center;
    font: 700 0.5rem var(--font-mono);
    color: #4ade80;
  }
  .gauge b {
    display: block;
    font-size: 1.15rem;
    color: var(--color-text);
  }
  .split {
    display: grid;
    grid-template-columns: minmax(360px, 0.8fr) 1.3fr;
    gap: 1.25rem;
  }
  .panel {
    padding: 1rem;
  }
  .panel header h2,
  .section-title h2 {
    font-size: 1.05rem;
    font-weight: 800;
  }
  .panel header small,
  .section-title a {
    font: 0.58rem var(--font-mono);
    color: var(--color-muted);
  }
  .worker {
    background: radial-gradient(circle at 50% 35%, #b26bff18, transparent 45%), var(--color-panel);
  }
  .worker header > i {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--color-muted);
  }
  .worker header > i.running {
    background: #3fd8ff;
    box-shadow: 0 0 12px #3fd8ff;
  }
  .worker-core {
    text-align: center;
    padding: 1.1rem;
  }
  .orb {
    width: 75px;
    height: 75px;
    margin: auto;
    display: grid;
    place-items: center;
    border: 9px solid #b26bff15;
    outline: 1px solid #b26bff66;
    border-radius: 50%;
    font: 800 1.2rem var(--font-mono);
    color: var(--color-brand);
  }
  .worker-core small {
    font: 0.55rem var(--font-mono);
    color: var(--color-brand);
  }
  .worker-core h2 {
    font-size: 1.15rem;
    font-weight: 800;
  }
  .worker-core p {
    font-size: 0.65rem;
    color: var(--color-muted);
  }
  .worker > a {
    display: grid;
    padding: 0.7rem;
    border: 1px solid var(--color-line);
    border-radius: 0.6rem;
  }
  .worker > a small {
    font-size: 0.55rem;
    color: var(--color-muted);
  }
  .worker > a b {
    font-size: 0.75rem;
  }
  .worker footer,
  .team-stats {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    margin-top: 0.8rem;
  }
  .worker footer div {
    text-align: center;
    border-right: 1px solid var(--color-line);
  }
  .worker footer span,
  .worker footer b {
    display: block;
    font: 0.55rem var(--font-mono);
  }
  .worker footer span {
    color: var(--color-muted);
  }
  .events {
    max-height: 350px;
    overflow: auto;
    margin-top: 0.7rem;
  }
  .events > a {
    display: grid;
    grid-template-columns: 60px 8px 1fr;
    gap: 0.6rem;
    padding: 0.6rem 0;
    border-top: 1px solid var(--color-line);
  }
  .events time {
    font: 0.58rem var(--font-mono);
    color: var(--color-muted);
  }
  .events > a > i {
    width: 6px;
    height: 6px;
    margin-top: 0.2rem;
    border-radius: 50%;
    background: #3fd8ff;
  }
  .events i.warning {
    background: #f59e0b;
  }
  .events i.error {
    background: #ef4444;
  }
  .events b {
    font-size: 0.68rem;
  }
  .events p,
  .events small {
    font-size: 0.6rem;
    color: var(--color-muted);
  }
  .section-title {
    margin-top: 0.7rem;
  }
  .teams {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 0.8rem;
  }
  .team {
    padding: 1rem;
  }
  .team header {
    display: flex;
    gap: 0.7rem;
    align-items: center;
  }
  .avatar {
    width: 38px;
    height: 38px;
    display: grid;
    place-items: center;
    border-radius: 0.6rem;
    background: #3fd8ff15;
    color: #3fd8ff;
    font: 800 0.7rem var(--font-mono);
  }
  .team h3 {
    font-size: 0.82rem;
    font-weight: 800;
  }
  .team header span {
    font: 0.52rem var(--font-mono);
    color: var(--color-muted);
  }
  .team header .working {
    color: #3fd8ff;
  }
  .team header .needs_human {
    color: #f59e0b;
  }
  .current {
    display: grid;
    margin: 0.8rem 0;
    padding: 0.65rem;
    border-radius: 0.6rem;
    background: var(--color-soft);
  }
  .current small,
  .current span {
    font-size: 0.55rem;
    color: var(--color-muted);
  }
  .current b {
    font-size: 0.72rem;
  }
  .team-stats {
    grid-template-columns: repeat(4, 1fr);
  }
  .team-stats div {
    text-align: center;
  }
  .team-stats b,
  .team-stats small {
    display: block;
  }
  .team-stats b {
    font: 0.72rem var(--font-mono);
  }
  .team-stats small {
    font-size: 0.48rem;
    color: var(--color-muted);
  }
  .team > a {
    display: block;
    margin-top: 0.8rem;
    font: 0.55rem var(--font-mono);
    color: var(--color-brand);
  }
  .bars {
    height: 175px;
    display: flex;
    align-items: end;
    gap: 0.4rem;
    padding-top: 0.8rem;
  }
  .bars > div {
    flex: 1;
    text-align: center;
  }
  .bars > div > div {
    height: 145px;
    display: flex;
    align-items: end;
    justify-content: center;
    gap: 2px;
  }
  .bars i {
    width: 35%;
    min-height: 2px;
    border-radius: 3px 3px 0 0;
  }
  .bars .done {
    background: #4ade80;
  }
  .bars .failed {
    background: #ef4444;
  }
  .bars small {
    font: 0.48rem var(--font-mono);
    color: var(--color-muted);
  }
  .chart footer {
    display: flex;
    gap: 1rem;
    font-size: 0.58rem;
    color: #4ade80;
  }
  .chart footer .red {
    color: #ef4444;
  }
  .usage > div {
    display: grid;
    gap: 0.75rem;
    margin-top: 1rem;
  }
  .usage-row {
    display: grid;
    grid-template-columns: 80px 1fr 50px;
    gap: 0.6rem;
    align-items: center;
    font-size: 0.6rem;
  }
  .usage-row > div {
    height: 6px;
    background: var(--color-line);
    border-radius: 5px;
    overflow: hidden;
  }
  .usage-row i {
    display: block;
    height: 100%;
    background: linear-gradient(90deg, var(--color-brand), #3fd8ff);
  }
  .usage-row > b {
    text-align: right;
    font-family: var(--font-mono);
  }
  .queue > a {
    display: grid;
    grid-template-columns: 38px 28px 1fr;
    gap: 0.5rem;
    padding: 0.65rem 0;
    border-top: 1px solid var(--color-line);
    align-items: center;
  }
  .queue > a > b,
  .queue > a > i {
    font: 0.55rem var(--font-mono);
    color: var(--color-muted);
  }
  .queue > a > i {
    color: var(--color-brand);
  }
  .queue > a div {
    display: grid;
  }
  .queue strong {
    font-size: 0.68rem;
  }
  .queue small {
    font-size: 0.55rem;
    color: var(--color-muted);
  }
  .dependencies > div {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 0.5rem;
    margin-top: 0.8rem;
  }
  .dependencies article {
    display: grid;
    grid-template-columns: 7px 1fr auto;
    gap: 0.5rem;
    align-items: center;
    padding: 0.6rem;
    border: 1px solid var(--color-line);
    border-radius: 0.55rem;
  }
  .dependencies article > i {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--color-muted);
  }
  .dependencies i.healthy {
    background: #4ade80;
  }
  .dependencies i.degraded {
    background: #f59e0b;
  }
  .dependencies i.critical {
    background: #ef4444;
  }
  .dependencies article div {
    display: grid;
  }
  .dependencies b {
    font-size: 0.66rem;
  }
  .dependencies small,
  .dependencies article > span {
    font-size: 0.5rem;
    color: var(--color-muted);
  }
  .empty {
    padding: 2rem;
    text-align: center;
    color: var(--color-muted);
    font: 0.65rem var(--font-mono);
  }
  .telemetry > div {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1rem;
    margin-top: 1rem;
  }
  .telemetry article {
    text-align: center;
  }
  .telemetry-ring {
    --meter: 0deg;
    width: 90px;
    aspect-ratio: 1;
    margin: auto;
    display: grid;
    place-items: center;
    border-radius: 50%;
    background:
      radial-gradient(circle, var(--color-panel) 61%, transparent 63%),
      conic-gradient(#3fd8ff var(--meter), var(--color-line) 0);
  }
  .telemetry-ring b {
    font: 700 1rem var(--font-mono);
  }
  .telemetry article > span,
  .telemetry article > small {
    display: block;
    margin-top: 0.4rem;
    font: 0.6rem var(--font-mono);
    color: var(--color-muted);
  }
  @media (max-width: 1100px) {
    .metrics {
      grid-template-columns: repeat(3, 1fr);
    }
    .split {
      grid-template-columns: 1fr;
    }
  }
  @media (max-width: 640px) {
    .cockpit {
      padding: 0.7rem;
    }
    .metrics {
      grid-template-columns: 1fr 1fr;
    }
    .health {
      grid-column: span 2;
    }
    .teams,
    .dependencies > div {
      grid-template-columns: 1fr;
    }
    .toolbar {
      align-items: flex-start;
    }
  }
</style>
