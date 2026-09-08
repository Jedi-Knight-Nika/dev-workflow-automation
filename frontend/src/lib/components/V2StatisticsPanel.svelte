<script lang="ts">
  import { onMount } from 'svelte';
  import { getV2Statistics, type V2Statistics } from '$lib/services/engineering-v2';
  let { teamId }: { teamId?: string } = $props();
  let data = $state<V2Statistics | null>(null);
  let error = $state('');
  let busy = $state(false);
  let disposed = false;
  async function refresh() {
    busy = true;
    try {
      const result = await getV2Statistics(teamId);
      if (!disposed) {
        data = result;
        error = '';
      }
    } catch (cause) {
      if (!disposed) error = String(cause);
    } finally {
      if (!disposed) busy = false;
    }
  }
  onMount(() => {
    void refresh();
    return () => {
      disposed = true;
    };
  });
  const duration = (ms: number | null) =>
    ms === null ? 'Unavailable' : `${(ms / 1000).toFixed(1)}s`;
</script>

<section>
  <header>
    <h2>V2 usage and phases · 30 days</h2>
    <button disabled={busy} onclick={refresh}>Refresh statistics</button>
  </header>
  <p>
    Native/API usage across the fixed workflow. Missing receipts or prices are unavailable, not
    zero. Local inference is separate from paid tokens.
  </p>
  {#if error}<p role="alert">{error}</p>{/if}
  {#if data}
    <div class="table-scroll">
      <table>
        <thead
          ><tr
            ><th>Role / model</th><th>Runs</th><th>Input / output tokens</th><th>Cost (USD)</th><th
              >Provider time</th
            ><th>Compactions</th></tr
          ></thead
        >
        <tbody
          >{#each data.cloud_runs as row (`${row.role}:${row.provider}:${row.model}`)}
            <tr
              ><td>{row.role} · {row.provider}/{row.model}</td><td>{row.attempts}</td><td
                >{row.input_tokens ?? 'Unknown'} / {row.output_tokens ??
                  'Unknown'}{#if row.incomplete_usage_runs}
                  ({row.incomplete_usage_runs} incomplete){/if}</td
              ><td
                >{row.cost_usd === null ? 'Unavailable' : `$${Number(row.cost_usd).toFixed(4)}`}</td
              ><td>{duration(row.provider_time_ms)}</td><td>{row.compactions}</td></tr
            >
          {:else}<tr><td colspan="6">No V2 cloud runs in this period.</td></tr>{/each}</tbody
        >
      </table>
    </div>
    {#each data.local_runs as row (row.model)}<p>
        Local {row.model}: {row.attempts} runs · {duration(row.duration_ms)} · {row.failed} failed
      </p>{/each}
    <details>
      <summary>Phase totals (completed durations; active time not included)</summary>
      {#each data.phases as row (`${row.stage}:${row.status}`)}<p>
          {row.stage} · {row.status}: {row.count} · {duration(
            row.finished_duration_seconds === null ? null : row.finished_duration_seconds * 1000
          )}
        </p>{/each}
    </details>
  {/if}
</section>

<style>
  section {
    padding: 1.25rem;
    border: 1px solid var(--border);
    border-radius: 1rem;
    margin-block: 1rem;
  }
  header {
    display: flex;
    gap: 1rem;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: center;
  }
  .table-scroll {
    overflow-x: auto;
  }
  table {
    width: 100%;
    border-collapse: collapse;
  }
  th,
  td {
    text-align: left;
    padding: 0.7rem;
    border-bottom: 1px solid var(--border);
  }
</style>
