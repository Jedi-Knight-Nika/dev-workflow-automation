import { expect, test } from '@playwright/test';

const ids = [
  '10000000-0000-4000-8000-000000000001',
  '10000000-0000-4000-8000-000000000002',
  '10000000-0000-4000-8000-000000000003'
];

test('dashboard shows concurrent workers and updates elapsed time without refetching', async ({
  page
}) => {
  await page.clock.install({ time: new Date('2026-09-07T12:00:00Z') });
  const workers = ids.slice(0, 2).map((id, i) => ({
    job_id: id,
    task_id: id,
    task_label: `TASK-${i}`,
    team_id: id,
    team_name: `Team ${i}`,
    agent_name: `Worker ${i}`,
    role: 'EXECUTOR',
    provider: 'openai',
    model: 'test-model',
    started_at: '2026-09-07T11:59:00Z',
    input_tokens: 100,
    output_tokens: 20
  }));
  let requests = 0;
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/dashboard/summary')) {
      requests++;
      await route.fulfill({
        json: {
          period: 'today',
          generated_at: '2026-09-07T12:00:00Z',
          health_score: 100,
          system_status: 'HEALTHY',
          active_tasks: 2,
          queued_jobs: 0,
          ready_to_merge: 0,
          needs_human: 0,
          completed: 0,
          failed: 0,
          tokens: 240,
          estimated_cost: null,
          autonomy_rate: null,
          active_worker: workers[0],
          active_workers: workers,
          running_jobs: 2,
          queue: [],
          teams: [],
          recent_events: [],
          usage_by_role: [],
          throughput: [],
          health: []
        }
      });
    } else if (path.endsWith('/dashboard/telemetry')) {
      await route.fulfill({ status: 503, json: { detail: 'Temporarily unavailable' } });
    } else if (path.endsWith('/events/stream')) {
      await route.abort();
    } else await route.fulfill({ json: [] });
  });
  await page.goto('/');
  await expect(page.getByText('ACTIVE WORKER · 2 RUNNING')).toBeVisible();
  await expect(
    page.getByRole('region', { name: 'Running workers' }).getByText('Worker 1')
  ).toBeVisible();
  await expect(page.getByText('Telemetry temporarily unavailable')).toBeVisible();
  const initial = requests;
  const elapsed = page.locator('.worker footer div').first().locator('b');
  const previousElapsed = await elapsed.textContent();
  await page.clock.runFor(2000);
  await expect(elapsed).not.toHaveText(previousElapsed || '');
  expect(requests).toBe(initial);
  await page.clock.runFor(15000);
  await expect.poll(() => requests).toBeGreaterThan(initial);
});

test('only the active node glows; dragging autosaves layout without publishing wiring', async ({
  page
}) => {
  const nodes = ids.map((id, i) => ({
    id,
    role: i === 0 ? 'ORCHESTRATOR' : 'EXECUTOR',
    label: ['Controller', 'Working executor', 'Idle executor'][i],
    position_x: i * 350,
    position_y: 150,
    enabled: true,
    activation_policy: 'any',
    batch_window_seconds: 0,
    integration_ids: [],
    repository_ids: [],
    provider: 'openai',
    model: 'test-model',
    model_validation_status: 'AVAILABLE',
    agent_id: null,
    node_type: 'AGENT',
    system_node_type: null
  }));
  let layoutWrites = 0;
  let graphWrites = 0;
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith('/workflow/activity')) {
      await route.fulfill({
        json: ids.map((node_id, i) => ({
          node_id,
          active_jobs: i === 1 ? 1 : 0,
          queued_jobs: 0,
          waiting_jobs: 0,
          current_job_action: i === 1 ? 'IMPLEMENT_PLAN' : null,
          task_id: null
        }))
      });
    } else if (path.endsWith('/workflow/layout')) {
      layoutWrites++;
      const body = request.postDataJSON();
      expect(Object.keys(body).sort()).toEqual(['positions', 'version']);
      expect(body.version).toBe(4);
      for (const position of body.positions) {
        const node = nodes.find((item) => item.id === position.node_id);
        if (node) {
          node.position_x = position.x;
          node.position_y = position.y;
        }
      }
      await route.fulfill({ status: 204 });
    } else if (path.endsWith('/workflow')) {
      if (request.method() === 'PUT') graphWrites++;
      await route.fulfill({ json: { version: 4, nodes, edges: [] } });
    } else if (path.endsWith('/events/stream')) {
      await route.fulfill({ status: 200, contentType: 'text/event-stream', body: ': ready\n\n' });
    } else {
      await route.fulfill({ json: [] });
    }
  });
  await page.goto('/agents');
  const working = page.locator(`[data-id="${ids[1]}"]`);
  const idle = page.locator(`[data-id="${ids[2]}"]`);
  await expect(working).toHaveClass(/running/);
  await expect(idle).not.toHaveClass(/running/);
  await expect(working.getByText('IMPLEMENT PLAN')).toBeVisible();
  const beforeX = nodes[1].position_x;
  const box = await working.boundingBox();
  if (!box) throw new Error('Working node missing');
  await page.mouse.move(box.x + 50, box.y + 25);
  await page.mouse.down();
  await page.mouse.move(box.x + 110, box.y + 75, { steps: 10 });
  await page.mouse.up();
  await expect.poll(() => layoutWrites).toBe(1);
  expect(graphWrites).toBe(0);
  expect(nodes[1].position_x).not.toBe(beforeX);
  await expect(page.getByRole('button', { name: 'Saved', exact: true })).toBeDisabled();
  await page.reload();
  await expect(working).toHaveClass(/running/);
  expect(graphWrites).toBe(0);
});

test('task detail keeps conversation visible, links short, and diagnostics expandable', async ({
  page
}) => {
  const id = ids[0];
  const sourceUrl = 'https://trello.com/c/abc/' + 'long-ticket-slug-'.repeat(20);
  const task = {
    id,
    title: 'A readable task',
    description: `Keep this acceptance criterion.\nTrello: ${sourceUrl}\nRead https://example.com/specification`,
    state: 'NEEDS_HUMAN',
    priority: 3,
    team_name: 'Test team',
    external_key: 'TRELLO-abc',
    source: { provider: 'trello', identifier: 'TRELLO-abc', url: sourceUrl },
    manual_takeover: false
  };
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === `/api/v1/tasks/${id}`) await route.fulfill({ json: task });
    else if (path.endsWith('/messages'))
      await route.fulfill({ json: { items: [], next_before_id: null } });
    else if (path.endsWith('/memory')) await route.fulfill({ json: null });
    else if (path.endsWith('/events/stream'))
      await route.fulfill({ status: 200, contentType: 'text/event-stream', body: ': ready\n\n' });
    else await route.fulfill({ json: [] });
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/tasks/${id}`);
  await expect(page.getByRole('heading', { name: 'A readable task' })).toBeVisible();
  const link = page.getByRole('link', { name: /trello · TRELLO-abc/ });
  await expect(link).toHaveAttribute('href', sourceUrl);
  await expect(page.getByText('Task conversation', { exact: true })).toBeVisible();
  await expect(page.getByRole('textbox').first()).toBeVisible();
  await expect(page.getByRole('link', { name: 'example.com', exact: true })).toHaveAttribute(
    'href',
    'https://example.com/specification'
  );
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true
  );
  const history = page
    .locator('details')
    .filter({ has: page.locator('summary', { hasText: 'Execution history' }) });
  await expect(history).not.toHaveAttribute('open');
  await history.locator('summary').click();
  await expect(history).toHaveAttribute('open');
});
