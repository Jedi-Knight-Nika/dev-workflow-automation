<script lang="ts">
  import { resolve } from '$app/paths';
  import { onDestroy } from 'svelte';
  import type { Terminal as XTerm } from '@xterm/xterm';
  import '@xterm/xterm/css/xterm.css';
  import Button from '$lib/components/Button.svelte';
  import ErrorBanner from '$lib/components/ErrorBanner.svelte';
  import type { AgentConfig, TerminalAccess } from '$lib/types';
  import { runTaskCommand } from '$lib/services/tasks';
  import {
    closeTerminal,
    openTerminal,
    terminalWebSocketProtocols,
    terminalWebSocketUrl
  } from '$lib/services/terminals';
  import { t } from '$lib/i18n/index.svelte';

  let { agent, nodeId, onClose }: { agent: AgentConfig; nodeId: string; onClose: () => void } =
    $props();
  let host: HTMLDivElement;
  let terminal: XTerm | null = null;
  let socket: WebSocket | null = null;
  let access: TerminalAccess | null = null;
  let connecting = $state(false);
  let connected = $state(false);
  let error = $state('');
  let resizeHandler: (() => void) | null = null;
  let manualControl = $state(false);
  let stopping = $state(false);
  let notice = $state('');

  async function connect() {
    if (!agent.active_task_id) return;
    connecting = true;
    error = '';
    try {
      if (!agent.active_task_manual_takeover) {
        await runTaskCommand(agent.active_task_id, 'takeover');
      }
      access = await openTerminal(agent.active_task_id, nodeId);
      const [{ Terminal }, { FitAddon }] = await Promise.all([
        import('@xterm/xterm'),
        import('@xterm/addon-fit')
      ]);
      terminal = new Terminal({
        cursorBlink: true,
        convertEol: true,
        fontFamily: "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace",
        fontSize: 13,
        theme: { background: '#070b12', foreground: '#d8e3f3', cursor: '#6ea2ff' },
        scrollback: 10_000
      });
      const fit = new FitAddon();
      terminal.loadAddon(fit);
      terminal.open(host);
      fit.fit();
      socket = new WebSocket(terminalWebSocketUrl(access), terminalWebSocketProtocols(access));
      socket.onopen = () => {
        connected = true;
        socket?.send(
          JSON.stringify({ type: 'resize', cols: terminal?.cols, rows: terminal?.rows })
        );
      };
      socket.onmessage = (event) => {
        const message = JSON.parse(String(event.data)) as { type: string; data?: string };
        if (message.type === 'output' && message.data) terminal?.write(message.data);
      };
      socket.onerror = () => (error = t('terminal.connectionFailed'));
      socket.onclose = () => (connected = false);
      terminal.onData((data) => socket?.send(JSON.stringify({ type: 'input', data })));
      terminal.onResize(({ cols, rows }) =>
        socket?.send(JSON.stringify({ type: 'resize', cols, rows }))
      );
      resizeHandler = () => fit.fit();
      window.addEventListener('resize', resizeHandler, { passive: true });
    } catch (cause) {
      error = String(cause);
    } finally {
      connecting = false;
    }
  }

  async function stopAgent() {
    if (!agent.active_task_id) return;
    stopping = true;
    error = '';
    try {
      await runTaskCommand(agent.active_task_id, 'pause');
      notice = t('terminal.stopRequested');
    } catch (cause) {
      error = String(cause);
    } finally {
      stopping = false;
    }
  }

  function interrupt() {
    socket?.send(JSON.stringify({ type: 'interrupt' }));
  }

  async function release() {
    if (access) await closeTerminal(access.session_id);
    socket?.close();
    if (agent.active_task_id) await runTaskCommand(agent.active_task_id, 'resume');
    onClose();
  }

  onDestroy(() => {
    socket?.close();
    terminal?.dispose();
    if (resizeHandler) window.removeEventListener('resize', resizeHandler);
  });
</script>

<div
  class="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4"
  role="presentation"
>
  <section
    class="border-line bg-panel flex h-[82vh] w-full max-w-6xl flex-col rounded-xl border shadow-2xl"
  >
    <header class="border-line flex items-center gap-3 border-b p-4">
      <div>
        <p class="text-brand font-mono text-[10px]">{t('terminal.liveActivity')}</p>
        <h2 class="font-semibold">{agent.role}</h2>
      </div>
      <span class="font-mono text-[10px] {agent.active_jobs > 0 ? 'text-accent' : 'text-muted'}">
        {agent.active_jobs > 0 ? t('terminal.working') : t('terminal.idle')}
      </span>
      <div class="ml-auto flex gap-2">
        {#if connected}<Button size="sm" variant="ghost" onclick={interrupt}
            >{t('terminal.sendCtrlC')}</Button
          >{/if}
        {#if connected}<Button size="sm" onclick={release}>{t('terminal.releaseResume')}</Button
          >{/if}
        <Button size="sm" variant="ghost" onclick={onClose}>{t('terminal.close')}</Button>
      </div>
    </header>
    <ErrorBanner message={error} class="m-3" />
    {#if notice}<p class="mx-4 mt-3 text-sm text-accent">{notice}</p>{/if}
    {#if !manualControl}
      <div class="flex min-h-0 flex-1 items-center justify-center p-6">
        <div class="border-line bg-panel-alt w-full max-w-2xl rounded-xl border p-6 shadow-xl">
          <div class="mb-6 flex items-center gap-4">
            <span class:active={agent.active_jobs > 0} class="live-orb" aria-hidden="true"></span>
            <div class="min-w-0">
              <p class="text-muted text-xs font-semibold tracking-[0.12em] uppercase">
                {agent.active_jobs > 0 ? t('terminal.agentWorking') : t('terminal.agentIdle')}
              </p>
              <p class="mt-1 truncate text-lg font-semibold">
                {agent.current_job_action?.replaceAll('_', ' ') || t('terminal.processingTask')}
              </p>
            </div>
          </div>
          <div class="thinking-track" class:active={agent.active_jobs > 0} aria-hidden="true">
            <span></span><span></span><span></span><span></span>
          </div>
          <p class="text-muted mt-4 text-sm">{t('terminal.observerHint')}</p>
          <div class="mt-6 flex flex-wrap gap-2">
            {#if agent.active_task_id}
              <a
                class="border-line text-muted hover:border-brand-2 hover:text-brand-2 rounded-lg border px-3 py-2 text-xs transition-colors"
                href={resolve('/tasks/[id]', { id: agent.active_task_id })}
                >{t('terminal.openTask')}</a
              >
              <Button variant="danger" disabled={stopping} onclick={stopAgent}>
                {stopping ? t('terminal.stopping') : t('terminal.stopAgent')}
              </Button>
            {/if}
            {#if agent.active_task_id && agent.active_task_has_workspace}
              <Button variant="ghost" onclick={() => (manualControl = true)}>
                {t('terminal.openManualControl')}
              </Button>
            {/if}
          </div>
        </div>
      </div>
    {:else if !agent.active_task_id || !agent.active_task_has_workspace}
      <div class="m-auto max-w-md text-center">
        <h3 class="font-semibold">{t('terminal.noActiveWorkspace')}</h3>
        <p class="text-muted mt-2 text-sm">
          {t('terminal.noActiveWorkspaceHint')}
        </p>
      </div>
    {:else if !connected}
      <div class="m-auto text-center">
        <p class="text-muted mb-4 max-w-md text-sm">
          {t('terminal.takeoverHint')}
        </p>
        <Button variant="primary" disabled={connecting} onclick={connect}>
          {connecting ? t('terminal.takingControl') : t('terminal.takeControlConnect')}
        </Button>
      </div>
    {/if}
    <div bind:this={host} class:hidden={!connected} class="min-h-0 flex-1 bg-[#070b12] p-2"></div>
  </section>
</div>

<style>
  .live-orb {
    width: 1rem;
    height: 1rem;
    flex: none;
    border-radius: 999px;
    background: var(--color-muted);
  }
  .live-orb.active {
    background: var(--color-accent);
    box-shadow:
      0 0 0 6px color-mix(in srgb, var(--color-accent) 12%, transparent),
      0 0 24px color-mix(in srgb, var(--color-accent) 65%, transparent);
    animation: live-pulse 1.5s ease-in-out infinite;
  }
  .thinking-track {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 0.5rem;
  }
  .thinking-track span {
    height: 0.3rem;
    border-radius: 999px;
    background: var(--color-line);
  }
  .thinking-track.active span {
    background: linear-gradient(90deg, var(--color-brand), var(--color-accent));
    animation: thinking 1.2s ease-in-out infinite alternate;
  }
  .thinking-track.active span:nth-child(2) {
    animation-delay: 120ms;
  }
  .thinking-track.active span:nth-child(3) {
    animation-delay: 240ms;
  }
  .thinking-track.active span:nth-child(4) {
    animation-delay: 360ms;
  }
  @keyframes thinking {
    from {
      opacity: 0.22;
      transform: scaleX(0.55);
    }
    to {
      opacity: 1;
      transform: scaleX(1);
    }
  }
  @keyframes live-pulse {
    50% {
      transform: scale(1.12);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .live-orb.active,
    .thinking-track.active span {
      animation: none;
    }
  }
</style>
