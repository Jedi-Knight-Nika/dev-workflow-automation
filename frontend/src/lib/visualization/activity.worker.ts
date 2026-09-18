import { CanvasRenderer } from './canvas';
import type { RendererCommand } from './types';

const renderer = new CanvasRenderer(null, (message) => postMessage(message));
onmessage = (event: MessageEvent<RendererCommand>) => renderer.send(event.data);
