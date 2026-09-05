<script lang="ts">
  import { onMount } from 'svelte';
  import ErrorBanner from '$lib/components/ErrorBanner.svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
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
    'REVIEW',
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
    'TEST_FAILED',
    'PLAN_MISMATCH',
    'NEEDS_REPLAN'
  ];
  let roles = $state<Role[]>([]),
    permissions = $state<string[]>([]),
    capabilities = $state<string[]>([]);
  let editing = $state<Role | null>(null),
    open = $state(false),
    advanced = $state(false),
    busy = $state(false),
    error = $state('');
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
    }
  }
  function edit(role?: Role) {
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
          enabled: role.enabled
        }
      : blank();
    advanced = false;
    open = true;
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
  <section class="role-grid">
    {#each roles as role (role.id)}
      <article class:disabled={!role.enabled} class="role-card">
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
          <span><strong>{role.active_agents}</strong> agents</span><span
            ><strong>{role.capabilities.length}</strong> capabilities</span
          ><span><strong>{role.permissions.length}</strong> permissions</span>
        </div>
        <div class="chips">
          {#each role.capabilities.slice(0, 3) as capability (capability)}<span
              >{capability.replace('CAN_', '')}</span
            >{/each}
        </div>
        <footer>
          {#if !role.built_in}<button onclick={() => edit(role)}>Edit</button>{/if}
          <button onclick={() => void copy(role)}>Clone</button>
          {#if !role.built_in}<button
              class="danger"
              disabled={role.active_agents > 0}
              onclick={() => void remove(role)}>Delete</button
            >{/if}
        </footer>
      </article>
    {/each}
  </section>
</main>

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
                ><option value="anthropic">Anthropic</option><option value="gemini"
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
          <label
            ><span>Reasoning</span><select bind:value={form.default_reasoning_effort}
              ><option>default</option><option>low</option><option>medium</option><option
                >high</option
              ><option>max</option></select
            ></label
          >
          <div class="two">
            <label
              ><span>Timeout: {form.default_timeout_minutes} min</span><input
                type="range"
                min="5"
                max="120"
                step="5"
                bind:value={form.default_timeout_minutes}
              /></label
            ><label
              ><span>Retries: {form.default_max_retries}</span><input
                type="range"
                min="0"
                max="10"
                bind:value={form.default_max_retries}
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
    grid-template-columns: repeat(3, 1fr);
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
  input[type='range'] {
    padding: 0.3rem 0;
    accent-color: var(--color-brand);
  }
  @media (max-width: 600px) {
    .two,
    .options {
      grid-template-columns: 1fr;
    }
    .intro {
      align-items: start;
      flex-direction: column;
    }
  }
</style>
