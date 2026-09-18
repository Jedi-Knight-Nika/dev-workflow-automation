import type { ActivityEvent } from './types';

export type CanvasContext = CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D;
export type CanvasHit = {
  x: number;
  y: number;
  width: number;
  height: number;
  event: ActivityEvent;
};

/** A small graph of explicit source references, never inferred from event proximity. */
export function drawRelations(
  ctx: CanvasContext,
  events: ActivityEvent[],
  width: number
): CanvasHit[] {
  const bySequence = new Map(events.map((event) => [event.sequence, event]));
  const edges = events
    .flatMap((child) =>
      (child.parents ?? []).map((parent) => ({ child, parent: bySequence.get(parent.sequence) }))
    )
    .filter((edge) => edge.parent)
    .slice(-6);
  if (!edges.length) return [];
  const nodes = [
    ...new Map(
      edges.flatMap(
        ({ child, parent }) =>
          [
            [parent!.sequence, parent!],
            [child.sequence, child]
          ] as const
      )
    ).values()
  ];
  const step = Math.max(150, (width - 40) / nodes.length);
  const positions = new Map(nodes.map((event, index) => [event.sequence, 20 + index * step]));
  ctx.font = '11px system-ui';
  ctx.fillStyle = '#94a3b8';
  ctx.fillText('Recorded cause → effect links (recent)', 20, 22);
  ctx.strokeStyle = '#8b7bc8';
  for (const { child, parent } of edges) {
    const from = positions.get(parent!.sequence)! + 60,
      to = positions.get(child.sequence)! + 60;
    ctx.beginPath();
    ctx.moveTo(from, 42);
    ctx.bezierCurveTo(from, 26, to, 26, to, 42);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(to - 3, 37);
    ctx.lineTo(to, 42);
    ctx.lineTo(to + 3, 37);
    ctx.stroke();
  }
  return nodes.map((event) => {
    const x = positions.get(event.sequence)!;
    ctx.fillStyle = '#19263b';
    ctx.fillRect(x, 43, 135, 38);
    ctx.fillStyle = '#c4b5fd';
    ctx.fillText(event.kind.replaceAll('_', ' ').slice(0, 19), x + 5, 57);
    ctx.fillStyle = '#94a3b8';
    ctx.fillText(event.actor.slice(0, 20), x + 5, 73);
    return { x, y: 43, width: 135, height: 38, event };
  });
}
