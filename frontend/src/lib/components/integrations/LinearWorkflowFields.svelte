<script lang="ts">
  import Button from '$lib/components/Button.svelte';
  import TextField from '$lib/components/TextField.svelte';
  import Select from '$lib/components/Select.svelte';
  import DestinationSelect from './DestinationSelect.svelte';
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
  const destinations = $derived(
    linearStates.map((state) => ({
      id: state.id,
      name: `${(state.team_key || state.team_name) ?? ''} — ${state.name ?? ''}`
    }))
  );
</script>

<div class="mt-3 space-y-2">
  {#if linearMembers.length}
    <Select id="linear-assignee" label="Import tasks assigned to" bind:value={assigneeId}>
      <option value="">Select a member</option>
      {#each linearMembers.filter((member) => member.active) as member (member.id)}
        <option value={member.id}>{member.name}</option>
      {/each}
    </Select>
  {:else}
    <TextField
      id="linear-assignee"
      label="Import tasks assigned to"
      bind:value={assigneeId}
      placeholder="Discover members and states, or enter a member ID"
    />
  {/if}
  <fieldset class="space-y-2 rounded border border-line p-3">
    <legend class="text-sm">Import from these states</legend>
    {#each linearStates as state (state.id)}
      <label class="flex items-center gap-2 text-sm"
        ><input type="checkbox" value={state.id} bind:group={sourceStateIds} />{state.team_key ||
          state.team_name} — {state.name}</label
      >
    {:else}<p class="text-xs text-muted">
        Discover states after saving credentials. No tasks are imported until a member and source
        states are selected.
      </p>{/each}
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
  <DestinationSelect
    id="linear-todo-state"
    label={t('integrations.todoState')}
    bind:value={todoStateId}
    {destinations}
    emptyLabel={t('integrations.doNotSynchronize')}
  />
  <DestinationSelect
    id="linear-progress-state"
    label={t('integrations.inProgressState')}
    bind:value={inProgressStateId}
    {destinations}
    emptyLabel={t('integrations.doNotSynchronize')}
  />
  <DestinationSelect
    id="linear-blocked-state"
    label={t('integrations.blockedState')}
    bind:value={blockedStateId}
    {destinations}
    emptyLabel={t('integrations.doNotSynchronize')}
  />
  <DestinationSelect
    id="linear-done-state"
    label={t('integrations.doneState')}
    bind:value={doneStateId}
    {destinations}
    emptyLabel={t('integrations.doNotSynchronize')}
  />
</div>
<div class="mt-3">
  {#if linearStates.length > 0}
    <DestinationSelect
      id="linear-in-review-state"
      label={t('integrations.inReviewState')}
      bind:value={inReviewStateId}
      {destinations}
      emptyLabel={t('integrations.doNotUpdateAfterPr')}
    />
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
    <DestinationSelect
      id="linear-ready-state"
      bind:value={readyForTestingStateId}
      {destinations}
      emptyLabel={t('integrations.doNotUpdateAfterMerge')}
    />
  {:else}
    <TextField
      id="linear-ready-state"
      bind:value={readyForTestingStateId}
      placeholder={t('integrations.saveCredentialsThenDiscover')}
    />
  {/if}
</div>
