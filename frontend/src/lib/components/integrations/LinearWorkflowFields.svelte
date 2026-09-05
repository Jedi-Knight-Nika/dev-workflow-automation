<script lang="ts">
  import Button from '$lib/components/Button.svelte';
  import TextField from '$lib/components/TextField.svelte';
  import Select from '$lib/components/Select.svelte';
  import type { LinearWorkflowState, Repository } from '$lib/types';
  import { t } from '$lib/i18n/index.svelte';

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
  <TextField
    id="linear-trigger-label"
    label={t('integrations.triggerLabel')}
    bind:value={triggerLabel}
    required
  />
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
