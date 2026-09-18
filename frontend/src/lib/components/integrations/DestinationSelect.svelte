<script lang="ts">
  import Select from '$lib/components/Select.svelte';

  let {
    id,
    label,
    value = $bindable(''),
    destinations,
    emptyLabel
  }: {
    id: string;
    label?: string;
    value?: string;
    destinations: readonly { id: string; name: string }[];
    emptyLabel: string;
  } = $props();
</script>

<Select {id} {label} bind:value>
  <option value="">{emptyLabel}</option>
  {#each destinations as destination (destination.id)}
    <option value={destination.id}>{destination.name}</option>
  {/each}
</Select>
