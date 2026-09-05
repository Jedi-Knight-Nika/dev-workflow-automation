<script lang="ts">
  import type { Snippet } from 'svelte';

  type Variant = 'primary' | 'outline' | 'ghost' | 'danger' | 'success' | 'warning';
  type Size = 'sm' | 'md' | 'lg';

  let {
    variant = 'outline',
    size = 'md',
    type = 'button',
    disabled = false,
    class: extraClass = '',
    onclick,
    children
  }: {
    variant?: Variant;
    size?: Size;
    type?: 'button' | 'submit';
    disabled?: boolean;
    class?: string;
    onclick?: (event: MouseEvent) => void;
    children: Snippet;
  } = $props();

  const variantClass: Record<Variant, string> = {
    primary:
      'bg-[linear-gradient(120deg,var(--color-brand),var(--color-brand-2))] text-white font-bold neon-glow motion-safe:hover:animate-glow-pulse',
    outline: 'border-line border text-muted hover:text-brand-2 hover:border-brand-2',
    ghost: 'border-line border bg-transparent text-muted hover:text-brand-2 hover:border-brand-2',
    danger: 'border border-danger/40 text-danger hover:bg-danger/10',
    success: 'border border-accent/40 text-accent hover:bg-accent/10',
    warning: 'border border-warning/40 text-warning hover:bg-warning/10'
  };

  const sizeClass: Record<Size, string> = {
    sm: 'px-2 py-1 text-[10px]',
    md: 'min-h-[2.25rem] px-3 py-2 text-xs',
    lg: 'min-h-[3rem] p-3 text-sm'
  };
</script>

<button
  {type}
  {disabled}
  {onclick}
  class="ease-smooth cursor-pointer rounded-lg transition-all duration-200 disabled:cursor-not-allowed disabled:opacity-30 motion-safe:enabled:hover:-translate-y-0.5 motion-safe:enabled:active:scale-[.96] motion-safe:enabled:active:translate-y-0 {variantClass[
    variant
  ]} {sizeClass[size]} {extraClass}"
>
  {@render children()}
</button>
