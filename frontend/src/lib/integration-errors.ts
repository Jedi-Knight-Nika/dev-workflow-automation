import { t } from '$lib/i18n/index.svelte';

export function integrationError(cause: unknown, provider = ''): string {
  if (!cause) return '';
  let message = cause instanceof Error ? cause.message : String(cause);
  try {
    const parsed = JSON.parse(message.replace(/^Error: /, ''));
    if (typeof parsed.detail === 'string') message = parsed.detail;
  } catch {
    // Historical errors and browser network failures are plain text.
  }
  if (/failed to fetch|networkerror|load failed|network request failed/i.test(message))
    return t('integrations.networkError');
  if (/401|unauthorized|rejected the (credentials|API key)/i.test(message))
    return t(
      provider.toLowerCase() === 'trello'
        ? 'integrations.trelloAuthError'
        : 'integrations.authError',
      { provider }
    );
  if (/403|forbidden|denied access/i.test(message))
    return t('integrations.accessError', { provider });
  if (/429|rate limit/i.test(message)) return t('integrations.rateLimitError', { provider });
  if (/timeout|timed out|too long to respond/i.test(message))
    return t('integrations.timeoutError', { provider });
  if (/cannot reach|temporarily unavailable|50[0234]/i.test(message))
    return t('integrations.unavailableError', { provider });
  if (/both a Trello|Trello credentials must|API key and token are required/i.test(message))
    return t('integrations.trelloPairRequired');
  return t('integrations.connectionError', { provider: provider || t('integrations.title') });
}
