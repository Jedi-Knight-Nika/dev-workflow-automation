/** Presentation-only geometry. Positions are browser-local, never task or model state. */
export type Point = { x: number; y: number };
export type Viewport = { left: number; top: number; width: number; height: number };
export type FloatingBox = Point & { width: number; height: number };
export const POSITION_KEY = 'observer-position';
const INSET = 12;
const GAP = 12;
const clamp = (value: number, min: number, max: number) =>
  Math.max(min, Math.min(value, Math.max(min, max)));

export function readPosition(value: string | null): Point | null {
  try {
    const point = JSON.parse(value || 'null');
    return point && [point.x, point.y].every((n) => typeof n === 'number' && Number.isFinite(n))
      ? { x: clamp(point.x, 0, 1), y: clamp(point.y, 0, 1) }
      : null;
  } catch {
    return null;
  }
}

export function dockPosition(position: Point | null, viewport: Viewport, size: number): Point {
  const travelX = Math.max(0, viewport.width - size - INSET * 2);
  const travelY = Math.max(0, viewport.height - size - INSET * 2);
  return {
    x: viewport.left + INSET + (position ? position.x * travelX : Math.max(0, travelX - 12)),
    y:
      viewport.top +
      INSET +
      (position ? position.y * travelY : Math.max(0, travelY - (viewport.width <= 640 ? 70 : 12)))
  };
}

export function normalizePosition(point: Point, viewport: Viewport, size: number): Point {
  return {
    x: clamp(
      (point.x - viewport.left - INSET) / Math.max(1, viewport.width - size - INSET * 2),
      0,
      1
    ),
    y: clamp(
      (point.y - viewport.top - INSET) / Math.max(1, viewport.height - size - INSET * 2),
      0,
      1
    )
  };
}

/** Prefer beside the launcher, then above/below on narrow screens; never leave the viewport. */
export function placePopup(
  anchor: Point,
  size: number,
  viewport: Viewport,
  wantedWidth: number,
  wantedHeight: number
): FloatingBox {
  const left = viewport.left + INSET;
  const top = viewport.top + INSET;
  const right = viewport.left + viewport.width - INSET;
  const bottom = viewport.top + viewport.height - INSET;
  const width = Math.min(wantedWidth, Math.max(0, right - left));
  let height = Math.min(wantedHeight, Math.max(0, bottom - top));
  const roomRight = right - anchor.x - size - GAP;
  const roomLeft = anchor.x - GAP - left;
  let x: number;
  let y: number;
  if (Math.max(roomLeft, roomRight) >= width) {
    x =
      roomRight >= width && roomRight >= roomLeft ? anchor.x + size + GAP : anchor.x - GAP - width;
    y = anchor.y + size / 2 - height / 2;
  } else {
    const above = anchor.y - GAP - top;
    const below = bottom - anchor.y - size - GAP;
    const room = Math.max(above, below);
    // Keep the composer usable even with the virtual keyboard open.
    height = Math.min(height, Math.max(Math.min(300, bottom - top), room));
    x = anchor.x + size / 2 - width / 2;
    y = above >= below ? anchor.y - GAP - height : anchor.y + size + GAP;
  }
  return { x: clamp(x, left, right - width), y: clamp(y, top, bottom - height), width, height };
}
