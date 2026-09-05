<script lang="ts">
  import { onDestroy } from 'svelte';
  import type { Terminal as XTerm } from '@xterm/xterm';
  import '@xterm/xterm/css/xterm.css';
  import Button from '$lib/components/Button.svelte';
  import ErrorBanner from '$lib/components/ErrorBanner.svelte';
  import type { AgentConfig, TerminalAccess } from '$lib/types';
  import { runTaskCommand } from '$lib/services/tasks';
  import { closeTerminal, openTerminal, terminalWebSocketUrl } from '$lib/services/terminals';

  let { agent, nodeId, onclose }: { agent: AgentConfig; nodeId: string; onclose: () => void } =
    $props();
  let host: HTMLDivElement;
  let terminal: XTerm | null = null;
  let socket: WebSocket | null = null;
  let access: TerminalAccess | null = null;
  let connecting = $state(false);
  let connected = $state(false);
  let error = $state('');

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
        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
        fontSize: 13,
        theme: { background: '#070b12', foreground: '#d8e3f3', cursor: '#6ea2ff' },
        scrollback: 10_000
      });
      const fit = new FitAddon();
      terminal.loadAddon(fit);
      terminal.open(host);
      fit.fit();
      socket = new WebSocket(terminalWebSocketUrl(access));
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
      socket.onerror = () => (error = 'Terminal connection failed');
      socket.onclose = () => (connected = false);
      terminal.onData((data) => socket?.send(JSON.stringify({ type: 'input', data })));
      terminal.onResize(({ cols, rows }) =>
        socket?.send(JSON.stringify({ type: 'resize', cols, rows }))
      );
      window.addEventListener('resize', () => fit.fit(), { passive: true });
    } catch (cause) {
      error = String(cause);
    } finally {
      connecting = false;
    }
  }

  function interrupt() {
    socket?.send(JSON.stringify({ type: 'interrupt' }));
  }

  async function release() {
    if (access) await closeTerminal(access.session_id);
    socket?.close();
    if (agent.active_task_id) await runTaskCommand(agent.active_task_id, 'resume');
    onclose();
  }

  onDestroy(() => {
    socket?.close();
    terminal?.dispose();
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
        <p class="text-brand font-mono text-[10px]">MANUAL CONTROL · {agent.role}</p>
        <h2 class="font-semibold">Workspace console</h2>
      </div>
      <span class="font-mono text-[10px] {connected ? 'text-accent' : 'text-muted'}">
        {connected ? 'CONNECTED' : 'OFFLINE'}
      </span>
      <div class="ml-auto flex gap-2">
        {#if connected}<Button size="sm" variant="ghost" onclick={interrupt}>Send Ctrl+C</Button
          >{/if}
        {#if connected}<Button size="sm" onclick={release}>Release & resume AI</Button>{/if}
        <Button size="sm" variant="ghost" onclick={onclose}>Close</Button>
      </div>
    </header>
    <ErrorBanner message={error} class="m-3" />
    {#if !agent.active_task_id || !agent.active_task_has_workspace}
      <div class="m-auto max-w-md text-center">
        <h3 class="font-semibold">No active workspace</h3>
        <p class="text-muted mt-2 text-sm">
          This agent needs an active task with a prepared repository workspace before manual control
          is available.
        </p>
      </div>
    {:else if !connected}
      <div class="m-auto text-center">
        <p class="text-muted mb-4 max-w-md text-sm">
          Taking control pauses this task, cancels queued AI work, and records a durable takeover
          event. Terminal input is enabled only after takeover succeeds.
        </p>
        <Button variant="primary" disabled={connecting} onclick={connect}>
          {connecting ? 'Taking control…' : 'Take control and connect'}
        </Button>
      </div>
    {/if}
    <div bind:this={host} class:hidden={!connected} class="min-h-0 flex-1 bg-[#070b12] p-2"></div>
  </section>
</div>
