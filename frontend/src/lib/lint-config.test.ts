import { ESLint } from 'eslint';
import { describe, expect, it } from 'vitest';

const eslint = new ESLint();

describe('unused-code lint policy', () => {
  it.each([
    ['import', "import { readFile as _unused } from 'node:fs'; export {};"],
    ['local', 'export function read() { const unused = 1; return 2; }'],
    ['underscore local', 'export function read() { const _unused = 1; return 2; }'],
    [
      'earlier parameter',
      'export function choose(unused: number, value: number) { return value; }'
    ],
    ['caught error', 'export function read() { try { return JSON.parse("{}"); } catch (error) {} }']
  ])('rejects an unused %s', async (_label, source) => {
    const [result] = await eslint.lintText(source, { filePath: 'src/lib/lint-probe.ts' });
    expect(result.messages).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ ruleId: '@typescript-eslint/no-unused-vars', severity: 2 })
      ])
    );
  });

  it('accepts intentional callback parameters and object-rest exclusions', async () => {
    const [result] = await eslint.lintText(
      'export function omit(_context: unknown, record: { secret: string; name: string }) {' +
        'const { secret, ...publicFields } = record; return publicFields; }',
      { filePath: 'src/lib/lint-probe.ts' }
    );
    expect(result.messages).toEqual([]);
  });

  it('rejects a stale suppression', async () => {
    const [result] = await eslint.lintText('// eslint-disable-next-line no-alert\nexport {};', {
      filePath: 'src/lib/lint-probe.ts'
    });
    expect(result.messages).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ severity: 2, message: expect.stringContaining('Unused eslint') })
      ])
    );
  });

  it('detects unused Svelte variables but preserves template references', async () => {
    const [unused] = await eslint.lintText(
      '<script lang="ts">const unused = 1;</script><p>Hello</p>',
      { filePath: 'src/lib/LintProbe.svelte' }
    );
    expect(unused.messages).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ ruleId: '@typescript-eslint/no-unused-vars', severity: 2 })
      ])
    );
    const [used] = await eslint.lintText(
      '<script lang="ts">const label = "Hello";</script><p>{label}</p>',
      { filePath: 'src/lib/LintProbe.svelte' }
    );
    expect(used.messages).toEqual([]);
  });
});
