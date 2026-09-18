import { expect, test, type Page } from '@playwright/test';

async function setupObserver(page: Page) {
  let enabled = true;
  const questions: { conversation_id?: string; message: string }[] = [];
  const events = [
    { type: 'observer.text_delta', text: 'Current facts' },
    { type: 'observer.completed', answer: 'Current facts', sources: [], mode: 'deterministic' }
  ];
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === '/api/observer/configuration')
      return route.fulfill({ json: { enabled, display_name: 'Jarvis', local_ai_enabled: false } });
    if (path === '/api/observer/briefing' || path === '/api/observer/status')
      return route.fulfill({
        json: {
          enabled,
          ai_available: false,
          highest_severity: 'NONE',
          events: [],
          open_attention_count: 0,
          message: 'A source-backed briefing',
          preferences: { focus: 'normal' },
          changes: [],
          suggested_questions: ['What needs attention?']
        }
      });
    if (path === '/api/observer/questions') {
      questions.push(request.postDataJSON());
      return route.fulfill({ json: { conversation_id: 'conversation', request_id: 'answer' } });
    }
    if (path === '/api/observer/questions/answer/events')
      return route.fulfill({
        contentType: 'text/event-stream',
        body: events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join('')
      });
    if (path === '/api/observer/conversations')
      return route.fulfill({
        json: [
          {
            id: 'saved',
            title: 'Saved discussion',
            scope: { page: 'DASHBOARD' },
            updated_at: '2026-09-01T00:00:00Z'
          }
        ]
      });
    if (path === '/api/observer/conversations/saved')
      return route.fulfill({
        json: [{ id: 'saved-answer', role: 'assistant', content: 'Saved facts', sources: [] }]
      });
    if (path.endsWith('/events/stream')) return route.abort();
    return route.fulfill({ json: [] });
  });
  await page.goto('/tasks');
  return {
    questions,
    disable: () => {
      enabled = false;
    }
  };
}

for (const viewport of [
  { width: 1280, height: 900 },
  { width: 390, height: 700 }
]) {
  test(`Observer preserves chat and history after component extraction (${viewport.width}px)`, async ({
    page
  }) => {
    await page.setViewportSize(viewport);
    const { questions, disable } = await setupObserver(page);
    const launcher = page.getByRole('button', { name: 'Open Jarvis assistant', exact: true });
    await launcher.click();
    const panel = page.locator('#observer-panel');
    await expect(panel).toBeVisible();
    const box = await panel.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(viewport.width + 1);
    const question = page.getByLabel('Ask Jarvis', { exact: true });
    await expect(question).toBeFocused();
    await question.fill('Tell me the facts');
    await question.press('Enter');
    await expect(panel.getByText('Current facts', { exact: true })).toBeVisible();
    expect(questions).toHaveLength(1);
    await page.getByRole('button', { name: 'Close Jarvis', exact: true }).click();
    await expect(panel).not.toBeVisible();
    await launcher.click();
    await expect(panel.getByText('Current facts', { exact: true })).toBeVisible();
    await panel.getByRole('button', { name: 'History', exact: true }).click();
    await expect(panel.getByText('Recent conversations', { exact: true })).toBeVisible();
    await panel.getByRole('button', { name: /Saved discussion/ }).click();
    await expect(panel.getByText('Saved facts', { exact: true })).toBeVisible();
    await question.fill('Continue saved discussion');
    await question.press('Enter');
    await expect.poll(() => questions.length).toBe(2);
    expect(questions[1].conversation_id).toBe('saved');
    await expect(question).toBeEnabled();
    await panel.getByRole('button', { name: 'New chat', exact: true }).click();
    await expect(panel.getByText('Saved facts', { exact: true })).not.toBeVisible();
    disable();
    await page.evaluate(() => window.dispatchEvent(new Event('observer:configuration')));
    await expect(launcher).not.toBeVisible();
    await expect(panel).not.toBeVisible();
    expect(questions).toHaveLength(2);
  });
}
