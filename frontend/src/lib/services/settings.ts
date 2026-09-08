import { api } from '$lib/api';
import type { AccountSettings } from '$lib/types';
export const getAccountSettings = (): Promise<AccountSettings> => api('/settings');
export const updateAccountSettings = (section: 'general', values: AccountSettings['general']) =>
  api<AccountSettings>('/settings/' + section, { method: 'PATCH', body: JSON.stringify(values) });
