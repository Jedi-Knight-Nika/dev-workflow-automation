import { describe, expect, it, vi } from 'vitest';
import { createLayoutWriter } from './workflow-layout';

describe('workflow layout autosave', () => {
  it('serializes writes and retains only the latest pending drag', async () => {
    let release!: () => void;
    const first = new Promise<void>((resolve) => {
      release = resolve;
    });
    const save = vi
      .fn()
      .mockImplementationOnce(() => first)
      .mockResolvedValue(undefined);
    const writer = createLayoutWriter(save);
    const layout = (x: number) => ({ version: 1, positions: [{ node_id: 'node', x, y: 1 }] });
    const done = writer.write(layout(1));
    void writer.write(layout(2));
    void writer.write(layout(3));
    expect(save).toHaveBeenCalledTimes(1);
    release();
    await done;
    expect(save.mock.calls.map(([value]) => value.positions[0].x)).toEqual([1, 3]);
    expect(Object.keys(save.mock.calls[0][0])).toEqual(['version', 'positions']);
  });
  it('keeps a failed layout available for explicit retry', async () => {
    const save = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue(undefined);
    const writer = createLayoutWriter(save);
    await expect(writer.write({ version: 2, positions: [] })).rejects.toThrow('offline');
    await writer.flush();
    expect(save).toHaveBeenCalledTimes(2);
  });
});
