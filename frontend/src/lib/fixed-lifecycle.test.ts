import { describe, expect, it } from 'vitest';
import { lifecycleEdges, lifecycleNodes } from './fixed-lifecycle';
import { STAGES, type EngineeringTask } from './services/engineering';

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
  it('shows the selected task and active stage', () => {
    const task = {
      id: 'task-1',
      title: 'Task',
      priority: 3,
      stage: 'DEVELOPING',
      status: 'ACTIVE',
      wait_reason: 'NONE',
      requirement_version: 1,
      pull_request_url: null
    } as EngineeringTask;
    const developer = lifecycleNodes([task], task).find((node) => node.id === 'DEVELOPING');
    expect(developer?.selected).toBe(true);
    expect(developer?.data.label).toContain('1 active');
  });
});
