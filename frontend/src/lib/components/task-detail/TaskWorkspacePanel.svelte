<script lang="ts">
  import type { Task } from '$lib/types';
  import { safeExternalUrl } from '$lib/task-links';
  let { task }: { task: Task } = $props();
</script>

<section class="min-w-0 rounded-xl border border-line p-5 xl:col-span-2">
  <h2 class="font-semibold">Task workspace and pull request</h2>
  <p class="mt-2 break-all text-xs text-muted">
    {task.workspace_path || 'The isolated task workspace is prepared when work starts.'}
  </p>
  <p class="mt-2 font-mono text-xs">
    {task.branch_name || 'No task branch yet'} · {task.current_revision?.slice(0, 12) ||
      'No validated revision yet'}
  </p>
  {#if safeExternalUrl(task.pull_request_url)}
    <!-- eslint-disable svelte/no-navigation-without-resolve -->
    <a
      class="mt-2 inline-block text-sm text-brand underline"
      href={safeExternalUrl(task.pull_request_url) || ''}
      target="_blank"
      rel="noopener noreferrer">Pull request #{task.pull_request_number} ↗</a
    >
    <!-- eslint-enable svelte/no-navigation-without-resolve -->
  {/if}
</section>
