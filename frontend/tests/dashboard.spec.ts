import { expect, test } from '@playwright/test';

test('creating a task is free by default and preserves zero story points', async ({ page }) => {
  const tasks: Record<string, unknown>[] = [];
  let created: Record<string, unknown> | null = null;
  await page.route('**/api/**', async (route) => {
    const request = route.request(),
      path = new URL(request.url()).pathname;
    if (path.endsWith('/events/stream')) return route.abort();
    if (path === '/api/tasks' && request.method() === 'POST') {
      created = request.postDataJSON();
      const task = {
        ...created,
        id: 'task-1',
        status: 'NEW',
        stage: 'INTAKE',
        wait_reason: 'NONE',
        source: null
      };
      tasks.push(task);
      return route.fulfill({ status: 201, json: task });
    }
    return route.fulfill({ json: path === '/api/tasks' ? tasks : [] });
  });
  await page.goto('/tasks');
  await page.getByRole('button', { name: 'Create task', exact: true }).click();
  await page.getByLabel('Title', { exact: true }).fill('Add regression coverage');
  await page.getByLabel('Requirement', { exact: true }).fill('Test the current API.');
  await page.getByLabel('Story points').fill('0');
  await expect(page.getByLabel('Start work after creation')).not.toBeChecked();
  await page.locator('form').getByRole('button', { name: 'Create task' }).click();
  await expect(page.getByText('Add regression coverage')).toBeVisible();
  expect(created).toMatchObject({ estimate: 0, start_work: false });
});
