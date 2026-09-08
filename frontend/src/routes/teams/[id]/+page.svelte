<script lang="ts">
  import { page } from '$app/state';
  import { onMount } from 'svelte';
  import ErrorBanner from '$lib/components/ErrorBanner.svelte';
  import FixedLifecycleCanvas from '$lib/components/FixedLifecycleCanvas.svelte';
  import AutomationPolicyEditor from '$lib/components/AutomationPolicyEditor.svelte';
  import V2StatisticsPanel from '$lib/components/V2StatisticsPanel.svelte';
  import {
    getTeamActivity,
    listProfiles,
    initializeProfiles,
    saveProfile,
    type AgentProfile,
    type TeamActivity
  } from '$lib/services/engineering-v2';

  let activity = $state<TeamActivity | null>(null);
  let profiles = $state<AgentProfile[]>([]);
  let busy = $state('');
  let error = $state('');
  let notice = $state('');
  let loading = $state(true);
  let refreshing = false;

  function teamId(): string {
    if (!page.params.id) throw new Error('Team ID is missing');
    return page.params.id;
  }

  async function refresh() {
    if (refreshing) return;
    refreshing = true;
    try {
      const requestedId = teamId();
      const next = await getTeamActivity(requestedId);
      if (teamId() === requestedId) activity = next;
    } catch (cause) {
      error = String(cause);
    } finally {
      refreshing = false;
    }
  }
  $effect(() => {
    const id = page.params.id;
    if (!id) return;
    loading = true;
    profiles = [];
    activity = null;
    let disposed = false;
    void Promise.all([getTeamActivity(id), listProfiles(id)])
      .then(([next, rows]) => {
        if (!disposed) {
          activity = next;
          profiles = rows;
        }
      })
      .catch((cause) => {
        if (!disposed) error = String(cause);
      })
      .finally(() => {
        if (!disposed) loading = false;
      });
    return () => {
      disposed = true;
    };
  });
  onMount(() => {
    const timer = setInterval(() => {
      if (!document.hidden) void refresh();
    }, 5000);
    return () => {
      clearInterval(timer);
    };
  });
  async function initialize() {
    busy = 'initialize';
    error = '';
    try {
      profiles = await initializeProfiles(teamId());
      notice = 'Fixed profiles created. No tasks were started or migrated.';
    } catch (cause) {
      error = String(cause);
    } finally {
      busy = '';
    }
  }
  async function save(profile: AgentProfile) {
    busy = profile.id;
    error = '';
    notice = '';
    try {
      const saved = await saveProfile(profile);
      profiles = profiles.map((item) => (item.id === saved.id ? saved : item));
      notice = `${saved.display_name} saved.`;
    } catch (cause) {
      error = String(cause);
    } finally {
      busy = '';
    }
  }
</script>

<svelte:head><title>{activity?.team_name ?? 'Team'} · V2 engineering</title></svelte:head>
<main>
  <header>
    <p>ENGINEERING V2 · CONTROLLED ROLLOUT</p>
    <h1>{activity?.team_name ?? 'Team'}</h1>
    <p>
      Configure fixed profiles, explicit ticket enrollment, budgets, and merge authority. Existing
      legacy tickets stay unchanged. Verify your isolated runtime before enabling workers.
    </p>
  </header>
  <ErrorBanner message={error} />
  {#if notice}<p role="status">{notice}</p>{/if}
  {#if loading}<p>Loading team…</p>{/if}
  {#if activity}<FixedLifecycleCanvas {activity} />{/if}
  {#if activity}{#key activity.team_id}<AutomationPolicyEditor
        teamId={activity.team_id}
        tasks={activity.tasks}
      />{/key}{/if}
  {#if activity}{#key activity.team_id}<V2StatisticsPanel teamId={activity.team_id} />{/key}{/if}
  <section class="profiles">
    <h2>Fixed agent profiles</h2>
    <p>
      Names and model preferences are configurable. Workflow transitions, tool authority, and system
      instructions are not.
    </p>
    {#if !loading && !profiles.length}<button disabled={!!busy} onclick={initialize}
        >Initialize V2 profiles</button
      >{/if}
    <div class="cards">
      {#each profiles as profile (profile.id)}
        <form
          onsubmit={(event) => {
            event.preventDefault();
            void save(profile);
          }}
        >
          <h3>{profile.role_kind}</h3>
          {#if profile.role_kind === 'THINKER' || profile.role_kind === 'REVIEWER'}
            <p>Reserved profile. Optional paid dispatch is not connected in this rollout.</p>
          {/if}
          <label
            >Display name<input bind:value={profile.display_name} maxlength="120" required /></label
          >
          <label
            >Provider<select
              bind:value={profile.provider}
              onchange={() => {
                profile.harness =
                  profile.role_kind === 'INTERPRETER'
                    ? null
                    : profile.provider === 'anthropic'
                      ? 'claude'
                      : 'codex';
              }}
            >
              {#if profile.role_kind === 'INTERPRETER'}<option value="ollama">Ollama (local)</option
                ><option value="deepseek">DeepSeek</option>{/if}
              <option value="openai">OpenAI</option>{#if profile.role_kind !== 'INTERPRETER'}<option
                  value="anthropic">Anthropic</option
                >{/if}
            </select></label
          >
          <label>Model<input bind:value={profile.model} maxlength="255" required /></label>
          <label
            >Soft budget (USD)<input
              inputmode="decimal"
              value={profile.soft_budget_usd ?? ''}
              onchange={(event) =>
                (profile.soft_budget_usd = event.currentTarget.value.trim() || null)}
              placeholder="Optional advisory value"
            /></label
          >
          <label
            >Hard budget (USD)<input
              inputmode="decimal"
              value={profile.hard_budget_usd ?? ''}
              onchange={(event) =>
                (profile.hard_budget_usd = event.currentTarget.value.trim() || null)}
              placeholder="Developer requires an explicit limit"
            /></label
          >
          <label
            >Effort<select bind:value={profile.effort}
              ><option value="none">None</option><option value="low">Low</option><option
                value="medium">Medium</option
              ><option value="high">High</option></select
            ></label
          >
          {#if profile.role_kind === 'THINKER' || profile.role_kind === 'REVIEWER'}<label
              class="check"
              ><input type="checkbox" bind:checked={profile.enabled} disabled /> Optional dispatch unavailable</label
            >{/if}
          <label
            >Team guidance<textarea
              bind:value={profile.supplemental_instructions}
              maxlength="8000"
              rows="4"
            ></textarea></label
          >
          <small
            >Harness: {profile.harness ?? 'classification only'} · prompt {profile.prompt_version} · version
            {profile.version}</small
          >
          <button disabled={!!busy}>{busy === profile.id ? 'Saving…' : 'Save profile'}</button>
        </form>
      {/each}
    </div>
  </section>
</main>

<style>
  main {
    padding: 1.5rem;
    max-width: 1600px;
    margin: auto;
  }
  header {
    margin-bottom: 1.5rem;
  }
  header p,
  .profiles > p {
    opacity: 0.75;
    max-width: 850px;
  }
  .profiles {
    margin-top: 2rem;
  }
  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 1rem;
  }
  form {
    display: grid;
    gap: 0.8rem;
    border: 1px solid #64748b66;
    border-radius: 12px;
    padding: 1rem;
  }
  label {
    display: grid;
    gap: 0.3rem;
    font-size: 0.85rem;
  }
  input,
  select,
  textarea,
  button {
    border: 1px solid #64748b66;
    border-radius: 7px;
    padding: 0.6rem;
    background: transparent;
    color: inherit;
  }
  button {
    cursor: pointer;
  }
  button:disabled {
    opacity: 0.5;
  }
  .check {
    display: flex;
    align-items: center;
  }
  small {
    opacity: 0.7;
  }
</style>
