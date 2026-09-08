<script lang="ts">
  import { onMount } from 'svelte';
  import {
    getAutomation,
    saveAutomation,
    type AutomationPolicy
  } from '$lib/services/engineering-v2';
  let { teamId }: { teamId: string } = $props();
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
        policy = { ...value, reviewer_scope: value.reviewer_scope ?? 'allowlist' };
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
      message = 'Policy saved. Task usage and native sessions are unchanged.';
    } catch (error) {
      message = String(error);
    } finally {
      busy = false;
    }
  }
</script>

<section>
  <h2>Automation and merge policy</h2>
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
        automatically</label
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
        ><input type="checkbox" bind:checked={policy.auto_merge} /> Auto-merge after approval of the current
        commit and green CI</label
      >
      <label
        >Who can approve on GitHub?<select bind:value={policy.reviewer_scope}>
          <option value="allowlist">Listed reviewers</option>
          <option value="any_human">Any human commenter (including the PR author)</option>
        </select></label
      >
      <label
        >{policy.reviewer_scope === 'allowlist'
          ? 'Authorized GitHub reviewer numeric IDs (not logins)'
          : 'GitHub IDs allowed to pause, resume or cancel tasks (optional)'}<textarea
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
        review approval</label
      >
      <p>
        When formal approval is off, human comments such as “LGTM” or “ready to merge” can approve
        the PR. Other wording uses the configured Interpreter; uncertain messages need
        clarification. Bots cannot approve. The comment must follow validation of the current commit
        and remain unchanged. Required CI checks and blocking reviews are checked again before
        merge.
      </p>
      <button disabled={busy}>Save policy</button>
    </form>
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
  select,
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
</style>
