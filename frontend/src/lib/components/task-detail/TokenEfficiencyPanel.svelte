<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api';
  let { taskId }: { taskId: string } = $props();
  type Metrics = {
    total_input_tokens: number | null;
    cached_input_tokens: number | null;
    output_tokens: number | null;
    tokens_to_first_edit: number | null;
    peak_active_context_tokens: number | null;
    tokens_since_last_progress: number | null;
    context_generation_count: number;
    rollover_count: number;
    compaction_count: number;
    warnings: string[];
    policy: { values: { execution_profile: string; mode: string } } | null;
  };
  type Generation = {
    id: string;
    sequence: number;
    status: string;
    model: string;
    harness: string;
  };
  let metrics = $state<Metrics | null>(null);
  let generations = $state<Generation[]>([]);
  let message = $state('');
  let note = $state('');
  let busy = $state(false);
  let override = $state('INHERIT');
  async function saveOverride() {
    if (busy) return;
    busy = true;
    try {
      const current = await api<{ version: number }>(`/v2/tasks/${taskId}/token-efficiency-policy`);
      await api(`/v2/tasks/${taskId}/token-efficiency-policy`, {
        method: 'PUT',
        body: JSON.stringify({
          version: current.version,
          values:
            override === 'INHERIT'
              ? {}
              : {
                  execution_profile: override,
                  mode: metrics?.policy?.values.mode ?? 'INSTRUMENT'
                }
        })
      });
      message = 'Execution override saved; budgets and cumulative usage are unchanged.';
    } catch (error) {
      message = String(error);
    } finally {
      busy = false;
    }
    await load();
  }
  const count = (value: number | null) => (value == null ? 'Unknown' : value.toLocaleString());
  async function load() {
    if (busy) return;
    busy = true;
    try {
      [metrics, generations] = await Promise.all([
        api<Metrics>(`/v2/tasks/${taskId}/token-efficiency`),
        api<Generation[]>(`/v2/tasks/${taskId}/context-generations`)
      ]);
    } catch (error) {
      message = String(error);
    } finally {
      busy = false;
    }
  }
  async function rollover() {
    if (busy) return;
    busy = true;
    try {
      const task = await api<{ requirement_version: number }>(`/tasks/${taskId}`);
      await api(`/v2/tasks/${taskId}/context-rollover`, {
        method: 'POST',
        body: JSON.stringify({ requirement_version: task.requirement_version, note })
      });
      message =
        'Checkpoint saved and old context sealed. Task remains suspended; resume separately.';
      note = '';
    } catch (error) {
      message = String(error);
    } finally {
      busy = false;
    }
    await load();
  }
  onMount(() => {
    void load();
    const timer = setInterval(() => {
      if (!document.hidden) void load();
    }, 5000);
    return () => clearInterval(timer);
  });
</script>

<section class="min-w-0 rounded-xl border border-line bg-panel p-5 space-y-3 xl:col-span-2">
  <h3 class="font-semibold">Native Developer · token efficiency</h3>
  {#if metrics}
    <p class="text-sm text-muted">
      {metrics.policy?.values.execution_profile ?? 'STANDARD'} · {metrics.policy?.values.mode ??
        'INSTRUMENT'} · Active context is an estimate, not cumulative billing.
    </p>
    <dl class="grid grid-cols-2 gap-3 md:grid-cols-4">
      {#each [['Input', count(metrics.total_input_tokens)], ['Cached input', count(metrics.cached_input_tokens)], ['Output', count(metrics.output_tokens)], ['Tokens to first edit', count(metrics.tokens_to_first_edit)], ['Peak active context', count(metrics.peak_active_context_tokens)], ['Tokens since progress', count(metrics.tokens_since_last_progress)], ['Compactions', count(metrics.compaction_count)], ['Rollovers', count(metrics.rollover_count)]] as [label, value] (label)}<div
        >
          <dt class="text-xs text-muted">{label}</dt>
          <dd class="font-mono text-sm">{value}</dd>
        </div>{/each}
    </dl>
    {#each metrics.warnings as warning (warning)}<p class="text-sm text-warning">
        {warning.replaceAll('_', ' ')}
      </p>{/each}
    <details>
      <summary class="cursor-pointer text-sm"
        >Context generations ({metrics.context_generation_count})</summary
      >
      {#each generations as generation (generation.id)}<p class="mt-2 text-sm">
          #{generation.sequence} · {generation.harness} / {generation.model} · {generation.status}
        </p>{/each}
      {#if !generations.length}<p class="text-sm text-muted">
          Historical runs predate V2.2 instrumentation. Unknown measurements are not zero.
        </p>{/if}
    </details>
    <details>
      <summary class="cursor-pointer text-sm">New context on the same checkout</summary>
      <p class="mt-2 text-sm text-muted">
        Pause first and reconcile all billing. Summarize completed work, decisions, remaining issues
        and next action. This seals the old native context without deleting it or resetting spend.
      </p>
      <label class="mt-2 block text-sm"
        >Continuation note<textarea
          class="mt-1 w-full rounded border border-line bg-panel p-2"
          rows="4"
          maxlength="2000"
          bind:value={note}
        ></textarea></label
      >
      <button
        class="mt-2 rounded border border-line px-3 py-2 text-sm disabled:opacity-50"
        disabled={busy || note.trim().length < 3}
        onclick={rollover}>Checkpoint and seal context</button
      >
    </details>
    <details>
      <summary class="cursor-pointer text-sm">Suspended-task execution override</summary>
      <label class="mt-2 block text-sm"
        >Profile
        <select class="ml-2 rounded border border-line bg-panel p-2" bind:value={override}>
          {#each ['INHERIT', 'FAST', 'STANDARD', 'LARGE'] as option (option)}<option
              >{option}</option
            >{/each}
        </select>
      </label>
      <button
        class="mt-2 rounded border border-line px-3 py-2 text-sm"
        disabled={busy}
        onclick={saveOverride}>Apply override</button
      >
    </details>
  {/if}
  {#if message}<p role="status" class="text-sm">{message}</p>{/if}
</section>
