<script lang="ts">
  import { answerHumanRequest, type HumanRequest } from '$lib/services/coordination';
  let { request, onAnswered }: { request: HumanRequest; onAnswered: () => void } = $props();
  let answer = $state(''),
    busy = $state(false),
    error = $state('');
  let submitted = $state(false);
  async function submit() {
    if (!answer.trim() || busy || submitted) return;
    busy = true;
    error = '';
    try {
      await answerHumanRequest(request, answer.trim());
      submitted = true;
      onAnswered();
    } catch (cause) {
      error = String(cause);
    } finally {
      busy = false;
    }
  }
</script>

<form
  class="space-y-3 rounded-xl border border-warning/40 bg-panel p-4"
  onsubmit={(event) => {
    event.preventDefault();
    void submit();
  }}
>
  <p class="text-xs font-semibold text-warning">Needs you · Coordinator</p>
  <p class="font-medium">{request.question}</p>
  <p class="text-sm text-muted">{request.why_needed}</p>
  {#if request.choices.length}
    <div class="flex flex-wrap gap-2">
      {#each request.choices as choice (choice)}<button
          type="button"
          class="btn-secondary"
          aria-pressed={answer === choice}
          onclick={() => (answer = choice)}>{choice}</button
        >{/each}
    </div>
  {/if}
  <label class="block text-sm"
    >Your answer<textarea class="input mt-1 w-full" rows="2" maxlength="8000" bind:value={answer}
    ></textarea></label
  >
  {#if error}<p role="alert" class="text-sm text-danger">{error}</p>{/if}
  <button type="submit" class="btn-primary" disabled={busy || submitted || !answer.trim()}
    >{submitted ? 'Answer queued' : busy ? 'Sending…' : 'Send & continue'}</button
  >
</form>
