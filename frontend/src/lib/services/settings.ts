import { api } from '$lib/api';
import type { AccountSettings } from '$lib/types';

export type SettingsSection = 'general' | 'ai' | 'execution' | 'safety' | 'knowledge' | 'storage';

export const getAccountSettings = (): Promise<AccountSettings> => api('/settings');

export function updateAccountSettings<K extends SettingsSection>(
  section: K,
  values: AccountSettings[K]
): Promise<AccountSettings> {
  return api(`/settings/${section}`, {
    method: 'PATCH',
    body: JSON.stringify(values)
  });
}
