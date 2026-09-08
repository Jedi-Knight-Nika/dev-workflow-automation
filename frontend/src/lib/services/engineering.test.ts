import { describe, expect, it } from 'vitest';
import {
  profileInput,
  sessionChangeInput,
  STAGES,
  type AgentProfile,
  type DeveloperSessionView
} from './engineering';

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
      prompt_version: 'fixed',
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
  it('sends versioned session intent, never model, budget, paths or native credentials', () => {
    const session: DeveloperSessionView = {
      session_id: 'record-id',
      generation: 2,
      has_native_session: true,
      harness: 'codex',
      provider: 'openai',
      model: 'current',
      state: 'READY',
      task_status: 'PAUSED',
      lifecycle_version: 5,
      profile_version: 3,
      target_harness: 'claude',
      target_provider: 'anthropic',
      target_model: 'target',
      keep_native_available: false,
      blocker: null
    };
    expect(sessionChangeInput(session, 'handoff', 'Operator request')).toEqual({
      session_id: 'record-id',
      lifecycle_version: 5,
      profile_version: 3,
      mode: 'handoff',
      reason: 'Operator request'
    });
  });
});
