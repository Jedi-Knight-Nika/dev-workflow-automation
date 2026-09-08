import { env } from '$env/dynamic/public';

export const API_BASE_URL = `${(env.PUBLIC_API_URL || '').replace(/\/$/, '')}/api`;

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: { 'content-type': 'application/json', ...options?.headers }
  });
  if (!response.ok) {
    const fallback = `API request failed with ${response.status}`;
    const contentType = response.headers.get('content-type') || '';
    const body = (await response.text()).trim();
    const isHtml = contentType.includes('text/html') || body.startsWith('<');
    throw new Error(isHtml || !body ? fallback : body.slice(0, 500));
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
