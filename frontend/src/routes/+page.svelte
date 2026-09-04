<script lang="ts">
  import { onMount } from 'svelte';
  import { env } from '$env/dynamic/public';

  type Task = {
    id: string;
    external_key: string | null;
    title: string;
    description: string;
    priority: number;
    state: string;
    created_at: string;
  };

  const API = env.PUBLIC_API_URL || 'http://localhost:8000';
  let tasks: Task[] = [];
  let title = '';
  let description = '';
  let loading = true;
  let error = '';

  async function loadTasks() {
    try {
      const response = await fetch(`${API}/api/v1/tasks`);
      if (!response.ok) throw new Error(`API returned ${response.status}`);
      tasks = await response.json();
      error = '';
    } catch (cause) {
      error = cause instanceof Error ? cause.message : 'Could not load tasks';
    } finally {
      loading = false;
    }
  }

  async function createTask(event: SubmitEvent) {
    event.preventDefault();
    if (!title.trim()) return;
    const response = await fetch(`${API}/api/v1/tasks`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ title, description, priority: 3, enqueue_planning: true })
    });
    if (!response.ok) {
      error = `Create failed: ${response.status}`;
      return;
    }
    title = '';
    description = '';
    await loadTasks();
  }

  onMount(() => {
    loadTasks();
    const events = new EventSource(`${API}/api/v1/events/stream`);
    events.addEventListener('update', loadTasks);
    events.onerror = () => {
      error = 'Live connection interrupted; retrying…';
    };
    return () => events.close();
  });
</script>

<svelte:head><title>Engineering Worker</title></svelte:head>

<header>
  <div class="brand">
    <span class="mark">AW</span>
    <div><strong>Engineering Worker</strong><small>Control center</small></div>
  </div>
  <div class="status"><i></i> System online</div>
</header>

<main>
  <section class="hero">
    <div>
      <p class="eyebrow">AUTOMATION QUEUE</p>
      <h1>Ship work, not busywork.</h1>
      <p class="sub">
        Plan, execute, review, and monitor engineering tasks from one durable workflow.
      </p>
    </div>
    <form onsubmit={createTask}>
      <label for="task-title">New engineering task</label>
      <input
        id="task-title"
        bind:value={title}
        placeholder="What needs to change?"
        maxlength="500"
      />
      <textarea
        bind:value={description}
        placeholder="Requirements, constraints, acceptance criteria…"
      ></textarea>
      <button type="submit">Queue task <span>→</span></button>
    </form>
  </section>

  <section class="summary">
    <div><b>{tasks.length}</b><span>Total tasks</span></div>
    <div>
      <b
        >{tasks.filter((t) => ['PLANNING', 'IMPLEMENTING', 'INTERNAL_REVIEW'].includes(t.state))
          .length}</b
      ><span>Active</span>
    </div>
    <div><b>{tasks.filter((t) => t.state === 'WAITING_GITHUB').length}</b><span>Waiting</span></div>
    <div>
      <b>{tasks.filter((t) => t.state === 'NEEDS_HUMAN').length}</b><span>Needs attention</span>
    </div>
  </section>

  <section class="queue">
    <div class="section-title">
      <div>
        <p class="eyebrow">CURRENT WORK</p>
        <h2>Task queue</h2>
      </div>
      <button class="refresh" onclick={loadTasks}>Refresh</button>
    </div>
    {#if error}<p class="error">{error}</p>{/if}
    {#if loading}<p class="empty">Loading durable state…</p>
    {:else if tasks.length === 0}<div class="empty">
        <strong>The lane is clear.</strong><span
          >Queue the first task above to validate the worker pipeline.</span
        >
      </div>
    {:else}<div class="tasks">
        {#each tasks as task (task.id)}
          <article>
            <div class="priority">P{task.priority}</div>
            <div class="task-copy">
              <small>{task.external_key || task.id.slice(0, 8)}</small>
              <h3>{task.title}</h3>
              <p>{task.description || 'No additional context provided.'}</p>
            </div>
            <div class:attention={task.state === 'NEEDS_HUMAN'} class="state">
              {task.state.replaceAll('_', ' ')}
            </div>
          </article>
        {/each}
      </div>{/if}
  </section>
</main>

<style>
  :global(*) {
    box-sizing: border-box;
  }
  :global(body) {
    margin: 0;
    background: #0a0d0c;
    color: #eef5ef;
    font-family:
      Inter,
      ui-sans-serif,
      system-ui,
      -apple-system,
      sans-serif;
  }
  :global(button),
  :global(input),
  :global(textarea) {
    font: inherit;
  }
  header {
    height: 72px;
    padding: 0 max(24px, calc((100vw - 1180px) / 2));
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid #202723;
    background: #0d110f;
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .brand div {
    display: flex;
    flex-direction: column;
  }
  .brand small {
    color: #758078;
    font-size: 11px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }
  .mark {
    display: grid;
    place-items: center;
    width: 38px;
    height: 38px;
    border: 1px solid #56f28d;
    color: #56f28d;
    font-size: 12px;
    font-weight: 800;
  }
  .status {
    font-size: 12px;
    color: #9ca69f;
    display: flex;
    gap: 8px;
    align-items: center;
  }
  .status i {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #56f28d;
    box-shadow: 0 0 12px #56f28d;
  }
  main {
    max-width: 1180px;
    margin: auto;
    padding: 64px 24px;
  }
  .hero {
    display: grid;
    grid-template-columns: 1fr 460px;
    gap: 80px;
    align-items: start;
  }
  .eyebrow {
    font:
      700 11px ui-monospace,
      monospace;
    letter-spacing: 0.18em;
    color: #56f28d;
    margin: 0 0 14px;
  }
  h1 {
    font-size: 58px;
    line-height: 1.02;
    letter-spacing: -0.045em;
    margin: 0;
    max-width: 600px;
  }
  .sub {
    color: #8e9991;
    max-width: 550px;
    font-size: 17px;
    line-height: 1.65;
  }
  form {
    background: #111613;
    border: 1px solid #28312b;
    padding: 24px;
    box-shadow: 12px 12px 0 #070908;
  }
  label {
    font-size: 12px;
    font-weight: 700;
    display: block;
    margin-bottom: 12px;
  }
  input,
  textarea {
    width: 100%;
    background: #090c0a;
    border: 1px solid #303a33;
    color: #fff;
    padding: 13px;
    outline: none;
    margin-bottom: 10px;
  }
  input:focus,
  textarea:focus {
    border-color: #56f28d;
  }
  textarea {
    height: 90px;
    resize: vertical;
  }
  form button {
    width: 100%;
    border: 0;
    background: #56f28d;
    color: #07100a;
    padding: 13px;
    font-weight: 800;
    cursor: pointer;
    display: flex;
    justify-content: space-between;
  }
  .summary {
    margin: 64px 0;
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    border: 1px solid #242c27;
  }
  .summary div {
    padding: 24px;
    border-right: 1px solid #242c27;
    display: flex;
    flex-direction: column;
  }
  .summary div:last-child {
    border: 0;
  }
  .summary b {
    font:
      500 32px ui-monospace,
      monospace;
  }
  .summary span {
    font-size: 12px;
    color: #758078;
    margin-top: 5px;
  }
  .section-title {
    display: flex;
    justify-content: space-between;
    align-items: end;
  }
  .section-title h2 {
    font-size: 27px;
    margin: 0;
  }
  .refresh {
    background: transparent;
    color: #97a198;
    border: 1px solid #303a33;
    padding: 8px 13px;
    cursor: pointer;
  }
  .tasks {
    margin-top: 20px;
    border-top: 1px solid #28312b;
  }
  .tasks article {
    display: grid;
    grid-template-columns: 55px 1fr auto;
    gap: 20px;
    align-items: center;
    padding: 20px 4px;
    border-bottom: 1px solid #202723;
  }
  .priority {
    font:
      700 12px ui-monospace,
      monospace;
    color: #56f28d;
  }
  .task-copy small {
    color: #657068;
    font:
      11px ui-monospace,
      monospace;
  }
  .task-copy h3 {
    margin: 5px 0;
    font-size: 16px;
  }
  .task-copy p {
    margin: 0;
    color: #778178;
    font-size: 13px;
  }
  .state {
    font:
      700 10px ui-monospace,
      monospace;
    letter-spacing: 0.08em;
    color: #a4afa7;
    border: 1px solid #303a33;
    padding: 7px 9px;
  }
  .state.attention {
    color: #ffbd66;
    border-color: #715125;
  }
  .empty {
    margin-top: 20px;
    min-height: 150px;
    border: 1px dashed #303a33;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    color: #6f7971;
    gap: 7px;
  }
  .empty strong {
    color: #aeb8b0;
  }
  .error {
    color: #ff897d;
    background: #291511;
    padding: 10px;
  }
  @media (max-width: 800px) {
    main {
      padding-top: 38px;
    }
    .hero {
      grid-template-columns: 1fr;
      gap: 30px;
    }
    h1 {
      font-size: 42px;
    }
    .summary {
      grid-template-columns: 1fr 1fr;
    }
    .summary div:nth-child(2) {
      border-right: 0;
    }
    .summary div:nth-child(-n + 2) {
      border-bottom: 1px solid #242c27;
    }
    .tasks article {
      grid-template-columns: 40px 1fr;
    }
    .state {
      grid-column: 2;
      justify-self: start;
    }
  }
</style>
