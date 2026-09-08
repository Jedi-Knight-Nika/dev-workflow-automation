import { expect, test } from '@playwright/test';

test('Team policy persists any-human and natural-language approval settings', async ({ page }) => {
  const teamId = '10000000-0000-4000-8000-000000000001';
  let policy = {
    version: 1,
    enrollment_enabled: true,
    auto_merge: false,
    repository_ids: ['10000000-0000-4000-8000-000000000002'],
    authorized_reviewer_ids: [],
    required_checks: ['Backend', 'Frontend', 'Quality gate'],
    task_budget_usd: '2',
    team_budget_usd: '2',
    reviewer_scope: 'allowlist',
    require_formal_approval: true
  };
  let writes = 0;
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/events/stream')) return route.abort();
    if (path.endsWith('/automation')) {
      if (route.request().method() === 'PUT') {
        policy = { ...route.request().postDataJSON(), version: policy.version + 1 };
        writes++;
        return route.fulfill({ json: { version: policy.version } });
      }
      return route.fulfill({ json: policy });
    }
    if (path.endsWith('/activity'))
      return route.fulfill({
        json: {
          team_id: teamId,
          team_name: 'Review team',
          enabled: true,
          tasks: [],
          milestones: []
        }
      });
    if (path.endsWith('/statistics'))
      return route.fulfill({ json: { cloud_runs: [], local_runs: [], phases: [] } });
    return route.fulfill({ json: [] });
  });
  await page.goto('/teams/' + teamId);
  await page.getByLabel('Who can approve on GitHub?').selectOption('any_human');
  await page.getByLabel('Require formal GitHub review approval').uncheck();
  await page.getByLabel('Auto-merge after approval of the current commit and green CI').check();
  await page.getByRole('button', { name: 'Save policy' }).click();
  await expect(page.getByRole('status')).toContainText('Policy saved');
  expect(policy).toMatchObject({
    reviewer_scope: 'any_human',
    require_formal_approval: false,
    auto_merge: true,
    authorized_reviewer_ids: [],
    required_checks: ['Backend', 'Frontend', 'Quality gate'],
    task_budget_usd: '2',
    team_budget_usd: '2'
  });
  await page.reload();
  await expect(page.getByLabel('Who can approve on GitHub?')).toHaveValue('any_human');
  await expect(page.getByLabel('Require formal GitHub review approval')).not.toBeChecked();
  expect(writes).toBe(1);
});
