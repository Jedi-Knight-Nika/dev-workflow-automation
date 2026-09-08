import type { OrbMode } from './types';
import type { DisplayMode } from '$lib/display.svelte';

/** Small deterministic particle field. Owns no requests, application state or inference. */
export function createHalo(
  canvas: HTMLCanvasElement,
  getMode: () => OrbMode,
  getDisplayMode: () => DisplayMode
) {
  const ctx = canvas.getContext('2d');
  if (!ctx) return { refresh() {}, destroy() {} };
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  let frame = 0;
  let last = 0;
  let size = 96;
  let accent = '#65e5d4';
  let destroyed = false;

  function resize() {
    size = canvas.getBoundingClientRect().width || 96;
    const dpr = Math.min(devicePixelRatio || 1, 2);
    canvas.width = Math.round(size * dpr);
    canvas.height = Math.round(size * dpr);
    ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function paint(now: number) {
    if (!ctx || destroyed) return;
    const mode = getMode();
    const jarvis = getDisplayMode() === 'jarvis';
    const t = reduced.matches ? 0 : now / 1000;
    const urgent = mode === 'thinking' || mode === 'speaking';
    const color =
      mode === 'critical'
        ? '#fb7185'
        : mode === 'warning'
          ? '#fbbf24'
          : mode === 'offline'
            ? '#94a3b8'
            : accent;
    const alpha = mode === 'sleeping' ? 0.55 : 1;
    ctx.clearRect(0, 0, size, size);
    const center = size / 2;
    ctx.globalAlpha = alpha;
    const haze = ctx.createRadialGradient(center, center, size * 0.08, center, center, size * 0.47);
    haze.addColorStop(0, color + '18');
    haze.addColorStop(0.66, color + '12');
    haze.addColorStop(1, color + '00');
    ctx.fillStyle = haze;
    ctx.fillRect(0, 0, size, size);
    ctx.fillStyle = color;
    if (!jarvis) {
      // Default mode is a quiet, continuous ring. The HUD particle field is opt-in.
      ctx.strokeStyle = color;
      ctx.lineWidth = Math.max(1, size * 0.018);
      ctx.globalAlpha = alpha * 0.25;
      ctx.beginPath();
      ctx.arc(center, center, size * 0.3, 0, Math.PI * 2);
      ctx.stroke();
      ctx.globalAlpha = alpha * 0.8;
      ctx.lineCap = 'round';
      ctx.beginPath();
      ctx.arc(
        center,
        center,
        size * 0.3,
        t * (urgent ? 1.6 : 0.22),
        t * (urgent ? 1.6 : 0.22) + Math.PI * 1.15
      );
      ctx.stroke();
      ctx.lineCap = 'butt';
    }
    // Jarvis: five warped shells, 340 points total. No per-frame DOM or large allocations.
    for (let ring = 0; ring < (jarvis ? 5 : 0); ring++) {
      for (let point = 0; point < 68; point++) {
        const angle = (point / 68) * Math.PI * 2 + t * (urgent ? 0.35 : 0.09) * (ring % 2 ? -1 : 1);
        const wave =
          Math.sin(angle * 3 + t * 0.8 + ring * 0.7) * 0.025 +
          Math.cos(angle * 5 - t * 0.6) * 0.016;
        const radius = size * (0.28 + ring * 0.019 + wave);
        const lift = Math.sin(angle * 2 + t + ring) * size * 0.024;
        const x = center + Math.cos(angle) * radius;
        const y = center + Math.sin(angle) * radius * 0.87 + lift;
        ctx.globalAlpha = alpha * (0.17 + (0.55 * (1 + Math.sin(angle + t * 0.3 + ring))) / 2);
        ctx.beginPath();
        ctx.arc(
          x,
          y,
          size * (0.003 + (0.002 * (1 + Math.sin(point * 7 + ring))) / 2),
          0,
          Math.PI * 2
        );
        ctx.fill();
      }
    }
    ctx.globalAlpha = alpha * 0.9;
    ctx.shadowBlur = size * 0.07;
    ctx.shadowColor = color;
    ctx.beginPath();
    ctx.arc(
      center,
      center,
      size * (0.034 + Math.sin(t * (urgent ? 3 : 1)) * 0.007),
      0,
      Math.PI * 2
    );
    ctx.fill();
    ctx.shadowBlur = 0;
    ctx.globalAlpha = 1;
  }

  function tick(now: number) {
    if (destroyed || document.hidden) return;
    // 24 fps while responding, 15 fps idle, one static frame for reduced motion.
    const interval = ['thinking', 'speaking'].includes(getMode())
      ? 1000 / 24
      : 1000 / (getDisplayMode() === 'jarvis' ? 15 : 12);
    if (now - last >= interval) {
      paint(now);
      last = now;
    }
    if (!reduced.matches) frame = requestAnimationFrame(tick);
  }
  function resume() {
    cancelAnimationFrame(frame);
    if (!document.hidden) {
      paint(performance.now());
      if (!reduced.matches) frame = requestAnimationFrame(tick);
    }
  }
  function theme() {
    // Match the accent hue the rest of the HUD chrome (brackets, radar, grid)
    // settled on - brand-2, not the primary brand color - so the orb reads as
    // part of the same system instead of a mismatched hue.
    const token = getComputedStyle(document.documentElement)
      .getPropertyValue('--color-brand-2')
      .trim();
    accent = /^#[\da-f]{6}$/i.test(token) ? token : '#65e5d4';
    resume();
  }
  const observer = new ResizeObserver(() => {
    resize();
    resume();
  });
  const themeObserver = new MutationObserver(theme);
  observer.observe(canvas);
  themeObserver.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['class', 'style', 'data-theme', 'data-display']
  });
  document.addEventListener('visibilitychange', resume);
  reduced.addEventListener('change', resume);
  resize();
  theme();
  return {
    refresh: resume,
    destroy: () => {
      destroyed = true;
      cancelAnimationFrame(frame);
      observer.disconnect();
      themeObserver.disconnect();
      document.removeEventListener('visibilitychange', resume);
      reduced.removeEventListener('change', resume);
    }
  };
}
