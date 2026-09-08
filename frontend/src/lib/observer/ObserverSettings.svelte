<script lang="ts">
  import { onMount } from 'svelte';
  import { observerApi } from './api';
  import {
    getAssistantName,
    setAssistantName,
    notifyAssistantConfiguration
  } from './identity.svelte';
  import type { ObserverConfiguration } from './types';
  let config = $state<ObserverConfiguration>();
  const assistantName = $derived(getAssistantName());
  let nameDraft = $state('Jarvis');
  let saving = $state(false);
  let error = $state('');
  let message = $state('');
  onMount(() => {
    void observerApi
      .configuration()
      .then((value) => {
        config = value;
        setAssistantName(value.display_name);
        nameDraft = getAssistantName();
      })
      .catch(() => {
        error = 'Assistant settings unavailable.';
      });
  });
  async function toggle() {
    if (!config || saving) return;
    saving = true;
    error = '';
    message = '';
    try {
      const result = await observerApi.setEnabled(!config.enabled);
      config = { ...config, enabled: result.enabled };
      message = result.enabled
        ? `${assistantName} enabled. Engineering workflows are unchanged.`
        : `${assistantName} stopped: detection, questions, polling and animation are off.`;
      notifyAssistantConfiguration();
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
  {#if config?.enabled}<details>
      <summary>Local AI & resource policy</summary>
      <dl>
        <div>
          <dt>Local model</dt>
          <dd>{config.model}</dd>
        </div>
        <div>
          <dt>Local inference</dt>
          <dd>
            {config.local_ai_enabled ? 'Enabled, capacity-guarded' : 'Off — deterministic answers'}
          </dd>
        </div>
        <div>
          <dt>Required free memory</dt>
          <dd>
            {config.memory_reserve_mb
              ? `${config.memory_reserve_mb} MiB`
              : 'Not configured — inference blocked'}
          </dd>
        </div>
        <div>
          <dt>Cloud calls / model downloads</dt>
          <dd>Never automatic</dd>
        </div>
      </dl>
      <p class="note">
        Local AI is deployment-managed: provision and benchmark the model, set
        OBSERVER_LOCAL_AI_ENABLED and OBSERVER_MIN_AVAILABLE_MEMORY_MB, then restart the API. Queued
        or running engineering jobs take priority.
      </p>
    </details>{/if}
  {#if error}<p role="alert" class="error">{error}</p>{/if}{#if message}<p
      role="status"
      class="saved"
    >
      {message}
    </p>{/if}
</section>

<style>
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
  button {
    width: 44px;
    height: 25px;
    padding: 3px;
    border: 1px solid var(--color-line);
    border-radius: 20px;
    background: var(--color-panel-alt);
    cursor: pointer;
  }
  button span {
    display: block;
    width: 17px;
    height: 17px;
    border-radius: 50%;
    background: var(--color-muted);
  }
  button.on {
    border-color: var(--color-brand);
    background: color-mix(in srgb, var(--color-brand) 20%, transparent);
  }
  button.on span {
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
  dl {
    margin-top: 12px;
  }
  dl div {
    display: flex;
    justify-content: space-between;
    gap: 16px;
    margin: 8px 0;
  }
  dt {
    color: var(--color-muted);
  }
  dd {
    color: var(--color-heading);
    font-size: 10px;
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
