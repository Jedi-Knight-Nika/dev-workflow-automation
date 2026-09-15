<script lang="ts">
  import { activityApi } from './api';
  import type { ActivityAggregate, Preflight } from './types';
  let {
    flight,
    detail,
    onrange
  }: { flight: Preflight; detail: number; onrange: (from: Date, to: Date) => void } = $props();
  let data = $state<ActivityAggregate | null>(null),
    error = $state('');
  const peak = $derived(Math.max(1, ...(data?.buckets.map((bucket) => bucket.events) ?? [])));
  $effect(() => {
    const request = new AbortController();
    data = null;
    error = '';
    void activityApi
      .aggregate(flight, detail, request.signal)
      .then((value) => {
        if (!request.signal.aborted) data = value;
      })
      .catch(() => {
        if (!request.signal.aborted)
          error =
            'Summary could not be loaded within its resource limit. Choose a smaller scope or range.';
      });
    return () => request.abort();
  });
</script>

<section aria-label="Activity range summary">
  <h3>Range summary</h3>
  {#if error}<p role="alert">{error}</p>{:else if !data}<p role="status">
      Summarizing recorded activity…
    </p>{:else}
    <p>
      {data.events.toLocaleString()} events · {data.unit} buckets (UTC). Select a bucket to replay that
      interval.
    </p>
    <p>
      Counts cover this snapshot. Tasks may appear in several buckets; lifecycle durations and
      receipts are available in a smaller replay.
    </p>
    <div class="buckets">
      <table>
        <thead
          ><tr
            ><th>Interval</th><th>Events</th><th>Tasks</th><th>Validation pass / fail</th><th
              >Reviews</th
            ><th>Human replies</th></tr
          ></thead
        ><tbody>
          {#each data.buckets as bucket (bucket.at)}<tr
              ><td
                ><button
                  onclick={() => {
                    const at = Date.parse(bucket.at),
                      end = at + (data?.unit === 'hour' ? 3600000 : 86400000);
                    onrange(
                      new Date(Math.max(Date.parse(flight.from), at)),
                      new Date(Math.min(Date.parse(flight.to), end - 1))
                    );
                  }}
                  >{new Date(bucket.at)
                    .toISOString()
                    .slice(0, data.unit === 'hour' ? 16 : 10)}</button
                ></td
              ><td
                ><meter min="0" max={peak} value={bucket.events} aria-label="Recorded events"
                ></meter>
                {bucket.events}</td
              ><td>{bucket.tasks}</td><td
                >{bucket.validation_passed} / {bucket.validation_failed}</td
              ><td>{bucket.reviews}</td><td>{bucket.human_responses}</td></tr
            >{/each}
        </tbody>
      </table>
    </div>
  {/if}
</section>

<style>
  section {
    margin-top: 1rem;
    font-size: 0.75rem;
  }
  p {
    color: var(--color-muted);
  }
  .buckets {
    max-height: 300px;
    overflow: auto;
  }
  table {
    width: 100%;
    border-collapse: collapse;
  }
  th,
  td {
    text-align: left;
    padding: 0.4rem;
    border-bottom: 1px solid var(--color-line);
  }
  button {
    cursor: pointer;
    color: var(--color-brand-2);
    background: transparent;
    border: 0;
    font: inherit;
  }
  meter {
    width: 45px;
  }
</style>
