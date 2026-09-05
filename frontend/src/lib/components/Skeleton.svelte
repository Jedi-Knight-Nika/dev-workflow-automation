<script lang="ts">
  let { class: extraClass = 'h-4 w-24' }: { class?: string } = $props();
</script>

<div class="skeleton rounded-md {extraClass}"></div>
