export type ProviderModel = { id: string; display_name: string };

export const AI_PROVIDERS = [
  { id: 'openai', label: 'OpenAI' },
  { id: 'anthropic', label: 'Anthropic / Claude' },
  { id: 'deepseek', label: 'DeepSeek (interpreter)' }
] as const;

/** Model availability comes from authenticated discovery, not a guessed static list. */
export function providerModelOptions(
  _provider: string,
  discovered: ProviderModel[] = []
): ProviderModel[] {
  return [...new Map(discovered.map((model) => [model.id, model])).values()];
}
