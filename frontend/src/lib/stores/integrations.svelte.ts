import { createResource } from './resource.svelte';
import { listIntegrations, listWebhookHealth } from '$lib/services/integrations';
import type { Integration, WebhookHealth } from '$lib/types';

export const integrationsResource = createResource<Integration[]>(listIntegrations, []);
export const webhookHealthResource = createResource<WebhookHealth[]>(listWebhookHealth, []);
