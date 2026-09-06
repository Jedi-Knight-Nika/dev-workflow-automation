export type ProviderModel = { id: string; display_name: string };

/**
 * Conservative defaults keep model selection usable before provider discovery.
 * Live provider discovery is merged into these options whenever credentials are available.
 */
export const DEFAULT_PROVIDER_MODELS: Record<string, ProviderModel[]> = {
  openai: [
    { id: 'gpt-5.6-sol', display_name: 'GPT-5.6 Sol' },
    { id: 'gpt-5.6-terra', display_name: 'GPT-5.6 Terra' },
    { id: 'gpt-5.6-luna', display_name: 'GPT-5.6 Luna' },
    { id: 'gpt-5.5', display_name: 'GPT-5.5' }
  ],
  anthropic: [
    { id: 'claude-opus-5', display_name: 'Claude Opus 5' },
    { id: 'claude-sonnet-5', display_name: 'Claude Sonnet 5' },
    { id: 'claude-fable-5', display_name: 'Claude Fable 5' },
    { id: 'claude-opus-4-8', display_name: 'Claude Opus 4.8' },
    { id: 'claude-sonnet-4-6', display_name: 'Claude Sonnet 4.6' },
    { id: 'claude-haiku-4-5-20251001', display_name: 'Claude Haiku 4.5' }
  ],
  google: [
    { id: 'gemini-3.8-flash', display_name: 'Gemini 3.8 Flash' },
    { id: 'gemini-3.7-flash', display_name: 'Gemini 3.7 Flash' },
    { id: 'gemini-3.6-flash', display_name: 'Gemini 3.6 Flash' },
    { id: 'gemini-3.5-flash', display_name: 'Gemini 3.5 Flash' },
    { id: 'gemini-3.1-pro-preview', display_name: 'Gemini 3.1 Pro Preview' },
    { id: 'gemini-2.5-pro', display_name: 'Gemini 2.5 Pro' },
    { id: 'gemini-2.5-flash', display_name: 'Gemini 2.5 Flash' }
  ]
};

export function providerModelOptions(
  provider: string,
  discovered: ProviderModel[] = []
): ProviderModel[] {
  const models = new Map<string, ProviderModel>();
  for (const model of [...(DEFAULT_PROVIDER_MODELS[provider] || []), ...discovered]) {
    models.set(model.id, model);
  }
  return [...models.values()];
}
