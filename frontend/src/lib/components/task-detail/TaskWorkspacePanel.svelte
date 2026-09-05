<script lang="ts">
  import Button from '$lib/components/Button.svelte';
  import type { Task } from '$lib/types';
  import { t } from '$lib/i18n/index.svelte';

  let {
    task,
    preparing,
    onPrepareWorkspace
  }: { task: Task; preparing: boolean; onPrepareWorkspace: () => void } = $props();
</script>

<section
  class="border-line flex flex-wrap items-center justify-between gap-3 rounded-xl border p-5 xl:col-span-2"
>
  <div>
    <strong>{t('taskDetail.gitWorkspace')}</strong>
    <p class="text-muted text-xs">
      {task.workspace_path ||
        (task.repository_id
          ? t('taskDetail.repoSelectedNotPrepared')
          : t('taskDetail.noRepositorySelected'))}
    </p>
    {#if task.branch_name}<p class="mt-1 font-mono text-[10px] text-brand">
        {task.branch_name} · {task.current_revision?.slice(0, 12)}
      </p>{/if}
    {#if task.pull_request_url}<!-- eslint-disable svelte/no-navigation-without-resolve -->
      <a
        class="mt-2 block text-xs text-brand underline"
        href={task.pull_request_url}
        target="_blank"
        rel="noreferrer">{t('taskDetail.pullRequest')} #{task.pull_request_number}</a
      ><!-- eslint-enable svelte/no-navigation-without-resolve -->{/if}
  </div>
  <Button disabled={!task.repository_id || preparing} onclick={onPrepareWorkspace}
    >{preparing
      ? t('taskDetail.preparing')
      : task.workspace_path
        ? t('taskDetail.refreshWorkspace')
        : t('taskDetail.prepareWorkspace')}</Button
  >
</section>
