<script lang="ts">
  import ShowMore from '$lib/components/ShowMore.svelte';
  import type { ValidationRecord } from '$lib/types';
  import { t } from '$lib/i18n/index.svelte';

  let { validations }: { validations: ValidationRecord[] } = $props();

  function statusClass(status: string): string {
    if (/FAIL|ERROR|CHANGES_REQUESTED|CANCEL|REJECT/.test(status)) return 'text-danger';
    if (/SUCCESS|APPROVED|PASS|COMPLETE/.test(status)) return 'text-accent';
    if (/PENDING|WAIT|REQUESTED|ACTION_REQUIRED|QUEUE/.test(status)) return 'text-warning';
    return 'text-muted';
  }
</script>

<section class="border-line rounded-xl border p-5 xl:col-span-2">
  <h2 class="mb-4 font-semibold">{t('taskDetail.githubValidation')}</h2>
  {#if validations.length === 0}
    <p class="text-muted text-sm">{t('taskDetail.noValidationEvidence')}</p>
  {:else}
    <ShowMore items={validations}>
      {#snippet children(visibleValidations: ValidationRecord[])}
        {#each visibleValidations as validation, index (validation.id)}
          <div
            class="border-line border-t py-3 motion-safe:animate-fade-in-up"
            style="animation-delay: {Math.min(index, 10) * 30}ms"
          >
            <div class="flex justify-between gap-3">
              <strong class="text-sm">{validation.name}</strong>
              <span class="font-mono text-xs {statusClass(validation.status)}"
                >{validation.status}</span
              >
            </div>
            <small class="text-muted">{validation.kind} · {validation.revision.slice(0, 12)}</small>
            {#if validation.details_url}<!-- eslint-disable svelte/no-navigation-without-resolve -->
              <a
                class="ml-3 text-xs text-brand underline"
                href={validation.details_url}
                target="_blank"
                rel="noreferrer">{t('taskDetail.openEvidence')}</a
              ><!-- eslint-enable svelte/no-navigation-without-resolve -->{/if}
          </div>
        {/each}
      {/snippet}
    </ShowMore>
  {/if}
</section>
