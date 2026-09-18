import { expect, test } from '@playwright/test';

for (const failure of ['none', 'refresh'] as const) {
  test(`sending preserves a later draft and does not retry a saved message (${failure})`, async ({
    page
  }) => {
    const id = '10000000-0000-4000-8000-000000000001';
    let posts = 0;
    let release: (() => void) | undefined;
    const pending = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route('**/api/**', async (route) => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      if (path.endsWith('/events/stream')) return route.abort();
      if (path.endsWith('/messages')) {
        if (request.method() === 'POST') {
          posts++;
          await pending;
          return route.fulfill({ json: { id: 1, body: request.postDataJSON().body } });
        }
        return route.fulfill({ json: { items: [], next_before_id: null } });
      }
      if (path === `/api/tasks/${id}`) {
        if (posts && failure === 'refresh')
          return route.fulfill({ status: 503, json: { detail: 'Refresh unavailable' } });
        return route.fulfill({
          json: {
            id,
            title: 'Conversation regression',
            description: 'Keep the requirement',
            priority: 3,
            status: 'NEW',
            stage: 'INTAKE',
            wait_reason: 'NONE',
            requirement_version: 1,
            lifecycle_version: 1,
            manual_takeover: false,
            archived_at: null,
            created_at: '2026-09-14T00:00:00Z',
            updated_at: '2026-09-14T00:00:00Z',
            source: null,
            labels: []
          }
        });
      }
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
    await page.goto(`/tasks/${id}`);
    const draft = page.getByLabel('Note or explicit command');
    await draft.fill('First message');
    await page.getByRole('button', { name: 'Save note', exact: true }).click();
    await expect.poll(() => posts).toBe(1);
    if (failure === 'none') await draft.fill('Second message still being written');
    release?.();
    await expect(page.getByRole('button', { name: 'Save note', exact: true })).toBeVisible();
    await expect(draft).toHaveValue(failure === 'none' ? 'Second message still being written' : '');
    if (failure === 'refresh')
      await expect(page.getByText(/Message saved\. Could not refresh/)).toBeVisible();
    expect(posts).toBe(1);
  });
}
