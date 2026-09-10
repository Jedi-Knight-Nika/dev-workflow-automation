export type ProviderModel = { id: string; display_name: string };

export const AI_PROVIDERS = [
  { id: 'ollama', label: 'Ollama (local)' },
  { id: 'openai', label: 'OpenAI' },
  { id: 'anthropic', label: 'Anthropic / Claude' },
  { id: 'deepseek', label: 'DeepSeek (interpreter)' }
] as const;
