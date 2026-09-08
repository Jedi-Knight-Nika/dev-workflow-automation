import { env } from '$env/dynamic/private';
import type { Handle } from '@sveltejs/kit';

// The standalone preview has no Caddy. Keep browser requests on the same origin.
export const handle: Handle = async ({ event, resolve }) => {
  if (!env.API_URL || !event.url.pathname.startsWith('/api/')) return resolve(event);
  if (event.url.pathname === '/api/observability/alerts')
    return new Response(null, { status: 404 });
  const headers = new Headers(event.request.headers);
  headers.delete('host');
  headers.delete('content-length');
  try {
    return await fetch(new URL(event.url.pathname + event.url.search, env.API_URL), {
      method: event.request.method,
      headers,
      body: ['GET', 'HEAD'].includes(event.request.method)
        ? undefined
        : await event.request.arrayBuffer(),
      redirect: 'manual',
      signal: event.request.signal
    });
  } catch {
    return Response.json({ detail: 'API unavailable' }, { status: 503 });
  }
};
