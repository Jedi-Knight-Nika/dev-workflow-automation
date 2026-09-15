import { expect, test, type Page, type Route } from '@playwright/test';

const first = '10000000-0000-4000-8000-000000000001';
const second = '10000000-0000-4000-8000-000000000002';

function task(id: string, status = 'ACTIVE') {
  return {
    id,
    title: id === first ? 'First task' : 'Second task',
    description: 'Task requirement',
    status,
    stage: 'DEVELOPING',
    wait_reason: 'NONE',
    priority: 3,
    requirement_version: 1,
    lifecycle_version: 1,
    manual_takeover: false,
    archived_at: null,
    created_at: '2026-09-15T00:00:00Z',
    updated_at: '2026-09-15T00:00:00Z',
    source: null,
    labels: []
  };
}

function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

async function mockTaskApi(page: Page, handle: (route: Route, path: string) => Promise<boolean>) {
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (await handle(route, path)) return;
    if (path.endsWith('/events/stream')) return route.abort();
    if (path === `/api/tasks/${first}`) return route.fulfill({ json: task(first) });
    if (path === `/api/tasks/${second}`) return route.fulfill({ json: task(second) });
    if (path.endsWith('/messages'))
      return route.fulfill({ json: { items: [], next_before_id: null } });
    if (path.endsWith('/coordinator'))
      return route.fulfill({ json: { mode: 'off', runs: [], actions: [], human_request: null } });
    if (path.endsWith('/metrics'))
      return route.fulfill({
        json: {
          attempts: 0,
          input_tokens: 0,
          output_tokens: 0,
          missing_usage_attempts: 0,
          duration_ms: 0,
          estimated_cost_usd: 0,
          roles: []
        }
      });
    if (path.endsWith('/session') || path.endsWith('/token-efficiency'))
      return route.fulfill({ json: null });
    return route.fulfill({ json: [] });
  });
}

test('navigation clears old controls and ignores a late Coordinator mode', async ({ page }) => {
  const destination = deferred(),
    oldCoordination = deferred();
  let oldRequest = false,
    requestedDestination = false;
  const posted: string[] = [];
  await mockTaskApi(page, async (route, path) => {
    if (path === `/api/tasks/${second}`) {
      requestedDestination = true;
      await destination.promise;
      await route.fulfill({ json: task(second) });
    } else if (path === `/api/tasks/${first}/coordinator`) {
      oldRequest = true;
      await oldCoordination.promise;
      await route.fulfill({ json: { mode: 'active', runs: [], actions: [], human_request: null } });
    } else if (path.endsWith('/messages') && route.request().method() === 'POST') {
      posted.push(path);
      await route.fulfill({ json: { id: 1 } });
    } else return false;
    return true;
  });
  await page.goto(`/tasks/${first}`);
  await page.getByLabel('Note or explicit command').fill('Old task draft');
  await expect.poll(() => oldRequest).toBe(true);
  // Exercise SvelteKit's client navigation, which reuses the task page component.
  await page.evaluate((id) => {
    const link = document.createElement('a');
    link.href = `/tasks/${id}`;
    link.textContent = 'Navigate to second task';
    document.body.append(link);
  }, second);
  await page.getByRole('link', { name: 'Navigate to second task' }).click();
  await expect.poll(() => requestedDestination).toBe(true);
  await expect(page.getByRole('region', { name: 'Task controls' })).not.toBeVisible();
  destination.resolve();
  await expect(page.getByRole('heading', { name: 'Second task', exact: true })).toBeVisible();
  const draft = page.getByLabel('Note or explicit command');
  await expect(draft).toHaveValue('');
  const response = page.waitForResponse(
    (r) => new URL(r.url()).pathname === `/api/tasks/${first}/coordinator`
  );
  oldCoordination.resolve();
  await response;
  await page.evaluate(() => new Promise<void>((done) => requestAnimationFrame(() => done())));
  await draft.fill('Message for the second task');
  await page.getByRole('button', { name: 'Save note', exact: true }).click();
  await expect.poll(() => posted).toEqual([`/api/tasks/${second}/messages`]);
});

test('an old polling response cannot overwrite a completed pause', async ({ page }) => {
  await page.clock.install();
  const stale = deferred();
  let taskReads = 0,
    paused = false,
    pending = false;
  await mockTaskApi(page, async (route, path) => {
    if (path === `/api/tasks/${first}`) {
      taskReads++;
      const result = task(first, paused ? 'PAUSED' : 'ACTIVE');
      if (taskReads === 2) {
        pending = true;
        await stale.promise;
      }
      await route.fulfill({ json: result });
    } else if (path.endsWith('/pause')) {
      paused = true;
      await route.fulfill({ json: task(first, 'PAUSED') });
    } else return false;
    return true;
  });
  await page.goto(`/tasks/${first}`);
  await expect(page.getByRole('button', { name: 'Pause work', exact: true })).toBeVisible();
  await page.clock.fastForward(10_500);
  await expect.poll(() => pending).toBe(true);
  await page.getByRole('button', { name: 'Pause work', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Resume work', exact: true })).toBeVisible();
  const response = page.waitForResponse((r) => new URL(r.url()).pathname === `/api/tasks/${first}`);
  stale.resolve();
  await response;
  await page.clock.runFor(50);
  await expect(page.getByRole('button', { name: 'Resume work', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Pause work', exact: true })).not.toBeVisible();
});

test('a message burst keeps the omitted history reachable', async ({ page }) => {
  let populated = false;
  const message = (id: number) => ({
    id,
    task_id: first,
    job_id: null,
    reply_to_id: null,
    author_type: 'USER',
    author_name: 'Operator',
    author_role: null,
    kind: 'COMMENT',
    body: id === 1 ? 'Earliest retained message' : `Message ${id}`,
    context: {},
    created_at: '2026-09-15T00:00:00Z'
  });
  await mockTaskApi(page, async (route, path) => {
    if (!path.endsWith('/messages')) return false;
    if (route.request().method() === 'POST') {
      populated = true;
      await route.fulfill({ json: message(51) });
    } else {
      const earlier = new URL(route.request().url()).searchParams.has('before_id');
      await route.fulfill({
        json: {
          items: !populated
            ? []
            : earlier
              ? [message(1)]
              : Array.from({ length: 50 }, (_, index) => message(index + 2)),
          next_before_id: populated && !earlier ? 2 : null
        }
      });
    }
    return true;
  });
  await page.goto(`/tasks/${first}`);
  await page.getByLabel('Note or explicit command').fill('New message');
  await page.getByRole('button', { name: 'Save note', exact: true }).click();
  await page.getByRole('button', { name: 'Earlier notes', exact: true }).click();
  await expect(page.getByText('Earliest retained message', { exact: true })).toBeVisible();
});
