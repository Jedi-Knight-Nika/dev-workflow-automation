import { env } from '$env/dynamic/public';

export const API_BASE_URL = `${(env.PUBLIC_API_URL || '').replace(/\/$/, '')}/api`;

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly requestId: string | null = null
  ) {
    super(message);
  }
}

function errorMessage(body: string, fallback: string): string {
  try {
    const parsed = JSON.parse(body);
    if (typeof parsed.detail === 'string') return parsed.detail.slice(0, 500);
    if (Array.isArray(parsed.detail)) {
      const messages = parsed.detail.flatMap((item: { msg?: unknown; loc?: unknown }) => {
        if (typeof item?.msg !== 'string') return [];
        const field = Array.isArray(item.loc)
          ? item.loc.filter((part) => part !== 'body').join('.')
          : '';
        return [field ? `${field}: ${item.msg}` : item.msg];
      });
      if (messages.length) return messages.join('; ').slice(0, 500);
    }
    return fallback;
  } catch {
    return body.slice(0, 500) || fallback;
  }
}

async function request(path: string, options?: RequestInit): Promise<Response> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: { 'content-type': 'application/json', ...options?.headers }
  });
  if (!response.ok) {
    const fallback = `API request failed with ${response.status}`;
    const contentType = response.headers.get('content-type') || '';
    const body = (await response.text()).trim();
    const isHtml = contentType.includes('text/html') || body.startsWith('<');
    throw new ApiError(
      response.status,
      isHtml || !body ? fallback : errorMessage(body, fallback),
      response.headers.get('x-request-id')
    );
  }
  return response;
}

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await request(path, options);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function apiPage<T>(path: string, options?: RequestInit) {
  const response = await request(path, options);
  return {
    items: (await response.json()) as T[],
    nextCursor: response.headers.get('x-next-cursor')
  };
}
