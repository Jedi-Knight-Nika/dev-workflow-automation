<script lang="ts">
  let { eyebrow, title, description }: { eyebrow: string; title: string; description: string } =
    $props();
</script>

<header class="border-line bg-panel-alt border-b px-4 py-6 sm:px-6 sm:py-7 md:px-10">
  <p class="text-brand mb-2 font-mono text-[10px] font-bold tracking-[.18em]">{eyebrow}</p>
  <h1 class="text-heading text-2xl font-bold tracking-tight sm:text-3xl">{title}</h1>
  <p class="text-muted mt-2 max-w-2xl text-sm">{description}</p>
</header>
