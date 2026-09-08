<script lang="ts">
  import { onMount, tick, untrack } from 'svelte';
  import { SvelteSet } from 'svelte/reactivity';
  import { page } from '$app/state';
  import { resolve } from '$app/paths';
  import { getDisplayMode } from '$lib/display.svelte';
  import ObserverOrb from './ObserverOrb.svelte';
  import { draggable } from './draggable';
  import {
    POSITION_KEY,
    dockPosition,
    normalizePosition,
    placePopup,
    readPosition,
    type Point,
    type Viewport
  } from './position';
  import { observerApi, streamAnswer } from './api';
  import type {
    AttentionEvent,
    Briefing,
    Conversation,
    Evidence,
    FocusMode,
    ObserverMessage,
    ObserverScope,
    ObserverStatus,
    OrbMode
  } from './types';

  let enabled = $state(false);
  let currentStatus = $state<ObserverStatus | null>(null);
  let briefing = $state<Briefing | null>(null);
  let open = $state(false);
  let busy = $state(false);
  let offline = $state(false);
  let bubble = $state('');
  let error = $state('');
  let activity = $state('');
  let input = $state('');
  let messages = $state<ObserverMessage[]>([]);
  let conversation = $state<string>();
  let conversations = $state<Conversation[]>([]);
  let showHistory = $state(false);
  let showChanges = $state(false);
  let showAttention = $state(false);
  let focus = $state<FocusMode>('normal');
  let dialog: HTMLDialogElement;
  let dock = $state<HTMLDivElement>();
  let launcher = $state<HTMLButtonElement>();
  let viewport = $state<Viewport>({ left: 0, top: 0, width: 1440, height: 900 });
  let position = $state<Point | null>(null);
  let dragging = $state(false);
  let bubbleHeight = $state(120);
  const displayMode = $derived(getDisplayMode());
  const dockSize = $derived(viewport.width <= 640 ? 66 : 78);
  const anchor = $derived(dockPosition(position, viewport, dockSize));
  const panelBox = $derived(placePopup(anchor, dockSize, viewport, 460, 700));
  const bubbleBox = $derived(placePopup(anchor, dockSize, viewport, 280, bubbleHeight));
  const dragOptions = {
    position: () => anchor,
    move: (point: Point) => {
      position = normalizePosition(point, viewport, dockSize);
    },
    commit: savePosition,
    reset: resetPosition,
    dragging: (active: boolean) => {
      dragging = active;
    }
  };
  let log = $state<HTMLDivElement>();
  let textarea = $state<HTMLTextAreaElement>();
  let request: AbortController | undefined;
  let refreshRequest: AbortController | undefined;
  let refreshTimer: ReturnType<typeof setTimeout> | undefined;
  let bubbleTimer: ReturnType<typeof setTimeout> | undefined;
  let mounted = false;
  let lastBubble = 0;
  const seen = new SvelteSet<string>();
  let explicitScope = $state<ObserverScope | null>(null);

  function savePosition() {
    try {
      localStorage.setItem(POSITION_KEY, JSON.stringify(position));
    } catch {
      /* storage is optional */
    }
  }

  function resetPosition() {
    position = null;
    savePosition();
  }

  function measureBubble(node: HTMLDivElement) {
    const observer = new ResizeObserver(() => {
      bubbleHeight = node.getBoundingClientRect().height;
    });
    observer.observe(node);
    return { destroy: () => observer.disconnect() };
  }

  const routeScope = $derived.by((): ObserverScope => {
    const match = page.url.pathname.match(/^\/(tasks|teams)\/([a-f\d-]{36})\/?$/i);
    if (match)
      return match[1] === 'tasks'
        ? { page: 'TASK', task_id: match[2] }
        : { page: 'TEAM', team_id: match[2] };
    return { page: 'DASHBOARD' };
  });
  const scope = $derived(explicitScope || routeScope);
  const mode = $derived<OrbMode>(
    offline
      ? 'offline'
      : busy
        ? activity === 'Answering'
          ? 'speaking'
          : 'thinking'
        : currentStatus?.highest_severity === 'CRITICAL'
          ? 'critical'
          : currentStatus?.highest_severity === 'WARNING'
            ? 'warning'
            : currentStatus?.ai_available
              ? 'idle'
              : 'sleeping'
  );
  const scopeName = $derived(
    scope.page === 'TASK' ? 'This task' : scope.page === 'TEAM' ? 'This Team' : 'Control center'
  );
  const attention = $derived(
    (currentStatus?.events || [])
      .filter((e) => e.status !== 'RESOLVED')
      .sort(
        (a, b) =>
          ({ CRITICAL: 0, WARNING: 1, INFO: 2 })[a.severity] -
          { CRITICAL: 0, WARNING: 1, INFO: 2 }[b.severity]
      )
  );

  $effect(() => {
    const key = `${routeScope.page}:${routeScope.task_id || routeScope.team_id || ''}`;
    if (mounted && key) {
      untrack(() => {
        explicitScope = null;
        request?.abort();
        messages = [];
        conversation = undefined;
        briefing = null;
        void refresh(true);
      });
    }
  });

  function stop() {
    request?.abort();
    refreshRequest?.abort();
    clearTimeout(refreshTimer);
    clearTimeout(bubbleTimer);
    busy = false;
    bubble = '';
    currentStatus = null;
    briefing = null;
    closePanel();
  }

  async function configuration() {
    try {
      const response = await observerApi.configuration();
      enabled = response.enabled;
      if (enabled) await refresh(true);
      else stop();
    } catch {
      enabled = false;
      stop();
    }
  }

  async function refresh(full = false) {
    clearTimeout(refreshTimer);
    if (!enabled || document.hidden) return;
    refreshRequest?.abort();
    const controller = new AbortController();
    refreshRequest = controller;
    try {
      const result = full
        ? await observerApi.briefing(scope, controller.signal)
        : await observerApi.status(scope, controller.signal);
      if (controller.signal.aborted || !enabled) return;
      currentStatus = result;
      offline = false;
      if ('message' in result) {
        briefing = result as Briefing;
        focus = briefing.preferences.focus;
      }
      const fresh = result.events.find(
        (e) => e.status === 'OPEN' && e.notified_at && !seen.has(`${e.id}:${e.notified_at}`)
      );
      const permitted =
        focus !== 'silent' && (focus !== 'critical-only' || fresh?.severity === 'CRITICAL');
      if (
        fresh &&
        permitted &&
        !open &&
        (Date.now() - lastBubble > 900000 || fresh.severity === 'CRITICAL')
      ) {
        bubble = fresh.title;
        lastBubble = Date.now();
        clearTimeout(bubbleTimer);
        bubbleTimer = setTimeout(() => {
          bubble = '';
        }, 10000);
      }
      for (const event of result.events) seen.add(`${event.id}:${event.notified_at}`);
    } catch {
      if (!controller.signal.aborted) {
        offline = true;
        // The master switch is authoritative. Once off, no polling continues.
        try {
          if (!(await observerApi.configuration()).enabled) {
            enabled = false;
            stop();
          }
        } catch {
          /* service unavailable */
        }
      }
    } finally {
      if (enabled && !controller.signal.aborted)
        refreshTimer = setTimeout(() => void refresh(), 30000);
    }
  }

  async function openPanel() {
    if (!enabled) return;
    open = true;
    bubble = '';
    error = '';
    await tick();
    // A floating companion, not a blocking modal: its launcher and the app remain usable.
    if (!enabled || !open) return;
    dialog.show();
    textarea?.focus();
    if (!briefing) await refresh(true);
  }

  function closePanel() {
    const restoreFocus =
      typeof document !== 'undefined' && dialog?.contains(document.activeElement);
    request?.abort();
    busy = false;
    open = false;
    dialog?.close();
    if (restoreFocus) launcher?.focus({ preventScroll: true });
  }

  async function send(question = input) {
    const message = question.trim();
    if (!message || busy || !enabled) return;
    input = '';
    error = '';
    busy = true;
    activity = 'Reading product facts';
    request?.abort();
    const controller = new AbortController();
    request = controller;
    const responseId = crypto.randomUUID();
    messages = [
      ...messages,
      { id: crypto.randomUUID(), role: 'user', content: message, sources: [] },
      { id: responseId, role: 'assistant', content: '', sources: [] }
    ];
    try {
      const created = await observerApi.question(message, scope, conversation, controller.signal);
      conversation = created.conversation_id;
      await streamAnswer(
        created.request_id,
        (event) => {
          if (controller.signal.aborted) return;
          if (event.type === 'observer.tool_started')
            activity = `Reading ${(event.tool || 'facts').replaceAll('_', ' ')}`;
          if (event.type === 'observer.text_delta') {
            activity = 'Answering';
            messages = messages.map((m) =>
              m.id === responseId ? { ...m, content: m.content + (event.text || '') } : m
            );
          }
          if (event.type === 'observer.completed') {
            messages = messages.map((m) =>
              m.id === responseId
                ? { ...m, content: event.answer || m.content, sources: event.sources || [] }
                : m
            );
            activity =
              event.mode === 'local'
                ? 'Local Ollama · verified facts'
                : 'Deterministic · no model call';
          }
          if (event.type === 'observer.failed') error = event.message || 'Observer unavailable.';
          void tick().then(() => {
            if (log) log.scrollTop = log.scrollHeight;
          });
        },
        controller.signal
      );
    } catch {
      if (!controller.signal.aborted)
        error = 'Observer could not finish this answer. Saved conversations remain in History.';
    } finally {
      if (request === controller) busy = false;
    }
  }

  async function eventAction(event: AttentionEvent, minutes?: number) {
    try {
      if (minutes) await observerApi.snooze(event.id, minutes);
      else await observerApi.acknowledge(event.id);
      await refresh();
    } catch {
      error = 'Could not update this attention item.';
    }
  }
  async function changeFocus() {
    try {
      await observerApi.preferences({ focus });
    } catch {
      error = 'Could not save notification preference.';
    }
  }
  async function markSeen() {
    try {
      await observerApi.preferences({ last_seen_at: new Date().toISOString() });
      showChanges = false;
    } catch {
      error = 'Could not save last visit.';
    }
  }
  async function history() {
    try {
      conversations = await observerApi.conversations();
      showHistory = !showHistory;
    } catch {
      error = 'History unavailable.';
    }
  }
  async function loadConversation(item: Conversation) {
    try {
      request?.abort();
      busy = false;
      messages = await observerApi.history(item.id);
      explicitScope = item.scope;
      conversation = item.id;
      showHistory = false;
      await refresh(true);
    } catch {
      error = 'Could not load that conversation.';
    }
  }
  function uniqueSources(sources: Evidence[]) {
    return sources.filter(
      (s, i) => sources.findIndex((x) => x.source === s.source && x.complete === s.complete) === i
    );
  }

  onMount(() => {
    mounted = true;
    try {
      position = readPosition(localStorage.getItem(POSITION_KEY));
    } catch {
      /* storage is optional */
    }
    const resize = () => {
      const visual = window.visualViewport;
      viewport = {
        left: visual?.offsetLeft || 0,
        top: visual?.offsetTop || 0,
        width: visual?.width || window.innerWidth,
        height: visual?.height || window.innerHeight
      };
    };
    resize();
    const outside = (event: PointerEvent) => {
      if (
        open &&
        event.target instanceof Node &&
        !dialog.contains(event.target) &&
        !dock?.contains(event.target)
      )
        closePanel();
    };
    const escape = (event: KeyboardEvent) => {
      if (open && event.key === 'Escape') {
        event.preventDefault();
        closePanel();
      }
    };
    window.addEventListener('resize', resize);
    window.visualViewport?.addEventListener('resize', resize);
    window.visualViewport?.addEventListener('scroll', resize);
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    void configuration();
    const visibility = () => {
      clearTimeout(refreshTimer);
      if (!document.hidden && enabled) void refresh();
    };
    const configChanged = () => void configuration();
    const ask = (event: Event) => {
      const detail = (event as CustomEvent<{ question: string; context?: ObserverScope }>).detail;
      if (!enabled || !detail?.question) return;
      explicitScope = detail.context || routeScope;
      conversation = undefined;
      messages = [];
      void openPanel().then(() => send(detail.question));
    };
    const channel =
      typeof BroadcastChannel !== 'undefined'
        ? new BroadcastChannel('observer-configuration')
        : null;
    if (channel) channel.onmessage = configChanged;
    window.addEventListener('observer:configuration', configChanged);
    window.addEventListener('observer:ask', ask);
    document.addEventListener('visibilitychange', visibility);
    return () => {
      mounted = false;
      enabled = false;
      stop();
      channel?.close();
      window.removeEventListener('observer:configuration', configChanged);
      window.removeEventListener('observer:ask', ask);
      document.removeEventListener('visibilitychange', visibility);
      window.removeEventListener('resize', resize);
      window.visualViewport?.removeEventListener('resize', resize);
      window.visualViewport?.removeEventListener('scroll', resize);
      document.removeEventListener('pointerdown', outside);
      document.removeEventListener('keydown', escape);
    };
  });
</script>

{#if enabled}
  <div
    class="observer-dock"
    bind:this={dock}
    data-display={displayMode}
    class:dragging
    style:left="{anchor.x}px"
    style:top="{anchor.y}px"
  >
    {#if bubble}<div
        class="observer-bubble"
        role="status"
        use:measureBubble
        style:left="{bubbleBox.x}px"
        style:top="{bubbleBox.y}px"
        style:width="{bubbleBox.width}px"
        style:max-height="{viewport.height - 24}px"
      >
        <span>{bubble}</span><button
          onclick={() => {
            bubble = '';
          }}
          aria-label="Dismiss Observer notice">×</button
        >
      </div>{/if}
    <button
      class="observer-launch"
      bind:this={launcher}
      use:draggable={dragOptions}
      onclick={() => (open ? closePanel() : openPanel())}
      aria-expanded={open}
      aria-controls="observer-panel"
      aria-describedby="observer-move-help"
      aria-label="Open Observer assistant"
      title="Observer · {offline
        ? 'offline'
        : currentStatus?.ai_available
          ? 'local AI available'
          : 'deterministic facts'} · Drag to move"
    >
      <ObserverOrb {mode} {displayMode} size={dockSize - 2} />
      {#if currentStatus?.open_attention_count}<span
          class="observer-badge"
          class:critical={currentStatus.highest_severity === 'CRITICAL'}
          >{currentStatus.open_attention_count}</span
        >{/if}
      <span class="dock-label">OBSERVER</span>
    </button>
    <span id="observer-move-help" class="sr-only"
      >Drag to move, or use arrow keys when focused. Shift moves faster. Home resets the position.</span
    >
  </div>
{/if}

<dialog
  id="observer-panel"
  aria-labelledby="observer-panel-title"
  bind:this={dialog}
  class="observer-dialog"
  data-display={displayMode}
  class:dragging
  class:compact={panelBox.height < 480}
  style:left="{panelBox.x}px"
  style:top="{panelBox.y}px"
  style:width="{panelBox.width}px"
  style:height="{panelBox.height}px"
  oncancel={closePanel}
  onclose={() => {
    open = false;
    request?.abort();
    busy = false;
  }}
>
  {#if open && enabled}
    <header class="panel-header">
      <button
        class="panel-drag"
        use:draggable={dragOptions}
        aria-label="Move Observer panel"
        aria-describedby="observer-move-help"
        title="Drag to move · Arrow keys to adjust"
      >
        <ObserverOrb {mode} {displayMode} size={82} />
        <span class="header-copy">
          <span class="eyebrow"
            >{displayMode === 'jarvis' ? 'OBSERVER / OPERATIONS LINK' : 'AMBIENT OPERATIONS'}</span
          >
          <span id="observer-panel-title" class="panel-title">Observer</span>
          <span class="subtext">Read-only companion · {scopeName}</span>
        </span>
        <span class="grip" aria-hidden="true">⠿</span>
      </button>
      <div class="window-controls">
        <button
          class="reset-position"
          onclick={resetPosition}
          aria-label="Reset Observer position"
          title="Reset position">↘</button
        >
        <button class="icon-button close" onclick={closePanel} aria-label="Close Observer">×</button
        >
      </div>
    </header>
    <div class="status-strip">
      <span
        class="status-dot"
        class:warning={mode === 'warning'}
        class:critical={mode === 'critical'}
      ></span><span
        >{offline
          ? 'Connection unavailable'
          : currentStatus?.ai_available
            ? 'Local Ollama available'
            : 'Deterministic mode'}</span
      ><span class="status-cost">NO CLOUD SPEND</span>
    </div>
    <nav class="panel-actions" aria-label="Observer views">
      <button
        onclick={() => {
          request?.abort();
          busy = false;
          messages = [];
          conversation = undefined;
          explicitScope = null;
          showHistory = false;
        }}>New chat</button
      >
      <button onclick={history} aria-expanded={showHistory}>History</button>
      <button
        onclick={() => {
          showChanges = !showChanges;
        }}
        aria-expanded={showChanges}>Since my visit</button
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
      {#if showHistory}<section class="history-list">
          <h3>Recent conversations</h3>
          {#each conversations as item (item.id)}<button onclick={() => loadConversation(item)}
              >{item.title}<small
                >{item.scope.page.toLowerCase()} · {new Date(
                  item.updated_at
                ).toLocaleDateString()}</small
              ></button
            >{:else}<p class="subtext">No saved conversations yet.</p>{/each}
        </section>{/if}
      {#if showChanges}<section class="briefing">
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
              showAttention = !showAttention;
            }}
            aria-expanded={showAttention}
            >{showAttention ? 'Collapse attention' : 'View all attention'}</button
          >
          {#each attention.slice(0, showAttention ? 100 : messages.length ? 0 : 2) as event (event.id)}<article
              class:critical={event.severity === 'CRITICAL'}
            >
              <div class="event-heading">
                <span>{event.severity}</span><small>{event.status.toLowerCase()}</small>
              </div>
              <p>{event.title}</p>
              <div class="event-actions">
                {#if event.task_id}<a
                    href={resolve('/tasks/[id]', { id: event.task_id })}
                    onclick={closePanel}>View task ↗</a
                  >{/if}{#if event.status === 'OPEN'}<button onclick={() => eventAction(event)}
                    >Acknowledge</button
                  ><button onclick={() => eventAction(event, 15)}>Snooze 15m</button><button
                    onclick={() => eventAction(event, 60)}>1h</button
                  >{/if}
              </div>
            </article>{/each}
        </section>{/if}
      {#if messages.length === 0}<section class="welcome">
          <p class="eyebrow">FACTS FIRST. AI SECOND.</p>
          <h3>Eyes on the system.<br />Hands off your work.</h3>
          <p>{briefing?.message || 'Reading current product facts…'}</p>
          {#if currentStatus?.reason}<p class="sleep-note">{currentStatus.reason}</p>{/if}
          <div class="questions">
            {#each briefing?.suggested_questions || ['What needs attention?', 'What can you do?'] as question (question)}<button
                onclick={() => send(question)}
                disabled={busy}>{question}<span>↗</span></button
              >{/each}
          </div>
        </section>{/if}
      <div
        role="log"
        aria-live="polite"
        aria-relevant="additions text"
        aria-label="Observer conversation"
      >
        {#each messages as message (message.id)}<article
            class="message"
            class:user={message.role === 'user'}
          >
            <div class="message-label">{message.role === 'user' ? 'YOU' : 'OBSERVER'}</div>
            <p>{message.content || (busy ? 'Reading verified facts…' : 'No answer received.')}</p>
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
      {#if error}<p class="error" role="alert">{error}</p>{/if}
    </div>
    <form
      class="composer"
      onsubmit={(event) => {
        event.preventDefault();
        void send();
      }}
    >
      <label for="observer-question" class="sr-only">Ask Observer</label><textarea
        id="observer-question"
        bind:this={textarea}
        bind:value={input}
        rows="2"
        maxlength="2000"
        placeholder={scope.page === 'TASK' ? 'Ask about this task…' : 'Ask about your system…'}
        disabled={busy}
        onkeydown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            void send();
          }
        }}
      ></textarea>
      <div class="composer-footer">
        <span>{busy ? activity : activity || 'No source access. No write authority.'}</span><button
          type="submit"
          disabled={busy || !input.trim()}
          aria-label="Send Observer question">{busy ? 'Reading…' : 'Send ↑'}</button
        >
      </div>
    </form>
    <footer class="panel-footer">
      <span>Engineering always has priority.</span><a
        href={resolve('/settings')}
        onclick={closePanel}>Observer settings</a
      >
    </footer>
  {/if}
</dialog>

<style>
  .observer-dock {
    position: fixed;
    z-index: 49;
    isolation: isolate;
  }
  .observer-launch {
    position: relative;
    display: grid;
    justify-items: center;
    border: 1px solid color-mix(in srgb, var(--color-brand) 30%, transparent);
    border-radius: 50%;
    background: color-mix(in srgb, var(--color-panel) 88%, transparent);
    width: 78px;
    height: 78px;
    box-shadow: 0 8px 30px #0003;
    cursor: grab;
    touch-action: none;
    user-select: none;
    -webkit-user-select: none;
    transition:
      border-color 180ms,
      box-shadow 180ms,
      background 180ms;
  }
  .observer-launch:hover {
    border-color: var(--color-brand);
  }
  .dock-label {
    position: absolute;
    bottom: 6px;
    font: 7px monospace;
    letter-spacing: 0.16em;
    color: var(--color-muted);
  }
  .observer-badge {
    position: absolute;
    top: 0;
    right: 0;
    background: #fbbf24;
    color: #111827;
    border-radius: 20px;
    padding: 2px 6px;
    font: 10px monospace;
  }
  .observer-badge.critical {
    background: #fb7185;
  }
  .observer-bubble {
    position: fixed;
    box-sizing: border-box;
    overflow-y: auto;
    max-width: 280px;
    background: var(--color-panel);
    color: var(--color-heading);
    border: 1px solid var(--color-line);
    border-radius: 14px;
    padding: 14px;
    font-size: 12px;
    display: flex;
    gap: 12px;
    box-shadow: 0 12px 40px #0003;
  }
  .observer-bubble button {
    align-self: flex-start;
  }
  .observer-dialog {
    position: fixed;
    inset: auto;
    z-index: 48;
    box-sizing: border-box;
    margin: 0;
    padding: 0;
    max-height: none;
    max-width: none;
    border: 1px solid color-mix(in srgb, var(--color-brand) 30%, var(--color-line));
    border-radius: 22px;
    background: var(--color-panel);
    color: var(--color-heading);
    box-shadow:
      0 24px 70px #0004,
      0 4px 16px #0002;
    overflow: hidden;
  }
  .observer-dialog[open] {
    display: flex;
    flex-direction: column;
  }
  .panel-header {
    display: flex;
    align-items: center;
    gap: 4px;
    flex-shrink: 0;
    min-height: 96px;
    padding: 6px 10px 0 2px;
    background: radial-gradient(
      ellipse at 0% 0%,
      color-mix(in srgb, var(--color-brand) 12%, transparent),
      transparent 80%
    );
  }
  .header-copy {
    flex: 1;
    min-width: 0;
  }
  .header-copy > span {
    display: block;
  }
  .panel-drag {
    display: flex;
    flex: 1;
    min-width: 0;
    align-items: center;
    text-align: left;
    border-radius: 12px;
    cursor: grab;
    touch-action: none;
    user-select: none;
    -webkit-user-select: none;
  }
  .grip {
    color: var(--color-muted);
    opacity: 0.55;
    font-size: 19px;
    padding: 0 5px;
  }
  .window-controls {
    display: flex;
    align-self: flex-start;
    align-items: center;
  }
  .reset-position {
    color: var(--color-muted);
    font-size: 18px;
    padding: 8px;
    border-radius: 8px;
  }
  .reset-position:hover {
    background: var(--color-panel-alt);
    color: var(--color-brand);
  }
  .dragging .observer-launch,
  .dragging .panel-drag {
    cursor: grabbing;
  }
  .eyebrow {
    font: 9px monospace;
    letter-spacing: 0.15em;
    color: var(--color-brand);
    margin-bottom: 7px;
  }
  .panel-title {
    font-size: 25px;
    font-weight: 500;
    letter-spacing: -0.03em;
  }
  .subtext {
    color: var(--color-muted);
    font-size: 11px;
  }
  .icon-button {
    font-size: 25px;
    color: var(--color-muted);
    padding: 5px 10px;
    cursor: pointer;
    border-radius: 8px;
  }
  .close {
    align-self: flex-start;
  }
  .icon-button:hover {
    background: var(--color-panel-alt);
  }
  .status-strip {
    display: flex;
    align-items: center;
    gap: 7px;
    margin: 0 22px;
    padding: 10px 0;
    font: 10px monospace;
    border-bottom: 1px solid var(--color-line);
    color: var(--color-muted);
  }
  .status-cost {
    margin-left: auto;
    font-size: 8px;
    color: var(--color-brand);
  }
  .status-dot {
    height: 5px;
    width: 5px;
    border-radius: 50%;
    background: var(--color-brand);
  }
  .status-dot.warning {
    background: #fbbf24;
  }
  .status-dot.critical {
    background: #fb7185;
  }
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
    color: var(--color-panel);
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

  /* Display mode is shared with the shell. Only the Observer's presentation changes. */
  .observer-dock[data-display='jarvis'] .observer-launch {
    border-color: color-mix(in srgb, var(--color-brand) 65%, var(--color-line));
    background: radial-gradient(
      circle,
      color-mix(in srgb, var(--color-brand) 15%, var(--color-panel)),
      var(--color-panel) 72%
    );
    box-shadow:
      0 0 26px color-mix(in srgb, var(--color-brand) 18%, transparent),
      inset 0 0 18px color-mix(in srgb, var(--color-brand) 10%, transparent),
      0 8px 30px #0004;
  }
  .observer-dock[data-display='jarvis'] .observer-launch::before {
    content: '';
    position: absolute;
    inset: -5px;
    border: 1px dashed color-mix(in srgb, var(--color-brand) 36%, transparent);
    border-radius: 50%;
    pointer-events: none;
  }
  .observer-dock[data-display='jarvis'] .dock-label {
    color: var(--color-brand);
    font-family: var(--font-jarvis-display);
    font-size: 6px;
  }
  .observer-dock[data-display='jarvis'] .observer-bubble,
  .observer-dialog[data-display='jarvis'] {
    border-radius: 12px;
    border-color: color-mix(in srgb, var(--color-brand) 50%, var(--color-line));
    background: linear-gradient(
      135deg,
      color-mix(in srgb, var(--color-brand) 7%, var(--color-panel)),
      var(--color-panel) 65%
    );
    box-shadow:
      0 24px 70px #0005,
      0 0 32px color-mix(in srgb, var(--color-brand) 12%, transparent),
      inset 0 0 0 3px color-mix(in srgb, var(--color-brand) 5%, transparent);
    font-family: var(--font-jarvis-body);
  }
  .observer-dialog[data-display='jarvis']::after {
    content: '';
    position: absolute;
    inset: 0;
    pointer-events: none;
    border-radius: inherit;
    background:
      linear-gradient(var(--color-brand), var(--color-brand)) left top / 30px 2px no-repeat,
      linear-gradient(var(--color-brand), var(--color-brand)) left top / 2px 30px no-repeat,
      linear-gradient(var(--color-brand-2), var(--color-brand-2)) right bottom / 30px 2px no-repeat,
      linear-gradient(var(--color-brand-2), var(--color-brand-2)) right bottom / 2px 30px no-repeat;
    opacity: 0.8;
  }
  .observer-dialog[data-display='jarvis'] .panel-header {
    background:
      linear-gradient(color-mix(in srgb, var(--color-brand) 6%, transparent) 1px, transparent 1px) 0
        0 / 20px 20px,
      linear-gradient(
          90deg,
          color-mix(in srgb, var(--color-brand) 6%, transparent) 1px,
          transparent 1px
        )
        0 0 / 20px 20px,
      radial-gradient(
        ellipse at left top,
        color-mix(in srgb, var(--color-brand) 16%, transparent),
        transparent 80%
      );
  }
  .observer-dialog[data-display='jarvis'] .panel-title {
    font-family: var(--font-jarvis-display);
    font-size: 20px;
    letter-spacing: 0.02em;
  }
  .observer-dialog[data-display='jarvis'] .status-dot {
    box-shadow: 0 0 8px currentColor;
    color: var(--color-brand);
  }
  .observer-dialog[data-display='jarvis'] .composer,
  .observer-dialog[data-display='jarvis'] .questions button {
    border-radius: 5px;
    border-color: color-mix(in srgb, var(--color-brand) 25%, var(--color-line));
    background: color-mix(in srgb, var(--color-brand) 4%, var(--color-panel-alt));
  }
  .observer-dialog[data-display='jarvis'] .sources span {
    border-radius: 3px;
  }
  .compact .panel-header {
    min-height: 62px;
  }
  .compact .panel-drag :global(.orb) {
    width: 54px !important;
    height: 54px !important;
  }
  .compact .eyebrow,
  .compact .panel-footer {
    display: none;
  }
  .compact .status-strip,
  .compact .panel-actions {
    padding-top: 6px;
    padding-bottom: 6px;
  }
  .compact .composer {
    margin-bottom: 10px;
  }
  @media (prefers-reduced-motion: reduce) {
    .observer-launch {
      transition: none;
    }
  }
  @media (max-width: 640px) {
    .observer-launch {
      width: 66px;
      height: 66px;
    }
    .observer-launch :global(.orb) {
      width: 64px !important;
      height: 64px !important;
    }
    .panel-header {
      padding-right: 6px;
    }
    .grip {
      display: none;
    }
    .reset-position {
      padding: 5px;
    }
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
