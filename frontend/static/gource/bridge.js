/* global GourceModule */
// Only the pinned engine is loaded. No upstream authentication, cloning or proxy UI.
const canvas = document.getElementById('canvas');
const status = document.getElementById('status');
const send = (type) => parent.postMessage({ channel: 'aew-gource', type }, location.origin);
let engine;
let loaded = false;
const fail = () => {
  status.textContent = 'Gource is unavailable. Return to the Canvas view.';
  send('error');
};
const resize = () => {
  canvas.width = Math.max(1, innerWidth);
  canvas.height = Math.max(1, innerHeight);
};
resize();
addEventListener('resize', resize);
canvas.addEventListener('webglcontextlost', (event) => {
  event.preventDefault();
  fail();
});
addEventListener('error', fail);
addEventListener('unhandledrejection', fail);
addEventListener('message', (event) => {
  if (
    event.source !== parent ||
    event.origin !== location.origin ||
    event.data?.channel !== 'aew-gource' ||
    !engine
  )
    return;
  try {
    if (event.data.type === 'load' && !loaded) {
      const log = event.data.log;
      if (typeof log !== 'string' || !log || new TextEncoder().encode(log).byteLength > 8_000_000) {
        fail();
        return;
      }
      if (engine.ccall('gource_load_log', 'number', ['string'], [log]) !== 1) {
        fail();
        return;
      }
      loaded = true;
      status.textContent = '';
      send('loaded');
    } else if (event.data.type === 'pause') {
      engine.ccall('gource_pause', null, [], []);
      engine.pauseMainLoop?.();
    } else if (event.data.type === 'resume') {
      engine.resumeMainLoop?.();
      engine.ccall('gource_resume', null, [], []);
    }
  } catch {
    fail();
  }
});
GourceModule({
  canvas,
  locateFile: (path) => new URL(`vendor/${path.split('/').pop()}`, location.href).href,
  print: () => {},
  printErr: () => {},
  onAbort: fail
})
  .then((module) => {
    engine = module;
    resize();
    send('ready');
  })
  .catch(fail);
