<script lang="ts">
  import { duration } from './format';
  import type { Bottlenecks } from './bottlenecks';
  let { values, live }: { values: Bottlenecks; live: boolean } = $props();
  const percent = (value: number | null) => (value === null ? 'unknown' : `${value.toFixed(1)}%`);
</script>

<details>
  <summary>Bottlenecks and Team capacity</summary>
  <div>
    <p>
      {percent(values.reviewPercent)} of recorded task time waiting for review · {percent(
        values.humanPercent
      )} waiting for people · {percent(values.unknownPercent)} with unknown state.
    </p>
    <p>
      At the playhead: {values.waitingHuman} tasks need a person · {values.waitingReview} await review
      · {values.blocked} blocked on other external conditions.
    </p>
    <p>
      Capacity covers Team-wide recorded agent jobs and policy limits, attributed using current task
      Teams. Intervals before policy history began are unknown.{live
        ? ' Capacity updates with live activity, about every 10 seconds. Pausing preserves the playhead.'
        : ''}
    </p>
    {#each values.capacity as team (team.id)}<p>
        <b>{team.name}</b>: {duration(team.saturatedMs)} at or above capacity / {duration(
          team.observedMs
        )} observed · {duration(team.unknownMs)} unknown · peak {team.peak} concurrent tasks · {percent(
          team.availableSlotMs ? (100 * team.utilizedSlotMs) / team.availableSlotMs : null
        )} slot utilization{team.partial
          ? ' · partial execution history; observed totals are not exact'
          : ''}
      </p>{:else}<p>No capacity evidence in this snapshot.</p>{/each}
  </div>
</details>

<style>
  details {
    padding: 0.5rem 1rem;
    font-size: 0.73rem;
    flex-shrink: 0;
    border-top: 1px solid var(--color-line);
  }
  summary {
    cursor: pointer;
  }
  div {
    max-height: 150px;
    overflow: auto;
  }
  p {
    margin: 0.5rem 0;
    color: var(--color-muted);
  }
  b {
    color: var(--color-text);
  }
</style>
