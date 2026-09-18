<script lang="ts">
  import type { WorkPlanSnapshot } from './types';
  let { snapshots }: { snapshots: WorkPlanSnapshot[] } = $props();
  let chosen = $state('');
  const current = $derived(
    snapshots.find((snapshot) => snapshot.runId === chosen) ?? snapshots.at(-1)
  );
</script>

<details>
  <summary>Work-plan dependency history</summary>
  <div class="content">
    <p>
      Observed Developer plan snapshots through the playhead. Dependencies connect work units within
      a run; updates do not change the execution plan.
    </p>
    {#if current}
      <select
        aria-label="Work-plan run"
        value={current.runId}
        onchange={(event) => (chosen = event.currentTarget.value)}
        >{#each snapshots as snapshot (snapshot.runId)}<option value={snapshot.runId}
            >{snapshot.task} · {new Date(snapshot.at).toLocaleString()}</option
          >{/each}</select
      >
      {#each current.plans as plan (plan.revision)}<h4>Plan revision {plan.revision + 1}</h4>
        <table>
          <thead><tr><th>Unit</th><th>Recorded status</th><th>Depends on</th></tr></thead><tbody
            >{#each plan.units as unit (unit.id)}<tr
                ><td>{unit.id}</td><td>{unit.status.toLowerCase()}</td><td
                  >{unit.depends_on.map((index) => plan.units[index]?.id ?? 'unknown').join(', ') ||
                    'Independent'}</td
                ></tr
              >{/each}</tbody
          >
        </table>
      {/each}
    {:else}<p>No structured work-plan snapshots were recorded in this part of the replay.</p>{/if}
  </div>
</details>

<style>
  details {
    padding: 0.5rem 1rem;
    font-size: 0.73rem;
    flex-shrink: 0;
    border-top: 1px solid var(--color-line);
  }
  summary {
    cursor: pointer;
  }
  .content {
    max-height: 180px;
    overflow: auto;
  }
  p {
    color: var(--color-muted);
  }
  table {
    width: 100%;
    border-collapse: collapse;
  }
  th,
  td {
    text-align: left;
    padding: 0.35rem;
    border-bottom: 1px solid var(--color-line);
  }
  h4 {
    margin-top: 0.7rem;
  }
  select {
    background: var(--color-panel);
    color: var(--color-text);
  }
</style>
