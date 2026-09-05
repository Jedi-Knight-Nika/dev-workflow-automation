<script lang="ts">
  import TextField from '$lib/components/TextField.svelte';
  import TextArea from '$lib/components/TextArea.svelte';

  let {
    appSlug = $bindable(),
    appId = $bindable(),
    installationId = $bindable(),
    privateKey = $bindable(),
    hasCredentials
  }: {
    appSlug: string;
    appId: string;
    installationId: string;
    privateKey: string;
    hasCredentials: boolean;
  } = $props();
</script>

<div class="space-y-2">
  <TextField
    bind:value={appSlug}
    placeholder="GitHub App slug (from its public URL)"
    pattern="[A-Za-z0-9-]+"
    title="Letters, numbers, and hyphens only"
    required
  />
  <TextField
    bind:value={appId}
    placeholder="GitHub App ID"
    inputmode="numeric"
    pattern="[0-9]+"
    required={!hasCredentials}
  />
  <TextField
    bind:value={installationId}
    placeholder="Installation ID (filled after installation)"
  />
  <TextArea
    bind:value={privateKey}
    placeholder="-----BEGIN RSA PRIVATE KEY-----"
    required={!hasCredentials}
    class="h-32 font-mono text-xs"
  />
</div>
