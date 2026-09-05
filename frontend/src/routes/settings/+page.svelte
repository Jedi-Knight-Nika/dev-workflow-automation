<script lang="ts">
  import { onMount } from 'svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import Skeleton from '$lib/components/Skeleton.svelte';
  import Spinner from '$lib/components/Spinner.svelte';
  import { t } from '$lib/i18n/index.svelte';
  import type { TelegramStatus } from '$lib/types';
  import {
    configureTelegram,
    connectTelegram,
    disconnectTelegram,
    telegramStatus,
    testTelegram
  } from '$lib/services/notifications';

  let telegram = $state<TelegramStatus | null>(null);
  let botToken = $state('');
  let webhookBaseUrl = $state('');
  let busy = $state(false);
  let message = $state('');
  let editingBot = $state(false);
  let loadingTelegram = $state(true);

  async function refreshTelegram() {
    try {
      telegram = await telegramStatus();
    } finally {
      loadingTelegram = false;
    }
  }
  async function configure() {
    busy = true;
    try {
      telegram = await configureTelegram(botToken, webhookBaseUrl);
      botToken = '';
      editingBot = false;
      message = 'Bot verified and encrypted. Connect your Telegram account next.';
    } catch (cause) {
      message = cause instanceof Error ? cause.message : String(cause);
    } finally {
      busy = false;
    }
  }
  async function connect() {
    const result = await connectTelegram();
    window.open(result.connect_url, '_blank', 'noopener,noreferrer');
    message = 'Press Start in Telegram, then refresh status.';
  }
  async function disconnect() {
    await disconnectTelegram();
    await refreshTelegram();
  }
  async function sendTest() {
    await testTelegram();
    message = 'Test notification queued.';
  }
  onMount(() => void refreshTelegram());
</script>

<PageHeader
  eyebrow={t('settings.eyebrow')}
  title={t('settings.title')}
  description={t('settings.description')}
/>
<main class="p-4 sm:p-6 md:p-10">
  <section class="border-line max-w-2xl overflow-hidden rounded-xl border">
    <div class="border-line flex justify-between border-b p-5">
      <div>
        <strong>{t('settings.executionLane')}</strong>
        <p class="text-muted text-xs">{t('settings.executionLaneDescription')}</p>
      </div>
      <span class="font-mono text-sm">1</span>
    </div>
    <div class="border-line flex justify-between border-b p-5">
      <div>
        <strong>{t('settings.mergePolicy')}</strong>
        <p class="text-muted text-xs">{t('settings.mergePolicyDescription')}</p>
      </div>
      <span class="font-mono text-sm">{t('settings.manual')}</span>
    </div>
    <div class="flex justify-between p-5">
      <div>
        <strong>{t('settings.workerTimeout')}</strong>
        <p class="text-muted text-xs">{t('settings.workerTimeoutDescription')}</p>
      </div>
      <span class="font-mono text-sm">300s</span>
    </div>
  </section>
  <section class="border-line mt-6 max-w-2xl overflow-hidden rounded-xl border">
    <div class="border-line border-b p-5">
      <div class="flex items-start justify-between gap-4">
        <div>
          <strong>Telegram critical alerts</strong>
          <p class="text-muted mt-1 text-xs">
            Action-required and critical incidents only. The bot token is encrypted and never
            returned to the browser.
          </p>
        </div>
        {#if loadingTelegram}
          <Skeleton class="h-4 w-20" />
        {:else}
          <span class="font-mono text-xs"
            >{telegram?.connected
              ? 'CONNECTED'
              : telegram?.configured
                ? 'CONFIGURED'
                : 'NOT SET'}</span
          >
        {/if}
      </div>
    </div>
    {#if loadingTelegram}
      <div class="space-y-3 p-5" aria-busy="true">
        <Skeleton class="h-3 w-40" />
        <Skeleton class="h-9 w-full" />
        <Skeleton class="h-3 w-56" />
        <Skeleton class="h-9 w-full" />
        <Skeleton class="h-9 w-32" />
      </div>
    {:else if !telegram?.configured || editingBot}
      <form
        class="space-y-3 p-5"
        onsubmit={(event) => {
          event.preventDefault();
          void configure();
        }}
      >
        <label class="text-muted block text-xs" for="telegram-token"
          >Bot token from @BotFather</label
        >
        <input
          id="telegram-token"
          type="password"
          bind:value={botToken}
          required
          autocomplete="off"
          placeholder="123456:AA..."
          class="border-line bg-input text-heading w-full rounded-lg border px-3 py-2 text-sm"
        />
        <label class="text-muted block text-xs" for="telegram-webhook"
          >Public HTTPS backend URL (Cloudflare Tunnel, ngrok, or hosted API)</label
        >
        <input
          id="telegram-webhook"
          type="url"
          bind:value={webhookBaseUrl}
          placeholder="https://api.example.com"
          class="border-line bg-input text-heading w-full rounded-lg border px-3 py-2 text-sm"
        />
        <div class="flex gap-2">
          <button
            disabled={busy}
            class="bg-brand flex items-center gap-2 rounded-lg px-4 py-2 text-sm text-white"
            >{#if busy}<Spinner class="size-3.5" />{/if}{busy
              ? 'Verifying…'
              : 'Verify and save'}</button
          >
          {#if telegram?.configured}<button
              type="button"
              class="border-line rounded-lg border px-4 py-2 text-sm"
              onclick={() => (editingBot = false)}>Cancel</button
            >{/if}
        </div>
      </form>
    {:else}
      <div class="flex flex-wrap items-center gap-2 p-5">
        {#if !telegram.connected}<button
            disabled={!telegram.webhook_configured}
            class="bg-brand rounded-lg px-4 py-2 text-sm text-white disabled:opacity-40"
            onclick={() => void connect()}>Connect Telegram</button
          >{/if}
        {#if telegram.connected}<button
            class="border-line rounded-lg border px-4 py-2 text-sm"
            onclick={() => void sendTest()}>Send test</button
          ><button
            class="border-danger text-danger rounded-lg border px-4 py-2 text-sm"
            onclick={() => void disconnect()}>Disconnect</button
          >{/if}
        <button
          class="border-line rounded-lg border px-4 py-2 text-sm"
          onclick={() => void refreshTelegram()}>Refresh status</button
        >
        <button
          class="border-line rounded-lg border px-4 py-2 text-sm"
          onclick={() => (editingBot = true)}>Replace bot</button
        >
      </div>
      {#if !telegram.webhook_configured}<p class="text-warning px-5 pb-5 text-xs">
          Add a public HTTPS backend URL and save the bot again before connecting your Telegram
          account.
        </p>{/if}
    {/if}
    {#if message}<p class="text-muted border-line border-t p-4 text-xs">{message}</p>{/if}
  </section>
</main>
