<script lang="ts">
  import { onMount } from 'svelte';
  import Button from '$lib/components/Button.svelte';
  import ErrorBanner from '$lib/components/ErrorBanner.svelte';
  import TokenEfficiencyPanel from './TokenEfficiencyPanel.svelte';
  import {
    getDeveloperSession,
    changeDeveloperSession,
    type DeveloperSessionView,
    type SessionChangeMode
  } from '$lib/services/engineering';

  let { taskId, onChanged }: { taskId: string; onChanged: () => Promise<void> } = $props();
  let session = $state<DeveloperSessionView | null>(null);
  let mode = $state<SessionChangeMode>('keep_native');
  let reason = $state('');
  let error = $state('');
  let notice = $state('');
  let busy = $state(false);

  async function reload() {
    busy = true;
    error = '';
    notice = '';
    try {
      session = await getDeveloperSession(taskId);
      if (session && !session.keep_native_available) mode = 'handoff';
    } catch (cause) {
      error = cause instanceof Error ? cause.message : 'Could not load the native session';
    } finally {
      busy = false;
    }
  }

  async function apply() {
    if (!session || session.blocker || busy) return;
    if (
      mode === 'handoff' &&
      !confirm(
        'Create a new native session on this checkout? Previous sessions and usage stay recorded. The task will remain suspended.'
      )
    )
      return;
    busy = true;
    error = '';
    notice = '';
    try {
      session = await changeDeveloperSession(taskId, session, mode, reason.trim());
      reason = '';
      notice =
        'Session configuration saved. Usage is unchanged. Resume work separately when ready.';
      await onChanged();
    } catch (cause) {
      error = cause instanceof Error ? cause.message : 'Could not change the native session';
    } finally {
      busy = false;
    }
  }

  onMount(() => {
    void reload();
  });
</script>

<TokenEfficiencyPanel {taskId} />

{#if session || error}
  <details class="min-w-0 rounded-xl border border-line bg-panel p-5 xl:col-span-2">
    <summary class="cursor-pointer text-sm font-semibold">Native Developer session</summary>
    <div class="mt-4 space-y-3">
      {#if error}<ErrorBanner message={error} />{/if}
      {#if notice}<p class="text-sm text-success" role="status">{notice}</p>{/if}
      {#if session}
        <p class="text-sm">
          Current: {session.harness} / {session.model} · generation {session.generation} · {session.state}
        </p>
        <p class="text-sm text-muted">
          Team profile: {session.target_harness} / {session.target_model}. Configure the target
          model in Teams, then explicitly apply it here. This never resets spending limits, modifies
          source files, or starts a paid turn.
        </p>
        {#if session.blocker}<p class="text-sm text-warning">{session.blocker}</p>{/if}
        <label class="block text-sm">
          Session change
          <select
            class="mt-1 w-full rounded-lg border border-line bg-panel p-2"
            bind:value={mode}
            disabled={busy}
          >
            {#if session.keep_native_available}
              <option value="keep_native">Keep the Codex thread and apply the Team model</option>
            {/if}
            <option value="handoff">New native session with a bounded handoff</option>
          </select>
        </label>
        <label class="block text-sm">
          Reason for change
          <textarea
            class="mt-1 w-full rounded-lg border border-line bg-panel p-2"
            rows="2"
            maxlength="500"
            bind:value={reason}
            disabled={busy}
          ></textarea>
        </label>
        <div class="flex flex-wrap gap-2">
          <Button disabled={busy || !!session.blocker || reason.trim().length < 3} onclick={apply}
            >Apply session change</Button
          >
        </div>
      {/if}
      <Button disabled={busy} onclick={reload}>Refresh session</Button>
    </div>
  </details>
{/if}
