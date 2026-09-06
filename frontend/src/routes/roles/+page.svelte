<script lang="ts">
  import { onMount } from 'svelte';
  import ErrorBanner from '$lib/components/ErrorBanner.svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import Skeleton from '$lib/components/Skeleton.svelte';
  import {
    cloneRole,
    createRole,
    deleteRole,
    listRoleCapabilities,
    listRolePermissions,
    listRoles,
    updateRole,
    type RoleInput
  } from '$lib/services/roles';
  import type { Role } from '$lib/types';

  const categories = [
    'INTAKE',
    'PLANNING',
    'EXECUTION',
    'VALIDATION',
    'REVIEW',
    'DELIVERY',
    'COORDINATION',
    'SPECIALIST',
    'CUSTOM'
  ];
  const outcomes = [
    'PASS',
    'FAIL_ACTIONABLE',
    'FAIL_ARCHITECTURAL',
    'UNCERTAIN',
    'NEEDS_HUMAN',
    'BLOCKED',
    'PLAN_READY',
    'REPLAN_READY',
    'NEEDS_CONTEXT',
    'IMPLEMENTED',
    'PARTIALLY_IMPLEMENTED',
    'TEST_PASS',
    'TEST_FAILED',
    'TEST_ENVIRONMENT_FAILURE',
    'TEST_INCOMPLETE',
    'PLAN_MISMATCH',
    'NEEDS_REPLAN',
    'REVIEW_PASS',
    'DELIVERY_READY',
    'DELIVERY_FAILED',
    'DELIVERY_BLOCKED'
  ];
  let roles = $state<Role[]>([]),
    permissions = $state<string[]>([]),
    capabilities = $state<string[]>([]);
  let editing = $state<Role | null>(null),
    details = $state<Role | null>(null),
    open = $state(false),
    advanced = $state(false),
    busy = $state(false),
    error = $state(''),
    loading = $state(true);
  let form = $state<RoleInput>(blank());

  function blank(): RoleInput {
    return {
      name: '',
      category: 'CUSTOM',
      description: '',
      system_instructions: '',
      capabilities: [],
      permissions: [],
      allowed_results: ['NEEDS_HUMAN', 'BLOCKED'],
      knowledge_collection_ids: [],
      default_provider: null,
      default_model: null,
      default_reasoning_effort: 'default',
      default_timeout_minutes: 30,
      default_max_retries: 2,
      runtime_profile: {
        reasoning_default: 'PROVIDER_DEFAULT',
        reasoning_min: 'PROVIDER_DEFAULT',
        reasoning_max: 'MAX',
        dynamic_reasoning_allowed: true,
        max_output_tokens: null,
        temperature: null,
        context_strategy: 'BALANCED',
        max_tool_calls: 40,
        job_timeout_seconds: 1800,
        max_job_attempts: 2,
        max_model_turns: 3,
        structured_output_mode: 'REQUIRED'
      },
      override_policy: {
        provider: 'ALLOW',
        model: 'ALLOW',
        reasoning_level: 'ALLOW_WITHIN_RANGE',
        max_output_tokens: 'ALLOW',
        temperature: 'ALLOW_IF_SUPPORTED',
        context_strategy: 'ALLOW',
        max_tool_calls: 'ALLOW_WITHIN_RANGE',
        job_timeout_seconds: 'ALLOW_WITHIN_RANGE',
        permissions: 'REDUCE_ONLY',
        system_instructions: 'ADDITIVE_ONLY',
        allowed_results: 'LOCKED'
      },
      enabled: true
    };
  }
  async function load() {
    try {
      [roles, permissions, capabilities] = await Promise.all([
        listRoles(),
        listRolePermissions(),
        listRoleCapabilities()
      ]);
    } catch (cause) {
      error = String(cause);
    } finally {
      loading = false;
    }
  }
  function edit(role?: Role) {
    details = null;
    editing = role ?? null;
    form = role
      ? {
          name: role.name,
          category: role.category,
          description: role.description,
          system_instructions: role.system_instructions,
          capabilities: [...role.capabilities],
          permissions: [...role.permissions],
          allowed_results: [...role.allowed_results],
          knowledge_collection_ids: [...role.knowledge_collection_ids],
          default_provider: role.default_provider,
          default_model: role.default_model,
          default_reasoning_effort: role.default_reasoning_effort,
          default_timeout_minutes: role.default_timeout_minutes,
          default_max_retries: role.default_max_retries,
          runtime_profile: structuredClone(role.runtime_profile),
          override_policy: { ...role.override_policy },
          enabled: role.enabled
        }
      : blank();
    advanced = false;
    open = true;
  }
  function openDetails(role: Role) {
    details = role;
  }
  function handleCardKeydown(event: KeyboardEvent, role: Role) {
    if (event.target !== event.currentTarget || !['Enter', ' '].includes(event.key)) return;
    event.preventDefault();
    openDetails(role);
  }
  function formatDate(value: string) {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short'
    }).format(new Date(value));
  }
  function cloneDetails() {
    if (details) void copy(details);
  }
  function editDetails() {
    if (details) edit(details);
  }
  function toggle(field: 'capabilities' | 'permissions' | 'allowed_results', value: string) {
    const values = form[field];
    form[field] = values.includes(value)
      ? values.filter((item) => item !== value)
      : [...values, value];
  }
  async function save() {
    busy = true;
    error = '';
    try {
      if (editing) await updateRole(editing.id, form);
      else await createRole(form);
      open = false;
      await load();
    } catch (cause) {
      error = String(cause);
    } finally {
      busy = false;
    }
  }
  async function copy(role: Role) {
    const name = prompt('Name for the cloned role', `${role.name} Copy`);
    if (!name?.trim()) return;
    try {
      await cloneRole(role.id, name.trim());
      await load();
    } catch (cause) {
      error = String(cause);
    }
  }
  async function remove(role: Role) {
    if (!confirm(`Delete ${role.name}?`)) return;
    try {
      await deleteRole(role.id);
      await load();
    } catch (cause) {
      error = String(cause);
    }
  }
  onMount(load);
</script>

<svelte:window
  onkeydown={(event) => {
    if (event.key !== 'Escape') return;
    if (open) open = false;
    else details = null;
  }}
/>

<PageHeader
  eyebrow="WORKFORCE DESIGN"
  title="Roles"
  description="Reusable behavioral contracts inherited by concrete AI agents."
/>
<main class="space-y-6 p-4 sm:p-6 md:p-10">
  <ErrorBanner message={error} />
  <section class="intro">
    <div>
      <strong>Role ≠ agent</strong>
      <p>
        A role defines responsibility, limits, knowledge defaults, and valid outcomes. A team agent
        supplies the identity and model.
      </p>
    </div>
    <button class="primary" onclick={() => edit()}>Create role</button>
  </section>
  <section class="role-grid" aria-busy={loading}>
    {#if loading}
      <!-- eslint-disable-next-line @typescript-eslint/no-unused-vars -->
      {#each Array(4) as _, index (index)}
        <article class="role-card">
          <Skeleton class="h-3 w-24" />
          <Skeleton class="h-5 w-32" />
          <Skeleton class="h-10 w-full" />
          <Skeleton class="h-6 w-full" />
        </article>
      {/each}
    {/if}
    {#each roles as role (role.id)}
      <div
        class:disabled={!role.enabled}
        class="role-card"
        role="button"
        tabindex="0"
        aria-label={`View ${role.name} role details`}
        onclick={() => openDetails(role)}
        onkeydown={(event) => handleCardKeydown(event, role)}
      >
        <header>
          <span class="category">{role.category}</span><span
            class:built-in={role.built_in}
            class="kind">{role.built_in ? 'SYSTEM TEMPLATE' : `VERSION ${role.version}`}</span
          >
        </header>
        <div>
          <h2>{role.name}</h2>
          <p>{role.description || 'No description supplied.'}</p>
        </div>
        <div class="counts">
          <span><strong>{role.total_agents}</strong> total agents</span><span
            ><strong>{role.active_agents}</strong> active</span
          ><span><strong>{role.inactive_agents}</strong> inactive</span><span
            ><strong>{role.capabilities.length}</strong> capabilities</span
          >
        </div>
        <div class="chips">
          {#each role.capabilities.slice(0, 3) as capability (capability)}<span
              >{capability.replace('CAN_', '')}</span
            >{/each}
        </div>
        <footer>
          <button
            onclick={(event) => {
              event.stopPropagation();
              openDetails(role);
            }}>Details</button
          >
          {#if !role.built_in}<button
              onclick={(event) => {
                event.stopPropagation();
                edit(role);
              }}>Edit</button
            >{/if}
          <button
            onclick={(event) => {
              event.stopPropagation();
              void copy(role);
            }}>Clone</button
          >
          {#if !role.built_in}<button
              class="danger"
              disabled={role.total_agents > 0}
              onclick={(event) => {
                event.stopPropagation();
                void remove(role);
              }}>Delete</button
            >{/if}
        </footer>
      </div>
    {/each}
  </section>
</main>

{#if details}
  <button class="backdrop" aria-label="Close role details" onclick={() => (details = null)}
  ></button>
  <dialog open class="details-dialog" aria-labelledby="role-title">
    <header class="details-header">
      <div>
        <div class="details-badges">
          <span class="category">{details.category}</span>
          <span class:enabled={details.enabled} class="status">
            {details.enabled ? 'ENABLED' : 'DISABLED'}
          </span>
          <span class:built-in={details.built_in} class="kind">
            {details.built_in ? 'SYSTEM TEMPLATE' : 'CUSTOM ROLE'}
          </span>
        </div>
        <h2 id="role-title">{details.name}</h2>
        <p>{details.description || 'No description supplied.'}</p>
      </div>
      <button class="icon-button" aria-label="Close role details" onclick={() => (details = null)}
        >×</button
      >
    </header>

    <div class="details-body">
      <section class="agent-summary" aria-label="Assigned AI agents">
        <div><strong>{details.total_agents}</strong><span>Total agents</span></div>
        <div class="active-count"><strong>{details.active_agents}</strong><span>Active</span></div>
        <div><strong>{details.inactive_agents}</strong><span>Inactive</span></div>
      </section>

      <section class="detail-section">
        <h3>Execution defaults</h3>
        <dl class="facts">
          <div>
            <dt>Provider</dt>
            <dd>{details.default_provider || 'Agent decides'}</dd>
          </div>
          <div>
            <dt>Model</dt>
            <dd>{details.default_model || 'Provider default'}</dd>
          </div>
          <div>
            <dt>Reasoning</dt>
            <dd>{details.runtime_profile.reasoning_default.replaceAll('_', ' ')}</dd>
          </div>
          <div>
            <dt>Timeout</dt>
            <dd>{Math.round(details.runtime_profile.job_timeout_seconds / 60)} minutes</dd>
          </div>
          <div>
            <dt>Retries</dt>
            <dd>{details.runtime_profile.max_job_attempts}</dd>
          </div>
          <div>
            <dt>Version</dt>
            <dd>{details.version}</dd>
          </div>
        </dl>
      </section>

      <section class="detail-section detail-grid">
        <div>
          <h3>Capabilities <span>{details.capabilities.length}</span></h3>
          <div class="detail-chips">
            {#each details.capabilities as item (item)}
              <span>{item.replaceAll('_', ' ')}</span>
            {:else}
              <em>None configured</em>
            {/each}
          </div>
        </div>
        <div>
          <h3>Permissions <span>{details.permissions.length}</span></h3>
          <div class="detail-chips">
            {#each details.permissions as item (item)}
              <span>{item.replaceAll('_', ' ')}</span>
            {:else}
              <em>None configured</em>
            {/each}
          </div>
        </div>
      </section>

      <section class="detail-section">
        <h3>Allowed outcomes <span>{details.allowed_results.length}</span></h3>
        <div class="detail-chips outcomes">
          {#each details.allowed_results as item (item)}
            <span>{item.replaceAll('_', ' ')}</span>
          {:else}
            <em>No outcomes configured</em>
          {/each}
        </div>
      </section>

      <section class="detail-section">
        <h3>Knowledge defaults <span>{details.knowledge_collection_ids.length}</span></h3>
        {#if details.knowledge_collection_ids.length}
          <ul class="knowledge-list">
            {#each details.knowledge_collection_ids as collectionId (collectionId)}
              <li>{collectionId}</li>
            {/each}
          </ul>
        {:else}
          <p>No knowledge collections are assigned by default.</p>
        {/if}
      </section>

      <section class="detail-section">
        <h3>System instructions</h3>
        <pre>{details.system_instructions || 'No role-specific instructions supplied.'}</pre>
      </section>

      <section class="role-meta">
        <span>Created {formatDate(details.created_at)}</span>
        <span>Updated {formatDate(details.updated_at)}</span>
      </section>
    </div>

    <footer class="details-actions">
      <button onclick={() => (details = null)}>Close</button>
      <button onclick={cloneDetails}>Clone</button>
      {#if !details.built_in}<button class="primary" onclick={editDetails}>Edit role</button>{/if}
    </footer>
  </dialog>
{/if}

{#if open}
  <button class="backdrop" aria-label="Close role editor" onclick={() => (open = false)}></button>
  <aside class="drawer">
    <header>
      <div>
        <span>ROLE CONTRACT</span>
        <h2>{editing ? `Edit ${editing.name}` : 'Create role'}</h2>
      </div>
      <button onclick={() => (open = false)}>×</button>
    </header>
    <div class="body">
      <div class="two">
        <label
          ><span>Name</span><input bind:value={form.name} placeholder="Security Reviewer" /></label
        ><label
          ><span>Category</span><select bind:value={form.category}
            >{#each categories as category (category)}<option>{category}</option>{/each}</select
          ></label
        >
      </div>
      <label
        ><span>Description</span><textarea
          bind:value={form.description}
          rows="2"
          placeholder="What this role owns and delivers"
        ></textarea></label
      >
      <label
        ><span>Default system instructions</span><textarea
          class="prompt"
          bind:value={form.system_instructions}
          rows="7"
          placeholder="Responsibility, priorities, constraints, success and blocker definitions…"
        ></textarea><small
          >Mandatory platform security and output instructions are added separately at runtime.</small
        ></label
      >
      <fieldset>
        <legend>Workflow capabilities</legend>
        <div class="options">
          {#each capabilities as item (item)}<label
              ><input
                type="checkbox"
                checked={form.capabilities.includes(item)}
                onchange={() => toggle('capabilities', item)}
              /><span>{item.replaceAll('_', ' ')}</span></label
            >{/each}
        </div>
      </fieldset>
      <fieldset>
        <legend>Runtime permissions</legend>
        <p>These control available operations; prompt text cannot grant additional access.</p>
        <div class="options">
          {#each permissions as item (item)}<label
              ><input
                type="checkbox"
                checked={form.permissions.includes(item)}
                onchange={() => toggle('permissions', item)}
              /><span>{item.replaceAll('_', ' ')}</span></label
            >{/each}
        </div>
      </fieldset>
      <fieldset>
        <legend>Allowed structured results</legend>
        <div class="options">
          {#each outcomes as item (item)}<label
              ><input
                type="checkbox"
                checked={form.allowed_results.includes(item)}
                onchange={() => toggle('allowed_results', item)}
              /><span>{item.replaceAll('_', ' ')}</span></label
            >{/each}
        </div>
      </fieldset>
      <button class="advanced" onclick={() => (advanced = !advanced)}
        >{advanced ? 'Hide' : 'Show'} advanced defaults</button
      >
      {#if advanced}<section class="advanced-panel">
          <div class="two">
            <label
              ><span>Provider</span><select bind:value={form.default_provider}
                ><option value={null}>Agent decides</option><option value="openai">OpenAI</option
                ><option value="anthropic">Anthropic</option><option value="google"
                  >Google Gemini</option
                ></select
              ></label
            ><label
              ><span>Model</span><input
                bind:value={form.default_model}
                placeholder="Provider default"
              /></label
            >
          </div>
          <div class="two">
            <label
              ><span>Default reasoning</span><select
                bind:value={form.runtime_profile.reasoning_default}
                ><option>PROVIDER_DEFAULT</option><option>MINIMAL</option><option>LOW</option
                ><option>MEDIUM</option><option>HIGH</option><option>MAX</option></select
              ></label
            ><label
              ><span>Context</span><select bind:value={form.runtime_profile.context_strategy}
                ><option>MINIMAL</option><option>BALANCED</option><option>DEEP</option></select
              ></label
            >
          </div>
          <label class="toggle-runtime"
            ><input type="checkbox" bind:checked={form.runtime_profile.dynamic_reasoning_allowed} />
            <span>Allow strategy to tune reasoning within the Role range</span></label
          >
          <div class="two">
            <label
              ><span>Minimum reasoning</span><select bind:value={form.runtime_profile.reasoning_min}
                ><option>PROVIDER_DEFAULT</option><option>MINIMAL</option><option>LOW</option
                ><option>MEDIUM</option><option>HIGH</option><option>MAX</option></select
              ></label
            ><label
              ><span>Maximum reasoning</span><select bind:value={form.runtime_profile.reasoning_max}
                ><option>PROVIDER_DEFAULT</option><option>MINIMAL</option><option>LOW</option
                ><option>MEDIUM</option><option>HIGH</option><option>MAX</option></select
              ></label
            >
          </div>
          <div class="two">
            <label
              ><span>Timeout (seconds)</span><input
                type="number"
                min="60"
                max="43200"
                bind:value={form.runtime_profile.job_timeout_seconds}
              /></label
            ><label
              ><span>Max attempts</span><input
                type="number"
                min="0"
                max="10"
                bind:value={form.runtime_profile.max_job_attempts}
              /></label
            >
          </div>
          <div class="two">
            <label
              ><span>Max tool calls</span><input
                type="number"
                min="1"
                max="200"
                bind:value={form.runtime_profile.max_tool_calls}
              /></label
            ><label
              ><span>Max model turns</span><input
                type="number"
                min="1"
                max="20"
                bind:value={form.runtime_profile.max_model_turns}
              /></label
            >
          </div>
          <div class="two">
            <label
              ><span>Max output tokens</span><input
                type="number"
                min="256"
                bind:value={form.runtime_profile.max_output_tokens}
                placeholder="Provider default"
              /></label
            ><label
              ><span>Temperature</span><input
                type="number"
                min="0"
                max="2"
                step="0.1"
                bind:value={form.runtime_profile.temperature}
                placeholder="Provider default"
              /></label
            >
          </div>
        </section>{/if}
    </div>
    <footer>
      <button onclick={() => (open = false)}>Cancel</button><button
        class="primary"
        disabled={busy || !form.name.trim()}
        onclick={() => void save()}>{busy ? 'Saving…' : 'Save role'}</button
      >
    </footer>
  </aside>
{/if}

<style>
  button,
  input,
  select,
  textarea {
    font: inherit;
  }
  button {
    cursor: pointer;
  }
  .primary {
    border-radius: 0.6rem;
    background: var(--color-brand);
    padding: 0.7rem 1rem;
    color: white;
    font-weight: 750;
  }
  .intro {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    border: 1px solid var(--color-line);
    border-radius: 1rem;
    background: var(--color-panel);
    padding: 1rem 1.2rem;
  }
  .intro p,
  .role-card p,
  fieldset p,
  small {
    color: var(--color-muted);
    font-size: 0.8rem;
  }
  .role-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(290px, 1fr));
    gap: 1rem;
  }
  .role-card {
    display: grid;
    gap: 1rem;
    border: 1px solid var(--color-line);
    border-radius: 1rem;
    background: var(--color-panel);
    padding: 1rem;
    cursor: pointer;
    transition:
      border-color 140ms ease,
      transform 140ms ease;
  }
  .role-card:hover,
  .role-card:focus-visible {
    border-color: color-mix(in srgb, var(--color-brand) 55%, var(--color-line));
    transform: translateY(-1px);
    outline: none;
  }
  .role-card.disabled {
    opacity: 0.55;
  }
  .role-card header,
  .role-card footer,
  .drawer > header,
  .drawer > footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.7rem;
  }
  .category,
  .kind {
    font: 700 0.65rem/1 var(--font-mono);
    letter-spacing: 0.08em;
    color: var(--color-muted);
  }
  .kind.built-in {
    color: var(--color-brand);
  }
  h2 {
    font-size: 1.15rem;
    font-weight: 800;
  }
  .counts {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 0.5rem;
    font-size: 0.7rem;
    color: var(--color-muted);
  }
  .counts span {
    border-left: 2px solid var(--color-line);
    padding-left: 0.5rem;
  }
  .counts strong {
    display: block;
    color: var(--color-text);
    font-size: 1rem;
  }
  .chips {
    min-height: 1.5rem;
    display: flex;
    flex-wrap: wrap;
    gap: 0.3rem;
  }
  .chips span {
    border-radius: 999px;
    background: var(--color-soft);
    padding: 0.3rem 0.5rem;
    font-size: 0.65rem;
  }
  .role-card footer button,
  .drawer footer button,
  .advanced {
    border: 1px solid var(--color-line);
    border-radius: 0.5rem;
    padding: 0.5rem 0.7rem;
    font-size: 0.75rem;
  }
  .danger {
    color: #d84a4a;
  }
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 40;
    background: rgb(0 0 0 / 0.44);
  }
  .details-dialog {
    position: fixed;
    inset: 50% auto auto 50%;
    z-index: 50;
    display: grid;
    grid-template-rows: auto minmax(0, 1fr) auto;
    width: min(860px, calc(100% - 2rem));
    max-height: min(880px, calc(100vh - 2rem));
    margin: 0;
    padding: 0;
    transform: translate(-50%, -50%);
    overflow: hidden;
    border: 1px solid var(--color-line);
    border-radius: 1rem;
    background: var(--color-bg);
    box-shadow: 0 24px 80px rgb(0 0 0 / 0.3);
  }
  .details-header,
  .details-actions {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: 1.25rem;
  }
  .details-header {
    border-bottom: 1px solid var(--color-line);
  }
  .details-header p,
  .detail-section p {
    margin-top: 0.35rem;
    color: var(--color-muted);
    font-size: 0.8rem;
  }
  .details-badges {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.7rem;
    margin-bottom: 0.45rem;
  }
  .status {
    font: 700 0.65rem/1 var(--font-mono);
    color: var(--color-muted);
  }
  .status.enabled {
    color: #2d9d68;
  }
  .icon-button {
    align-self: start;
    padding: 0.1rem 0.35rem;
    font-size: 1.5rem;
  }
  .details-body {
    overflow: auto;
    display: grid;
    gap: 1rem;
    padding: 1.25rem;
  }
  .agent-summary {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.65rem;
  }
  .agent-summary div {
    display: grid;
    gap: 0.2rem;
    border: 1px solid var(--color-line);
    border-radius: 0.75rem;
    background: var(--color-panel);
    padding: 0.9rem;
  }
  .agent-summary strong {
    font-size: 1.4rem;
  }
  .agent-summary span,
  dt,
  .role-meta {
    color: var(--color-muted);
    font-size: 0.7rem;
  }
  .agent-summary .active-count {
    border-color: color-mix(in srgb, #2d9d68 50%, var(--color-line));
  }
  .detail-section {
    border: 1px solid var(--color-line);
    border-radius: 0.8rem;
    padding: 1rem;
  }
  .detail-section h3 {
    margin-bottom: 0.7rem;
    font-size: 0.82rem;
    font-weight: 800;
  }
  .detail-section h3 span {
    color: var(--color-muted);
    font-family: var(--font-mono);
  }
  .detail-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1.25rem;
  }
  .facts {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.75rem;
  }
  .facts div {
    min-width: 0;
  }
  .facts dd {
    overflow-wrap: anywhere;
    font-size: 0.78rem;
    font-weight: 700;
    text-transform: capitalize;
  }
  .detail-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
  }
  .detail-chips span {
    border-radius: 999px;
    background: var(--color-soft);
    padding: 0.35rem 0.55rem;
    font-size: 0.65rem;
  }
  .detail-chips em {
    color: var(--color-muted);
    font-size: 0.75rem;
    font-style: normal;
  }
  .outcomes span {
    font-family: var(--font-mono);
  }
  .knowledge-list {
    display: grid;
    gap: 0.3rem;
    color: var(--color-muted);
    font: 0.68rem var(--font-mono);
  }
  .detail-section pre {
    max-height: 260px;
    overflow: auto;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    color: var(--color-muted);
    font: 0.74rem/1.55 var(--font-mono);
  }
  .role-meta {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    gap: 0.5rem;
  }
  .details-actions {
    justify-content: flex-end;
    border-top: 1px solid var(--color-line);
  }
  .details-actions button {
    border: 1px solid var(--color-line);
    border-radius: 0.5rem;
    padding: 0.55rem 0.8rem;
    font-size: 0.75rem;
  }
  .drawer {
    position: fixed;
    inset: 0 0 0 auto;
    z-index: 50;
    display: grid;
    grid-template-rows: auto 1fr auto;
    width: min(760px, 100%);
    background: var(--color-bg);
    box-shadow: -20px 0 60px rgb(0 0 0 / 0.2);
  }
  .drawer > header,
  .drawer > footer {
    border-bottom: 1px solid var(--color-line);
    padding: 1rem 1.25rem;
  }
  .drawer > footer {
    border-top: 1px solid var(--color-line);
    border-bottom: 0;
    justify-content: flex-end;
  }
  .drawer > header span {
    font: 700 0.65rem var(--font-mono);
    letter-spacing: 0.12em;
    color: var(--color-brand);
  }
  .drawer > header > button {
    font-size: 1.5rem;
  }
  .body {
    overflow: auto;
    display: grid;
    align-content: start;
    gap: 1.25rem;
    padding: 1.25rem;
  }
  .two {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1rem;
  }
  label {
    display: grid;
    gap: 0.4rem;
    font-size: 0.78rem;
    font-weight: 700;
  }
  input,
  select,
  textarea {
    width: 100%;
    border: 1px solid var(--color-line);
    border-radius: 0.55rem;
    background: var(--color-panel);
    padding: 0.7rem;
    color: var(--color-text);
  }
  .prompt {
    font-family: var(--font-mono);
    font-size: 0.78rem;
  }
  fieldset {
    border-top: 1px solid var(--color-line);
    padding-top: 1rem;
  }
  legend {
    padding-right: 0.7rem;
    font-size: 0.85rem;
    font-weight: 800;
  }
  .options {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 0.45rem;
    margin-top: 0.7rem;
  }
  .options label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    border: 1px solid var(--color-line);
    border-radius: 0.5rem;
    padding: 0.55rem;
    font-size: 0.68rem;
  }
  .options input {
    width: auto;
  }
  .advanced {
    justify-self: start;
  }
  .advanced-panel {
    display: grid;
    gap: 1rem;
    border-radius: 0.8rem;
    background: var(--color-panel);
    padding: 1rem;
  }
  @media (max-width: 600px) {
    .two,
    .options,
    .detail-grid {
      grid-template-columns: 1fr;
    }
    .counts,
    .facts {
      grid-template-columns: repeat(2, 1fr);
    }
    .intro {
      align-items: start;
      flex-direction: column;
    }
  }
</style>
