import { MarkerType, type Edge, type Node, type XYPosition } from '@xyflow/svelte';
import { STAGES, type EngineeringTask } from './services/engineering';

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

export type LifecycleNodeData = {
  label: string;
  title: string;
  nickname: string;
  detail: string;
  icon: string;
  color: string;
  active: boolean;
  waiting: boolean;
  liveTaskId: string | null;
  onRename: (id: string, nickname: string) => void;
  onOpenLive: (taskId: string, title: string) => void;
};

export type LifecyclePositions = Record<string, XYPosition>;
export type LifecycleNicknames = Record<string, string>;

const icons = ['inbox', 'spark', 'map', 'shield', 'wrench', 'rocket', 'chat', 'merge', 'check'];
const colors = [
  '#22d3ee',
  '#a78bfa',
  '#f59e0b',
  '#34d399',
  '#fb7185',
  '#f97316',
  '#60a5fa',
  '#c084fc',
  '#4ade80'
];

export function lifecycleNodes(
  tasks: EngineeringTask[],
  selected?: EngineeringTask,
  savedPositions: LifecyclePositions = {},
  nicknames: LifecycleNicknames = {},
  onRename: LifecycleNodeData['onRename'] = () => undefined,
  onOpenLive: LifecycleNodeData['onOpenLive'] = () => undefined
): Node<LifecycleNodeData, 'lifecycle'>[] {
  return STAGES.map((stage, index) => {
    const active = tasks.filter((task) => task.stage === stage && task.status === 'ACTIVE').length;
    const waiting = tasks.some(
      (task) =>
        task.stage === stage && ['WAITING_HUMAN', 'WAITING_EXTERNAL'].includes(task.status ?? '')
    );
    return {
      id: stage,
      type: 'lifecycle',
      position: savedPositions[stage] ?? { x: positions[index][0], y: positions[index][1] },
      data: {
        label: `${stage.replaceAll('_', ' ')}${active ? ` · ${active} active` : ''}`,
        title: stage.replaceAll('_', ' '),
        nickname: nicknames[stage] ?? stage.replaceAll('_', ' '),
        detail: active ? `${active} active` : '',
        icon: icons[index],
        color: colors[index],
        active: active > 0,
        waiting,
        liveTaskId: null,
        onRename,
        onOpenLive
      },
      selected: selected?.stage === stage,
      draggable: true,
      connectable: false,
      deletable: false,
      class: active ? 'lifecycle-active' : waiting ? 'lifecycle-waiting' : 'lifecycle-idle'
    };
  });
}

export const lifecycleEdges: Edge[] = connections.map(([source, target]) => ({
  id: `${source}-${target}`,
  source,
  target,
  deletable: false,
  animated: false,
  type: 'smoothstep',
  style:
    'stroke: color-mix(in srgb, var(--color-brand-2) 40%, var(--color-line)); stroke-width: 1.4px;',
  markerEnd: {
    type: MarkerType.ArrowClosed,
    width: 16,
    height: 16,
    color: 'color-mix(in srgb, var(--color-brand-2) 45%, var(--color-line))'
  }
}));
