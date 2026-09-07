<script lang="ts">
  import Button from '$lib/components/Button.svelte';
  import PixelAgentAvatar from '$lib/components/agents/PixelAgentAvatar.svelte';
  import type { TaskMessage } from '$lib/types';
  import { tick } from 'svelte';

  let {
    messages,
    taskState,
    resumeOnSend,
    hasOlder,
    loadingOlder,
    sending,
    onLoadOlder,
    onSend,
    onReact,
    onDelete
  }: {
    messages: TaskMessage[];
    taskState: string;
    resumeOnSend: boolean;
    hasOlder: boolean;
    loadingOlder: boolean;
    sending: boolean;
    onLoadOlder: () => Promise<void>;
    onSend: (body: string, replyToId?: number) => Promise<void>;
    onReact: (messageId: number, reaction: string) => Promise<void>;
    onDelete: (messageId: number) => Promise<void>;
  } = $props();

  let draft = $state('');
  let showRoutine = $state(false);
  let replyingTo = $state<TaskMessage | null>(null);
  let menu = $state<{ message: TaskMessage; x: number; y: number } | null>(null);
  let feed: HTMLDivElement;
  let previousLastId = $state<number | null>(null);

  function isBlocker(message: TaskMessage): boolean {
    const result = String(message.context.result ?? '');
    return ['BLOCKED', 'NEEDS_HUMAN', 'NEEDS_CONTEXT'].includes(result);
  }

  function needsResponse(message: TaskMessage): boolean {
    return isBlocker(message) && ['NEEDS_HUMAN', 'CONTEXT_PENDING'].includes(taskState);
  }

  function isRoutine(message: TaskMessage): boolean {
    return (
      message.author_type === 'AGENT' &&
      ['EVENT_INTERPRETED', 'PLAN_READY'].includes(String(message.context.result ?? ''))
    );
  }

  let hiddenRoutineCount = $derived(messages.filter(isRoutine).length);
  let visibleMessages = $derived(
    showRoutine ? messages : messages.filter((item) => !isRoutine(item))
  );

  $effect(() => {
    const lastId = messages.at(-1)?.id ?? null;
    if (lastId === null || lastId === previousLastId) return;
    const shouldScroll =
      previousLastId === null || feed.scrollHeight - feed.scrollTop < feed.clientHeight + 180;
    previousLastId = lastId;
    if (shouldScroll)
      void tick().then(() => feed.scrollTo({ top: feed.scrollHeight, behavior: 'smooth' }));
  });

  async function submit() {
    const body = draft.trim();
    if (!body || sending) return;
    await onSend(body, replyingTo?.id);
    draft = '';
    replyingTo = null;
  }

  function keydown(event: KeyboardEvent) {
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      void submit();
    }
  }
</script>

<section class="border-line overflow-hidden rounded-xl border xl:col-span-2">
  <header class="border-line flex items-center justify-between border-b px-5 py-4">
    <div>
      <h2 class="font-semibold">Task conversation</h2>
      <p class="text-muted mt-0.5 text-xs">Internal context shared with agents on future runs.</p>
    </div>
    <span
      class="bg-brand/10 text-brand rounded-full px-2.5 py-1 text-[10px] font-bold tracking-wider"
      >INTERNAL</span
    >
  </header>

  <div
    bind:this={feed}
    class="conversation-feed bg-input/35 max-h-[32rem] min-h-48 overflow-y-auto px-4 py-5 sm:px-6"
  >
    {#if hasOlder}
      <div class="mb-5 flex justify-center">
        <Button size="sm" disabled={loadingOlder} onclick={() => void onLoadOlder()}>
          {loadingOlder ? 'Loading…' : 'Load earlier messages'}
        </Button>
      </div>
    {/if}
    {#if hiddenRoutineCount}
      <button
        type="button"
        class="border-line bg-panel text-muted mx-auto mb-5 block rounded-full border px-3 py-1.5 text-[10px] font-semibold hover:text-heading"
        onclick={() => (showRoutine = !showRoutine)}
      >
        {showRoutine
          ? 'Hide routine workflow updates'
          : `${hiddenRoutineCount} routine workflow updates hidden`}
      </button>
    {/if}
    {#if messages.length === 0}
      <div class="text-muted grid min-h-36 place-content-center text-center text-sm">
        <p class="text-heading font-medium">No internal messages yet</p>
        <p class="mt-1 max-w-md text-xs">
          Ask a question or leave context. Agent summaries will appear here after important work.
        </p>
      </div>
    {:else}
      <div class="space-y-5">
        {#each visibleMessages as message (message.id)}
          <article
            class="flex gap-3 {message.author_type === 'USER' ? 'flex-row-reverse' : ''}"
            oncontextmenu={(event) => {
              event.preventDefault();
              menu = { message, x: event.clientX, y: event.clientY };
            }}
          >
            {#if message.author_type === 'AGENT'}
              <PixelAgentAvatar
                seed={message.agent_id ?? message.author_name}
                label={message.author_name}
                size={34}
              />
            {:else}
              <div
                class="bg-brand/15 text-brand grid size-[34px] shrink-0 place-items-center rounded-lg text-xs font-black"
              >
                YOU
              </div>
            {/if}
            <div
              class="max-w-[min(42rem,85%)] {message.author_type === 'USER'
                ? 'items-end'
                : 'items-start'} flex flex-col"
            >
              <div class="text-muted mb-1 flex items-center gap-2 text-[11px]">
                <strong class="text-heading">{message.author_name}</strong>
                {#if message.author_role}<span>{message.author_role}</span>{/if}
                {#if message.kind === 'STATUS_UPDATE'}<span class="text-accent">UPDATE</span>{/if}
                <time>{new Date(message.created_at).toLocaleString()}</time>
              </div>
              <div
                class="whitespace-pre-wrap rounded-2xl border px-4 py-3 text-sm leading-relaxed shadow-sm {needsResponse(
                  message
                )
                  ? 'border-warning/50 bg-warning/10 rounded-tl-sm'
                  : message.author_type === 'USER'
                    ? 'border-line bg-brand/12 rounded-tr-sm'
                    : 'border-line bg-panel rounded-tl-sm'}"
              >
                {#if message.reply_to_id}
                  {@const parent = messages.find((item) => item.id === message.reply_to_id)}
                  <div class="border-line text-muted mb-2 border-l-2 pl-2 text-[11px]">
                    Reply to {parent?.author_name || 'message'} · {parent?.body.slice(0, 90) ||
                      'Unavailable'}
                  </div>
                {/if}
                {message.body}
              </div>
              {#if Array.isArray(message.context.user_reactions) && message.context.user_reactions.length}
                <div class="mt-1.5 flex gap-1">
                  {#each message.context.user_reactions as reaction (String(reaction))}
                    <button
                      type="button"
                      class="border-line bg-panel rounded-full border px-2 py-0.5 text-xs"
                      onclick={() => void onReact(message.id, String(reaction))}
                      >{String(reaction)}</button
                    >
                  {/each}
                </div>
              {/if}
              {#if isBlocker(message)}
                <span
                  class="mt-1.5 rounded-full px-2 py-1 text-[10px] font-bold {needsResponse(message)
                    ? 'bg-warning/15 text-warning'
                    : 'bg-accent/10 text-accent'}"
                  >{needsResponse(message) ? 'REPLY NEEDED' : 'RESOLVED'} · {String(
                    message.context.result
                  ).replaceAll('_', ' ')}</span
                >
              {/if}
              {#if message.context.task_state}
                <span class="text-muted mt-1.5 text-[10px]"
                  >Task state · {String(message.context.task_state).replaceAll('_', ' ')}</span
                >
              {/if}
            </div>
          </article>
        {/each}
      </div>
    {/if}
  </div>

  <form
    class="border-line bg-panel border-t p-4"
    onsubmit={(event) => {
      event.preventDefault();
      void submit();
    }}
  >
    {#if replyingTo}
      <div
        class="border-line bg-input mb-2 flex items-center gap-2 rounded-lg border px-3 py-2 text-xs"
      >
        <span class="text-muted">Replying to</span><strong>{replyingTo.author_name}</strong>
        <span class="text-muted min-w-0 flex-1 truncate">{replyingTo.body}</span>
        <button type="button" aria-label="Cancel reply" onclick={() => (replyingTo = null)}
          >×</button
        >
      </div>
    {/if}
    <textarea
      bind:value={draft}
      onkeydown={keydown}
      maxlength="8000"
      rows="3"
      aria-label="Write an internal task message"
      placeholder="Reply with context, a decision, or a question for the next agent run…"
      class="border-line bg-input focus:border-brand/70 min-h-20 w-full resize-y rounded-xl border px-3.5 py-3 text-sm outline-none transition-colors"
    ></textarea>
    <div class="mt-2 flex items-center justify-between gap-3">
      <span class="text-muted text-[10px]"
        >Ctrl/⌘ + Enter to send · {resumeOnSend
          ? 'Your reply will resume this task'
          : 'Not synced to Trello or Linear'}</span
      >
      <Button variant="primary" size="sm" type="submit" disabled={sending || !draft.trim()}
        >{sending ? 'Sending…' : resumeOnSend ? 'Send & resume' : 'Send message'}</Button
      >
    </div>
  </form>
</section>

{#if menu}
  <button
    class="fixed inset-0 z-[80] cursor-default"
    aria-label="Close message menu"
    onclick={() => (menu = null)}
  ></button>
  <div
    class="border-line bg-panel fixed z-[81] w-48 rounded-xl border p-1.5 text-sm shadow-2xl"
    style={`left:${Math.min(menu.x, window.innerWidth - 205)}px;top:${Math.min(menu.y, window.innerHeight - 230)}px`}
  >
    <button
      class="hover:bg-input w-full rounded-lg px-3 py-2 text-left"
      onclick={() => {
        replyingTo = menu!.message;
        menu = null;
      }}>Reply</button
    >
    <div class="border-line my-1 flex justify-around border-y py-1.5">
      {#each ['👍', '👎', '❤️', '👀'] as reaction (reaction)}
        <button
          class="hover:bg-input rounded-md p-1.5"
          onclick={() => {
            void onReact(menu!.message.id, reaction);
            menu = null;
          }}>{reaction}</button
        >
      {/each}
    </div>
    {#if menu.message.author_type === 'USER' && !menu.message.deleted_at}
      <button
        class="hover:bg-danger/10 text-danger w-full rounded-lg px-3 py-2 text-left"
        onclick={() => {
          void onDelete(menu!.message.id);
          menu = null;
        }}>Delete</button
      >
    {/if}
  </div>
{/if}
