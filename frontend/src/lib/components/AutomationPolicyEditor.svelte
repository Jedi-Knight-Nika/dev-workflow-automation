<script lang="ts">
  import { onMount } from 'svelte';
  import { getAutomation, saveAutomation, type AutomationPolicy } from '$lib/services/engineering';
  let { teamId }: { teamId: string } = $props();
  let policy = $state<AutomationPolicy | null>(null);
  let repositories = $state('');
  let reviewers = $state('');
  let checks = $state('');
  let message = $state('');
  let busy = $state(false);
  const checkPlaceholder = 'Backend\nFrontend\nQuality gate';
  const split = (value: string) =>
    value
      .split(/[\n,]/)
      .map((item) => item.trim())
      .filter(Boolean);
  onMount(() => {
    let disposed = false;
    void getAutomation(teamId)
      .then((value) => {
        if (disposed) return;
        policy = { ...value, reviewer_scope: value.reviewer_scope ?? 'allowlist' };
        repositories = value.repository_ids.join('\n');
        reviewers = value.authorized_reviewer_ids.join('\n');
        checks = value.required_checks.join('\n');
      })
      .catch((error) => {
        if (!disposed) message = String(error);
      });
    return () => {
      disposed = true;
    };
  });
  async function save() {
    if (!policy) return;
    busy = true;
    try {
      const result = await saveAutomation(teamId, {
        ...policy,
        repository_ids: split(repositories),
        authorized_reviewer_ids: split(reviewers),
        required_checks: split(checks)
      });
      policy.version = result.version;
      message = 'Policy saved. Task usage and native sessions are unchanged.';
    } catch (error) {
      message = String(error);
    } finally {
      busy = false;
    }
  }
</script>

<section class="policy-panel">
  <header>
    <div>
      <p class="eyebrow">DELIVERY CONTROL</p>
      <h2>Automation and merge policy</h2>
      <p>
        Choose where work may run, cap spending, and define the exact evidence required to merge.
      </p>
    </div>
    {#if policy}<span class:enabled={policy.enrollment_enabled} class="state-pill"
        >{policy.enrollment_enabled ? 'Automation on' : 'Automation off'}</span
      >{/if}
  </header>
  {#if message}<p class="notice" role="status">{message}</p>{/if}
  {#if policy}
    <form
      onsubmit={(event) => {
        event.preventDefault();
        void save();
      }}
    >
      <div class="policy-card enrollment">
        <div>
          <strong>Automatic enrollment</strong>
          <span>Start eligible imported tickets without a manual enrollment click.</span>
        </div>
        <label class="switch" aria-label="Enroll eligible imports automatically">
          <input type="checkbox" bind:checked={policy.enrollment_enabled} />
          <i></i>
        </label>
      </div>

      <fieldset>
        <legend><span>01</span> Spending boundaries</legend>
        <p>Hard admission limits. Automation cannot raise or bypass them.</p>
        <div class="two-columns">
          <label
            >Task limit <span>USD per task</span>
            <div class="money-input">
              <b>$</b><input
                type="number"
                min="0.01"
                max="10000"
                step="0.01"
                bind:value={policy.task_budget_usd}
                required
              />
            </div></label
          >
          <label
            >Team cumulative limit <span>Total USD ceiling</span>
            <div class="money-input">
              <b>$</b><input
                type="number"
                min="0.01"
                max="10000"
                step="0.01"
                bind:value={policy.team_budget_usd}
                required
              />
            </div></label
          >
        </div>
      </fieldset>

      <fieldset>
        <legend><span>02</span> Repository scope</legend>
        <p>Only these repository UUIDs may receive automated work.</p>
        <label
          >Allowed repositories <span>One UUID per line</span><textarea
            bind:value={repositories}
            rows="3"
            spellcheck="false"
            placeholder="00000000-0000-0000-0000-000000000000"
          ></textarea></label
        >
      </fieldset>

      <fieldset>
        <legend><span>03</span> Merge authority</legend>
        <div class="policy-card compact">
          <div>
            <strong>Auto-merge</strong>
            <span>Merge only the validated current commit after every configured gate passes.</span>
          </div>
          <label class="switch" aria-label="Enable automatic merge">
            <input type="checkbox" bind:checked={policy.auto_merge} />
            <i></i>
          </label>
        </div>
        <div class="two-columns">
          <label
            >Who can approve on GitHub?<select bind:value={policy.reviewer_scope}>
              <option value="allowlist">Only listed reviewers</option>
              <option value="any_human">Any human commenter, including PR author</option>
            </select></label
          >
          <label
            >{policy.reviewer_scope === 'allowlist'
              ? 'Authorized reviewer numeric IDs'
              : 'Control-authorized GitHub IDs (optional)'}<span
              >{policy.reviewer_scope === 'allowlist'
                ? 'Immutable IDs, one per line'
                : 'May pause, resume, or cancel'}</span
            ><textarea bind:value={reviewers} rows="3" spellcheck="false"></textarea></label
          >
        </div>
        <label class="approval-check">
          <input type="checkbox" bind:checked={policy.require_formal_approval} />
          <span
            ><strong>Require formal GitHub review approval</strong><small
              >When off, a valid human “LGTM” or “ready to merge” comment may approve.</small
            ></span
          >
        </label>
      </fieldset>

      <fieldset>
        <legend><span>04</span> Required checks</legend>
        <p>Every named CI check must exist and pass for the current commit.</p>
        <label
          >CI check names <span>One exact name per line</span><textarea
            bind:value={checks}
            rows="4"
            spellcheck="false"
            placeholder={checkPlaceholder}
          ></textarea></label
        >
      </fieldset>

      <div class="safety-note">
        <b>Current-commit safety stays enforced.</b>
        <p>
          Bots cannot approve. Validation, CI, blocking reviews, pause state, and the exact PR head
          are checked again immediately before merge.
        </p>
      </div>
      <footer>
        <span>Policy revision {policy.version}</span>
        <button disabled={busy}>{busy ? 'Saving…' : 'Save automation policy'}</button>
      </footer>
    </form>
  {/if}
</section>

<style>
  .policy-panel {
    margin: 1.5rem 0;
    overflow: hidden;
    border: 1px solid var(--color-line);
    border-radius: 16px;
    background: var(--color-panel-alt);
    box-shadow: 0 18px 55px -42px color-mix(in srgb, var(--color-brand-2) 60%, transparent);
  }
  header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1.5rem;
    padding: 1.4rem 1.5rem;
    border-bottom: 1px solid var(--color-line);
    background: radial-gradient(
      circle at 90% 0,
      color-mix(in srgb, var(--color-brand-2) 12%, transparent),
      transparent 45%
    );
  }
  h2 {
    margin: 0.2rem 0;
    color: var(--color-heading);
    font-size: 1.15rem;
  }
  p {
    margin: 0.25rem 0;
    color: var(--color-muted);
    font-size: 0.8rem;
    line-height: 1.55;
  }
  .eyebrow {
    color: var(--color-brand-2);
    font-size: 0.62rem;
    font-weight: 800;
    letter-spacing: 0.16em;
  }
  .state-pill {
    flex: none;
    border: 1px solid var(--color-line);
    border-radius: 999px;
    padding: 0.38rem 0.65rem;
    color: var(--color-muted);
    background: var(--color-input);
    font-size: 0.66rem;
    font-weight: 700;
  }
  .state-pill.enabled {
    border-color: color-mix(in srgb, var(--color-accent) 55%, var(--color-line));
    color: var(--color-accent);
    box-shadow: 0 0 14px -5px var(--color-accent);
  }
  .notice {
    margin: 1rem 1.5rem 0;
    border-radius: 8px;
    padding: 0.7rem;
    background: color-mix(in srgb, var(--color-brand-2) 9%, transparent);
  }
  form {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 1rem;
    padding: 1.25rem;
  }
  fieldset,
  .policy-card,
  .safety-note {
    min-width: 0;
    border: 1px solid var(--color-line);
    border-radius: 12px;
    padding: 1rem;
    background: color-mix(in srgb, var(--color-panel) 88%, transparent);
  }
  fieldset:nth-of-type(3),
  fieldset:nth-of-type(4),
  .enrollment,
  .safety-note,
  footer {
    grid-column: 1 / -1;
  }
  legend {
    padding: 0 0.35rem;
    color: var(--color-heading);
    font-size: 0.82rem;
    font-weight: 750;
  }
  legend span {
    margin-right: 0.4rem;
    color: var(--color-brand-2);
    font-size: 0.62rem;
  }
  .policy-card {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
  }
  .policy-card strong,
  .policy-card span {
    display: block;
  }
  .policy-card span {
    margin-top: 0.25rem;
    color: var(--color-muted);
    font-size: 0.72rem;
  }
  .policy-card.compact {
    margin: 0.65rem 0 1rem;
    padding: 0.8rem;
  }
  .two-columns {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.8rem;
    margin-top: 0.8rem;
  }
  label {
    display: grid;
    gap: 0.35rem;
    color: var(--color-heading);
    font-size: 0.72rem;
    font-weight: 650;
  }
  label > span {
    color: var(--color-muted);
    font-size: 0.62rem;
    font-weight: 400;
  }
  textarea,
  select,
  input:not([type='checkbox']) {
    width: 100%;
    min-width: 0;
    border: 1px solid var(--color-line);
    border-radius: 8px;
    padding: 0.68rem;
    background: var(--color-input);
    color: var(--color-text);
    outline: none;
    font: inherit;
    font-weight: 450;
  }
  textarea {
    resize: vertical;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 0.68rem;
  }
  textarea:focus,
  select:focus,
  input:focus {
    border-color: var(--color-brand-2);
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--color-brand-2) 12%, transparent);
  }
  .money-input {
    position: relative;
  }
  .money-input b {
    position: absolute;
    top: 50%;
    left: 0.7rem;
    transform: translateY(-50%);
    color: var(--color-brand-2);
  }
  .money-input input {
    padding-left: 1.7rem;
  }
  .switch {
    display: inline-flex;
    cursor: pointer;
  }
  .switch input {
    position: absolute;
    opacity: 0;
    pointer-events: none;
  }
  .switch i {
    position: relative;
    width: 42px;
    height: 23px;
    border: 1px solid var(--color-line);
    border-radius: 999px;
    background: var(--color-input);
    transition: 0.2s ease;
  }
  .switch i::after {
    content: '';
    position: absolute;
    top: 3px;
    left: 3px;
    width: 15px;
    height: 15px;
    border-radius: 50%;
    background: var(--color-muted);
    transition: 0.2s ease;
  }
  .switch input:checked + i {
    border-color: var(--color-accent);
    background: color-mix(in srgb, var(--color-accent) 20%, var(--color-input));
    box-shadow: 0 0 12px -4px var(--color-accent);
  }
  .switch input:checked + i::after {
    transform: translateX(19px);
    background: var(--color-accent);
  }
  .approval-check {
    display: flex;
    align-items: flex-start;
    gap: 0.65rem;
    margin-top: 1rem;
    border-top: 1px solid var(--color-line);
    padding-top: 1rem;
  }
  .approval-check input {
    margin-top: 0.18rem;
    accent-color: var(--color-accent);
  }
  .approval-check span,
  .approval-check small {
    display: block;
  }
  .approval-check small {
    margin-top: 0.2rem;
    color: var(--color-muted);
    font-weight: 400;
  }
  .safety-note {
    border-color: color-mix(in srgb, var(--color-brand-2) 30%, var(--color-line));
    background: linear-gradient(
      110deg,
      color-mix(in srgb, var(--color-brand-2) 8%, var(--color-panel)),
      var(--color-panel)
    );
  }
  .safety-note b {
    color: var(--color-heading);
    font-size: 0.76rem;
  }
  footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    border-top: 1px solid var(--color-line);
    padding-top: 1rem;
    color: var(--color-muted);
    font-size: 0.66rem;
  }
  footer button {
    border: 1px solid color-mix(in srgb, var(--color-accent) 65%, transparent);
    border-radius: 8px;
    padding: 0.7rem 1.1rem;
    background: linear-gradient(
      135deg,
      color-mix(in srgb, var(--color-brand) 75%, #111827),
      color-mix(in srgb, var(--color-accent) 60%, #111827)
    );
    color: white;
    cursor: pointer;
    font-weight: 750;
    box-shadow: 0 0 18px -7px var(--color-accent);
  }
  footer button:disabled {
    cursor: wait;
    opacity: 0.55;
  }
  @media (max-width: 760px) {
    form,
    .two-columns {
      grid-template-columns: 1fr;
    }
    fieldset,
    .enrollment,
    .safety-note,
    footer {
      grid-column: 1;
    }
    header {
      align-items: center;
    }
  }
</style>
