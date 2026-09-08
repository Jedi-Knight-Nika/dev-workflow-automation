<script lang="ts">
  const nodes = [
    { left: 8, top: 22, duration: 13, delay: 0 },
    { left: 18, top: 68, duration: 16, delay: 2.4 },
    { left: 34, top: 40, duration: 11, delay: 5.1 },
    { left: 52, top: 78, duration: 15, delay: 1.2 },
    { left: 67, top: 18, duration: 12, delay: 3.6 },
    { left: 81, top: 55, duration: 17, delay: 6.3 },
    { left: 91, top: 30, duration: 14, delay: 0.8 },
    { left: 45, top: 12, duration: 18, delay: 4.4 }
  ];

  // A handful of node pairs wired with a static "data link" tracer line.
  const links = [
    [0, 2],
    [2, 4],
    [4, 6],
    [1, 3]
  ];
</script>

<div class="jarvis-root" aria-hidden="true">
  <div class="grid"></div>
  <div class="texture"></div>
  <svg class="links" preserveAspectRatio="none" viewBox="0 0 100 100">
    {#each links as [a, b], index (index)}
      <line
        x1={nodes[a].left}
        y1={nodes[a].top}
        x2={nodes[b].left}
        y2={nodes[b].top}
        class="link"
        style={`animation-delay: ${index * 0.9}s`}
      />
    {/each}
  </svg>
  {#each nodes as node, index (index)}
    <span
      class="node"
      style={`left: ${node.left}%; top: ${node.top}%; animation-duration: ${node.duration}s; animation-delay: ${node.delay}s;`}
    ></span>
  {/each}
  <div class="scan-beam"></div>
  <span class="bracket tl"></span>
  <span class="bracket tr"></span>
  <span class="bracket bl"></span>
  <span class="bracket br"></span>
  <div class="dial dial-tl">
    <span class="dial-ring"></span>
  </div>
  <div class="dial dial-br">
    <span class="dial-ring"></span>
    <span class="dial-ring dial-ring-inner"></span>
    <span class="dial-sweep"></span>
    <span class="dial-core"></span>
    {#each Array.from({ length: 12 }, (_, i) => i * 30) as angle, index (angle)}
      <span
        class="dial-tick"
        style={`transform: rotate(${angle}deg) translateY(-58px); animation-delay: ${index * 0.18}s;`}
      ></span>
    {/each}
  </div>
</div>

<style>
  .jarvis-root {
    position: fixed;
    inset: 0;
    z-index: 20;
    pointer-events: none;
    overflow: hidden;
  }
  .grid {
    position: absolute;
    inset: -48px;
    background-image:
      linear-gradient(color-mix(in srgb, var(--color-brand-2) 12%, transparent) 1px, transparent 1px),
      linear-gradient(
        90deg,
        color-mix(in srgb, var(--color-brand-2) 12%, transparent) 1px,
        transparent 1px
      );
    background-size: 48px 48px;
    opacity: 0.2;
    mix-blend-mode: screen;
    animation: -global-jarvis-grid-drift 16s linear infinite;
  }
  .texture {
    position: absolute;
    inset: 0;
    background: repeating-linear-gradient(
      to bottom,
      color-mix(in srgb, var(--color-brand-2) 5%, transparent) 0px,
      transparent 1px,
      transparent 3px
    );
    mix-blend-mode: overlay;
    opacity: 0.4;
  }
  .links {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    opacity: 0.35;
    mix-blend-mode: screen;
  }
  .link {
    stroke: var(--color-brand-2);
    stroke-width: 0.12;
    stroke-dasharray: 1.2 2.4;
    vector-effect: non-scaling-stroke;
    animation: -global-jarvis-link-flow 5s linear infinite;
  }
  .node {
    position: absolute;
    width: 4px;
    height: 4px;
    border-radius: 50%;
    background: var(--color-brand-2);
    box-shadow: 0 0 7px 1px color-mix(in srgb, var(--color-brand-2) 65%, transparent);
    mix-blend-mode: screen;
    animation-name: -global-jarvis-float;
    animation-timing-function: ease-in-out;
    animation-iteration-count: infinite;
  }
  .scan-beam {
    position: absolute;
    left: 0;
    right: 0;
    top: 0;
    height: 2px;
    background: linear-gradient(
      90deg,
      transparent,
      color-mix(in srgb, var(--color-brand) 65%, transparent) 20%,
      color-mix(in srgb, var(--color-brand-2) 80%, transparent) 50%,
      color-mix(in srgb, var(--color-brand) 65%, transparent) 80%,
      transparent
    );
    box-shadow: 0 0 14px 2px color-mix(in srgb, var(--color-brand-2) 50%, transparent);
    mix-blend-mode: screen;
    animation: -global-jarvis-scan 8s linear infinite;
  }
  .bracket {
    position: absolute;
    width: 30px;
    height: 30px;
    opacity: 0.5;
    filter: drop-shadow(0 0 6px color-mix(in srgb, var(--color-brand-2) 55%, transparent));
    animation: -global-jarvis-pulse 3.4s ease-in-out infinite;
  }
  .bracket.tl {
    top: 14px;
    left: 14px;
    border-top: 2px solid var(--color-brand-2);
    border-left: 2px solid var(--color-brand-2);
    border-top-left-radius: 6px;
  }
  .bracket.tr {
    top: 14px;
    right: 14px;
    border-top: 2px solid var(--color-brand-2);
    border-right: 2px solid var(--color-brand-2);
    border-top-right-radius: 6px;
    animation-delay: 0.4s;
  }
  .bracket.bl {
    bottom: 14px;
    left: 14px;
    border-bottom: 2px solid var(--color-brand-2);
    border-left: 2px solid var(--color-brand-2);
    border-bottom-left-radius: 6px;
    animation-delay: 0.8s;
  }
  .bracket.br {
    bottom: 14px;
    right: 14px;
    border-bottom: 2px solid var(--color-brand-2);
    border-right: 2px solid var(--color-brand-2);
    border-bottom-right-radius: 6px;
    animation-delay: 1.2s;
  }
  .dial {
    position: absolute;
    width: 120px;
    height: 120px;
    border-radius: 50%;
    opacity: 0.32;
  }
  .dial-tl {
    top: 40px;
    left: 40px;
    width: 56px;
    height: 56px;
    opacity: 0.22;
  }
  .dial-br {
    right: 28px;
    bottom: 28px;
    filter: drop-shadow(0 0 14px color-mix(in srgb, var(--color-brand-2) 40%, transparent));
  }
  .dial-ring {
    position: absolute;
    inset: 0;
    border-radius: 50%;
    border: 1px solid color-mix(in srgb, var(--color-brand-2) 45%, transparent);
  }
  .dial-ring-inner {
    inset: 16px;
    border: 1px dashed color-mix(in srgb, var(--color-brand-2) 30%, transparent);
  }
  .dial-sweep {
    position: absolute;
    inset: 0;
    border-radius: 50%;
    background: conic-gradient(
      from 0deg,
      color-mix(in srgb, var(--color-brand-2) 55%, transparent),
      transparent 30%
    );
    mix-blend-mode: screen;
    animation: -global-jarvis-spin 4s linear infinite;
  }
  .dial-core {
    position: absolute;
    top: 50%;
    left: 50%;
    width: 6px;
    height: 6px;
    margin: -3px;
    border-radius: 50%;
    background: var(--color-brand-2);
    box-shadow: 0 0 10px 2px color-mix(in srgb, var(--color-brand-2) 65%, transparent);
  }
  .dial-tick {
    position: absolute;
    top: 50%;
    left: 50%;
    width: 2px;
    height: 6px;
    margin: -3px 0 0 -1px;
    background: color-mix(in srgb, var(--color-brand-2) 30%, transparent);
    animation: -global-jarvis-tick-pulse 2.2s ease-in-out infinite;
  }
  @media (prefers-reduced-motion: reduce) {
    .scan-beam,
    .bracket,
    .dial-tick,
    .dial-sweep,
    .grid,
    .node,
    .link {
      animation: none;
    }
    .node {
      display: none;
    }
  }
  @media (max-width: 640px) {
    .dial-br {
      width: 84px;
      height: 84px;
    }
    .dial-tl {
      display: none;
    }
  }

  /* Light theme reads glow poorly (screen-blend washes out on white), so trade
     the neon-glow language for a crisper blueprint/schematic look instead. */
  :root[data-theme='light'] .jarvis-root .grid,
  :root[data-theme='light'] .jarvis-root .links,
  :root[data-theme='light'] .jarvis-root .scan-beam,
  :root[data-theme='light'] .jarvis-root .dial-sweep,
  :root[data-theme='light'] .jarvis-root .node {
    mix-blend-mode: multiply;
  }
  :root[data-theme='light'] .jarvis-root .texture {
    opacity: 0.15;
  }
  :root[data-theme='light'] .jarvis-root .grid {
    opacity: 0.16;
  }
  :root[data-theme='light'] .jarvis-root .links {
    opacity: 0.3;
  }
  @media (prefers-color-scheme: light) {
    :root:not([data-theme='dark']) .jarvis-root .grid,
    :root:not([data-theme='dark']) .jarvis-root .links,
    :root:not([data-theme='dark']) .jarvis-root .scan-beam,
    :root:not([data-theme='dark']) .jarvis-root .dial-sweep,
    :root:not([data-theme='dark']) .jarvis-root .node {
      mix-blend-mode: multiply;
    }
    :root:not([data-theme='dark']) .jarvis-root .texture {
      opacity: 0.15;
    }
    :root:not([data-theme='dark']) .jarvis-root .grid {
      opacity: 0.16;
    }
    :root:not([data-theme='dark']) .jarvis-root .links {
      opacity: 0.3;
    }
  }

  @keyframes -global-jarvis-scan {
    0% {
      transform: translateY(0);
      opacity: 0;
    }
    5% {
      opacity: 0.55;
    }
    95% {
      opacity: 0.55;
    }
    100% {
      transform: translateY(100vh);
      opacity: 0;
    }
  }
  @keyframes -global-jarvis-pulse {
    0%,
    100% {
      opacity: 0.35;
    }
    50% {
      opacity: 0.8;
    }
  }
  @keyframes -global-jarvis-spin {
    to {
      transform: rotate(360deg);
    }
  }
  @keyframes -global-jarvis-grid-drift {
    from {
      background-position:
        0 0,
        0 0;
    }
    to {
      background-position:
        48px 48px,
        48px 48px;
    }
  }
  @keyframes -global-jarvis-float {
    0% {
      transform: translateY(0) scale(0.6);
      opacity: 0;
    }
    15% {
      opacity: 0.8;
    }
    85% {
      opacity: 0.8;
    }
    100% {
      transform: translateY(-130px) scale(1);
      opacity: 0;
    }
  }
  @keyframes -global-jarvis-link-flow {
    to {
      stroke-dashoffset: -36;
    }
  }
  @keyframes -global-jarvis-tick-pulse {
    0%,
    100% {
      background: color-mix(in srgb, var(--color-brand-2) 30%, transparent);
    }
    50% {
      background: color-mix(in srgb, var(--color-brand-2) 95%, transparent);
    }
  }
</style>
