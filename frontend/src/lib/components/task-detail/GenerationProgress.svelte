<script lang="ts">
  import type { TaskGenerationProgress } from '$lib/task-generation';
  import { t } from '$lib/i18n/index.svelte';

  let { progress, connected }: { progress: TaskGenerationProgress | null; connected: boolean } =
    $props();
</script>

{#if progress && connected}
  <section
    class="border-accent/40 bg-accent/5 rounded-xl border p-4 xl:col-span-2"
    aria-live="polite"
  >
    <div class="flex items-center gap-3">
      <span class="bg-accent size-2 animate-pulse rounded-full" aria-hidden="true"></span>
      <div>
        <p class="text-heading text-sm font-semibold">{t('taskDetail.aiGenerating')}</p>
        <p class="text-muted text-xs">
          {progress.role.replaceAll('_', ' ')} · {progress.action.replaceAll('_', ' ')} ·
          {t('taskDetail.charactersReceived', {
            count: progress.charactersReceived.toLocaleString()
          })}
        </p>
      </div>
    </div>
  </section>
{/if}
