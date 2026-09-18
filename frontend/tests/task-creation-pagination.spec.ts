import { expect, test } from '@playwright/test';

test('selected team and retry identity are sent in one creation request', async ({ page }) => {
  const teamId = '10000000-0000-4000-8000-000000000001';
  const requests: Record<string, unknown>[] = [];
  const assignments: string[] = [];
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith('/events/stream')) return route.abort();
    if (path === '/api/teams')
      return route.fulfill({ json: [{ id: teamId, name: 'Selected team', enabled: true }] });
    if (path === '/api/tasks' && request.method() === 'POST') {
      requests.push(request.postDataJSON());
      if (requests.length === 1)
        return route.fulfill({ status: 503, json: { detail: 'Retry the same request' } });
      return route.fulfill({ status: 201, json: { ...requests.at(-1), id: 'created' } });
    }
    if (request.method() === 'POST') assignments.push(path);
    return route.fulfill({ json: [] });
  });
  await page.goto('/tasks');
  await page.getByRole('button', { name: 'Create task', exact: true }).click();
  await page.getByLabel('Title', { exact: true }).fill('Atomic task');
  await page.locator('form').getByLabel(/^Team/).selectOption(teamId);
  await page.getByLabel('Start work after creation').check();
  const submit = page.locator('form').getByRole('button', { name: 'Create task' });
  await submit.click();
  await expect(page.getByText('Retry the same request', { exact: false })).toBeVisible();
  await submit.click();
  await expect(page.locator('form')).not.toBeVisible();
  expect(requests).toHaveLength(2);
  expect(requests[0]).toMatchObject({ team_id: teamId, start_work: true });
  expect(requests[0].request_id).toMatch(/^[0-9a-f-]{36}$/);
  expect(requests[1].request_id).toBe(requests[0].request_id);
  expect(assignments).toEqual([]);
});

test('task pages keep their cursor during refresh and reset it when filters change', async ({
  page
}) => {
  const queries: URLSearchParams[] = [];
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith('/events/stream')) return route.abort();
    if (url.pathname === '/api/tasks') {
      queries.push(url.searchParams);
      const second = url.searchParams.has('cursor');
      return route.fulfill({
        headers: second ? {} : { 'x-next-cursor': 'next-page' },
        json: [
          {
            id: second ? 'second' : 'first',
            title: second ? 'Second page task' : 'First page task',
            status: 'NEW',
            stage: 'INTAKE',
            wait_reason: 'NONE',
            priority: 3
          }
        ]
      });
    }
    return route.fulfill({ json: [] });
  });
  await page.goto('/tasks');
  await expect(page.getByText('First page task', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Next', exact: true }).click();
  await expect(page.getByText('Second page task', { exact: true })).toBeVisible();
  expect(queries.at(-1)?.get('cursor')).toBe('next-page');
  const refreshCount = queries.length;
  await expect.poll(() => queries.length, { timeout: 15000 }).toBeGreaterThan(refreshCount);
  expect(queries.at(-1)?.get('cursor')).toBe('next-page');
  await page.getByRole('button', { name: 'Previous', exact: true }).click();
  await expect(page.getByText('First page task', { exact: true })).toBeVisible();
  expect(queries.at(-1)?.has('cursor')).toBe(false);
  await page.getByRole('button', { name: 'Next', exact: true }).click();
  await page.getByLabel('Sort tasks').selectOption('created');
  await expect(page.getByText('First page task', { exact: true })).toBeVisible();
  expect(queries.at(-1)?.get('sort')).toBe('created');
  expect(queries.at(-1)?.has('cursor')).toBe(false);
});
