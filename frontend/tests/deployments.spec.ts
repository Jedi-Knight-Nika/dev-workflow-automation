import { expect, test } from '@playwright/test';

test('deployment history loads on demand, filters the selected repository, and reports partial history', async ({
  page
}) => {
  const requests: string[] = [];
  let writes = 0;
  const repo = {
    id: '10000000-0000-4000-8000-000000000001',
    owner: 'test',
    name: 'app',
    provider: 'github',
    enabled: true,
    archived_at: null
  };
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    if (route.request().method() !== 'GET') writes++;
    if (url.pathname.endsWith('/events/stream')) return route.abort();
    if (url.pathname === '/api/repositories') return route.fulfill({ json: [repo] });
    if (url.pathname === '/api/deployments') {
      requests.push(url.searchParams.get('repository_id') || 'all');
      return route.fulfill({
        json: {
          truncated: true,
          events: [
            {
              id: '1',
              observation_id: '1',
              deployment_id: '10',
              repository_id: repo.id,
              repository: 'test/app',
              environment: 'preview',
              production: false,
              status: 'SUCCESS',
              started_at: '2026-09-15T00:00:00Z',
              occurred_at: '2026-09-15T00:01:00Z'
            }
          ]
        }
      });
    }
    return route.fulfill({ json: [] });
  });
  await page.goto('/repositories');
  await expect(page.getByRole('heading', { name: 'Repositories', exact: true })).toBeVisible();
  expect(requests).toEqual([]);
  await page.getByText('Deployment history', { exact: true }).click();
  await expect(page.getByLabel('Deployment metrics')).toContainText('1 deployments observed');
  await expect(page.getByText('History is incomplete.', { exact: false })).toBeVisible();
  await page.getByRole('combobox', { name: 'Repository', exact: true }).selectOption(repo.id);
  await expect.poll(() => requests).toEqual(['all', repo.id]);
  await page.getByLabel('Production only').check();
  await expect(page.getByLabel('Deployment metrics')).toContainText('0 deployments observed');
  expect(writes).toBe(0);
});
