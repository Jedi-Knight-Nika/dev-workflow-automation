<script lang="ts">
  import Button from '$lib/components/Button.svelte';
  import TextField from '$lib/components/TextField.svelte';
  import Select from '$lib/components/Select.svelte';
  import type { LinearWorkflowState, Repository } from '$lib/types';
  import { t } from '$lib/i18n/index.svelte';

  let {
    assigneeId = $bindable(),
    sourceStateIds = $bindable(),
    linearMembers,
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
    assigneeId: string;
    sourceStateIds: string[];
    linearMembers: { id: string; name: string; active: boolean }[];
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
  <label class="block text-sm" for="linear-assignee">Import tasks assigned to</label>
  {#if linearMembers.length}
    <select id="linear-assignee" class="input w-full" bind:value={assigneeId}>
      <option value="">Select a member</option>
      {#each linearMembers.filter((member) => member.active) as member (member.id)}
        <option value={member.id}>{member.name}</option>
      {/each}
    </select>
  {:else}
    <TextField id="linear-assignee" bind:value={assigneeId} placeholder="Discover members and states, or enter a member ID" />
  {/if}
  <fieldset class="space-y-2 rounded border border-line p-3">
    <legend class="text-sm">Import from these states</legend>
    {#each linearStates as state (state.id)}
      <label class="flex items-center gap-2 text-sm"><input type="checkbox" value={state.id} bind:group={sourceStateIds} />{state.team_key || state.team_name} — {state.name}</label>
    {:else}<p class="text-xs text-muted">Discover states after saving credentials. No tasks are imported until a member and source states are selected.</p>{/each}
  </fieldset>
  <Select
    id="linear-repository"
    label={t('integrations.repositoryForNewTasks')}
    bind:value={repositoryId}
  >
    <option value="">{t('integrations.noAutomaticRepository')}</option>
    {#each repositories as repository (repository.id)}<option value={repository.id}
        >{repository.owner}/{repository.name}</option
      >{/each}
  </Select>
</div>
<div class="mt-3 flex flex-wrap items-end justify-between gap-3">
  <label class="text-muted block text-xs" for="linear-ready-state"
    >{t('integrations.readyForTestingState')}</label
  >
  <Button size="sm" disabled={loadingLinearStates || !hasCredentials} onclick={onDiscoverStates}
    >{loadingLinearStates ? t('common.loading') : t('integrations.discoverStates')}</Button
  >
</div>
<div class="mt-3 grid gap-3 sm:grid-cols-2">
  <Select id="linear-todo-state" label={t('integrations.todoState')} bind:value={todoStateId}>
    <option value="">{t('integrations.doNotSynchronize')}</option>
    {#each linearStates as state (state.id)}<option value={state.id}
        >{state.team_key || state.team_name} — {state.name}</option
      >{/each}
  </Select>
  <Select
    id="linear-progress-state"
    label={t('integrations.inProgressState')}
    bind:value={inProgressStateId}
  >
    <option value="">{t('integrations.doNotSynchronize')}</option>
    {#each linearStates as state (state.id)}<option value={state.id}
        >{state.team_key || state.team_name} — {state.name}</option
      >{/each}
  </Select>
  <Select
    id="linear-blocked-state"
    label={t('integrations.blockedState')}
    bind:value={blockedStateId}
  >
    <option value="">{t('integrations.doNotSynchronize')}</option>
    {#each linearStates as state (state.id)}<option value={state.id}
        >{state.team_key || state.team_name} — {state.name}</option
      >{/each}
  </Select>
  <Select id="linear-done-state" label={t('integrations.doneState')} bind:value={doneStateId}>
    <option value="">{t('integrations.doNotSynchronize')}</option>
    {#each linearStates as state (state.id)}<option value={state.id}
        >{state.team_key || state.team_name} — {state.name}</option
      >{/each}
  </Select>
</div>
<div class="mt-3">
  {#if linearStates.length > 0}
    <Select
      id="linear-in-review-state"
      label={t('integrations.inReviewState')}
      bind:value={inReviewStateId}
    >
      <option value="">{t('integrations.doNotUpdateAfterPr')}</option>
      {#each linearStates as state (state.id)}
        <option value={state.id}>{state.team_key || state.team_name} — {state.name}</option>
      {/each}
    </Select>
  {:else}
    <TextField
      id="linear-in-review-state"
      label={t('integrations.inReviewState')}
      bind:value={inReviewStateId}
      placeholder={t('integrations.saveCredentialsThenDiscover')}
    />
  {/if}
</div>
<div class="mt-3">
  {#if linearStates.length > 0}
    <Select id="linear-ready-state" bind:value={readyForTestingStateId}>
      <option value="">{t('integrations.doNotUpdateAfterMerge')}</option>
      {#each linearStates as state (state.id)}
        <option value={state.id}>{state.team_key || state.team_name} — {state.name}</option>
      {/each}
    </Select>
  {:else}
    <TextField
      id="linear-ready-state"
      bind:value={readyForTestingStateId}
      placeholder={t('integrations.saveCredentialsThenDiscover')}
    />
  {/if}
</div>
