<script lang="ts">
  export type ResourceState =
    'READY' | 'WORKING' | 'NEEDS_ATTENTION' | 'NOT_CONFIGURED' | 'DISABLED';

  let { state, detail = '' }: { state: ResourceState; detail?: string } = $props();

  const labels: Record<ResourceState, string> = {
    READY: 'Ready',
    WORKING: 'Working',
    NEEDS_ATTENTION: 'Needs attention',
    NOT_CONFIGURED: 'Not configured',
    DISABLED: 'Disabled'
  };
  const tones: Record<ResourceState, string> = {
    READY: 'text-accent border-accent/30 bg-accent/5',
    WORKING: 'text-warning border-warning/30 bg-warning/5',
    NEEDS_ATTENTION: 'text-danger border-danger/30 bg-danger/5',
    NOT_CONFIGURED: 'text-muted border-line bg-panel-alt',
    DISABLED: 'text-muted border-line bg-panel-alt'
  };
  const symbols: Record<ResourceState, string> = {
    READY: '●',
    WORKING: '◐',
    NEEDS_ATTENTION: '⚠',
    NOT_CONFIGURED: '○',
    DISABLED: '⏸'
  };
</script>

<span
  class="inline-flex items-center gap-1.5 rounded-full border px-2 py-1 font-mono text-[10px] {tones[
    state
  ]}"
  title={detail || labels[state]}
>
  <span aria-hidden="true">{symbols[state]}</span>
  {labels[state]}
</span>
