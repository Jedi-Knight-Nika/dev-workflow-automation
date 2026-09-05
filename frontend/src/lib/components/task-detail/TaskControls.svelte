<script lang="ts">
  import Button from '$lib/components/Button.svelte';
  import type { Task } from '$lib/types';
  import { t } from '$lib/i18n/index.svelte';

  let {
    task,
    commanding,
    onEnqueue,
    onTaskCommand,
    onPublishPullRequest,
    onMergePullRequest,
    onRetryLinearSync
  }: {
    task: Task;
    commanding: boolean;
    onEnqueue: (role: 'THINKER' | 'EXECUTOR' | 'REVIEWER', action: string) => void;
    onTaskCommand: (command: 'pause' | 'cancel' | 'takeover' | 'resume') => void;
    onPublishPullRequest: () => void;
    onMergePullRequest: () => void;
    onRetryLinearSync: () => void;
  } = $props();
</script>

<section class="border-line flex flex-wrap items-center gap-2 rounded-xl border p-5 xl:col-span-2">
  <strong class="mr-auto">{t('taskDetail.controls')}</strong>
  {#if task.manual_takeover}<span
      class="rounded-full border border-warning/40 px-2.5 py-1 font-mono text-[10px] text-warning"
      >{t('taskDetail.manualControl')}</span
    >{/if}
  <Button
    disabled={commanding || task.manual_takeover}
    onclick={() => onEnqueue('THINKER', 'CREATE_PLAN')}>{t('taskDetail.plan')}</Button
  >
  <Button
    disabled={commanding || task.manual_takeover || !task.repository_id}
    onclick={() => onEnqueue('EXECUTOR', 'IMPLEMENT_PLAN')}>{t('taskDetail.implement')}</Button
  >
  <Button
    disabled={commanding || task.manual_takeover || !task.workspace_path}
    onclick={() => onEnqueue('REVIEWER', 'REVIEW_CHANGES')}>{t('taskDetail.review')}</Button
  >
  <Button
    disabled={commanding || task.manual_takeover || !task.workspace_path}
    onclick={onPublishPullRequest}
    >{task.pull_request_number ? t('taskDetail.updatePr') : t('taskDetail.publishPr')}</Button
  >
  <Button
    variant="success"
    disabled={commanding ||
      task.manual_takeover ||
      !task.pull_request_number ||
      task.state === 'MERGED'}
    onclick={onMergePullRequest}>{t('taskDetail.merge')}</Button
  >
  {#if task.state === 'MERGED' && task.external_key}<Button
      disabled={commanding}
      onclick={onRetryLinearSync}>{t('taskDetail.retryLinearSync')}</Button
    >{/if}
  {#if task.manual_takeover}<Button
      variant="warning"
      disabled={commanding}
      onclick={() => onTaskCommand('resume')}>{t('taskDetail.resumeAutomation')}</Button
    >{:else}<Button
      variant="warning"
      disabled={commanding || task.state === 'MERGED' || task.state === 'CANCELLED'}
      onclick={() => onTaskCommand('takeover')}>{t('taskDetail.takeOverManually')}</Button
    >{/if}
  <Button disabled={commanding || task.manual_takeover} onclick={() => onTaskCommand('pause')}
    >{t('taskDetail.pause')}</Button
  >
  <Button variant="warning" disabled={commanding} onclick={() => onTaskCommand('cancel')}
    >{t('taskDetail.cancel')}</Button
  >
</section>
