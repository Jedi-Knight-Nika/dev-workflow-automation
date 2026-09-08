<script lang="ts">
  import Button from '$lib/components/Button.svelte';
  import type { TaskMessage } from '$lib/types';

  let {
    messages,
    taskStatus,
    hasOlder = false,
    loadingOlder = false,
    sending = false,
    onLoadOlder,
    onSend
  }: {
    messages: TaskMessage[];
    taskStatus: string;
    hasOlder?: boolean;
    loadingOlder?: boolean;
    sending?: boolean;
    onLoadOlder?: () => void;
    onSend: (body: string, replyTo?: number) => Promise<void>;
  } = $props();
  let draft = $state('');
  let error = $state('');
  async function submit() {
    if (!draft.trim() || sending) return;
    error = '';
    try {
      await onSend(draft.trim());
      draft = '';
    } catch (cause) {
      error = String(cause);
    }
  }
</script>

<section class="rounded-xl border border-line bg-panel p-5">
  <h2 class="font-semibold">Task notes and feedback</h2>
  <p class="my-2 text-xs text-muted">
    Notes do not start AI work. Explicit /feedback, /pause, /resume and /cancel commands include the
    task ID. Current status: {taskStatus}.
  </p>
  {#if hasOlder}<Button disabled={loadingOlder} onclick={onLoadOlder}
      >{loadingOlder ? 'Loading…' : 'Earlier notes'}</Button
    >{/if}
  <div class="my-4 space-y-4">
    {#each messages as message (message.id)}
      <article class="border-l border-line pl-3">
        <p class="text-xs text-muted">
          {message.author_name} · {message.author_role || message.author_type}
          ·
          <time datetime={message.created_at}>{new Date(message.created_at).toLocaleString()}</time>
        </p>
        <p class="mt-1 whitespace-pre-wrap break-words text-sm">{message.body}</p>
      </article>
    {:else}<p class="text-sm text-muted">No notes yet.</p>{/each}
  </div>
  <form
    onsubmit={(event) => {
      event.preventDefault();
      void submit();
    }}
    class="space-y-2"
  >
    <label class="sr-only" for="task-note">Note or explicit command</label>
    <textarea
      id="task-note"
      bind:value={draft}
      maxlength={8000}
      rows={3}
      class="w-full rounded-lg border border-line bg-panel-alt p-3 text-sm"
      placeholder="Add context or a note…"
    ></textarea>
    {#if error}<p role="alert" class="text-sm text-danger">{error}</p>{/if}
    <Button type="submit" disabled={sending || !draft.trim()}
      >{sending ? 'Saving…' : 'Save note'}</Button
    >
  </form>
</section>
