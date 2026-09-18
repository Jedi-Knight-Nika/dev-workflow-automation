<script lang="ts">
  import { t } from '$lib/i18n/index.svelte';
  import type { Repository, Team } from '$lib/types';

  let {
    editing,
    name = $bindable(),
    description = $bindable(),
    concurrency = $bindable(),
    repositoryIds = $bindable(),
    repositories,
    busy,
    onSave,
    onClose
  }: {
    editing: Team | null;
    name: string;
    description: string;
    concurrency: number;
    repositoryIds: string[];
    repositories: Repository[];
    busy: boolean;
    onSave: () => void;
    onClose: () => void;
  } = $props();

  function toggleRepository(id: string) {
    repositoryIds = repositoryIds.includes(id)
      ? repositoryIds.filter((item) => item !== id)
      : [...repositoryIds, id];
  }
</script>

<button class="backdrop" aria-label={t('teamsPage.close')} onclick={onClose}></button>
<aside class="drawer">
  <header>
    <div>
      <span>{t('teamsPage.configEyebrow')}</span>
      <h2>
        {editing ? t('teamsPage.editTeam', { name: editing.name }) : t('teamsPage.createTeamTitle')}
      </h2>
    </div>
    <button onclick={onClose}>×</button>
  </header>
  <div class="body">
    <label
      ><span>{t('teamsPage.name')}</span><input
        bind:value={name}
        placeholder={t('teamsPage.namePlaceholder')}
      /></label
    >
    <label
      ><span>{t('teamsPage.descriptionLabel')}</span><textarea
        bind:value={description}
        rows="4"
        placeholder={t('teamsPage.descriptionPlaceholder')}></textarea></label
    >
    <label
      ><span>{t('teamsPage.parallelTasksLabel')}</span><input
        bind:value={concurrency}
        type="number"
        min="1"
        max="32"
      /><small>{t('teamsPage.parallelTasksHelp')}</small></label
    >
    <fieldset>
      <legend>{t('teamsPage.projectsAccess')}</legend>
      <p>
        {t('teamsPage.projectsAccessDescription')}
      </p>
      <div class="repo-list mb-3">
        <label>
          <input
            type="radio"
            name="repository-scope"
            checked={repositoryIds.length === 0}
            onchange={() => (repositoryIds = [])}
          />
          <span
            ><strong>{t('teamsPage.allImportedRepos')}</strong><small
              >{t('teamsPage.allImportedReposHelp')}</small
            ></span
          >
        </label>
        <label>
          <input
            type="radio"
            name="repository-scope"
            checked={repositoryIds.length > 0}
            onchange={() =>
              (repositoryIds = repositories
                .filter((repository) => repository.enabled)
                .map((repository) => repository.id))}
          />
          <span
            ><strong>{t('teamsPage.onlySelectedRepos')}</strong><small
              >{t('teamsPage.onlySelectedReposHelp')}</small
            ></span
          >
        </label>
      </div>
      {#if repositoryIds.length > 0}<div class="repo-list">
          {#each repositories.filter((repo) => repo.enabled) as repository (repository.id)}<label
              ><input
                type="checkbox"
                checked={repositoryIds.includes(repository.id)}
                onchange={() => toggleRepository(repository.id)}
              /><span
                ><strong>{repository.owner}/{repository.name}</strong><small
                  >{t('teamsPage.repoBranchStatus', {
                    branch: repository.default_branch,
                    status: repository.enabled ? t('teamsPage.enabled') : t('teamsPage.disabled')
                  })}</small
                ></span
              ></label
            >{/each}
        </div>{/if}
    </fieldset>
    <p>
      {t('teamsPage.postSaveNote')}
    </p>
  </div>
  <footer>
    <button class="cancel" onclick={onClose}>{t('teamsPage.cancel')}</button>
    <div class="save-group">
      <span>{editing ? t('teamsPage.updateTeamSettings') : t('teamsPage.createTeamTitle')}</span
      ><button class="primary accent-action" disabled={busy || !name.trim()} onclick={onSave}
        >{busy
          ? t('teamsPage.saving')
          : editing
            ? t('teamsPage.saveChanges')
            : t('teamsPage.createTeam')}</button
      >
    </div>
  </footer>
</aside>

<style>
  .primary {
    border-radius: 0.55rem;
    background: var(--color-brand);
    padding: 0.65rem 0.9rem;
    color: var(--color-on-brand);
    font-size: 0.8rem;
    font-weight: 700;
  }
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 40;
    width: 100%;
    background: rgb(0 0 0/0.35);
    backdrop-filter: blur(2px);
  }
  .drawer {
    position: fixed;
    top: 50%;
    left: 50%;
    z-index: 50;
    display: grid;
    width: min(620px, calc(100% - 2rem));
    max-height: min(780px, calc(100dvh - 2rem));
    grid-template-rows: auto 1fr auto;
    overflow: hidden;
    transform: translate(-50%, -50%);
    border: 1px solid var(--color-line);
    border-radius: 1rem;
    background: var(--color-bg);
    box-shadow: 0 24px 80px rgb(0 0 0/0.3);
  }
  .drawer > header,
  .drawer > footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid var(--color-line);
    padding: 1.2rem;
  }
  .drawer > footer {
    justify-content: space-between;
    gap: 1rem;
    border-top: 1px solid var(--color-line);
    border-bottom: 0;
  }
  .drawer > footer .cancel {
    color: var(--color-muted);
    font-size: 0.8rem;
    padding: 0.65rem 0.2rem;
  }
  .save-group {
    display: flex;
    align-items: center;
    gap: 0.8rem;
  }
  .save-group > span {
    color: var(--color-muted);
    font-size: 0.68rem;
  }
  @media (max-width: 520px) {
    .save-group > span {
      display: none;
    }
  }
  .drawer header span,
  legend,
  .body > label > span {
    color: var(--color-muted);
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.07em;
    text-transform: uppercase;
  }
  .drawer h2 {
    margin-top: 0.3rem;
    font-size: 1.2rem;
    font-weight: 750;
  }
  .drawer header button {
    font-size: 1.6rem;
  }
  .body {
    display: grid;
    align-content: start;
    gap: 1.2rem;
    min-height: 0;
    overflow-y: auto;
    overscroll-behavior: contain;
    padding: 1.2rem;
  }
  .body > label {
    display: grid;
    gap: 0.4rem;
  }
  .body input,
  .body textarea {
    border: 1px solid var(--color-line);
    border-radius: 0.6rem;
    background: var(--color-panel);
    padding: 0.7rem;
    color: var(--color-text);
  }
  fieldset {
    display: grid;
    gap: 0.7rem;
    border: 1px solid var(--color-line);
    border-radius: 0.75rem;
    padding: 0.9rem;
  }
  .body small,
  fieldset > p {
    color: var(--color-muted);
    font-size: 0.7rem;
  }
  .repo-list {
    display: grid;
    gap: 0.4rem;
    margin-top: 0.7rem;
  }
  .repo-list label {
    display: flex;
    align-items: center;
    gap: 0.7rem;
    border: 1px solid var(--color-line);
    border-radius: 0.6rem;
    padding: 0.65rem;
  }
  .repo-list label span {
    display: grid;
    gap: 0.15rem;
    font-size: 0.78rem;
  }
  .repo-list input {
    width: 1rem;
    height: 1rem;
    padding: 0;
  }
  @media (max-width: 640px) {
    .drawer {
      width: calc(100% - 1rem);
      max-height: calc(100dvh - 1rem);
    }
  }
</style>
