import { describe, expect, it } from 'vitest';
import { profileInput, STAGES, type AgentProfile } from './engineering-v2';

describe('fixed engineering contracts', () => {
  it('sends only editable fields, never system prompt or role overrides', () => {
    const profile: AgentProfile = {
      id: 'profile',
      team_id: 'team',
      role_kind: 'DEVELOPER',
      version: 2,
      display_name: 'Developer',
      avatar: '',
      enabled: true,
      provider: 'openai',
      model: 'gpt-5.6-terra',
      harness: 'codex',
      effort: 'medium',
      supplemental_instructions: 'Keep code clean',
      prompt_version: 'v2.1',
      soft_budget_usd: null,
      hard_budget_usd: 5
    };
    const input = profileInput(profile);
    expect(input).not.toHaveProperty('role_kind');
    expect(input).not.toHaveProperty('prompt_version');
    expect(input.version).toBe(2);
    expect(input.hard_budget_usd).toBe(5);
  });
  it('has fixed unique stages and no mandatory old-role pipeline', () => {
    expect(new Set(STAGES).size).toBe(STAGES.length);
    expect(STAGES).toContain('DEVELOPING');
    expect(STAGES).not.toContain('EXECUTOR');
    expect(STAGES).not.toContain('TESTER');
  });
});
