import type { Point } from './position';

type Options = {
  position: () => Point;
  move: (point: Point) => void;
  commit: () => void;
  reset: () => void;
  dragging: (active: boolean) => void;
};

/** Pointer capture supports mouse, pen and touch without global move listeners or a render loop. */
export function draggable(node: HTMLButtonElement, options: Options) {
  let pointer: number | null = null;
  let origin: Point;
  let start: Point;
  let moved = false;
  let suppressClick = false;

  function down(event: PointerEvent) {
    if (!event.isPrimary || event.button !== 0 || pointer !== null) return;
    pointer = event.pointerId;
    start = { x: event.clientX, y: event.clientY };
    origin = options.position();
    moved = false;
    suppressClick = false;
    node.setPointerCapture(pointer);
  }
  function move(event: PointerEvent) {
    if (event.pointerId !== pointer) return;
    const dx = event.clientX - start.x;
    const dy = event.clientY - start.y;
    if (!moved && Math.hypot(dx, dy) < 5) return;
    moved = true;
    options.dragging(true);
    options.move({ x: origin.x + dx, y: origin.y + dy });
    event.preventDefault();
  }
  function finish(event: PointerEvent) {
    if (event.pointerId !== pointer) return;
    pointer = null;
    suppressClick = moved;
    options.dragging(false);
    if (moved) options.commit();
    if (node.hasPointerCapture(event.pointerId)) node.releasePointerCapture(event.pointerId);
  }
  function click(event: MouseEvent) {
    // A release after dragging must not accidentally open or close the assistant.
    if (suppressClick && event.detail !== 0) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
    suppressClick = false;
  }
  function key(event: KeyboardEvent) {
    const direction: Record<string, Point> = {
      ArrowLeft: { x: -1, y: 0 },
      ArrowRight: { x: 1, y: 0 },
      ArrowUp: { x: 0, y: -1 },
      ArrowDown: { x: 0, y: 1 }
    };
    if (event.key === 'Home') {
      event.preventDefault();
      options.reset();
    } else if (direction[event.key]) {
      event.preventDefault();
      const point = options.position();
      const step = event.shiftKey ? 40 : 10;
      options.move({
        x: point.x + direction[event.key].x * step,
        y: point.y + direction[event.key].y * step
      });
      options.commit();
    }
  }
  node.addEventListener('pointerdown', down);
  node.addEventListener('pointermove', move);
  node.addEventListener('pointerup', finish);
  node.addEventListener('pointercancel', finish);
  node.addEventListener('lostpointercapture', finish);
  node.addEventListener('click', click, true);
  node.addEventListener('keydown', key);
  return {
    destroy() {
      if (pointer !== null && node.hasPointerCapture(pointer)) node.releasePointerCapture(pointer);
      options.dragging(false);
      node.removeEventListener('pointerdown', down);
      node.removeEventListener('pointermove', move);
      node.removeEventListener('pointerup', finish);
      node.removeEventListener('pointercancel', finish);
      node.removeEventListener('lostpointercapture', finish);
      node.removeEventListener('click', click, true);
      node.removeEventListener('keydown', key);
    }
  };
}
