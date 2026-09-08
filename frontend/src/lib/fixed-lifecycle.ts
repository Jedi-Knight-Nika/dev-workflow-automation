import type { Edge, Node } from '@xyflow/svelte';
import { STAGES, type EngineeringTask } from './services/engineering-v2';

// This is product-owned topology, never saved as a user-editable workflow.
const connections = [
  ['INTAKE', 'DEVELOPING'],
  ['DEVELOPING', 'PLANNING'],
  ['PLANNING', 'DEVELOPING'],
  ['DEVELOPING', 'VALIDATING'],
  ['VALIDATING', 'FIXING'],
  ['FIXING', 'VALIDATING'],
  ['VALIDATING', 'PUBLISHING'],
  ['PUBLISHING', 'REVIEWING'],
  ['REVIEWING', 'FIXING'],
  ['REVIEWING', 'MERGING'],
  ['MERGING', 'COMPLETE']
] as const;
const positions = [
  [0, 160],
  [230, 0],
  [230, 160],
  [460, 160],
  [690, 160],
  [920, 160],
  [690, 340],
  [1150, 160],
  [1380, 160]
];

export function lifecycleNodes(tasks: EngineeringTask[], selected?: EngineeringTask): Node[] {
  return STAGES.map((stage, index) => {
    const active = tasks.filter((task) => task.stage === stage && task.status === 'ACTIVE').length;
    return {
      id: stage,
      position: { x: positions[index][0], y: positions[index][1] },
      data: { label: `${stage.replaceAll('_', ' ')}${active ? ` · ${active} active` : ''}` },
      selected: selected?.stage === stage,
      draggable: false,
      connectable: false,
      deletable: false,
      style: active
        ? 'border-color: var(--color-accent); background: color-mix(in srgb, var(--color-accent) 16%, var(--color-panel)); color: var(--color-heading); box-shadow: 0 0 18px -2px color-mix(in srgb, var(--color-accent) 55%, transparent);'
        : undefined
    };
  });
}

export const lifecycleEdges: Edge[] = connections.map(([source, target]) => ({
  id: `${source}-${target}`,
  source,
  target,
  deletable: false,
  animated: true,
  type: 'smoothstep',
  style: 'stroke: var(--color-brand-2); stroke-width: 1.6px;'
}));
