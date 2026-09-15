import { CanvasRenderer } from './canvas';
import { newerCapacity } from './bottlenecks';
import type { Filters, RendererCommand, RendererMessage, ReplayConfig } from './types';

export function createRenderer(
  canvas: HTMLCanvasElement,
  config: ReplayConfig,
  receive: (message: RendererMessage) => void
) {
  let fallback: CanvasRenderer | null = null;
  let worker: Worker | null = null;
  let disposed = false;
  let index = 0;
  let filters: Filters = { actor: '', kind: '', team: '', communication: true };
  let speed = 1,
    realGaps = false;
  const publish = (message: RendererMessage) => {
    if (disposed) return;
    if (message.type === 'FRAME') index = message.frame.index;
    receive(message);
  };
  const fail = (code: 'worker_crash' | 'graphics_unavailable' = 'graphics_unavailable') => {
    if (disposed) return;
    worker?.terminate();
    worker = null;
    const previousIndex = index;
    fallback?.send({ type: 'DISPOSE' });
    fallback = new CanvasRenderer(null, publish);
    fallback.send({ type: 'LOAD', config });
    fallback.send({ type: 'SEEK', index: previousIndex });
    fallback.send({ type: 'FILTER', filters });
    fallback.send({ type: 'SPEED', speed, realGaps });
    receive({
      type: 'ERROR',
      code,
      message: 'Graphics are unavailable. Use the timeline and event inspector below.'
    });
  };
  try {
    if (typeof Worker !== 'undefined' && canvas.transferControlToOffscreen) {
      worker = new Worker(new URL('./activity.worker.ts', import.meta.url), { type: 'module' });
      worker.onmessage = (event: MessageEvent<RendererMessage>) => {
        publish(event.data);
      };
      worker.onerror = () => fail('worker_crash');
      const offscreen = canvas.transferControlToOffscreen();
      worker.postMessage({ type: 'INIT', canvas: offscreen }, [offscreen]);
      worker.postMessage({ type: 'LOAD', config });
    } else {
      const context = canvas.getContext('2d');
      if (!context) {
        fail();
      } else {
        fallback = new CanvasRenderer(context, publish);
        fallback.send({ type: 'LOAD', config });
      }
    }
  } catch {
    fail();
  }
  return {
    send(command: RendererCommand) {
      if (!disposed) {
        if (command.type === 'APPEND') {
          const unique = new Map(config.events.map((event) => [event.sequence, event]));
          for (const event of command.events) unique.set(event.sequence, event);
          if (unique.size <= config.maxEvents) config = { ...config, events: [...unique.values()] };
        } else if (command.type === 'CAPACITY') {
          if (!newerCapacity(config.capacity, command.evidence)) return;
          config = { ...config, capacity: command.evidence };
        } else if (command.type === 'MODE') config = { ...config, mode: command.mode };
        else if (command.type === 'FILTER') filters = command.filters;
        else if (command.type === 'SPEED') ({ speed, realGaps } = command);
        if (worker) {
          try {
            worker.postMessage(command);
          } catch {
            fail();
          }
        } else fallback?.send(command);
      }
    },
    dispose() {
      disposed = true;
      worker?.terminate();
      worker = null;
      fallback?.send({ type: 'DISPOSE' });
      fallback = null;
    }
  };
}
