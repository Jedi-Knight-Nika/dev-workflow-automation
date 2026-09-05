import { expect, test, type Page } from '@playwright/test';
import type { Task } from '../src/lib/types';

const task: Task = {
  id: '11111111-1111-1111-1111-111111111111',
  external_key: 'CIT-531',
  title: 'Repair allocation export',
  description: 'Keep API and export calculations consistent.',
  priority: 2,
  state: 'IMPLEMENTING',
  current_revision: 'abc123',
  repository_id: '22222222-2222-2222-2222-222222222222',
  branch_name: 'agent/cit-531',
  workspace_path: '/data/workspaces/tasks/1',
  pull_request_number: null,
  pull_request_url: null,
  manual_takeover: false,
  created_at: '2026-09-05T10:00:00Z',
  updated_at: '2026-09-05T10:00:00Z'
};

async function mockControlPlane(page: Page) {
  const tasks: Task[] = [task];
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === '/api/v1/events/stream') {
      await route.fulfill({ status: 200, contentType: 'text/event-stream', body: '' });
    } else if (path === '/api/v1/tasks' && request.method() === 'POST') {
      const body = request.postDataJSON() as { title: string; description: string };
      const created = {
        ...task,
        id: '33333333-3333-3333-3333-333333333333',
        external_key: null,
        ...body
      };
      tasks.unshift(created);
      await route.fulfill({ json: created, status: 201 });
    } else if (path === '/api/v1/tasks') {
      await route.fulfill({ json: tasks });
    } else if (path === '/api/v1/repositories') {
      await route.fulfill({
        json: [
          {
            id: task.repository_id,
            provider: 'github',
            external_repo_id: '42',
            owner: 'citycom-inc',
            name: 'service',
            clone_url: 'https://github.com/citycom-inc/service.git',
            default_branch: 'main',
            enabled: true,
            local_path: '/data/workspaces/_repositories/42',
            index_status: 'READY',
            index_error: null,
            latest_sha: 'abc123',
            indexed_sha: 'abc123',
            indexed_at: '2026-09-05T10:00:00Z',
            updated_at: '2026-09-05T10:00:00Z',
            clone_status: 'CLONED',
            chunk_count: 120
          }
        ]
      });
    } else if (path === '/api/v1/workers') {
      await route.fulfill({
        json: [
          {
            id: 'worker:1',
            hostname: 'worker',
            process_id: 42,
            status: 'ONLINE',
            online: true,
            capabilities: ['jobs', 'linear', 'indexing'],
            started_at: '2026-09-05T10:00:00Z',
            last_heartbeat: '2026-09-05T10:00:00Z',
            stopped_at: null
          }
        ]
      });
    } else if (path === '/api/v1/activity') {
      await route.fulfill({
        json: {
          active_job: {
            id: '44444444-4444-4444-4444-444444444444',
            task_id: task.id,
            role: 'EXECUTOR',
            action: 'IMPLEMENT_PLAN',
            state: 'RUNNING',
            attempt: 1,
            priority: 2,
            payload: {},
            result: null,
            worker_id: 'worker:1',
            created_at: task.created_at,
            started_at: task.created_at,
            finished_at: null,
            failure_reason: null,
            retry_not_before: null
          },
          queued_jobs: []
        }
      });
    } else if (path === '/api/v1/integrations') {
      await route.fulfill({
        json: [
          {
            id: '55555555-5555-5555-5555-555555555555',
            provider_type: 'source_control',
            provider_name: 'github',
            status: 'CONNECTED',
            configuration: {},
            has_credentials: true,
            last_error: null,
            updated_at: task.updated_at
          }
        ]
      });
    } else if (path === '/api/v1/webhook-health') {
      await route.fulfill({
        json: [
          {
            provider: 'github',
            pending: 0,
            failed: 0,
            last_delivery_at: task.updated_at,
            last_processed_at: task.updated_at,
            last_error: null
          }
        ]
      });
    } else {
      await route.fulfill({ json: [] });
    }
  });
}

test('dashboard exposes current execution and system health', async ({ page }) => {
  await mockControlPlane(page);
  await page.goto('/');

  await expect(page.getByText('CIT-531').first()).toBeVisible();
  await expect(page.getByText('EXECUTOR · IMPLEMENT PLAN')).toBeVisible();
  await expect(page.getByText('CONNECTED · 0 pending · 0 failed')).toBeVisible();
  await expect(page.getByText('1/1')).toBeVisible();
  await expect(page.getByText('1 worker online')).toBeVisible();
});

test('operator can queue a task and navigate to inventory', async ({ page }) => {
  await mockControlPlane(page);
  await page.goto('/');

  await page.getByLabel('New engineering task').fill('Add regression coverage');
  await page.getByPlaceholder('Requirements, constraints, acceptance criteria…').fill('Test it.');
  await page.getByRole('button', { name: 'Queue task' }).click();
  await expect(page.getByText('Add regression coverage')).toBeVisible();

  await page.getByRole('link', { name: 'Tasks' }).click();
  await expect(page.getByRole('heading', { name: 'Tasks' })).toBeVisible();
  await expect(
    page.getByRole('link', { name: /P2 Repair allocation export CIT-531/ })
  ).toBeVisible();
});

test('operator can configure and launch GitHub App installation', async ({ page }) => {
  let savedBody: Record<string, unknown> | null = null;
  let configured = false;
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === '/api/v1/integrations/github' && request.method() === 'PUT') {
      savedBody = request.postDataJSON() as Record<string, unknown>;
      configured = true;
      await route.fulfill({
        json: {
          id: '55555555-5555-5555-5555-555555555555',
          provider_type: 'source_control',
          provider_name: 'github',
          status: 'CONFIGURED',
          configuration: { auth_type: 'github_app', app_slug: 'engineering-worker' },
          has_credentials: true,
          last_error: null,
          updated_at: task.updated_at
        }
      });
    } else if (path === '/api/v1/integrations') {
      await route.fulfill({
        json: configured
          ? [
              {
                id: '55555555-5555-5555-5555-555555555555',
                provider_type: 'source_control',
                provider_name: 'github',
                status: 'CONFIGURED',
                configuration: { auth_type: 'github_app', app_slug: 'engineering-worker' },
                has_credentials: true,
                last_error: null,
                updated_at: task.updated_at
              }
            ]
          : []
      });
    } else if (path === '/api/v1/github/app/install-url') {
      await route.fulfill({
        json: {
          url: 'https://github.com/apps/engineering-worker/installations/new?state=signed.state'
        }
      });
    } else {
      await route.fulfill({ json: [] });
    }
  });
  await page.route('https://github.com/**', (route) => route.abort());
  await page.goto('/integrations');

  await page.getByRole('button', { name: 'Configure' }).first().click();
  await page.getByLabel('Authentication').selectOption('github_app');
  await page.getByPlaceholder('GitHub App slug (from its public URL)').fill('engineering-worker');
  await page.getByPlaceholder('GitHub App ID').fill('123');
  await page.getByPlaceholder('-----BEGIN RSA PRIVATE KEY-----').fill('private-key');
  await page.getByRole('button', { name: 'Save securely' }).click();

  expect(savedBody).toEqual({
    provider_type: 'source_control',
    status: 'CONFIGURED',
    configuration: { auth_type: 'github_app', app_slug: 'engineering-worker' },
    credential: JSON.stringify({
      auth_type: 'github_app',
      app_id: '123',
      installation_id: '',
      private_key: 'private-key'
    })
  });
  await expect(page.getByRole('button', { name: 'Install app' })).toBeVisible();
  const githubRequest = page.waitForRequest(
    'https://github.com/apps/engineering-worker/installations/new?state=signed.state'
  );
  await page.getByRole('button', { name: 'Install app' }).click();
  await githubRequest;
});
