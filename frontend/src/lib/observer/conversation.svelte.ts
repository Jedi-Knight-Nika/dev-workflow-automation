import { observerApi, streamAnswer } from './api';
import { applyReplyEvent } from './messages';
import type { Conversation, ObserverMessage, ObserverScope } from './types';

type ConversationOptions = {
  enabled: () => boolean;
  name: () => string;
  scope: () => ObserverScope;
  open: () => boolean;
  reply: (answer: string) => void;
  scroll: () => void;
  changeScope: (scope: ObserverScope | null) => void;
  refresh: () => Promise<void>;
};

export function createObserverConversation(options: ConversationOptions) {
  const state = $state({
    busy: false,
    input: '',
    error: '',
    activity: '',
    messages: [] as ObserverMessage[],
    id: undefined as string | undefined,
    conversations: [] as Conversation[],
    showHistory: false,
    showChanges: false,
    showAttention: false
  });
  let request: AbortController | undefined;

  async function send(question = state.input) {
    const message = question.trim();
    if (!message || state.busy || !options.enabled()) return;
    state.input = '';
    state.error = '';
    state.busy = true;
    state.activity = 'Reading product facts';
    request?.abort();
    const controller = new AbortController();
    request = controller;
    const responseId = crypto.randomUUID();
    state.messages = [
      ...state.messages,
      { id: crypto.randomUUID(), role: 'user', content: message, sources: [] },
      { id: responseId, role: 'assistant', content: '', sources: [] }
    ];
    try {
      const created = await observerApi.question(
        message,
        options.scope(),
        state.id,
        controller.signal
      );
      state.id = created.conversation_id;
      await streamAnswer(
        created.request_id,
        (event) => {
          if (controller.signal.aborted) return;
          const failureMessage = event.message || `${options.name()} unavailable.`;
          state.messages = applyReplyEvent(state.messages, responseId, event, failureMessage);
          if (event.type === 'observer.tool_started')
            state.activity = `Reading ${(event.tool || 'facts').replaceAll('_', ' ')}`;
          if (event.type === 'observer.model_started')
            state.activity = 'Local AI · composing an explanation';
          if (event.type === 'observer.text_delta') {
            state.activity = 'Answering';
          }
          if (event.type === 'observer.completed') {
            state.activity =
              event.mode === 'local'
                ? 'Local Ollama · source-backed explanation'
                : event.reason || 'Deterministic facts';
            if (!options.open()) {
              options.reply(event.answer || '');
            }
          }
          if (event.type === 'observer.failed') {
            state.error = failureMessage;
          }
          options.scroll();
        },
        controller.signal
      );
    } catch {
      if (!controller.signal.aborted)
        state.error = `${options.name()} could not finish this answer. Saved conversations remain in History.`;
    } finally {
      if (request === controller) state.busy = false;
      state.messages = state.messages.map((message) =>
        message.id === responseId && !message.content
          ? {
              ...message,
              content: controller.signal.aborted
                ? 'Reply cancelled because the chat was reset or assistant settings changed. Send again when ready; no automatic AI retry was started.'
                : state.error || 'The reply was interrupted. Please try again.'
            }
          : message
      );
    }
  }

  async function history() {
    try {
      state.conversations = await observerApi.conversations();
      state.showHistory = !state.showHistory;
    } catch {
      state.error = 'History unavailable.';
    }
  }
  async function loadConversation(item: Conversation) {
    try {
      request?.abort();
      state.busy = false;
      state.messages = await observerApi.history(item.id);
      options.changeScope(item.scope);
      state.id = item.id;
      state.showHistory = false;
      await options.refresh();
    } catch {
      state.error = 'Could not load that conversation.';
    }
  }

  function abort() {
    request?.abort();
  }

  function reset() {
    abort();
    state.busy = false;
    state.messages = [];
    state.id = undefined;
    state.showHistory = false;
    options.changeScope(null);
  }

  return { state, send, history, loadConversation, abort, reset };
}

export type ObserverConversation = ReturnType<typeof createObserverConversation>;
