<script lang="ts">
  import { resolve } from '$app/paths';
  import type { RunnerResource } from '$lib/types/observability';
  import { bytes, count, duration, money } from './format';
  import { t } from '$lib/i18n/index.svelte';
  let { runner }: { runner: RunnerResource } = $props();
</script>

<article class="runner">
  <header>
    <strong>{runner.profile_name || runner.service_kind}</strong><span>{runner.phase}</span>
  </header>
  {#if runner.task_id}<a href={resolve('/tasks/[id]', { id: runner.task_id })}
      >{runner.task_key || runner.task_title || runner.task_id}</a
    >{/if}
  <small>{runner.harness || t('operations.system')} · {runner.model || runner.service_kind}</small>
  <dl>
    <div>
      <dt>{t('operations.containerDevElapsed')}</dt>
      <dd>{duration(runner.wall_seconds)} / {duration(runner.developer_active_seconds)}</dd>
    </div>
    <div>
      <dt>{t('operations.providerActive')}</dt>
      <dd>{duration(runner.ai_active_seconds)}</dd>
    </div>
    <div>
      <dt>{t('operations.inputOutput')}</dt>
      <dd>{count(runner.input_tokens)} / {count(runner.output_tokens)}</dd>
    </div>
    <div>
      <dt>{t('operations.knownTaskCost')}</dt>
      <dd>
        {money(runner.known_cost_usd)} · {t('operations.unknownCount', {
          count: runner.unknown_cost_runs ?? 0
        })}
      </dd>
    </div>
    <div>
      <dt>{t('operations.cpu')}</dt>
      <dd>
        {t('operations.cores', {
          count: runner.resources?.cpu?.toFixed(2) ?? t('operations.unavailable')
        })}
      </dd>
    </div>
    <div>
      <dt>{t('operations.ramLimit')}</dt>
      <dd>
        {bytes(runner.resources?.memory)} / {runner.resources?.memory_limit === 0
          ? t('operations.noLimit')
          : bytes(runner.resources?.memory_limit)}
      </dd>
    </div>
    <div>
      <dt>{t('operations.peakRam')}</dt>
      <dd>{bytes(runner.summary?.values.max_memory_bytes ?? runner.resources?.memory_peak)}</dd>
    </div>
  </dl>
</article>

<style>
  .runner {
    padding: 1rem;
    border: 1px solid var(--color-line);
    border-radius: 1rem;
    display: grid;
    gap: 0.6rem;
    min-width: 0;
    background: var(--color-panel);
    position: relative;
    transition:
      border-color 0.3s var(--ease-smooth),
      box-shadow 0.3s var(--ease-smooth);
  }
  .runner::before {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: inherit;
    box-shadow: 0 0 0 1px color-mix(in srgb, var(--color-brand) 25%, transparent) inset;
    pointer-events: none;
  }
  .runner:hover {
    border-color: color-mix(in srgb, var(--color-brand) 55%, var(--color-line));
    box-shadow: 0 0 22px -6px color-mix(in srgb, var(--color-brand) 45%, transparent);
  }
  header,
  dl div {
    display: flex;
    justify-content: space-between;
    gap: 0.7rem;
  }
  header strong {
    color: var(--color-heading);
  }
  a {
    color: var(--color-brand-2);
    overflow-wrap: anywhere;
  }
  a:hover {
    text-shadow: 0 0 10px color-mix(in srgb, var(--color-brand-2) 55%, transparent);
  }
  small,
  dt,
  header span {
    font-size: 0.75rem;
    opacity: 0.75;
    color: var(--color-muted);
  }
  dd {
    font-size: 0.8rem;
    text-align: right;
  }
  dl {
    display: grid;
    gap: 0.5rem;
  }
</style>
