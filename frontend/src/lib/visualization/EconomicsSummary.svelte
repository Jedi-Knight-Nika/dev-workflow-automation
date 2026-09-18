<script lang="ts">
  import { money, title } from './format';
  import type { Economics } from './economics';
  let { economics }: { economics: Economics } = $props();
  let dimension = $state<'tasks' | 'teams' | 'roles' | 'models'>('tasks');
</script>

<details>
  <summary>AI usage comparisons</summary>
  <div class="content">
    <p>
      Receipts in this range through the playhead. Runs and provider request attempts are counted
      separately. Older or native receipts may have unknown or partial request counts.
    </p>
    <select aria-label="Group AI usage" bind:value={dimension}
      ><option value="tasks">Tasks</option><option value="teams">Teams</option><option value="roles"
        >Roles</option
      ><option value="models">Models</option></select
    >
    <table>
      <thead
        ><tr
          ><th>{title(dimension)}</th><th>Receipts</th><th>Runs / settled</th><th
            >Provider requests</th
          ><th>Input / output tokens</th></tr
        ></thead
      ><tbody>
        {#each economics[dimension] as group (group.id)}<tr
            ><td>{group.label}</td><td
              >{money(group.cost)}{group.unknownCosts ? ` + ${group.unknownCosts} unknown` : ''}</td
            ><td>{group.calls} / {group.completedCalls}</td><td>
              {group.partialRequestRuns ? 'At least ' : ''}{group.providerRequests.toLocaleString()}
              {group.unknownRequestRuns ? ` + ${group.unknownRequestRuns} runs unknown` : ''}
              {group.partialRequestRuns ? ` (${group.partialRequestRuns} runs partial)` : ''}
            </td><td
              >{group.inputTokens.toLocaleString()} / {group.outputTokens.toLocaleString()}{group.incompleteUsage
                ? ' (partial)'
                : ''}</td
            ></tr
          >{/each}
      </tbody>
    </table>
    {#if economics.changes.length}<p>
        Recorded model changes within each task and role; these do not imply a quality or price
        escalation.
      </p>
      <ul>
        {#each economics.changes.slice(-20) as change, index (index)}<li>
            {change.task} · {change.role}: {change.before} → {change.after} · {new Date(
              change.at
            ).toLocaleString()}
          </li>{/each}
      </ul>{/if}
  </div>
</details>

<style>
  details {
    padding: 0.5rem 1rem;
    font-size: 0.73rem;
    border-top: 1px solid var(--color-line);
    flex-shrink: 0;
  }
  summary {
    cursor: pointer;
  }
  .content {
    max-height: 180px;
    overflow: auto;
  }
  p,
  ul {
    color: var(--color-muted);
    margin: 0.5rem 0;
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
  select {
    background: var(--color-panel);
    color: var(--color-text);
  }
</style>
