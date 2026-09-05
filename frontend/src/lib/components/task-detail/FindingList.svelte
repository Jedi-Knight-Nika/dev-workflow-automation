<script lang="ts">
  import ShowMore from '$lib/components/ShowMore.svelte';
  import type { ReviewFinding } from '$lib/types';

  let { findings }: { findings: ReviewFinding[] } = $props();
</script>

<section class="border-line rounded-xl border p-5 xl:col-span-2">
  <h2 class="mb-4 font-semibold">Internal review findings</h2>
  {#if findings.length === 0}
    <p class="text-muted text-sm">No internal findings recorded.</p>
  {:else}
    <ShowMore items={findings}>
      {#snippet children(visibleFindings: ReviewFinding[])}
        {#each visibleFindings as finding, index (finding.id)}
          <article
            class="border-line border-t py-3 motion-safe:animate-fade-in-up"
            style="animation-delay: {Math.min(index, 10) * 30}ms"
          >
            <div class="flex flex-wrap justify-between gap-3">
              <strong class="text-sm"
                >{finding.severity} · {finding.status}{finding.occurrence_count > 1
                  ? ` · repeated ${finding.occurrence_count}×`
                  : ''}</strong
              >
              <span class="text-muted font-mono text-[10px]"
                >{finding.workspace_fingerprint.slice(0, 12)}</span
              >
            </div>
            <p class="mt-1 text-sm">{finding.message}</p>
            {#if finding.file_path}<p class="text-muted mt-1 font-mono text-xs">
                {finding.file_path}{finding.line ? `:${finding.line}` : ''}
              </p>{/if}
          </article>
        {/each}
      {/snippet}
    </ShowMore>
  {/if}
</section>
