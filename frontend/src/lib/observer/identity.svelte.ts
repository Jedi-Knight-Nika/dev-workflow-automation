/** Display identity only. Never part of a Developer or local-model prompt. */
let name = $state('Jarvis');

export function getAssistantName(): string {
  return name;
}

export function setAssistantName(value: string | undefined): void {
  name = value?.trim() || 'Jarvis';
}

export function notifyAssistantConfiguration(): void {
  window.dispatchEvent(new Event('observer:configuration'));
  if (typeof BroadcastChannel !== 'undefined') {
    const channel = new BroadcastChannel('observer-configuration');
    channel.postMessage('changed');
    channel.close();
  }
}
