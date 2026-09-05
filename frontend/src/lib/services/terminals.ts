import { API_URL, api } from '$lib/api';
import type { TerminalAccess } from '$lib/types';

export function openTerminal(taskId: string, nodeId: string): Promise<TerminalAccess> {
  return api<TerminalAccess>(`/tasks/${taskId}/terminal`, {
    method: 'POST',
    body: JSON.stringify({ node_id: nodeId || null })
  });
}

export function terminalWebSocketUrl(access: TerminalAccess): string {
  const base = API_URL || window.location.origin;
  const url = new URL(`/api/v1/terminal/${access.session_id}/stream`, base.replace(/^http/, 'ws'));
  url.searchParams.set('token', access.token);
  return url.toString();
}

export function closeTerminal(sessionId: string): Promise<void> {
  return api<void>(`/terminal/${sessionId}`, { method: 'DELETE' });
}
