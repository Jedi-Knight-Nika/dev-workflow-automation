<script lang="ts">
  import { resolve } from '$app/paths';
  import { observerApi } from './api';
  import { uniqueSources } from './messages';
  import type { ObserverConversation } from './conversation.svelte';
  import type { AttentionEvent, Briefing, FocusMode, ObserverScope, ObserverStatus } from './types';

  let {
    conversation,
    assistantName,
    briefing,
    currentStatus,
    scope,
    attention,
    focus = $bindable(),
    log = $bindable(),
    textarea = $bindable(),
    onclose,
    onrefresh
  }: {
    conversation: ObserverConversation;
    assistantName: string;
    briefing: Briefing | null;
    currentStatus: ObserverStatus | null;
    scope: ObserverScope;
    attention: AttentionEvent[];
    focus: FocusMode;
    log: HTMLDivElement | undefined;
    textarea: HTMLTextAreaElement | undefined;
    onclose: () => void;
    onrefresh: () => Promise<void>;
  } = $props();
  const chat = $derived(conversation.state);
  async function eventAction(event: AttentionEvent, minutes?: number) {
    try {
      if (minutes) await observerApi.snooze(event.id, minutes);
      else await observerApi.acknowledge(event.id);
      await onrefresh();
    } catch {
      chat.error = 'Could not update this attention item.';
    }
  }
  async function changeFocus() {
    try {
      await observerApi.preferences({ focus });
    } catch {
      chat.error = 'Could not save notification preference.';
    }
  }
  async function markSeen() {
    try {
      await observerApi.preferences({ last_seen_at: new Date().toISOString() });
      chat.showChanges = false;
    } catch {
      chat.error = 'Could not save last visit.';
    }
  }
</script>

<nav class="panel-actions" aria-label="{assistantName} views">
  <button onclick={conversation.reset}>New chat</button>
  <button onclick={conversation.history} aria-expanded={chat.showHistory}>History</button>
  <button
    onclick={() => {
      chat.showChanges = !chat.showChanges;
    }}
    aria-expanded={chat.showChanges}>Since my visit</button
  >
  <label class="focus-select"
    ><span class="sr-only">Notifications</span><select bind:value={focus} onchange={changeFocus}
      ><option value="normal">Notifications</option><option value="warnings-only"
        >Warnings only</option
      ><option value="critical-only">Critical only</option><option value="silent">Silent</option
      ></select
    ></label
  >
</nav>
<div class="conversation" bind:this={log}>
  {#if chat.showHistory}<section class="history-list">
      <h3>Recent conversations</h3>
      {#each chat.conversations as item (item.id)}<button
          onclick={() => conversation.loadConversation(item)}
          >{item.title}<small
            >{item.scope.page.toLowerCase()} · {new Date(
              item.updated_at
            ).toLocaleDateString()}</small
          ></button
        >{:else}<p class="subtext">No saved conversations yet.</p>{/each}
    </section>{/if}
  {#if chat.showChanges}<section class="briefing">
      <h3>Since your last seen marker</h3>
      {#each briefing?.changes || [] as change (change.key)}<p>{change.text}</p>{/each}<button
        class="text-button"
        onclick={markSeen}>Mark these changes seen</button
      >
    </section>{/if}
  {#if attention.length}<section class="attention">
      <h3>Important now <span>{attention.length}</span></h3>
      <button
        class="text-button"
        onclick={() => {
          chat.showAttention = !chat.showAttention;
        }}
        aria-expanded={chat.showAttention}
        >{chat.showAttention ? 'Collapse attention' : 'View all attention'}</button
      >
      {#each attention.slice(0, chat.showAttention ? 100 : chat.messages.length ? 0 : 2) as event (event.id)}<article
          class:critical={event.severity === 'CRITICAL'}
        >
          <div class="event-heading">
            <span>{event.severity}</span><small>{event.status.toLowerCase()}</small>
          </div>
          <p>{event.title}</p>
          <div class="event-actions">
            {#if event.task_id}<a
                href={resolve('/tasks/[id]', { id: event.task_id })}
                onclick={onclose}>View task ↗</a
              >{/if}{#if event.status === 'OPEN'}<button onclick={() => eventAction(event)}
                >Acknowledge</button
              ><button onclick={() => eventAction(event, 15)}>Snooze 15m</button><button
                onclick={() => eventAction(event, 60)}>1h</button
              >{/if}
          </div>
        </article>{/each}
    </section>{/if}
  {#if chat.messages.length === 0}<section class="welcome">
      <p class="eyebrow">FACTS FIRST. AI SECOND.</p>
      <h3>Eyes on the system.<br />Hands off your work.</h3>
      <p>{briefing?.message || 'Reading current product facts…'}</p>
      {#if currentStatus?.reason}<p class="sleep-note">{currentStatus.reason}</p>{/if}
      <div class="questions">
        {#each briefing?.suggested_questions || ['What needs attention?', 'What can you do?'] as question (question)}<button
            onclick={() => conversation.send(question)}
            disabled={chat.busy}>{question}<span>↗</span></button
          >{/each}
      </div>
    </section>{/if}
  <div
    role="log"
    aria-live="polite"
    aria-relevant="additions text"
    aria-label="{assistantName} conversation"
  >
    {#each chat.messages as message (message.id)}<article
        class="message"
        class:user={message.role === 'user'}
      >
        <div class="message-label">{message.role === 'user' ? 'YOU' : assistantName}</div>
        <p>
          {message.content || (chat.busy ? `${chat.activity}…` : 'This reply was interrupted.')}
        </p>
        {#if message.sources.length}<div class="sources">
            {#each uniqueSources(message.sources) as source (source.source + source.complete)}<span
                class:incomplete={!source.complete}
                title={source.measured_at
                  ? `Measured ${new Date(source.measured_at).toLocaleString()}`
                  : 'Source time unavailable'}
                >{source.source.replaceAll('_', ' ')} · {source.complete
                  ? source.measured_at
                    ? new Date(source.measured_at).toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit'
                      })
                    : 'contract'
                  : 'partial'}</span
              >{/each}
          </div>{/if}
      </article>{/each}
  </div>
  {#if chat.error}<p class="error" role="alert">{chat.error}</p>{/if}
</div>
<form
  class="composer"
  onsubmit={(event) => {
    event.preventDefault();
    void conversation.send();
  }}
>
  <label for="observer-question" class="sr-only">Ask {assistantName}</label><textarea
    id="observer-question"
    bind:this={textarea}
    bind:value={chat.input}
    rows="2"
    maxlength="2000"
    placeholder={scope.page === 'TASK' ? 'Ask about this task…' : 'Ask about your system…'}
    disabled={chat.busy}
    onkeydown={(event) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        void conversation.send();
      }
    }}></textarea>
  <div class="composer-footer">
    <span
      >{chat.busy ? chat.activity : chat.activity || 'No source access. No write authority.'}</span
    ><button
      class="accent-action"
      type="submit"
      disabled={chat.busy || !chat.input.trim()}
      aria-label="Send {assistantName} question">{chat.busy ? 'Reading…' : 'Send ↑'}</button
    >
  </div>
</form>
<footer class="panel-footer">
  <span>Engineering always has priority.</span><a href={resolve('/settings')} onclick={onclose}
    >{assistantName} settings</a
  >
</footer>

<style>
  .panel-actions {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 13px 22px;
    font-size: 10px;
    color: var(--color-muted);
  }
  .panel-actions button:hover,
  .text-button:hover {
    color: var(--color-brand);
  }
  .focus-select {
    margin-left: auto;
  }
  .focus-select select {
    background: var(--color-panel);
    color: var(--color-muted);
    max-width: 105px;
    font-size: 10px;
    border: 0;
  }
  .conversation {
    overflow-y: auto;
    flex: 1;
    padding: 0 22px 18px;
    min-height: 0;
    overscroll-behavior: contain;
  }
  .welcome {
    padding: 24px 0;
  }
  .welcome h3 {
    font-size: 23px;
    font-weight: 450;
    letter-spacing: -0.04em;
    line-height: 1.35;
    margin: 12px 0 18px;
  }
  .welcome > p:not(.eyebrow) {
    font-size: 12px;
    line-height: 1.75;
    color: var(--color-muted);
  }
  .welcome .sleep-note {
    border-left: 2px solid var(--color-line);
    padding-left: 10px;
    margin-top: 14px;
    font-size: 10px !important;
  }
  .questions {
    display: grid;
    gap: 7px;
    margin-top: 24px;
  }
  .questions button {
    text-align: left;
    border: 1px solid var(--color-line);
    border-radius: 10px;
    padding: 11px 13px;
    font-size: 11px;
    display: flex;
    justify-content: space-between;
    gap: 8px;
    background: var(--color-panel-alt);
  }
  .questions button:hover {
    border-color: var(--color-brand);
  }
  .questions span {
    color: var(--color-brand);
  }
  .attention h3,
  .briefing h3,
  .history-list h3 {
    font: 10px monospace;
    color: var(--color-muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin: 14px 0 10px;
  }
  .attention h3 span {
    color: var(--color-brand);
  }
  .attention article {
    border: 1px solid #fbbf2433;
    border-radius: 10px;
    padding: 10px 12px;
    margin-bottom: 7px;
    background: #fbbf2405;
  }
  .attention article.critical {
    border-color: #fb718555;
    background: #fb718507;
  }
  .event-heading {
    display: flex;
    justify-content: space-between;
    font: 8px monospace;
    color: #d99a12;
  }
  .event-heading small {
    color: var(--color-muted);
  }
  .attention p {
    font-size: 11px;
    margin-top: 7px;
  }
  .event-actions {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    margin-top: 9px;
    font-size: 10px;
    color: var(--color-muted);
  }
  .event-actions button:hover,
  .event-actions a:hover {
    color: var(--color-brand);
  }
  .message {
    padding: 18px 0;
    border-bottom: 1px solid var(--color-line);
  }
  .message.user {
    margin: 10px 0;
    padding: 12px 14px;
    border: 1px solid var(--color-line);
    border-radius: 12px;
    background: var(--color-panel-alt);
  }
  .message-label {
    font: 8px monospace;
    letter-spacing: 0.12em;
    color: var(--color-brand);
    margin-bottom: 8px;
  }
  .message.user .message-label {
    color: var(--color-muted);
  }
  .message p {
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    font-size: 12px;
    line-height: 1.75;
  }
  .sources {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
    margin-top: 12px;
  }
  .sources span {
    font: 8px monospace;
    color: var(--color-muted);
    background: var(--color-panel-alt);
    border: 1px solid var(--color-line);
    border-radius: 5px;
    padding: 4px 6px;
  }
  .sources .incomplete {
    color: #d99a12;
  }
  .composer {
    border: 1px solid var(--color-line);
    border-radius: 13px;
    padding: 12px;
    margin: 0 16px;
    background: var(--color-panel-alt);
  }
  .composer:focus-within {
    border-color: color-mix(in srgb, var(--color-brand) 55%, var(--color-line));
  }
  .composer textarea {
    resize: none;
    width: 100%;
    font-size: 12px;
    background: transparent;
    color: var(--color-heading);
    border: none;
    outline: none;
  }
  .composer textarea::placeholder {
    color: var(--color-muted);
  }
  .composer-footer {
    display: flex;
    gap: 8px;
    align-items: center;
    justify-content: space-between;
    margin-top: 4px;
  }
  .composer-footer span {
    font: 8px monospace;
    color: var(--color-muted);
  }
  .composer-footer button {
    font-size: 10px;
    padding: 6px 10px;
    background: var(--color-brand);
    color: var(--color-on-brand);
    border-radius: 7px;
  }
  .composer-footer button:disabled {
    opacity: 0.4;
  }
  .panel-footer {
    display: flex;
    gap: 8px;
    justify-content: space-between;
    padding: 12px 22px;
    font-size: 9px;
    color: var(--color-muted);
  }
  .panel-footer a {
    text-decoration: underline;
    text-underline-offset: 3px;
  }
  .history-list button {
    display: block;
    width: 100%;
    text-align: left;
    padding: 10px;
    font-size: 11px;
    border: 1px solid var(--color-line);
    border-radius: 8px;
    margin-bottom: 6px;
  }
  .history-list small {
    display: block;
    color: var(--color-muted);
    font-size: 9px;
    margin-top: 4px;
  }
  .briefing p {
    font-size: 10px;
    line-height: 1.7;
    padding: 6px 0;
  }
  .text-button {
    font-size: 10px;
    color: var(--color-brand);
  }
  .error {
    color: #fb7185;
    font-size: 11px;
    padding: 14px 0;
  }
  .eyebrow {
    font: 9px monospace;
    letter-spacing: 0.15em;
    color: var(--color-brand);
    margin-bottom: 7px;
  }
  .subtext {
    color: var(--color-muted);
    font-size: 11px;
  }
  button {
    cursor: pointer;
  }
  button:disabled {
    cursor: default;
  }
  button:focus-visible,
  a:focus-visible,
  select:focus-visible {
    outline: 2px solid var(--color-brand);
    outline-offset: 3px;
  }

  :global(.observer-dialog[data-display='jarvis']) .composer,
  :global(.observer-dialog[data-display='jarvis']) .questions button {
    border-radius: 5px;
    border-color: color-mix(in srgb, var(--color-brand) 25%, var(--color-line));
    background: color-mix(in srgb, var(--color-brand) 4%, var(--color-panel-alt));
  }
  :global(.observer-dialog[data-display='jarvis']) .sources span {
    border-radius: 3px;
  }
  :global(.observer-dialog.compact) .eyebrow,
  :global(.observer-dialog.compact) .panel-footer {
    display: none;
  }
  :global(.observer-dialog.compact) .panel-actions {
    padding-top: 6px;
    padding-bottom: 6px;
  }
  :global(.observer-dialog.compact) .composer {
    margin-bottom: 10px;
  }
  @media (max-width: 640px) {
    .eyebrow {
      font-size: 8px;
    }
    .panel-actions {
      gap: 10px;
    }
    .panel-footer {
      padding-bottom: max(12px, env(safe-area-inset-bottom));
    }
  }
</style>
