<script lang="ts">
  import { onMount } from 'svelte';
  import { asset } from '$app/paths';
  let { log, onclose, onerror }: { log: string; onclose: () => void; onerror: () => void } =
    $props();
  let frame = $state<HTMLIFrameElement>();
  let loading = $state(true),
    failed = $state(false),
    paused = $state(false);
  const send = (type: string) =>
    frame?.contentWindow?.postMessage({ channel: 'aew-gource', type }, window.location.origin);
  onMount(() => {
    const fail = () => {
      if (failed) return;
      send('pause');
      failed = true;
      loading = false;
      onerror();
    };
    const timeout = setTimeout(fail, 20_000);
    const message = (event: MessageEvent) => {
      if (
        failed ||
        !frame ||
        event.source !== frame.contentWindow ||
        event.origin !== window.location.origin ||
        event.data?.channel !== 'aew-gource'
      )
        return;
      if (event.data.type === 'ready')
        frame.contentWindow?.postMessage(
          { channel: 'aew-gource', type: 'load', log },
          window.location.origin
        );
      if (event.data.type === 'loaded' || event.data.type === 'error') {
        clearTimeout(timeout);
        loading = false;
        if (event.data.type === 'error') fail();
        if (document.hidden) send('pause');
      }
    };
    const visibility = () => send(document.hidden || paused ? 'pause' : 'resume');
    window.addEventListener('message', message);
    document.addEventListener('visibilitychange', visibility);
    return () => {
      clearTimeout(timeout);
      window.removeEventListener('message', message);
      document.removeEventListener('visibilitychange', visibility);
    };
  });
</script>

<section aria-label="Gource historical replay" class="gource">
  <header>
    <div>
      <h3>Gource code replay</h3>
      <p>Frozen file history · independent playback · drag to move, scroll to zoom</p>
    </div>
    <button onclick={onclose}>Return to activity replay</button>
  </header>
  {#if loading}<p role="status">Initializing the optional WebAssembly renderer…</p>{/if}
  {#if failed}<p role="alert">
      Gource could not render this snapshot. Return to activity replay to use the Canvas view.
    </p>{/if}
  {#if !failed}<iframe
      bind:this={frame}
      title="Gource code visualization"
      src={asset('/gource/index.html')}
      sandbox="allow-scripts allow-same-origin"
      allow="fullscreen"
    ></iframe>{/if}
  <footer>
    <button
      disabled={loading || failed}
      onclick={() => {
        paused = !paused;
        send(paused ? 'pause' : 'resume');
      }}>{paused ? 'Resume Gource' : 'Pause Gource'}</button
    ><span
      >Gource Web · <a href={asset('/gource/vendor/COPYING')} target="_blank" rel="noreferrer"
        >License</a
      >
      · <a href={asset('/gource/vendor/source.tar.gz')} download>Corresponding source</a></span
    >
  </footer>
</section>

<style>
  .gource {
    position: absolute;
    inset: 0;
    z-index: 5;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    background: var(--color-panel);
  }
  header,
  footer {
    padding: 0.8rem 1rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    flex-shrink: 0;
  }
  h3,
  p {
    margin: 0;
  }
  p,
  footer {
    font-size: 0.75rem;
    color: var(--color-muted);
  }
  iframe {
    width: 100%;
    flex: 1;
    border: 0;
    min-height: 0;
  }
  button {
    cursor: pointer;
    background: var(--color-panel-alt);
    color: var(--color-text);
    border: 1px solid var(--color-line);
    padding: 0.5rem;
    border-radius: 6px;
  }
  a {
    color: var(--color-brand-2);
  }
  [role='alert'] {
    padding: 0.8rem;
    color: var(--color-danger);
  }
</style>
