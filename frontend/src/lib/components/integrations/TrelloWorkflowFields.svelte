<script lang="ts">
  import Button from '$lib/components/Button.svelte';
  import TextField from '$lib/components/TextField.svelte';
  import Select from '$lib/components/Select.svelte';
  import DestinationSelect from './DestinationSelect.svelte';
  import type { Repository, TrelloBoard, TrelloList } from '$lib/types';
  import { t } from '$lib/i18n/index.svelte';

  let {
    apiKey = $bindable(),
    token = $bindable(),
    boardId = $bindable(),
    listIds = $bindable(),
    todoListId = $bindable(),
    inProgressListId = $bindable(),
    inReviewListId = $bindable(),
    blockedListId = $bindable(),
    readyForTestingListId = $bindable(),
    doneListId = $bindable(),
    repositoryId = $bindable(),
    repositories,
    boards,
    lists,
    loading,
    saving,
    verifying,
    hasCredentials,
    connected,
    onDiscoverBoards,
    onDiscoverLists,
    onContinueSetup
  }: {
    apiKey: string;
    token: string;
    boardId: string;
    listIds: string[];
    todoListId: string;
    inProgressListId: string;
    inReviewListId: string;
    blockedListId: string;
    readyForTestingListId: string;
    doneListId: string;
    repositoryId: string;
    repositories: Repository[];
    boards: TrelloBoard[];
    lists: TrelloList[];
    loading: boolean;
    saving: boolean;
    verifying: boolean;
    hasCredentials: boolean;
    connected: boolean;
    onDiscoverBoards: () => void;
    onDiscoverLists: () => void;
    onContinueSetup: () => void;
  } = $props();

  function toggleList(id: string, checked: boolean) {
    listIds = checked ? Array.from(new Set([...listIds, id])) : listIds.filter((v) => v !== id);
  }
</script>

<div class="space-y-3">
  <div class="border-brand/30 bg-brand/5 rounded-lg border p-3 text-xs">
    <p class="font-semibold">Trello requires two credentials</p>
    <p class="text-muted mt-1 leading-relaxed">
      Use the API key generated for a Trello app, then generate its Trello user token. An Atlassian
      account API token is different and will not work here.
    </p>
    <a
      class="mt-2 inline-block font-medium text-brand hover:underline"
      href="https://trello.com/apps/admin"
      target="_blank"
      rel="noreferrer">Open Trello App Admin →</a
    >
  </div>
  <TextField
    id="trello-api-key"
    label={`${t('integrations.trelloApiKey')} ${hasCredentials ? t('integrations.keepExisting') : ''}`}
    type="password"
    bind:value={apiKey}
    autocomplete="off"
    required={!hasCredentials}
  />
  <TextField
    id="trello-token"
    label={t('integrations.trelloToken')}
    type="password"
    bind:value={token}
    autocomplete="off"
    required={!hasCredentials}
  />
  <Button
    type="button"
    size="sm"
    onclick={onDiscoverBoards}
    disabled={saving || loading || !connected || !!apiKey || !!token}
  >
    {loading ? t('common.loading') : t('integrations.trelloDiscoverBoards')}
  </Button>
  <Button
    type="button"
    variant="primary"
    onclick={onContinueSetup}
    disabled={saving || loading || (!hasCredentials && (!apiKey || !token))}
    >{verifying
      ? t('integrations.verifyingCredentials')
      : t('integrations.verifyAndContinue')}</Button
  >
  <Select
    id="trello-board"
    label={t('integrations.trelloBoard')}
    bind:value={boardId}
    onchange={onDiscoverLists}
  >
    <option value="">{t('integrations.trelloSelectBoard')}</option>
    {#each boards as board (board.id)}<option value={board.id}>{board.name}</option>{/each}
  </Select>
  {#if lists.length}
    <fieldset class="space-y-2">
      <legend class="text-muted text-xs">{t('integrations.trelloSourceLists')}</legend>
      {#each lists as list (list.id)}
        <label class="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={listIds.includes(list.id)}
            onchange={(event) => toggleList(list.id, event.currentTarget.checked)}
          />
          {list.name}
        </label>
      {/each}
    </fieldset>
    <fieldset class="grid gap-3 sm:grid-cols-2">
      <legend class="text-muted col-span-full text-xs">Workflow destination lists</legend>
      <DestinationSelect
        id="trello-todo-list"
        label="New / Todo"
        bind:value={todoListId}
        destinations={lists}
        emptyLabel="Do not move"
      />
      <DestinationSelect
        id="trello-progress-list"
        label="In progress"
        bind:value={inProgressListId}
        destinations={lists}
        emptyLabel="Do not move"
      />
      <DestinationSelect
        id="trello-review-list"
        label="In review"
        bind:value={inReviewListId}
        destinations={lists}
        emptyLabel="Do not move"
      />
      <DestinationSelect
        id="trello-blocked-list"
        label="Blocked / needs attention"
        bind:value={blockedListId}
        destinations={lists}
        emptyLabel="Do not move"
      />
      <DestinationSelect
        id="trello-ready-list"
        label="Ready for testing"
        bind:value={readyForTestingListId}
        destinations={lists}
        emptyLabel="Do not move"
      />
      <DestinationSelect
        id="trello-done-list"
        label="Done / cancelled"
        bind:value={doneListId}
        destinations={lists}
        emptyLabel="Do not move"
      />
    </fieldset>
  {/if}
  <Select
    id="trello-repository"
    label={t('integrations.repositoryForNewTasks')}
    bind:value={repositoryId}
  >
    <option value="">{t('integrations.noAutomaticRepository')}</option>
    {#each repositories as repository (repository.id)}<option value={repository.id}
        >{repository.owner}/{repository.name}</option
      >{/each}
  </Select>
  {#if !hasCredentials}<p class="text-muted text-[10px]">
      {t('integrations.trelloSaveThenDiscover')}
    </p>{/if}
</div>
