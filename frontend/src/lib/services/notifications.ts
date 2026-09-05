import { api } from '$lib/api';
import type { AppNotification, TelegramStatus } from '$lib/types';

export const listNotifications = (): Promise<AppNotification[]> => api('/notifications?limit=50');
export const unreadCount = (): Promise<{ count: number }> => api('/notifications/unread-count');
export const markNotification = (
  id: string,
  action: 'read' | 'acknowledge'
): Promise<AppNotification> => api(`/notifications/${id}/${action}`, { method: 'POST' });
export const telegramStatus = (): Promise<TelegramStatus> => api('/notifications/telegram/status');
export const configureTelegram = (
  botToken: string,
  webhookBaseUrl: string
): Promise<TelegramStatus> =>
  api('/notifications/telegram/configure', {
    method: 'PUT',
    body: JSON.stringify({ bot_token: botToken, webhook_base_url: webhookBaseUrl || null })
  });
export const connectTelegram = (): Promise<{ connect_url: string }> =>
  api('/notifications/telegram/connect', { method: 'POST' });
export const disconnectTelegram = (): Promise<void> =>
  api('/notifications/telegram/disconnect', { method: 'DELETE' });
export const testTelegram = (): Promise<void> =>
  api('/notifications/telegram/test', { method: 'POST' });
