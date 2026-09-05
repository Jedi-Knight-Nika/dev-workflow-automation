<script lang="ts">
  import PageHeader from '$lib/components/PageHeader.svelte';
</script>

<PageHeader
  eyebrow="SYSTEM"
  title="Settings"
  description="Global execution, scheduling, and merge-policy defaults."
/>
<main class="p-4 sm:p-6 md:p-10">
  <section class="border-line max-w-2xl overflow-hidden rounded-xl border">
    <div class="border-line flex justify-between border-b p-5">
      <div>
        <strong>Execution lane</strong>
        <p class="text-muted text-xs">Maximum simultaneous code-modifying workers.</p>
      </div>
      <span class="font-mono text-sm">1</span>
    </div>
    <div class="border-line flex justify-between border-b p-5">
      <div>
        <strong>Merge policy</strong>
        <p class="text-muted text-xs">Human approval remains required for MVP.</p>
      </div>
      <span class="font-mono text-sm">MANUAL</span>
    </div>
    <div class="flex justify-between p-5">
      <div>
        <strong>Worker timeout</strong>
        <p class="text-muted text-xs">Maximum execution time before recovery policy.</p>
      </div>
      <span class="font-mono text-sm">300s</span>
    </div>
  </section>
</main>
