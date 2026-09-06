<script lang="ts">
  import Button from '$lib/components/Button.svelte';
  import PixelAgentAvatar from '$lib/components/agents/PixelAgentAvatar.svelte';
  import type { TaskMessage } from '$lib/types';
  import { tick } from 'svelte';

  let {
    messages,
    hasOlder,
    loadingOlder,
    sending,
    onLoadOlder,
    onSend
  }: {
    messages: TaskMessage[];
    hasOlder: boolean;
    loadingOlder: boolean;
    sending: boolean;
    onLoadOlder: () => Promise<void>;
    onSend: (body: string) => Promise<void>;
  } = $props();

  let draft = $state('');
  let feed: HTMLDivElement;
  let previousLastId = $state<number | null>(null);

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
    await onSend(body);
    draft = '';
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
    {#if messages.length === 0}
      <div class="text-muted grid min-h-36 place-content-center text-center text-sm">
        <p class="text-heading font-medium">No internal messages yet</p>
        <p class="mt-1 max-w-md text-xs">
          Ask a question or leave context. Agent summaries will appear here after important work.
        </p>
      </div>
    {:else}
      <div class="space-y-5">
        {#each messages as message (message.id)}
          <article class="flex gap-3 {message.author_type === 'USER' ? 'flex-row-reverse' : ''}">
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
                class="border-line whitespace-pre-wrap rounded-2xl border px-4 py-3 text-sm leading-relaxed shadow-sm {message.author_type ===
                'USER'
                  ? 'bg-brand/12 rounded-tr-sm'
                  : 'bg-panel rounded-tl-sm'}"
              >
                {message.body}
              </div>
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
        >Ctrl/⌘ + Enter to send · Not synced to Trello or Linear</span
      >
      <Button variant="primary" size="sm" type="submit" disabled={sending || !draft.trim()}
        >{sending ? 'Sending…' : 'Send message'}</Button
      >
    </div>
  </form>
</section>
