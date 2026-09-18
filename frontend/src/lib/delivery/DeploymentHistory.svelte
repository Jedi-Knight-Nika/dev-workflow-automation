<script lang="ts">
  import { onDestroy } from 'svelte';
  import { SvelteURLSearchParams } from 'svelte/reactivity';
  import { api } from '$lib/api';
  import type { Repository } from '$lib/types';
  import { deploymentMetrics, type DeploymentEvidence } from './metrics';
  import DeploymentSummary from './DeploymentSummary.svelte';

  let { repositories }: { repositories: Repository[] } = $props();
  type History = {
    events: (DeploymentEvidence & { id: string; repository: string })[];
    truncated: boolean;
  };
  let history = $state<History | null>(null),
    error = $state(''),
    loading = $state(false);
  let repository = $state(''),
    days = $state(7),
    production = $state(false),
    open = $state(false);
  let controller: AbortController | undefined;
  const events = $derived(
    (history?.events ?? []).filter((event) => !production || event.production === true)
  );
  const metrics = $derived(deploymentMetrics(events));
  onDestroy(() => controller?.abort());

  async function refresh() {
    controller?.abort();
    const request = new AbortController();
    controller = request;
    loading = true;
    history = null;
    error = '';
    const end = new Date(),
      start = new Date(end.getTime() - days * 86400000);
    const params = new SvelteURLSearchParams({
      start: start.toISOString(),
      end: end.toISOString(),
      limit: '2000'
    });
    if (repository) params.set('repository_id', repository);
    try {
      const result = await api<History>(`/deployments?${params}`, { signal: request.signal });
      if (!request.signal.aborted) history = result;
    } catch (cause) {
      if (!request.signal.aborted) error = String(cause);
    } finally {
      if (!request.signal.aborted) loading = false;
    }
  }
</script>

<details
  class="space-y-3 rounded-xl border border-line p-5"
  ontoggle={(event) => {
    open = event.currentTarget.open;
    if (open && !history && !loading) void refresh();
    if (!open) {
      controller?.abort();
      loading = false;
    }
  }}
>
  <summary class="cursor-pointer font-semibold">Deployment history</summary>
  <form
    class="flex flex-wrap items-center gap-3"
    onsubmit={(event) => {
      event.preventDefault();
      void refresh();
    }}
  >
    <label class="text-sm"
      >Repository
      <select
        class="input"
        value={repository}
        onchange={(event) => {
          repository = event.currentTarget.value;
          void refresh();
        }}
      >
        <option value="">All repositories</option>
        {#each repositories as row (row.id)}<option value={row.id}>{row.owner}/{row.name}</option
          >{/each}
      </select>
    </label>
    <label class="text-sm"
      >Range
      <select
        class="input"
        value={days}
        onchange={(event) => {
          days = Number(event.currentTarget.value);
          void refresh();
        }}
        ><option value={7}>7 days</option><option value={30}>30 days</option><option value={90}
          >90 days</option
        ></select
      >
    </label>
    <label class="text-sm"
      ><input type="checkbox" bind:checked={production} /> Production only</label
    >
    <button class="btn-secondary" disabled={loading}>Refresh deployments</button>
  </form>
  {#if error}<p class="text-danger" role="alert">{error}</p>{/if}
  {#if loading}<p class="text-sm text-muted">Loading deployment history…</p>{/if}
  {#if history}
    {#if history.truncated}<p class="text-warning">
        History is incomplete. Select a shorter range or one repository; metrics cover the loaded
        observations.
      </p>{/if}
    <DeploymentSummary {metrics} />
    <div class="max-h-80 overflow-auto">
      <table class="w-full text-left text-xs">
        <thead
          ><tr
            ><th>Time</th><th>Repository</th><th>Environment</th><th>Deployment</th><th>Outcome</th
            ></tr
          ></thead
        >
        <tbody
          >{#each [...events].reverse() as event (event.id)}<tr>
              <td class="py-2">{new Date(event.occurred_at).toLocaleString()}</td><td
                >{event.repository}</td
              ><td>{event.environment}</td><td>{event.deployment_id}</td><td
                >{event.status.toLowerCase().replaceAll('_', ' ')}</td
              >
            </tr>{/each}</tbody
        >
      </table>
    </div>
    {#if !events.length}<p class="text-sm text-muted">
        No deployment observations in this range. History appears when GitHub deployment events
        arrive.
      </p>{/if}
  {/if}
</details>
