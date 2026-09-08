import { expect, test } from '@playwright/test';

for (const [failure, action] of [
  ['credentials', 'Verify credentials and load boards'],
  ['network', 'Verify credentials and load boards'],
  ['credentials', 'Save and verify connection'],
  ['network', 'Save and verify connection']
]) {
  test(`Trello ${failure} failure during ${action} stays in dialog and supports correcting credentials`, async ({
    page
  }) => {
    let integration = {
      id: 'trello',
      provider_name: 'trello',
      provider_type: 'task_management',
      status: 'DISCONNECTED',
      display_status: 'NOT_CONFIGURED',
      has_credentials: false,
      configuration: {},
      last_error: '',
      sync_status: 'IDLE',
      last_synced_at: null
    };
    let attempts = 0;
    let boardRequests = 0;
    await page.route('**/api/v1/**', async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith('/events/stream')) return route.abort();
      if (path.endsWith('/integrations/trello/test')) {
        attempts++;
        if (attempts === 1) {
          if (failure === 'network') return route.abort('failed');
          integration = {
            ...integration,
            status: 'ERROR',
            display_status: 'NEEDS_ATTENTION',
            last_error:
              "Client error '401 Unauthorized' for url 'https://api.trello.com/1/members/me/boards'"
          };
        } else
          integration = {
            ...integration,
            status: 'CONNECTED',
            display_status: 'READY',
            last_error: ''
          };
        return route.fulfill({ json: integration });
      }
      if (path.endsWith('/integrations/trello') && route.request().method() === 'PUT') {
        integration = { ...integration, status: 'CONFIGURED', has_credentials: true };
        return route.fulfill({ json: integration });
      }
      if (path.endsWith('/integrations')) return route.fulfill({ json: [integration] });
      if (path.endsWith('/trello/boards')) {
        boardRequests++;
        return route.fulfill({
          json: [{ id: 'board', name: 'My tasks', url: 'https://trello.com/b/test' }]
        });
      }
      if (path.endsWith('/github/app/account'))
        return route.fulfill({ status: 409, json: { detail: 'Not configured' } });
      return route.fulfill({ json: [] });
    });
    await page.goto('/integrations');
    await page
      .locator('article')
      .filter({ has: page.getByRole('heading', { name: 'Trello', exact: true }) })
      .getByRole('button', { name: 'Configure', exact: true })
      .click();
    const dialog = page.getByRole('dialog');
    await dialog.locator('#trello-api-key').fill('test-key');
    await dialog.locator('#trello-token').fill('test-token');
    await dialog.getByRole('button', { name: action }).click();
    await expect(dialog.getByRole('alert')).toContainText(
      failure === 'credentials'
        ? 'Trello rejected the API key or token'
        : 'Cannot reach Engineering Worker'
    );
    await expect(dialog.locator('#trello-api-key')).toHaveValue('test-key');
    await expect(dialog.locator('#trello-token')).toHaveValue('test-token');
    await expect(dialog).not.toContainText('401 Unauthorized');
    await expect(dialog).not.toContainText('TypeError');
    expect(boardRequests).toBe(0);
    await dialog.locator('#trello-token').fill('corrected-token');
    await dialog.getByRole('button', { name: action }).click();
    await expect(dialog.getByRole('status')).toContainText('Connected to Trello');
    await expect(dialog.locator('#trello-board option', { hasText: 'My tasks' })).toHaveCount(1);
    await expect(dialog.locator('#trello-token')).toHaveValue('');
    expect(boardRequests).toBe(1);
  });
}
