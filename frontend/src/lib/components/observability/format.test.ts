import { describe, expect, it } from 'vitest';
import { bytes, count, duration, money, percent } from './format';
describe('observability display semantics', () => {
  it('distinguishes missing measurements from measured zero', () => {
    expect(money(null)).toBe('Unavailable');
    expect(money('0')).toBe('$0.0000');
    expect(bytes(null)).toBe('Unavailable');
    expect(bytes(0)).toBe('0.00 GiB');
    expect(count(null)).toBe('Unknown');
    expect(duration(null)).toBe('Unavailable');
    expect(percent(null)).toBe('Unavailable');
    expect(percent(1.45)).toBe('145.0%');
  });
});
