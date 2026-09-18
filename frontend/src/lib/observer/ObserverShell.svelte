<script lang="ts">
  import { onMount, tick, untrack } from 'svelte';
  import { SvelteSet } from 'svelte/reactivity';
  import { page } from '$app/state';
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
  import { observerApi } from './api';
  import { createObserverConversation } from './conversation.svelte';
  import ObserverPanelContent from './ObserverPanelContent.svelte';
  import { getAssistantName, setAssistantName } from './identity.svelte';
  import type { Briefing, FocusMode, ObserverScope, ObserverStatus, OrbMode } from './types';

  let enabled = $state(false);
  const assistantName = $derived(getAssistantName());
  let currentStatus = $state<ObserverStatus | null>(null);
  let briefing = $state<Briefing | null>(null);
  let open = $state(false);
  let offline = $state(false);
  let bubble = $state('');
  let unreadReply = $state(false);
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
  let refreshRequest: AbortController | undefined;
  let refreshTimer: ReturnType<typeof setTimeout> | undefined;
  let bubbleTimer: ReturnType<typeof setTimeout> | undefined;
  let mounted = false;
  let lastBubble = 0;
  const seen = new SvelteSet<string>();
  let explicitScope = $state<ObserverScope | null>(null);

  const conversation = createObserverConversation({
    enabled: () => enabled,
    name: () => assistantName,
    scope: () => scope,
    open: () => open,
    reply: (answer) => {
      unreadReply = true;
      if (focus === 'silent') return;
      bubble = `${assistantName} replied: ${answer.slice(0, 130)}`;
      clearTimeout(bubbleTimer);
      bubbleTimer = setTimeout(() => {
        bubble = '';
      }, 15000);
    },
    scroll: () => {
      void tick().then(() => {
        if (log) log.scrollTop = log.scrollHeight;
      });
    },
    changeScope: (value) => {
      explicitScope = value;
    },
    refresh: () => refresh(true)
  });
  const chat = conversation.state;

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
      : chat.busy
        ? chat.activity === 'Answering'
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
        conversation.abort();
        chat.messages = [];
        chat.id = undefined;
        briefing = null;
        void refresh(true);
      });
    }
  });

  function stop() {
    conversation.abort();
    refreshRequest?.abort();
    clearTimeout(refreshTimer);
    clearTimeout(bubbleTimer);
    chat.busy = false;
    bubble = '';
    unreadReply = false;
    currentStatus = null;
    briefing = null;
    closePanel();
  }

  async function configuration() {
    try {
      const response = await observerApi.configuration();
      setAssistantName(response.display_name);
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
    unreadReply = false;
    bubble = '';
    chat.error = '';
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
    open = false;
    dialog?.close();
    if (restoreFocus) launcher?.focus({ preventScroll: true });
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
    const channel =
      typeof BroadcastChannel !== 'undefined'
        ? new BroadcastChannel('observer-configuration')
        : null;
    if (channel) channel.onmessage = configChanged;
    window.addEventListener('observer:configuration', configChanged);
    document.addEventListener('visibilitychange', visibility);
    return () => {
      mounted = false;
      enabled = false;
      stop();
      channel?.close();
      window.removeEventListener('observer:configuration', configChanged);
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
          aria-label="Dismiss {assistantName} notice">×</button
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
      aria-label="Open {assistantName} assistant"
      title="{assistantName} · {offline
        ? 'offline'
        : currentStatus?.ai_available
          ? 'local AI available'
          : 'deterministic facts'} · Drag to move"
    >
      <ObserverOrb {mode} {displayMode} size={dockSize - 2} />
      {#if unreadReply}<span class="observer-badge" aria-label="Unread reply">●</span>
      {:else if currentStatus?.open_attention_count}<span
          class="observer-badge"
          class:critical={currentStatus.highest_severity === 'CRITICAL'}
          >{currentStatus.open_attention_count}</span
        >{/if}
      <span class="dock-label">{assistantName}</span>
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
  }}
>
  {#if open && enabled}
    <header class="panel-header">
      <button
        class="panel-drag"
        use:draggable={dragOptions}
        aria-label="Move {assistantName} panel"
        aria-describedby="observer-move-help"
        title="Drag to move · Arrow keys to adjust"
      >
        <ObserverOrb {mode} {displayMode} size={82} />
        <span class="header-copy">
          <span class="eyebrow"
            >{displayMode === 'jarvis' ? 'ASSISTANT / OPERATIONS LINK' : 'AMBIENT OPERATIONS'}</span
          >
          <span id="observer-panel-title" class="panel-title" title={assistantName}
            >{assistantName}</span
          >
          <span class="subtext">Read-only companion · {scopeName}</span>
        </span>
        <span class="grip" aria-hidden="true">⠿</span>
      </button>
      <div class="window-controls">
        <button
          class="reset-position"
          onclick={resetPosition}
          aria-label="Reset {assistantName} position"
          title="Reset position">↘</button
        >
        <button class="icon-button close" onclick={closePanel} aria-label="Close {assistantName}"
          >×</button
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
    <ObserverPanelContent
      {conversation}
      {assistantName}
      {briefing}
      {currentStatus}
      {scope}
      {attention}
      bind:focus
      bind:log
      bind:textarea
      onclose={closePanel}
      onrefresh={() => refresh()}
    />
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
    max-width: 80%;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    text-transform: uppercase;
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
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
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
  button {
    cursor: pointer;
  }
  button:disabled {
    cursor: default;
  }
  button:focus-visible {
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
  .compact .panel-header {
    min-height: 62px;
  }
  .compact .panel-drag :global(.orb) {
    width: 54px !important;
    height: 54px !important;
  }
  .compact .eyebrow {
    display: none;
  }
  .compact .status-strip {
    padding-top: 6px;
    padding-bottom: 6px;
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
  }
</style>
