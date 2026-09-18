import { afterEach, expect, it, vi } from 'vitest';
import { api } from './api';

vi.mock('$env/dynamic/public', () => ({ env: {} }));
afterEach(() => vi.unstubAllGlobals());

it('reports readable validation details without echoing invalid input', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: [{ loc: ['body', 'title'], msg: 'Required', input: 'private input' }]
        }),
        { status: 422, headers: { 'content-type': 'application/json', 'x-request-id': 'request' } }
      )
    )
  );
  await expect(api('/tasks')).rejects.toMatchObject({
    status: 422,
    message: 'title: Required',
    requestId: 'request'
  });
});

it('does not display an HTML proxy error or retry a failed mutation', async () => {
  const fetch = vi.fn().mockResolvedValue(
    new Response('<h1>Proxy error</h1>', {
      status: 503,
      headers: { 'content-type': 'text/html' }
    })
  );
  vi.stubGlobal('fetch', fetch);
  await expect(api('/tasks', { method: 'POST' })).rejects.toMatchObject({
    message: 'API request failed with 503'
  });
  expect(fetch).toHaveBeenCalledOnce();
});
