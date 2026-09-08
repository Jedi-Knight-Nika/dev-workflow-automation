<script lang="ts">
  import { onMount } from 'svelte';
  import { observerApi, installLocalModel, streamAnswer } from './api';
  import {
    getAssistantName,
    setAssistantName,
    notifyAssistantConfiguration
  } from './identity.svelte';
  import type { ObserverConfiguration, LocalModels } from './types';
  let config = $state<ObserverConfiguration>();
  const assistantName = $derived(getAssistantName());
  let nameDraft = $state('Jarvis');
  let saving = $state(false);
  let error = $state('');
  let message = $state('');
  let models = $state<LocalModels>();
  let localEnabled = $state(false);
  let modelDraft = $state('qwen3.5:2b');
  let reserve = $state(1024);
  let outputTokens = $state(384);
  let timeout = $state(45);
  let installModel = $state('qwen3.5:2b');
  let downloading = $state(false);
  let downloadStatus = $state('');
  let testing = $state(false);
  let testAnswer = $state('');
  let readiness = $state('');
  let downloadController: AbortController | undefined;
  let testController: AbortController | undefined;

  function setConfig(value: ObserverConfiguration) {
    config = value;
    localEnabled = value.local_ai_enabled;
    modelDraft = value.model;
    reserve = value.memory_reserve_mb;
    outputTokens = value.output_tokens;
    timeout = value.response_timeout_seconds;
  }
  async function refreshModels() {
    try {
      models = await observerApi.models();
      if (config?.enabled) {
        const status = await observerApi.status({ page: 'DASHBOARD' });
        readiness = status.ai_available
          ? 'Ready for local chat. One request at a time; engineering work takes priority.'
          : status.reason || 'Local AI is sleeping.';
      }
    } catch {
      readiness = 'Could not verify local runtime readiness.';
    }
  }
  async function saveLocal() {
    if (!config || saving) return;
    saving = true;
    error = '';
    message = '';
    try {
      setConfig(
        await observerApi.configureLocal({
          local_ai_enabled: localEnabled,
          model: modelDraft,
          memory_reserve_mb: reserve,
          output_tokens: outputTokens,
          response_timeout_seconds: timeout
        })
      );
      message = 'Local AI settings saved and applied. No restart needed.';
      notifyAssistantConfiguration();
      await refreshModels();
    } catch (cause) {
      error = String(cause);
    } finally {
      saving = false;
    }
  }
  async function download() {
    if (downloading || !config?.enabled) return;
    const controller = new AbortController();
    downloadController = controller;
    downloading = true;
    error = '';
    downloadStatus = 'Checking capacity…';
    try {
      await installLocalModel(
        installModel,
        (value) => {
          downloadStatus = value.done
            ? 'Model installed. Select it above and save local AI settings.'
            : `${value.status || 'Downloading'}${value.percent == null ? '' : ` · ${value.percent}%`}`;
        },
        controller.signal
      );
      await refreshModels();
    } catch (cause) {
      if (!controller.signal.aborted) error = String(cause);
    } finally {
      downloading = false;
    }
  }
  async function testLocal() {
    if (testing || !config?.enabled) return;
    const controller = new AbortController();
    testController = controller;
    testing = true;
    error = '';
    testAnswer = '';
    readiness = 'Checking sources and capacity…';
    try {
      const request = await observerApi.question(
        'Say hello and briefly explain what you can help me with.',
        { page: 'DASHBOARD' },
        undefined,
        controller.signal
      );
      await streamAnswer(
        request.request_id,
        (value) => {
          if (value.type === 'observer.model_started') readiness = 'Local AI is composing…';
          if (value.type === 'observer.completed') {
            testAnswer = value.answer || '';
            readiness =
              value.mode === 'local'
                ? 'Local AI test passed · no paid API calls.'
                : value.reason || 'Deterministic fallback used.';
          }
          if (value.type === 'observer.failed') error = value.message || 'Test could not complete.';
        },
        controller.signal
      );
    } catch (cause) {
      if (!controller.signal.aborted) error = String(cause);
    } finally {
      testing = false;
      if (controller.signal.aborted) readiness = 'Local AI test stopped.';
    }
  }
  onMount(() => {
    void observerApi
      .configuration()
      .then((value) => {
        setConfig(value);
        setAssistantName(value.display_name);
        nameDraft = getAssistantName();
        void refreshModels();
      })
      .catch(() => {
        error = 'Assistant settings unavailable.';
      });
    return () => {
      downloadController?.abort();
      testController?.abort();
    };
  });
  async function toggle() {
    if (!config || saving) return;
    saving = true;
    error = '';
    message = '';
    try {
      const result = await observerApi.setEnabled(!config.enabled);
      config = { ...config, enabled: result.enabled };
      if (!result.enabled) {
        downloadController?.abort();
        testController?.abort();
      }
      message = result.enabled
        ? `${assistantName} enabled. Engineering workflows are unchanged.`
        : `${assistantName} stopped: detection, questions, polling and animation are off.`;
      notifyAssistantConfiguration();
      if (result.enabled) await refreshModels();
    } catch {
      error = 'Could not change assistant state. The displayed setting has not changed.';
    } finally {
      saving = false;
    }
  }
  async function saveName() {
    if (!config || saving) return;
    const nextName = nameDraft.trim();
    if (!nextName) {
      error = 'Enter an assistant name.';
      return;
    }
    saving = true;
    error = '';
    message = '';
    try {
      config = await observerApi.rename(nextName);
      setAssistantName(config.display_name);
      nameDraft = config.display_name;
      message = 'Assistant name saved.';
      notifyAssistantConfiguration();
    } catch {
      error = 'Could not save the name. Use 1–40 characters without control characters.';
    } finally {
      saving = false;
    }
  }
</script>

<section class="observer-settings" aria-labelledby="observer-settings-title">
  <div class="heading">
    <div>
      <p class="eyebrow">READ-ONLY COMPANION</p>
      <h2 id="observer-settings-title">{assistantName} assistant</h2>
    </div>
    <button
      type="button"
      role="switch"
      aria-checked={config?.enabled || false}
      aria-label="Enable {assistantName} assistant"
      disabled={!config || saving}
      onclick={toggle}
      class:on={config?.enabled}><span></span></button
    >
  </div>
  <p class="description">
    A quiet view of tasks, costs and system health. No engineering actions. No paid cloud fallback.
  </p>
  <form
    class="name-form"
    onsubmit={(event) => {
      event.preventDefault();
      void saveName();
    }}
  >
    <label for="assistant-display-name">Assistant name</label>
    <div class="name-controls">
      <input
        id="assistant-display-name"
        bind:value={nameDraft}
        required
        maxlength="40"
        disabled={!config || saving}
        autocomplete="off"
      />
      <button type="submit" disabled={!config || saving || nameDraft.trim() === assistantName}>
        Save name
      </button>
    </div>
    <p>Display name only. Does not change models, instructions or Team workflows.</p>
  </form>
  <div class="state-row">
    <span class:active={config?.enabled}>{config?.enabled ? 'ON' : 'OFF'}</span>
    <p>
      {config?.enabled
        ? 'Attention detection and the companion panel are available.'
        : 'No assistant detection, inference, dashboard polling or animation runs.'}
    </p>
  </div>
  <p class="note">
    The master switch cancels assistant work across the API and controller. It does not stop shared
    Ollama, monitoring, Teams or the Interpreter. Saved conversations remain available when
    re-enabled.
  </p>
  <form
    class="local-form"
    onsubmit={(event) => {
      event.preventDefault();
      void saveLocal();
    }}
  >
    <h3>Local conversation</h3>
    <label class="local-switch"
      ><input type="checkbox" bind:checked={localEnabled} disabled={!config || saving} />Enable
      local AI explanations</label
    >
    <p class="note">
      Applied with Save below. One bounded Ollama call per question. No AI calls for page refreshes
      or alerts; no cloud fallback.
    </p>
    <label
      >Installed model<select class="input" bind:value={modelDraft} disabled={!config || saving}>
        {#if !models?.models.some((m) => m.name === modelDraft)}<option value={modelDraft}
            >{modelDraft} · not installed</option
          >{/if}
        {#each models?.models || [] as model (model.name)}<option value={model.name}
            >{model.name} · {(model.size_bytes / 1073741824).toFixed(1)} GiB on disk</option
          >{/each}
      </select></label
    >
    <div class="local-actions">
      <button type="button" class="btn-secondary" onclick={refreshModels}
        >Refresh models & status</button
      ><span
        >{models?.reachable
          ? 'Private Ollama connected'
          : models?.reason || 'Checking private Ollama…'}</span
      >
    </div>
    <details>
      <summary>Resource & response limits</summary>
      <div class="limits">
        <label
          >Memory to leave free (MiB)<input
            class="input"
            type="number"
            min="512"
            max="1048576"
            step="256"
            bind:value={reserve}
            required
          /></label
        >
        <label
          >Maximum output tokens<input
            class="input"
            type="number"
            min="128"
            max="768"
            step="64"
            bind:value={outputTokens}
            required
          /></label
        >
        <label
          >Response timeout (seconds)<input
            class="input"
            type="number"
            min="10"
            max="60"
            bind:value={timeout}
            required
          /></label
        >
      </div>
      <p class="note">
        Cold-model memory is estimated separately; resident weights are not counted twice. Fixed:
        two CPU threads, 4k context, up to 60 seconds of warm model reuse. The master switch unloads
        Jarvis's model; inference stops when engineering work arrives. These settings never change
        Team budgets or Developer token policies.
      </p>
    </details>
    <div class="local-actions">
      <button class="btn-primary" disabled={!config || saving}
        >{saving ? 'Saving…' : 'Save local AI settings'}</button
      ><button
        type="button"
        class="btn-secondary"
        disabled={!config?.enabled || testing || downloading || saving}
        onclick={testLocal}>{testing ? 'Testing…' : 'Test local chat'}</button
      >{#if testing}<button
          type="button"
          class="btn-secondary"
          onclick={() => testController?.abort()}>Cancel test</button
        >{/if}
    </div>
    <p class="note" role="status">{readiness}</p>
    {#if testAnswer}<p class="test-answer">{testAnswer}</p>{/if}
  </form>
  <details class="model-setup">
    <summary>Install a local model</summary>
    <p class="note">
      Explicit download only; never triggered by a chat or toggle. Requires idle engineering and
      verified disk headroom. Downloads stop if this page closes or the master switch is turned off.
      The smallest model uses the least resources.
    </p>
    <label
      >Download model<select class="input" bind:value={installModel} disabled={downloading}
        >{#each models?.catalog || [] as model (model.name)}<option value={model.name}
            >{model.name} · needs {(model.minimum_free_disk_mb / 1024).toFixed(0)} GiB free disk</option
          >{/each}</select
      ></label
    >
    <div class="local-actions">
      <button
        type="button"
        class="btn-secondary"
        onclick={download}
        disabled={!config?.enabled || !models?.reachable || downloading || testing}
        >Download selected model</button
      >{#if downloading}<button
          type="button"
          class="btn-secondary"
          onclick={() => {
            downloadController?.abort();
            downloadStatus = 'Download stopped.';
          }}>Cancel download</button
        >{/if}
    </div>
    {#if downloadStatus}<p role="status" class="note">{downloadStatus}</p>{/if}
  </details>
  {#if error}<p role="alert" class="error">{error}</p>{/if}{#if message}<p
      role="status"
      class="saved"
    >
      {message}
    </p>{/if}
</section>

<style>
  .local-form {
    display: grid;
    gap: 14px;
    margin-top: 20px;
    border-top: 1px solid var(--color-line);
    padding-top: 20px;
  }
  .local-form h3 {
    color: var(--color-heading);
    font-weight: 700;
  }
  .local-form label,
  .model-setup label {
    display: grid;
    gap: 6px;
    font-size: 12px;
    color: var(--color-heading);
  }
  .local-form .local-switch {
    display: flex;
    align-items: center;
    gap: 9px;
  }
  .local-actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px;
  }
  .local-actions span {
    color: var(--color-muted);
    font-size: 11px;
  }
  .limits {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 12px;
    margin: 14px 0;
  }
  .model-setup {
    margin-top: 20px;
  }
  .model-setup .local-actions {
    margin-top: 12px;
  }
  .test-answer {
    white-space: pre-wrap;
    border-left: 2px solid var(--color-brand);
    padding: 12px;
    background: var(--color-panel-alt);
    font-size: 13px;
  }
  .heading > div {
    min-width: 0;
    overflow-wrap: anywhere;
  }
  .name-form {
    display: grid;
    gap: 8px;
    margin: 18px 0;
  }
  .name-form label {
    color: var(--color-heading);
    font-size: 12px;
  }
  .name-controls {
    display: flex;
    gap: 8px;
  }
  .name-controls input {
    min-width: 0;
    flex: 1;
    padding: 9px 12px;
    border: 1px solid var(--color-line);
    border-radius: 8px;
    background: var(--color-input);
    color: var(--color-heading);
  }
  .name-controls button {
    padding: 9px 12px;
    border: 1px solid var(--color-line);
    border-radius: 8px;
    color: var(--color-brand);
    cursor: pointer;
  }
  .name-controls button:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .name-form p {
    font-size: 11px;
    color: var(--color-muted);
  }
  .observer-settings {
    border: 1px solid var(--color-line);
    border-radius: 14px;
    padding: 22px;
    background: radial-gradient(
      ellipse at 100% 0%,
      color-mix(in srgb, var(--color-brand) 7%, transparent),
      transparent 70%
    );
  }
  .heading {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
  }
  .eyebrow {
    color: var(--color-brand);
    font: 9px monospace;
    letter-spacing: 0.15em;
    margin-bottom: 6px;
  }
  h2 {
    color: var(--color-heading);
    font-size: 17px;
    font-weight: 550;
  }
  .description {
    font-size: 12px;
    color: var(--color-muted);
    margin: 10px 0 16px;
    line-height: 1.7;
  }
  button[role='switch'] {
    width: 44px;
    height: 25px;
    padding: 3px;
    border: 1px solid var(--color-line);
    border-radius: 20px;
    background: var(--color-panel-alt);
    cursor: pointer;
  }
  button[role='switch'] span {
    display: block;
    width: 17px;
    height: 17px;
    border-radius: 50%;
    background: var(--color-muted);
  }
  button[role='switch'].on {
    border-color: var(--color-brand);
    background: color-mix(in srgb, var(--color-brand) 20%, transparent);
  }
  button[role='switch'].on span {
    transform: translateX(18px);
    background: var(--color-brand);
  }
  button:disabled {
    opacity: 0.5;
  }
  button:focus-visible {
    outline: 2px solid var(--color-brand);
    outline-offset: 4px;
  }
  .state-row {
    display: flex;
    gap: 10px;
    align-items: center;
    font-size: 11px;
    color: var(--color-muted);
  }
  .state-row span {
    font: 9px monospace;
    padding: 4px 6px;
    border: 1px solid var(--color-line);
    border-radius: 5px;
  }
  .state-row span.active {
    color: var(--color-brand);
  }
  .note {
    font-size: 10px;
    color: var(--color-muted);
    line-height: 1.75;
    margin-top: 12px;
  }
  details {
    border-top: 1px solid var(--color-line);
    margin-top: 16px;
    padding-top: 14px;
    font-size: 11px;
  }
  summary {
    cursor: pointer;
    color: var(--color-heading);
  }
  .error {
    color: #fb7185;
    font-size: 11px;
    margin-top: 12px;
  }
  .saved {
    color: var(--color-brand);
    font-size: 11px;
    margin-top: 12px;
  }
</style>
