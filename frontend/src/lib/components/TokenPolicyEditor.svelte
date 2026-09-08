<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api';
  let { teamId }: { teamId: string } = $props();
  type Policy = { version: number; values: Record<string, string | number | boolean> };
  let policy = $state<Policy | null>(null);
  let profile = $state('STANDARD');
  let mode = $state('INSTRUMENT');
  let effort = $state('medium');
  let advanced = $state('');
  let busy = $state(false);
  let message = $state('');
  async function load() {
    try {
      policy = await api<Policy>(`/teams/${teamId}/token-efficiency-policy`);
      profile = String(policy.values.execution_profile);
      mode = String(policy.values.mode);
      effort = String(policy.values.reasoning_effort);
      advanced = JSON.stringify(policy.values, null, 2);
    } catch (error) {
      message = String(error);
    }
  }
  async function save() {
    if (!policy || busy) return;
    busy = true;
    message = '';
    try {
      const values = profile === 'CUSTOM' ? JSON.parse(advanced) : {};
      await api(`/teams/${teamId}/token-efficiency-policy`, {
        method: 'PUT',
        body: JSON.stringify({
          version: policy.version,
          values: {
            ...values,
            execution_profile: profile,
            mode,
            reasoning_effort: profile === 'FAST' ? 'low' : effort
          }
        })
      });
      await load();
      message =
        'Policy saved. Applies to subsequent turns; lifetime usage and USD limits are unchanged.';
    } catch (error) {
      message = String(error);
    } finally {
      busy = false;
    }
  }
  onMount(() => {
    void load();
  });
</script>

<section class="rounded-xl border border-line bg-panel p-5 space-y-4">
  <h2 class="font-semibold">Developer token efficiency</h2>
  <p class="text-sm text-muted">
    One Developer, bounded context. Start with instrumentation; enable warnings or hard stops after
    reviewing task evidence. This never increases the USD budget.
  </p>
  {#if policy}
    <div class="flex flex-wrap gap-4">
      <label class="text-sm"
        >Execution profile
        <select class="block rounded border border-line bg-panel p-2" bind:value={profile}>
          {#each ['FAST', 'STANDARD', 'LARGE', 'CUSTOM'] as name (name)}<option>{name}</option
            >{/each}
        </select>
      </label>
      <label class="text-sm"
        >Governor
        <select class="block rounded border border-line bg-panel p-2" bind:value={mode}>
          <option value="INSTRUMENT">Measure only</option><option value="WARN">Warnings</option
          ><option value="ENFORCE">Warnings + hard stops</option>
        </select>
      </label>
      <label class="text-sm"
        >Reasoning
        <select
          class="block rounded border border-line bg-panel p-2"
          bind:value={effort}
          disabled={profile === 'FAST'}
        >
          <option value="low">Low</option><option value="medium">Medium</option><option value="high"
            >High — explicit escalation</option
          >
        </select>
      </label>
    </div>
    <details>
      <summary class="cursor-pointer text-sm">Advanced limits (CUSTOM profile)</summary>
      <label class="sr-only" for="token-policy-json">Token policy JSON</label>
      <textarea
        id="token-policy-json"
        class="mt-3 w-full rounded border border-line bg-panel p-3 font-mono text-xs"
        rows="15"
        bind:value={advanced}
        disabled={profile !== 'CUSTOM'}
      ></textarea>
    </details>
    <button
      class="accent-action rounded bg-accent px-4 py-2 text-sm text-on-accent disabled:opacity-50"
      disabled={busy}
      onclick={save}>Save token policy</button
    >
  {/if}
  {#if message}<p role="status" class="text-sm">{message}</p>{/if}
</section>
