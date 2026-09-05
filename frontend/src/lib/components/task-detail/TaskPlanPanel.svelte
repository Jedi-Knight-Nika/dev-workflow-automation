<script lang="ts">
  import { isStringArray, type ThinkerPlan } from '$lib/task-plan';
  import type { Job } from '$lib/types';

  let { latestPlan, latestThinker }: { latestPlan: ThinkerPlan | null; latestThinker: Job | null } =
    $props();
</script>

<section class="border-line rounded-xl border p-5 xl:col-span-2">
  <div class="mb-4 flex flex-wrap items-center justify-between gap-2">
    <h2 class="font-semibold">Latest technical plan</h2>
    {#if latestPlan}<span class="font-mono text-[10px] text-accent">PLAN READY</span>{/if}
  </div>
  {#if latestPlan}
    <h3 class="text-lg font-medium">{latestPlan.goal}</h3>
    {#if latestPlan.targets.length}<p class="text-muted mt-2 text-xs">
        Targets: {latestPlan.targets.join(', ')}
      </p>{/if}
    <div class="mt-5 grid gap-5 md:grid-cols-2">
      <div>
        <h3 class="mb-2 text-xs font-semibold tracking-wider text-brand uppercase">Steps</h3>
        <ol class="text-muted list-decimal space-y-1 pl-5 text-sm">
          {#each latestPlan.ordered_steps as step, index (index)}<li>{step}</li>{/each}
        </ol>
      </div>
      <div>
        <h3 class="mb-2 text-xs font-semibold tracking-wider text-brand uppercase">
          Acceptance criteria
        </h3>
        <ul class="text-muted list-disc space-y-1 pl-5 text-sm">
          {#each latestPlan.acceptance_criteria as criterion, index (index)}<li>
              {criterion}
            </li>{/each}
        </ul>
      </div>
      <div>
        <h3 class="mb-2 text-xs font-semibold tracking-wider uppercase">Required tests</h3>
        <ul class="text-muted list-disc space-y-1 pl-5 text-sm">
          {#each latestPlan.required_tests as test, index (index)}<li>{test}</li>{/each}
        </ul>
      </div>
      <div>
        <h3 class="mb-2 text-xs font-semibold tracking-wider uppercase">Constraints and risks</h3>
        <ul class="text-muted list-disc space-y-1 pl-5 text-sm">
          {#each [...latestPlan.constraints, ...latestPlan.risks] as item, index (index)}<li>
              {item}
            </li>{/each}
        </ul>
      </div>
    </div>
  {:else if latestThinker?.result?.result === 'NEEDS_CONTEXT'}
    <p class="text-sm text-warning">
      The Thinker needs more context: {String(latestThinker.result.data.reason || 'Unspecified')}
    </p>
    {#if isStringArray(latestThinker.result.data.questions)}
      <ul class="text-muted mt-3 list-disc space-y-1 pl-5 text-sm">
        {#each latestThinker.result.data.questions as question, index (index)}<li>
            {question}
          </li>{/each}
      </ul>
    {/if}
  {:else if latestThinker?.result?.result === 'NEEDS_HUMAN'}
    <p class="text-sm text-warning">
      Human decision required: {String(latestThinker.result.data.reason || 'Unspecified')}
    </p>
  {:else}
    <p class="text-muted text-sm">No successful Thinker plan has been produced yet.</p>
  {/if}
</section>
