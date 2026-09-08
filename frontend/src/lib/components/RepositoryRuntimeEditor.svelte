<script lang="ts">
  import { api } from '$lib/api';
  let { repositoryId }: { repositoryId: string } = $props();
  interface Runtime {
    developer_image_ref: string;
    validator_image_ref: string;
    validation_commands: string[][];
    image_digest: string | null;
    last_verified_at: string | null;
  }
  let runtime = $state<Runtime | null>(null),
    commands = $state('[]'),
    error = $state(''),
    notice = $state(''),
    busy = $state(false);
  async function load() {
    try {
      runtime = await api<Runtime>(`/repositories/${repositoryId}/runtime`);
      commands = JSON.stringify(runtime.validation_commands, null, 2);
    } catch {
      error = 'Runtime configuration unavailable';
    }
  }
  async function save() {
    if (!runtime) return;
    busy = true;
    error = '';
    try {
      const argv: unknown = JSON.parse(commands);
      if (!Array.isArray(argv)) throw new Error('Use JSON arrays of arguments');
      runtime = await api<Runtime>(`/repositories/${repositoryId}/runtime`, {
        method: 'PUT',
        body: JSON.stringify({ ...runtime, validation_commands: argv })
      });
      notice = 'Runtime saved. Build these images on the worker host before starting work.';
    } catch (cause) {
      error = String(cause);
    } finally {
      busy = false;
    }
  }
</script>

<details
  ontoggle={(event) => {
    if (event.currentTarget.open && !runtime) void load();
  }}
>
  <summary>Developer & validator runtime</summary>{#if error}<p role="alert">
      {error}
    </p>{/if}{#if notice}<p role="status">{notice}</p>{/if}{#if runtime}<form
      onsubmit={(event) => {
        event.preventDefault();
        void save();
      }}
    >
      <label>Developer image<input bind:value={runtime.developer_image_ref} required /></label
      ><label>Validator image<input bind:value={runtime.validator_image_ref} required /></label
      ><label
        >Validation commands · JSON argument arrays<textarea
          bind:value={commands}
          rows="5"
          spellcheck="false"
        ></textarea></label
      >
      <p>
        Use prebuilt images with repository tooling. Validators run without network access. Pin
        production images by digest.
      </p>
      <p>
        Verified {runtime.last_verified_at
          ? new Date(runtime.last_verified_at).toLocaleString()
          : 'Not yet'} · {runtime.image_digest ?? 'No recorded digest'}
      </p>
      <button disabled={busy}>Save runtime</button>
    </form>{/if}
</details>

<style>
  summary {
    cursor: pointer;
  }
  form {
    display: grid;
    gap: 0.7rem;
    margin-top: 1rem;
  }
  label {
    display: grid;
    gap: 0.3rem;
    font-size: 0.8rem;
  }
  input,
  textarea,
  button {
    border: 1px solid #64748b55;
    border-radius: 0.4rem;
    padding: 0.5rem;
    background: transparent;
  }
  p {
    font-size: 0.75rem;
    opacity: 0.8;
    overflow-wrap: anywhere;
  }
</style>
