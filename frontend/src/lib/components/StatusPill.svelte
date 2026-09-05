<script lang="ts">
  import type { Snippet } from 'svelte';

  type Tone = 'accent' | 'muted' | 'danger' | 'warning';

  let {
    tone = 'muted',
    class: extraClass = '',
    children
  }: { tone?: Tone; class?: string; children: Snippet } = $props();

  const toneClass: Record<Tone, string> = {
    accent: 'text-accent',
    muted: 'text-muted',
    danger: 'text-danger',
    warning: 'text-warning'
  };
</script>

<span class="font-mono text-[10px] font-bold tracking-[.08em] {toneClass[tone]} {extraClass}">
  {@render children()}
</span>
