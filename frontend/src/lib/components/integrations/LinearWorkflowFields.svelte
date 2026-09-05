<script lang="ts">
  import Button from '$lib/components/Button.svelte';
  import TextField from '$lib/components/TextField.svelte';
  import Select from '$lib/components/Select.svelte';
  import type { LinearWorkflowState, Repository } from '$lib/types';

  let {
    triggerLabel = $bindable(),
    repositoryId = $bindable(),
    todoStateId = $bindable(),
    inProgressStateId = $bindable(),
    inReviewStateId = $bindable(),
    blockedStateId = $bindable(),
    readyForTestingStateId = $bindable(),
    doneStateId = $bindable(),
    repositories,
    linearStates,
    loadingLinearStates,
    hasCredentials,
    onDiscoverStates
  }: {
    triggerLabel: string;
    repositoryId: string;
    todoStateId: string;
    inProgressStateId: string;
    inReviewStateId: string;
    blockedStateId: string;
    readyForTestingStateId: string;
    doneStateId: string;
    repositories: Repository[];
    linearStates: LinearWorkflowState[];
    loadingLinearStates: boolean;
    hasCredentials: boolean;
    onDiscoverStates: () => void;
  } = $props();
</script>

<div class="mt-3 space-y-2">
  <TextField id="linear-trigger-label" label="Trigger label" bind:value={triggerLabel} required />
  <Select id="linear-repository" label="Repository for new tasks" bind:value={repositoryId}>
    <option value="">No automatic repository</option>
    {#each repositories as repository (repository.id)}<option value={repository.id}
        >{repository.owner}/{repository.name}</option
      >{/each}
  </Select>
</div>
<div class="mt-3 flex flex-wrap items-end justify-between gap-3">
  <label class="text-muted block text-xs" for="linear-ready-state"
    >Ready for Testing workflow state</label
  >
  <Button size="sm" disabled={loadingLinearStates || !hasCredentials} onclick={onDiscoverStates}
    >{loadingLinearStates ? 'Loading…' : 'Discover states'}</Button
  >
</div>
<div class="mt-3 grid gap-3 sm:grid-cols-2">
  <Select id="linear-todo-state" label="Todo state" bind:value={todoStateId}>
    <option value="">Do not synchronize</option>
    {#each linearStates as state (state.id)}<option value={state.id}
        >{state.team_key || state.team_name} — {state.name}</option
      >{/each}
  </Select>
  <Select id="linear-progress-state" label="In Progress state" bind:value={inProgressStateId}>
    <option value="">Do not synchronize</option>
    {#each linearStates as state (state.id)}<option value={state.id}
        >{state.team_key || state.team_name} — {state.name}</option
      >{/each}
  </Select>
  <Select id="linear-blocked-state" label="Blocked state" bind:value={blockedStateId}>
    <option value="">Do not synchronize</option>
    {#each linearStates as state (state.id)}<option value={state.id}
        >{state.team_key || state.team_name} — {state.name}</option
      >{/each}
  </Select>
  <Select id="linear-done-state" label="Done state" bind:value={doneStateId}>
    <option value="">Do not synchronize</option>
    {#each linearStates as state (state.id)}<option value={state.id}
        >{state.team_key || state.team_name} — {state.name}</option
      >{/each}
  </Select>
</div>
<div class="mt-3">
  {#if linearStates.length > 0}
    <Select
      id="linear-in-review-state"
      label="In Review workflow state"
      bind:value={inReviewStateId}
    >
      <option value="">Do not update after PR publication</option>
      {#each linearStates as state (state.id)}
        <option value={state.id}>{state.team_key || state.team_name} — {state.name}</option>
      {/each}
    </Select>
  {:else}
    <TextField
      id="linear-in-review-state"
      label="In Review workflow state"
      bind:value={inReviewStateId}
      placeholder="Save credentials, then discover states"
    />
  {/if}
</div>
<div class="mt-3">
  {#if linearStates.length > 0}
    <Select id="linear-ready-state" bind:value={readyForTestingStateId}>
      <option value="">Do not update after merge</option>
      {#each linearStates as state (state.id)}
        <option value={state.id}>{state.team_key || state.team_name} — {state.name}</option>
      {/each}
    </Select>
  {:else}
    <TextField
      id="linear-ready-state"
      bind:value={readyForTestingStateId}
      placeholder="Save credentials, then discover states"
    />
  {/if}
</div>
