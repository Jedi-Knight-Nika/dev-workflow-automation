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
      onclick={() => {
        if (confirm('Cancel this task? Work stops; its files and evidence remain available.'))
          onTaskCommand('cancel');
      }}>Cancel task</Button
    >
  {:else}
    <Button
      disabled={commanding}
      onclick={() => {
        if (confirm('Archive this completed or cancelled task?')) onTaskCommand('archive');
      }}>Archive</Button
    >
  {/if}
  <p class="w-full text-xs text-muted">
    Resume keeps the current phase, native session and budget usage. Publication and merge follow
    the Team policy.
  </p>
</section>
