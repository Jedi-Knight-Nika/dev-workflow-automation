<script lang="ts">
  let { eyebrow, title, description }: { eyebrow: string; title: string; description: string } =
    $props();
</script>

<header class="border-line border-b bg-[#0d110f] px-6 py-7 md:px-10">
  <p class="text-accent mb-2 font-mono text-[10px] font-bold tracking-[.18em]">{eyebrow}</p>
  <h1 class="text-3xl font-bold tracking-tight">{title}</h1>
  <p class="text-muted mt-2 max-w-2xl text-sm">{description}</p>
</header>
