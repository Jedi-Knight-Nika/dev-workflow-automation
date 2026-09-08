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
    role: 'DEVELOPER',
    provider: 'openai',
    model: 'test-model',
    started_at: '2026-09-07T11:59:00Z',
    input_tokens: 100,
    output_tokens: 20
  }));
  let requests = 0;
  await page.route('**/api/**', async (route) => {
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

test('fullscreen map keeps the queue and milestones visible without workflow writes', async ({
  page
}) => {
  let writes = 0;
  await page.route('**/api/**', async (route) => {
    const request = route.request(),
      path = new URL(request.url()).pathname;
    if (request.method() !== 'GET') writes++;
    if (path.endsWith('/events/stream')) return route.abort();
    if (path.endsWith('/activity'))
      return route.fulfill({
        json: {
          team_id: ids[0],
          team_name: 'Test team',
          enabled: true,
          tasks: [
            {
              id: ids[1],
              title: 'Implement feature',
              priority: 2,
              status: 'ACTIVE',
              stage: 'DEVELOPING',
              wait_reason: 'NONE',
              requirement_version: 1
            }
          ],
          milestones: [
            {
              id: ids[2],
              task_id: ids[1],
              stage: 'DEVELOPING',
              status: 'ACTIVE',
              actor: 'worker:1',
              started_at: '2026-09-08T10:00:00Z',
              finished_at: null
            }
          ]
        }
      });
    if (path.endsWith('/automation'))
      return route.fulfill({
        json: {
          version: 1,
          enrollment_enabled: false,
          auto_merge: false,
          repository_ids: [],
          authorized_reviewer_ids: [],
          required_checks: [],
          task_budget_usd: '1',
          team_budget_usd: '5',
          require_formal_approval: true
        }
      });
    if (path.endsWith('/statistics'))
      return route.fulfill({ json: { cloud_runs: [], phases: [], local_runs: [] } });
    return route.fulfill({ json: [] });
  });
  await page.goto('/teams/' + ids[0]);
  await page.getByRole('button', { name: 'Fullscreen', exact: true }).click();
  await expect.poll(() => page.evaluate(() => Boolean(document.fullscreenElement))).toBe(true);
  await expect(page.getByRole('complementary', { name: 'Queue and task details' })).toBeVisible();
  await expect(page.getByText('worker:1')).toBeVisible();
  await page.getByRole('button', { name: 'Exit fullscreen (Esc)' }).click();
  await expect.poll(() => page.evaluate(() => Boolean(document.fullscreenElement))).toBe(false);
  expect(writes).toBe(0);
});

test('ticket displays native receipts, exact status actor/time and responsive notes', async ({
  page
}) => {
  const id = ids[0],
    at = '2026-09-08T10:00:00Z';
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/events/stream')) return route.abort();
    if (path === '/api/tasks/' + id)
      return route.fulfill({
        json: {
          id,
          title: 'A readable task',
          description: 'Keep this acceptance criterion.',
          status: 'PAUSED',
          stage: 'DEVELOPING',
          wait_reason: 'NONE',
          priority: 3,
          requirement_version: 1,
          team_name: 'Test team',
          manual_takeover: false
        }
      });
    if (path.endsWith('/messages'))
      return route.fulfill({ json: { items: [], next_before_id: null } });
    if (path.endsWith('/session') || path.endsWith('/metrics'))
      return route.fulfill({ json: null });
    if (path.endsWith('/runs'))
      return route.fulfill({
        json: [
          {
            id: ids[1],
            role_kind: 'DEVELOPER',
            provider: 'openai',
            model: 'unit-model',
            harness: 'codex',
            status: 'COMPLETED',
            cost_usd: '0.012000',
            input_tokens: 100,
            output_tokens: 20,
            cache_read_tokens: 80,
            usage_complete: true,
            artifact: 'IMPLEMENTED\nUpdated the API.',
            started_at: at,
            finished_at: at,
            requirement_version: 1,
            failure_code: null
          }
        ]
      });
    if (path.endsWith('/events'))
      return route.fulfill({
        json: [
          {
            id: 1,
            event_type: 'TASK_LIFECYCLE_CHANGED',
            source: 'system',
            created_at: at,
            payload: {
              actor: 'operator',
              from_status: 'ACTIVE',
              to_status: 'PAUSED',
              from_stage: 'DEVELOPING',
              to_stage: 'DEVELOPING'
            }
          }
        ]
      });
    return route.fulfill({ json: [] });
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/tasks/' + id);
  await expect(page.getByRole('heading', { name: 'A readable task' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Resume work', exact: true })).toBeVisible();
  await expect(page.getByText('Changed by operator')).toBeVisible();
  await expect(page.getByText('$0.012000')).toBeVisible();
  await page.getByText('Result / feedback', { exact: true }).click();
  await expect(page.getByText('Updated the API.', { exact: false })).toBeVisible();
  await expect(page.getByRole('textbox').first()).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true
  );
});
