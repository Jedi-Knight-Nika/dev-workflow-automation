import { env } from '$env/dynamic/public';

export const API_URL = env.PUBLIC_API_URL || '';

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}/api/v1${path}`, {
    ...options,
    headers: { 'content-type': 'application/json', ...options?.headers }
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `API request failed with ${response.status}`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
