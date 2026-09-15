import { expect, test } from '@playwright/test';

for (const provider of ['linear', 'trello'] as const) {
  test(`${provider} destination selectors preserve choices and saved configuration`, async ({
    page
  }) => {
    let saved: Record<string, unknown> | undefined;
    const integration = {
      id: provider,
      provider_name: provider,
      provider_type: 'task_management',
      status: 'CONNECTED',
      display_status: 'READY',
      has_credentials: true,
      configuration: {},
      last_error: '',
      sync_status: 'IDLE',
      last_synced_at: null
    };
    const destinations = Array.from({ length: 6 }, (_, index) => ({
      id: `destination-${index}`,
      name: `Destination ${index}`,
      closed: false,
      type: 'started',
      team_id: 'team',
      team_key: 'TEAM',
      team_name: 'Team'
    }));
    await page.route('**/api/**', async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith('/events/stream')) return route.abort();
      if (path === `/api/integrations/${provider}` && route.request().method() === 'PUT') {
        saved = route.request().postDataJSON();
        return route.fulfill({ json: integration });
      }
      if (path === `/api/integrations/${provider}/test`)
        return route.fulfill({ json: integration });
      if (path === '/api/integrations') return route.fulfill({ json: [integration] });
      if (path.endsWith('/linear/workflow-states') || path.endsWith('/trello/boards/board/lists'))
        return route.fulfill({ json: destinations });
      if (path.endsWith('/linear/members'))
        return route.fulfill({ json: [{ id: 'member', name: 'Member', email: '', active: true }] });
      if (path.endsWith('/trello/boards'))
        return route.fulfill({
          json: [{ id: 'board', name: 'Board', url: 'https://trello.com/b/test' }]
        });
      if (path.endsWith('/github/app/account'))
        return route.fulfill({ status: 409, json: { detail: 'Not configured' } });
      return route.fulfill({ json: [] });
    });
    await page.goto('/integrations');
    const name = provider === 'linear' ? 'Linear' : 'Trello';
    await page
      .locator('article')
      .filter({ has: page.getByRole('heading', { name, exact: true }) })
      .getByRole('button', { name: 'Update', exact: true })
      .click();
    const dialog = page.getByRole('dialog');
    if (provider === 'linear') {
      await dialog.getByRole('button', { name: 'Discover states', exact: true }).click();
      await dialog.locator('#linear-assignee').selectOption('member');
    } else {
      await dialog.getByRole('button', { name: 'Discover boards', exact: true }).click();
      await dialog.locator('#trello-board').selectOption('board');
    }
    const fields = [
      ['todo', 'todo'],
      ['progress', 'in_progress'],
      ['in-review', 'in_review'],
      ['blocked', 'blocked'],
      ['ready', 'ready_for_testing'],
      ['done', 'done']
    ];
    const expected: Record<string, string | null> = {};
    for (const [index, [field, key]] of fields.entries()) {
      const actualField = provider === 'trello' && field === 'in-review' ? 'review' : field;
      const suffix = provider === 'linear' ? 'state' : 'list';
      const select = dialog.locator(`#${provider}-${actualField}-${suffix}`);
      const value = index === 3 ? '' : `destination-${index}`;
      await expect(select.locator('option')).toHaveCount(7);
      await expect(select.locator('option').nth(1)).toHaveText(
        provider === 'linear' ? 'TEAM — Destination 0' : 'Destination 0'
      );
      await select.selectOption(value);
      await expect(select).toHaveValue(value);
      expected[`${key}_${suffix}_id`] = value || null;
    }
    await dialog.getByRole('button', { name: 'Save and verify connection', exact: true }).click();
    await expect(dialog).not.toBeVisible();
    expect(saved).toMatchObject({ credential: null, configuration: expected });
  });
}
