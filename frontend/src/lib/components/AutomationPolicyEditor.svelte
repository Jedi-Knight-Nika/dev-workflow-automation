<script lang="ts">
  import { onMount } from 'svelte';
  import {
    getAutomation,
    saveAutomation,
    enrollTask,
    type AutomationPolicy,
    type EngineeringTask
  } from '$lib/services/engineering-v2';
  let { teamId, tasks }: { teamId: string; tasks: EngineeringTask[] } = $props();
  let policy = $state<AutomationPolicy | null>(null);
  let repositories = $state('');
  let reviewers = $state('');
  let checks = $state('');
  let message = $state('');
  let busy = $state(false);
  const split = (value: string) =>
    value
      .split(/[\n,]/)
      .map((item) => item.trim())
      .filter(Boolean);
  onMount(() => {
    let disposed = false;
    void getAutomation(teamId)
      .then((value) => {
        if (disposed) return;
        policy = value;
        repositories = value.repository_ids.join('\n');
        reviewers = value.authorized_reviewer_ids.join('\n');
        checks = value.required_checks.join('\n');
      })
      .catch((error) => {
        if (!disposed) message = String(error);
      });
    return () => {
      disposed = true;
    };
  });
  async function save() {
    if (!policy) return;
    busy = true;
    try {
      const result = await saveAutomation(teamId, {
        ...policy,
        repository_ids: split(repositories),
        authorized_reviewer_ids: split(reviewers),
        required_checks: split(checks)
      });
      policy.version = result.version;
      message = 'Policy saved. Existing tickets were not migrated.';
    } catch (error) {
      message = String(error);
    } finally {
      busy = false;
    }
  }
  async function enroll(task: EngineeringTask) {
    if (
      !confirm(
        `Enroll “${task.title}” in V2? An enabled worker may start paid development under this Team’s configured USD budget.`
      )
    )
      return;
    busy = true;
    try {
      await enrollTask(task.id);
      message = 'Task enrolled; activity will refresh shortly.';
    } catch (error) {
      message = String(error);
    } finally {
      busy = false;
    }
  }
</script>

<section>
  <h2>V2 rollout and merge policy</h2>
  <p>
    Opt-in per Team and repository. Keep disabled until your isolated runtime and approved spending
    limits have been verified.
  </p>
  {#if message}<p role="status">{message}</p>{/if}
  {#if policy}
    <form
      onsubmit={(event) => {
        event.preventDefault();
        void save();
      }}
    >
      <label
        ><input type="checkbox" bind:checked={policy.enrollment_enabled} /> Enroll new eligible imports
        into V2</label
      >
      <label
        >Allowed repository UUIDs (one per line)<textarea bind:value={repositories} rows="3"
        ></textarea></label
      >
      <label
        >Task limit (USD)<input
          type="number"
          min="0.01"
          max="10000"
          step="0.01"
          bind:value={policy.task_budget_usd}
          required
        /></label
      >
      <label
        >Team cumulative limit (USD)<input
          type="number"
          min="0.01"
          max="10000"
          step="0.01"
          bind:value={policy.team_budget_usd}
          required
        /></label
      >
      <label
        ><input type="checkbox" bind:checked={policy.auto_merge} /> Auto-merge after current-SHA approval
        and green CI</label
      >
      <label
        >Authorized GitHub reviewer numeric IDs (not logins)<textarea
          bind:value={reviewers}
          rows="3"
        ></textarea></label
      >
      <label
        >Required CI check names (one per line)<textarea bind:value={checks} rows="3"
        ></textarea></label
      >
      <label
        ><input type="checkbox" bind:checked={policy.require_formal_approval} /> Require formal GitHub
        review approval (otherwise an authorized /lgtm with the exact current SHA is also accepted)</label
      >
      <p>
        Formal GitHub approval is required by default. Task text and AI output never grant merge
        authority. An in-flight provider request may finish before an interruption takes effect.
      </p>
      <button disabled={busy}>Save policy</button>
    </form>
    {#if policy.enrollment_enabled}
      <h3>Explicit enrollment</h3>
      <p>
        Only unstarted tickets without an existing workspace/PR are eligible. History is retained.
      </p>
      {#each tasks.filter((task) => task.execution_version !== 2) as task (task.id)}
        <div class="ticket">
          <span>{task.title}</span><button disabled={busy} onclick={() => enroll(task)}
            >Enroll in V2</button
          >
        </div>
      {/each}
    {/if}
  {/if}
</section>

<style>
  section {
    padding: 1.5rem;
    border: 1px solid var(--border);
    border-radius: 1rem;
    margin: 1rem 0;
  }
  form {
    display: grid;
    gap: 0.9rem;
    max-width: 48rem;
  }
  label {
    display: grid;
    gap: 0.4rem;
  }
  label:has(input[type='checkbox']) {
    display: flex;
    align-items: center;
  }
  textarea,
  input:not([type='checkbox']) {
    width: 100%;
    padding: 0.6rem;
    background: var(--surface);
    color: inherit;
    border: 1px solid var(--border);
    border-radius: 0.4rem;
  }
  button {
    padding: 0.6rem 1rem;
    cursor: pointer;
  }
  .ticket {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 1rem;
    padding: 0.5rem 0;
  }
</style>
