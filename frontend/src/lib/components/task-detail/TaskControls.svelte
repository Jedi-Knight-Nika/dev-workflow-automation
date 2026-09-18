<script lang="ts">
  import Button from '$lib/components/Button.svelte';
  import type { Task } from '$lib/types';
  import type { TaskCommand } from '$lib/services/tasks';

  let {
    task,
    commanding,
    onTaskCommand
  }: {
    task: Task;
    commanding: boolean;
    onTaskCommand: (command: TaskCommand) => void;
  } = $props();
  const terminal = $derived(['MERGED', 'CANCELLED', 'FAILED'].includes(task.status));
  const suspended = $derived(['NEW', 'PAUSED', 'WAITING_HUMAN'].includes(task.status));
  let confirmation = $state<{ taskId: string; action: 'cancel' | 'archive' } | null>(null);

  function confirmCommand() {
    if (!confirmation || confirmation.taskId !== task.id || commanding) return;
    const action = confirmation.action;
    confirmation = null;
    onTaskCommand(action);
  }
</script>

<section
  class="flex flex-wrap items-center gap-3 rounded-xl border border-line p-4 xl:col-span-2"
  aria-label="Task controls"
>
  {#if !terminal}
    {#if suspended}
      <Button disabled={commanding} onclick={() => onTaskCommand('resume')}>
        {task.status === 'NEW'
          ? 'Start work'
          : task.manual_takeover
            ? 'Release takeover and resume'
            : 'Resume work'}
      </Button>
    {:else}
      <Button disabled={commanding} onclick={() => onTaskCommand('pause')}>Pause work</Button>
    {/if}
    {#if !task.manual_takeover}
      <Button variant="warning" disabled={commanding} onclick={() => onTaskCommand('takeover')}
        >Take over manually</Button
      >
    {/if}
    <Button
      variant="danger"
      disabled={commanding}
      onclick={() => (confirmation = { taskId: task.id, action: 'cancel' })}>Cancel task</Button
    >
  {:else}
    <Button
      disabled={commanding}
      onclick={() => (confirmation = { taskId: task.id, action: 'archive' })}>Archive</Button
    >
  {/if}
  {#if confirmation?.taskId === task.id && (confirmation.action === 'archive') === terminal}
    <div
      class="flex w-full flex-wrap items-center gap-3 rounded-lg border border-line p-3"
      role="group"
      aria-label="Confirm task action"
    >
      <p class="text-sm" role="status">
        {confirmation.action === 'cancel'
          ? 'Cancel this task? Work stops; files and execution evidence are preserved.'
          : 'Archive this completed or cancelled task?'}
      </p>
      <Button variant="danger" disabled={commanding} onclick={confirmCommand}>
        {confirmation.action === 'cancel' ? 'Yes, cancel task' : 'Yes, archive task'}
      </Button>
      <Button disabled={commanding} onclick={() => (confirmation = null)}>Keep task</Button>
    </div>
  {/if}
  <p class="w-full text-xs text-muted">
    Resume keeps the current phase, native session and budget usage. Publication and merge follow
    the Team policy.
  </p>
</section>
