import type { WorkflowLayout } from './services/agents';

/** Serialize layout writes and coalesce intermediate drags; never write graph configuration. */
export function createLayoutWriter(save: (layout: WorkflowLayout) => Promise<void>) {
  let pending: WorkflowLayout | undefined;
  let running: Promise<void> | undefined;
  async function drain() {
    while (pending) {
      const layout = pending;
      pending = undefined;
      try {
        await save(layout);
      } catch (error) {
        pending ??= layout;
        throw error;
      }
    }
  }
  function flush(): Promise<void> {
    if (!running)
      running = drain().finally(() => {
        running = undefined;
      });
    return running;
  }
  return {
    write(layout: WorkflowLayout) {
      pending = layout;
      return flush();
    },
    flush
  };
}
