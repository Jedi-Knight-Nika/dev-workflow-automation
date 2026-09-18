<script lang="ts">
  import { duration, title } from './format';
  import type { ProcessMetrics } from './process-metrics';
  let { metrics }: { metrics: ProcessMetrics } = $props();
</script>

<details>
  <summary>Process and code summary</summary>
  <div class="metrics">
    <p>Recorded task time through the playhead; concurrent tasks contribute separately.</p>
    <dl>
      {#each Object.entries(metrics.time) as [name, elapsed] (name)}
        {#if elapsed > 0}<div>
            <dt>{title(name)}</dt>
            <dd>{duration(elapsed)}</dd>
          </div>{/if}
      {/each}
    </dl>
    <p>
      First-attempt queue time: {duration(metrics.queueMs)}{metrics.unknownQueueRuns
        ? ` · ${metrics.unknownQueueRuns} runs with unknown queue time`
        : ''}. Queue time overlaps task time.
    </p>
    <p>
      {metrics.validationPassed} validation passes · {metrics.validationFailed} failures · {metrics.failedChecks}
      unsuccessful checks · {metrics.repairs} entries into repair
    </p>
    <p>
      First validation in this range: {metrics.firstValidation ?? 'not recorded'} · {metrics.reviews}
      reviews · {metrics.humanResponses} human responses
    </p>
    <p>
      {metrics.ciFailedChecks} failed CI checks/status contexts · {metrics.ciFailedSuites} failed CI suites.
      Suites are counted separately from their checks; repeated notifications are deduplicated.
      {metrics.ciUnknown
        ? `${metrics.ciUnknown} CI observations have incomplete identity or outcome.`
        : ''}
    </p>
    <p>
      {metrics.manualTakeovers} manual code takeovers across {metrics.manualTasks} tasks. This records
      operator takeover, not inferred source edits.
    </p>
    <p>
      {metrics.files} observed files · {metrics.directories} directories · {metrics.testsChanged} test
      files · +{metrics.added} / −{metrics.deleted} known lines
    </p>
    {#if metrics.incompleteFiles}<p>
        File or line detail is incomplete. Totals cover collected validated commits only.
      </p>{/if}
    {#if metrics.languages.length}<p>
        Languages by file extension: {metrics.languages.join(', ')}
      </p>{/if}
    {#if metrics.hotFiles.length}<p>Most frequently changed files</p>
      <ul>
        {#each metrics.hotFiles as file, index (index)}<li>
            {file.path} · {file.touches} changes
          </li>{/each}
      </ul>{/if}
  </div>
</details>

<style>
  details {
    border-top: 1px solid var(--color-line);
    padding: 0.5rem 1rem;
    flex-shrink: 0;
    font-size: 0.73rem;
  }
  summary {
    cursor: pointer;
  }
  .metrics {
    max-height: 160px;
    overflow: auto;
  }
  p,
  ul {
    margin: 0.5rem 0;
    color: var(--color-muted);
  }
  dl {
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
  }
  dt {
    text-transform: capitalize;
  }
  dd {
    margin: 0;
  }
</style>
