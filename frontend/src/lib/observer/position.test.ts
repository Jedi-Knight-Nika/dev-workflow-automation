import { describe, expect, it } from 'vitest';
import { dockPosition, normalizePosition, placePopup, readPosition } from './position';

describe('Observer floating placement', () => {
  it('restores a relative position and clamps corrupt or off-screen saved data', () => {
    expect(readPosition('not-json')).toBeNull();
    expect(readPosition('{"x":"0.5","y":0}')).toBeNull();
    expect(readPosition('{"x":2,"y":-1}')).toEqual({ x: 1, y: 0 });
    const viewport = { left: 0, top: 0, width: 1440, height: 900 };
    const point = { x: 340, y: 230 };
    const saved = normalizePosition(point, viewport, 78);
    expect(dockPosition(saved, viewport, 78)).toEqual(point);
    expect(normalizePosition({ x: -500, y: 2000 }, viewport, 78)).toEqual({ x: 0, y: 1 });
  });

  it.each([
    { left: 0, top: 0, width: 1440, height: 900 },
    { left: 0, top: 0, width: 390, height: 844 },
    { left: 0, top: 0, width: 844, height: 390 },
    { left: 0, top: 170, width: 390, height: 340 }
  ])('keeps the launcher, popup and notice visible after resize: %j', (viewport) => {
    const size = viewport.width <= 640 ? 66 : 78;
    for (const x of [0, 0.25, 0.5, 0.75, 1]) {
      for (const y of [0, 0.25, 0.5, 0.75, 1]) {
        const anchor = dockPosition({ x, y }, viewport, size);
        for (const [width, height] of [
          [460, 700],
          [280, 120]
        ]) {
          const box = placePopup(anchor, size, viewport, width, height);
          expect(box.x).toBeGreaterThanOrEqual(viewport.left + 12);
          expect(box.y).toBeGreaterThanOrEqual(viewport.top + 12);
          expect(box.x + box.width).toBeLessThanOrEqual(viewport.left + viewport.width - 12);
          expect(box.y + box.height).toBeLessThanOrEqual(viewport.top + viewport.height - 12);
        }
      }
    }
  });
});
