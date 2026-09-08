<script lang="ts">
  import ShowMore from '$lib/components/ShowMore.svelte';
  import type { NativeRun } from '$lib/types';
  let { runs }: { runs: NativeRun[] } = $props();
  const count = (value: number | null) => (value === null ? 'unknown' : value.toLocaleString());
</script>

<section
  class="min-w-0 rounded-xl border border-line p-5 xl:col-span-2"
  aria-label="AI run receipts"
>
  <h2 class="mb-3 font-semibold">AI run receipts</h2>
  <p class="mb-4 text-sm text-muted">
    Each paid turn has its own result and usage receipt. Missing cost is unknown, never zero.
  </p>
  {#if runs.length === 0}
    <p class="text-sm text-muted">No AI turns recorded.</p>
  {:else}
    <ShowMore items={runs}>
      {#snippet children(visibleRuns: NativeRun[])}
        {#each visibleRuns as run (run.id)}
          <article class="border-t border-line py-3">
            <div class="flex flex-wrap justify-between gap-2 text-sm">
              <strong>{run.role_kind} · {run.status}</strong>
              <span>{run.cost_usd === null ? 'Cost unknown' : '$' + run.cost_usd}</span>
            </div>
            <p class="text-xs text-muted">
              {run.provider} / {run.model} · {run.harness || 'API'} · requirement v{run.requirement_version}
            </p>
            <p class="mt-1 text-xs text-muted">
              Started {new Date(run.started_at).toLocaleString()} · {run.finished_at
                ? 'Finished ' + new Date(run.finished_at).toLocaleString()
                : 'Not finished'}
            </p>
            <p class="mt-1 text-xs text-muted">
              Input {count(run.input_tokens)} · Output {count(run.output_tokens)} · Cached input {count(
                run.cache_read_tokens
              )}{run.usage_complete ? '' : ' · Incomplete receipt'}
            </p>
            {#if run.failure_code}<p class="mt-2 text-sm text-danger">{run.failure_code}</p>{/if}
            {#if run.artifact}
              <details class="mt-3 text-sm">
                <summary class="cursor-pointer text-brand">Result / feedback</summary>
                <pre
                  class="mt-2 max-h-80 overflow-auto whitespace-pre-wrap break-words rounded bg-surface p-3 text-xs">{run.artifact}</pre>
              </details>
            {/if}
          </article>
        {/each}
      {/snippet}
    </ShowMore>
  {/if}
</section>
