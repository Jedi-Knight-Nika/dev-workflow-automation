import { expect, test, type Page } from '@playwright/test';
import type { ActivityEvent } from '../src/lib/visualization/types';

const taskId = '10000000-0000-4000-8000-000000000001';
const start = new Date(Date.now() - 3600_000).toISOString();
const entry = (
  sequence: number,
  kind: string,
  payload: Record<string, unknown> = {}
): ActivityEvent => ({
  sequence,
  id: String(sequence),
  kind,
  occurred_at: new Date(Date.parse(start) + sequence * 1000).toISOString(),
  recorded_at: start,
  task_id: taskId,
  task_title: 'Improve checkout',
  task_key: 'TASK-7',
  team_id: null,
  team_name: null,
  project: 'Store',
  actor_type: 'agent',
  actor: 'Developer',
  correlation_id: null,
  payload,
  files: []
});
const events = [
  entry(1, 'TASK_CREATED'),
  entry(2, 'TASK_STATE_CHANGED', { version: 2, to_status: 'ACTIVE', to_stage: 'DEVELOPING' }),
  entry(3, 'AI_RUN_COMPLETED', {
    run_id: 'run',
    role: 'DEVELOPER',
    cost_usd: null,
    input_tokens: 100,
    output_tokens: 20,
    usage_complete: true,
    request_count: 3,
    request_count_complete: true
  }),
  {
    ...entry(4, 'CODE_CHANGED'),
    files: [
      {
        repository_id: 'repo',
        operation: 'A' as const,
        path: 'src/checkout.ts',
        previous_path: null,
        lines_added: 10,
        lines_deleted: 0
      }
    ]
  }
];

events[1].parents = [{ ...events[0], relationship: 'triggered_by' }];

test('compares usage and restores observed work dependencies at the selected time', async ({
  page
}) => {
  await setup(page, [
    ...events,
    entry(5, 'WORK_PLAN_UPDATED', {
      run_id: 'run',
      work_plans: [
        {
          revision: 0,
          units: [
            { id: 'schema', status: 'READY', depends_on: [] },
            { id: 'api', status: 'RUNNING', depends_on: [0] }
          ]
        }
      ]
    })
  ]);
  const dialog = await open(page);
  await dialog.getByRole('button', { name: 'Start visualization' }).click();
  const timeline = dialog.getByRole('slider', { name: 'Activity timeline' });
  await expect(timeline).toHaveAttribute('max', '5');
  await timeline.fill('5');
  await dialog.locator('summary').filter({ hasText: 'AI usage comparisons' }).click();
  await dialog.getByLabel('Group AI usage').selectOption('roles');
  const comparisons = dialog.locator('details').filter({ hasText: 'AI usage comparisons' });
  await expect(comparisons).toContainText('DEVELOPER');
  await expect(comparisons).toContainText('1 / 1');
  await expect(
    comparisons.getByRole('row').filter({ hasText: 'DEVELOPER' }).getByRole('cell').nth(3)
  ).toHaveText('3');
  await dialog.locator('summary').filter({ hasText: 'Bottlenecks and Team capacity' }).click();
  await expect(dialog).toContainText('No capacity evidence in this snapshot');
  await dialog.locator('summary').filter({ hasText: 'Work-plan dependency history' }).click();
  const history = dialog.locator('details').filter({ hasText: 'Work-plan dependency history' });
  await expect(history.getByRole('row').filter({ hasText: 'api' })).toContainText('schema');
  await timeline.fill('4');
  await expect(dialog).toContainText('No structured work-plan snapshots');
});

test('loads the real Gource engine only on demand and disposes its frame on return', async ({
  page
}) => {
  const assets: string[] = [];
  page.on('request', (request) => {
    if (request.url().includes('/gource/')) assets.push(request.url());
  });
  await setup(page);
  const dialog = await open(page);
  await dialog.getByRole('button', { name: 'Start visualization' }).click();
  const timeline = dialog.getByRole('slider', { name: 'Activity timeline' });
  await expect(timeline).toHaveAttribute('max', '4');
  await dialog.getByLabel('Visualization view').selectOption('code');
  await timeline.fill('4');
  expect(assets).toEqual([]);
  await dialog.getByRole('button', { name: 'Open Gource replay', exact: true }).click();
  const gource = dialog.getByRole('region', { name: 'Gource historical replay' });
  await expect(gource.getByRole('button', { name: 'Pause Gource', exact: true })).toBeEnabled({
    timeout: 25_000
  });
  expect(assets.some((url) => url.endsWith('.wasm'))).toBe(true);
  expect(assets.every((url) => new URL(url).origin === new URL(page.url()).origin)).toBe(true);
  await expect(gource.getByRole('button', { name: 'Return to activity replay' })).toBeInViewport();
  await gource.getByRole('button', { name: 'Pause Gource', exact: true }).click();
  await expect(gource.getByRole('button', { name: 'Resume Gource', exact: true })).toBeEnabled();
  await page.screenshot({ path: '/tmp/aew-gource.png' });
  await gource.getByRole('button', { name: 'Return to activity replay' }).click();
  await expect(dialog.locator('iframe')).toHaveCount(0);
  await expect(timeline).toHaveValue('4');
  expect(await page.evaluate(() => window.activityHarness.workers)).toBe(1);
  await dialog.getByRole('button', { name: 'Close activity visualization' }).click();
  expect(await page.evaluate(() => window.activityHarness.workers)).toBe(0);
});

test('disposes a failed Gource engine and preserves the Canvas replay', async ({ page }) => {
  const calls = await setup(page);
  await page.route('**/gource/vendor/gource-web.wasm', (route) => route.abort());
  const dialog = await open(page);
  await dialog.getByRole('button', { name: 'Start visualization' }).click();
  const timeline = dialog.getByRole('slider', { name: 'Activity timeline' });
  await expect(timeline).toHaveAttribute('max', '4');
  await timeline.fill('4');
  await dialog.getByLabel('Visualization view').selectOption('code');
  await dialog.getByRole('button', { name: 'Open Gource replay', exact: true }).click();
  await expect(dialog.getByRole('alert')).toContainText('Gource could not render', {
    timeout: 25_000
  });
  await expect(dialog.locator('iframe')).toHaveCount(0);
  await dialog.getByRole('button', { name: 'Return to activity replay' }).click();
  await expect(timeline).toHaveValue('4');
  await dialog.getByRole('button', { name: 'Close activity visualization' }).click();
  expect(await page.evaluate(() => window.activityHarness.workers)).toBe(0);
  await expect
    .poll(() => calls.some((call) => call.includes('/visualization/telemetry')))
    .toBe(true);
});

declare global {
  interface Window {
    activityHarness: {
      workers: number;
      streams: number;
      streamUrls: string[];
      emit: (kind: string, data: unknown) => void;
      failGraphics: () => void;
    };
  }
}

async function setup(page: Page, history = events) {
  await page.addInitScript(() => {
    const state: Window['activityHarness'] = (window.activityHarness = {
      workers: 0,
      streams: 0,
      streamUrls: [] as string[],
      emit: () => {},
      failGraphics: () => {}
    });
    const RealWorker = window.Worker;
    window.Worker = class extends RealWorker {
      private stopped = false;
      constructor(url: string | URL, options?: WorkerOptions) {
        super(url, options);
        state.workers++;
        state.failGraphics = () => this.dispatchEvent(new ErrorEvent('error'));
      }
      terminate() {
        if (!this.stopped) {
          state.workers--;
          this.stopped = true;
        }
        super.terminate();
      }
    };
    window.EventSource = class extends EventTarget {
      onopen: (() => void) | null = null;
      onerror: (() => void) | null = null;
      private closed = false;
      constructor(url: string | URL) {
        super();
        if (String(url).includes('/visualization/stream')) {
          state.streams++;
          state.streamUrls.push(String(url));
          state.emit = (kind, data) =>
            this.dispatchEvent(new MessageEvent(kind, { data: JSON.stringify(data) }));
          queueMicrotask(() => this.onopen?.());
        }
      }
      close() {
        if (!this.closed) {
          state.streams = Math.max(0, state.streams - 1);
          this.closed = true;
        }
      }
    } as unknown as typeof EventSource;
  });
  const calls: string[] = [];
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    calls.push(`${route.request().method()} ${url.pathname}${url.search}`);
    if (url.pathname.endsWith('/visualization/scopes'))
      return route.fulfill({
        json: { teams: [], repositories: [], projects: [], truncated: false }
      });
    if (url.pathname.endsWith('/visualization/preflight')) {
      const input = route.request().postDataJSON();
      return route.fulfill({
        json: {
          scope: input.scope,
          from: input.from,
          to: input.to || new Date().toISOString(),
          through_sequence: history.length,
          estimated_events: history.length,
          tasks: 1,
          file_changes: 1,
          max_events: Math.max(5, history.length),
          max_files: 50,
          max_tasks: 20,
          too_large: false,
          delayed: false,
          warnings: [],
          live_available: true,
          last_projected_at: start
        }
      });
    }
    if (url.pathname.endsWith('/visualization/telemetry')) return route.fulfill({ status: 204 });
    if (url.pathname.includes('/visualization/inspect/')) {
      const selected =
        history.find((event) => event.sequence === Number(url.pathname.split('/').pop())) ??
        history[0];
      return route.fulfill({
        json: {
          event: selected,
          children: [],
          checks: [],
          truncated: false,
          file_status: null,
          file_attempts: 0,
          file_retry_at: null
        }
      });
    }
    if (url.pathname.endsWith('/visualization/baseline'))
      return route.fulfill({ json: { tasks: [] } });
    if (url.pathname.endsWith('/visualization/events')) {
      const after = Number(url.searchParams.get('after_sequence'));
      return route.fulfill({
        json: {
          events: history.slice(after, after + 2),
          next_sequence: Math.min(after + 2, history.length),
          has_more: after + 2 < history.length
        }
      });
    }
    if (url.pathname.endsWith('/events/stream')) return route.abort();
    return route.fulfill({ json: [] });
  });
  await page.goto('/repositories');
  return calls;
}

async function open(page: Page, live = false) {
  await page.getByRole('button', { name: 'Visualize activity', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Activity replay' });
  // The first lazy import compiles the viewer on the development server under parallel load.
  await expect(dialog.getByRole('button', { name: 'Start visualization' })).toBeEnabled({
    timeout: 15_000
  });
  if (live) await dialog.getByLabel('Follow live activity').check();
  return dialog;
}

test('loads on demand, replays through a frozen sequence, and releases graphics on close', async ({
  page
}) => {
  const calls = await setup(page);
  expect(calls.some((call) => call.includes('/visualization/'))).toBe(false);
  expect(await page.evaluate(() => window.activityHarness.workers)).toBe(0);
  const dialog = await open(page);
  expect(calls.some((call) => call.includes('/visualization/events'))).toBe(false);
  expect(await page.evaluate(() => window.activityHarness.workers)).toBe(0);
  await dialog.getByRole('button', { name: 'Start visualization' }).click();
  const timeline = dialog.getByRole('slider', { name: 'Activity timeline' });
  await expect(timeline).toHaveAttribute('max', '4');
  expect(await page.evaluate(() => window.activityHarness.workers)).toBe(1);
  const pages = calls.filter((call) => call.includes('/visualization/events'));
  expect(pages).toHaveLength(2);
  expect(pages.every((call) => call.includes('through_sequence=4'))).toBe(true);
  await timeline.fill('3');
  await expect(dialog.getByRole('region', { name: 'Activity inspector' })).toContainText(
    'ai run completed'
  );
  await expect(dialog).toContainText('$0.0000 + 1 unknown');
  await dialog.getByLabel('Visualization view').selectOption('code');
  await timeline.fill('4');
  await expect(dialog.getByRole('region', { name: 'Activity inspector' })).toContainText(
    'src/checkout.ts'
  );
  await dialog.getByRole('button', { name: 'Maximize', exact: true }).click();
  await expect(dialog).toHaveClass(/maximized/);
  await page.setViewportSize({ width: 1100, height: 900 });
  await expect(timeline).toHaveValue('4');
  await page.screenshot({ path: '/tmp/aew-activity.png' });
  await dialog.getByRole('button', { name: 'Close activity visualization' }).click();
  await expect(dialog).toHaveCount(0);
  expect(await page.evaluate(() => window.activityHarness.workers)).toBe(0);
  expect(
    calls.filter(
      (call) =>
        !call.startsWith('GET') &&
        !call.includes('/visualization/preflight') &&
        !call.includes('/visualization/telemetry')
    )
  ).toEqual([]);
  const reopened = await open(page);
  await reopened.getByRole('button', { name: 'Start visualization' }).click();
  await expect(reopened.getByRole('slider')).toHaveAttribute('max', '4');
  await reopened.getByRole('button', { name: 'Close activity visualization' }).click();
  expect(await page.evaluate(() => window.activityHarness.workers)).toBe(0);
});

test('live follow deduplicates events, resumes after visibility pause, and stops at its bound', async ({
  page
}) => {
  await setup(page);
  const dialog = await open(page, true);
  await dialog.getByRole('button', { name: 'Start visualization' }).click();
  await expect(dialog.getByRole('slider')).toHaveValue('4');
  await page.evaluate(
    (event) => {
      window.activityHarness.emit('activity', event);
      window.activityHarness.emit('activity', event);
    },
    entry(5, 'MESSAGE_SENT')
  );
  await expect(dialog.getByRole('slider')).toHaveAttribute('max', '5');
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => true });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  expect(await page.evaluate(() => window.activityHarness.streams)).toBe(0);
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => false });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect
    .poll(() => page.evaluate(() => window.activityHarness.streamUrls.at(-1)))
    .toContain('after_sequence=5');
  await page.evaluate(() => window.activityHarness.emit('status', { delayed: true }));
  await expect(dialog).toContainText('This view may be incomplete');
  await page.evaluate(
    (event) => window.activityHarness.emit('activity', event),
    entry(6, 'MESSAGE_SENT')
  );
  await expect(dialog.getByRole('alert')).toContainText('reached its limit');
  expect(await page.evaluate(() => window.activityHarness.streams)).toBe(0);
  await expect(dialog.getByRole('slider')).toHaveAttribute('max', '5');
  await dialog.getByRole('button', { name: 'Close activity visualization' }).click();
  expect(await page.evaluate(() => window.activityHarness.workers)).toBe(0);
});

test('a graphics failure retains live history in the timeline fallback', async ({ page }) => {
  await setup(page);
  const dialog = await open(page, true);
  await dialog.getByRole('button', { name: 'Start visualization' }).click();
  await expect(dialog.getByRole('slider')).toHaveValue('4');
  await page.evaluate(
    (event) => window.activityHarness.emit('activity', event),
    entry(5, 'MESSAGE_SENT')
  );
  await expect(dialog.getByRole('slider')).toHaveValue('5');
  await page.evaluate(() => window.activityHarness.failGraphics());
  await expect(dialog.getByRole('alert')).toContainText('Graphics are unavailable');
  await expect(dialog.getByRole('slider')).toHaveValue('5');
  await dialog.getByRole('slider').fill('3');
  await expect(dialog).toContainText('$0.0000 + 1 unknown');
  expect(await page.evaluate(() => window.activityHarness.workers)).toBe(0);
  await dialog.getByRole('button', { name: 'Close activity visualization' }).click();
});

test('shows distinct CI and manual intervention metrics through the playhead', async ({ page }) => {
  await setup(page, [
    ...events,
    entry(5, 'CI_CHECK_UPDATED', {
      check_key: 'check',
      check_type: 'check_run',
      status: 'FAILURE'
    }),
    entry(6, 'TASK_STATE_CHANGED', {
      version: 3,
      to_status: 'PAUSED',
      to_stage: 'DEVELOPING',
      action: 'TAKEOVER',
      from_manual_takeover: false
    })
  ]);
  const dialog = await open(page);
  await dialog.getByRole('button', { name: 'Start visualization' }).click();
  const timeline = dialog.getByRole('slider', { name: 'Activity timeline' });
  await expect(timeline).toHaveAttribute('max', '6');
  await timeline.fill('6');
  await dialog.locator('summary').filter({ hasText: 'Process and code summary' }).click();
  const process = dialog.locator('details').filter({ hasText: 'Process and code summary' });
  await expect(process).toContainText('1 failed CI checks/status contexts');
  await expect(process).toContainText('1 manual code takeovers across 1 tasks');
  await expect(process).toContainText('0 reviews');
  await timeline.fill('4');
  await expect(process).toContainText('0 failed CI checks/status contexts');
  await expect(process).toContainText('0 manual code takeovers');
});

test('refreshes live capacity through SSE without reloading or moving a paused playhead', async ({
  page
}) => {
  const calls = await setup(page);
  const dialog = await open(page, true);
  await dialog.getByRole('button', { name: 'Start visualization' }).click();
  const timeline = dialog.getByRole('slider', { name: 'Activity timeline' });
  await expect(timeline).toHaveValue('4');
  await dialog.locator('summary').filter({ hasText: 'Bottlenecks and Team capacity' }).click();
  const capacity = dialog.locator('details').filter({ hasText: 'Bottlenecks and Team capacity' });
  const snapshot = (offset: number) => ({
    delayed: false,
    capacity: {
      as_of: new Date(Date.parse(start) + offset).toISOString(),
      through_sequence: 4,
      truncated: false,
      teams: [
        {
          id: 'team',
          name: 'Backend Team',
          limits: [{ at: start, capacity: 1 }],
          jobs: [{ id: 'job', task_id: taskId, start, end: null, complete: true }]
        }
      ]
    }
  });
  const preflights = calls.filter((call) => call.includes('/visualization/preflight')).length;
  await page.evaluate((value) => window.activityHarness.emit('status', value), snapshot(3_600_000));
  await expect(capacity).toContainText('1.00h at or above capacity');
  await dialog.getByRole('button', { name: 'Pause', exact: true }).click();
  await page.evaluate((value) => window.activityHarness.emit('status', value), snapshot(7_200_000));
  await expect(capacity).toContainText('1.00h at or above capacity');
  await dialog.getByRole('button', { name: 'Follow live', exact: true }).click();
  await expect(capacity).toContainText('2.00h at or above capacity');
  await page.evaluate((value) => window.activityHarness.emit('status', value), snapshot(3_600_000));
  await expect(capacity).toContainText('2.00h at or above capacity');
  expect(calls.filter((call) => call.includes('/visualization/preflight'))).toHaveLength(
    preflights
  );
  await expect(timeline).toHaveValue('4');
  await dialog.getByRole('button', { name: 'Close activity visualization' }).click();
  expect(await page.evaluate(() => window.activityHarness.streams)).toBe(0);
  expect(await page.evaluate(() => window.activityHarness.workers)).toBe(0);
});

test('shows explicit causes, revision checks and incomplete file coverage', async ({ page }) => {
  const calls = await setup(page);
  await page.route('**/api/visualization/inspect/*?*', async (route) => {
    const selected = events[2];
    return route.fulfill({
      json: {
        event: {
          ...selected,
          parents: [{ ...events[1], relationship: 'triggered_by' }],
          unresolved_parents: 1
        },
        children: [],
        checks: [
          {
            ...events[1],
            kind: 'VALIDATION_CHECK_COMPLETED',
            payload: { check_kind: 'tests', status: 'FAILED' }
          }
        ],
        truncated: false,
        file_status: 'TOO_LARGE',
        file_attempts: 1,
        file_retry_at: null
      }
    });
  });
  const dialog = await open(page, true);
  await dialog.getByRole('button', { name: 'Start visualization' }).click();
  await expect(dialog.getByRole('slider')).toHaveAttribute('max', '4');
  await dialog.getByRole('slider').fill('3');
  const inspector = dialog.getByRole('region', { name: 'Activity inspector' });
  await expect(inspector).toContainText('tests: FAILED');
  await expect(inspector).toContainText('1 references are unavailable');
  await expect(inspector.getByRole('link', { name: 'Open technical details' })).toHaveAttribute(
    'href',
    /#execution-details$/
  );
  await inspector.getByRole('button', { name: 'task state changed', exact: true }).click();
  await expect(dialog.getByRole('slider')).toHaveValue('2');
  await page.evaluate(() =>
    window.activityHarness.emit('status', {
      delayed: false,
      file_history: { counts: { TOO_LARGE: 1 }, incomplete: true, sampled: false }
    })
  );
  await expect(dialog).toContainText('1 over collection limit');
  await dialog.getByText('Process and code summary', { exact: true }).click();
  await expect(dialog).toContainText('First-attempt queue time');
  await dialog.getByRole('button', { name: 'Close activity visualization' }).click();
  await expect
    .poll(() => calls.some((call) => call.includes('/visualization/telemetry')))
    .toBe(true);
});

test('summarizes oversized ranges without loading raw events and narrows a selected bucket', async ({
  page
}) => {
  const calls = await setup(page);
  let requested = '';
  await page.route('**/api/visualization/preflight', async (route) => {
    const input = route.request().postDataJSON();
    requested = input.from;
    return route.fulfill({
      json: {
        scope: input.scope,
        from: input.from,
        to: input.to || new Date().toISOString(),
        through_sequence: 4,
        estimated_events: 6,
        tasks: 1,
        file_changes: 1,
        max_events: 5,
        max_files: 50,
        max_tasks: 20,
        too_large: true,
        delayed: false,
        warnings: [],
        live_available: true,
        last_projected_at: start
      }
    });
  });
  const at = new Date();
  at.setUTCMinutes(0, 0, 0);
  await page.route('**/api/visualization/aggregate?*', async (route) =>
    route.fulfill({
      json: {
        unit: 'hour',
        events: 15000,
        through_sequence: 4,
        buckets: [
          {
            at: at.toISOString(),
            events: 15000,
            tasks: 1,
            validation_passed: 2,
            validation_failed: 1,
            reviews: 1,
            human_responses: 0
          }
        ]
      }
    })
  );
  await page.getByRole('button', { name: 'Visualize activity', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Activity replay' });
  await expect(dialog.getByRole('button', { name: 'Start visualization' })).toBeDisabled();
  await dialog.getByRole('button', { name: 'Open range summary' }).click();
  await expect(dialog.getByRole('region', { name: 'Activity range summary' })).toContainText(
    '15,000 events'
  );
  expect(calls.some((call) => call.includes('/visualization/events'))).toBe(false);
  expect(await page.evaluate(() => window.activityHarness.workers)).toBe(0);
  await dialog.getByRole('button', { name: at.toISOString().slice(0, 16), exact: true }).click();
  await expect.poll(() => requested).toBe(at.toISOString());
});
