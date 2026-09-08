import { describe, expect, it } from 'vitest';
import { lifecycleEdges, lifecycleNodes } from './fixed-lifecycle';
import { STAGES, type EngineeringTask } from './services/engineering-v2';

describe('fixed lifecycle map', () => {
  it('has immutable topology and no graph editing controls', () => {
    const nodes = lifecycleNodes([]);
    expect(nodes.map((node) => node.id)).toEqual([...STAGES]);
    expect(nodes.every((node) => !node.draggable && !node.connectable && !node.deletable)).toBe(
      true
    );
    expect(
      lifecycleEdges.every(
        (edge) => !edge.deletable && STAGES.includes(edge.source as (typeof STAGES)[number])
      )
    ).toBe(true);
    expect(
      lifecycleEdges.some((edge) => edge.source === 'REVIEWING' && edge.target === 'FIXING')
    ).toBe(true);
  });
  it('does not present legacy activity as native Developer execution', () => {
    const task = { execution_version: 1, stage: 'DEVELOPING', status: 'ACTIVE' } as EngineeringTask;
    expect(lifecycleNodes([task], task).some((node) => node.selected || node.style)).toBe(false);
    task.execution_version = 2;
    const developer = lifecycleNodes([task], task).find((node) => node.id === 'DEVELOPING');
    expect(developer?.selected).toBe(true);
    expect(developer?.data.label).toContain('1 active');
  });
});
