import type { ActivityEvent, TaskState } from './types';

export type TimeBucket =
  | 'coding'
  | 'planning'
  | 'validation'
  | 'review'
  | 'human'
  | 'checks'
  | 'blocked'
  | 'paused'
  | 'delivery'
  | 'unstarted'
  | 'unknown';
export type ProcessMetrics = {
  time: Record<TimeBucket, number>;
  queueMs: number;
  unknownQueueRuns: number;
  repairs: number;
  validationPassed: number;
  validationFailed: number;
  failedChecks: number;
  reviews: number;
  humanResponses: number;
  firstValidation: 'passed' | 'failed' | null;
  ciFailedChecks: number;
  ciFailedSuites: number;
  ciUnknown: number;
  manualTakeovers: number;
  manualTasks: number;
  files: number;
  directories: number;
  testsChanged: number;
  added: number;
  deleted: number;
  incompleteFiles: boolean;
  languages: string[];
  hotFiles: { path: string; touches: number }[];
};

function bucket(task: TaskState): TimeBucket | null {
  if (task.status === 'UNKNOWN') return 'unknown';
  if (task.status === 'NEW') return 'unstarted';
  if (task.status === 'PAUSED') return 'paused';
  if (task.status === 'WAITING_HUMAN') return 'human';
  if (task.status === 'WAITING_EXTERNAL')
    return task.wait_reason === 'GITHUB_REVIEW'
      ? 'review'
      : task.wait_reason === 'GITHUB_CHECKS'
        ? 'checks'
        : 'blocked';
  if (task.status !== 'ACTIVE') return null;
  switch (task.stage) {
    case 'DEVELOPING':
    case 'FIXING':
      return 'coding';
    case 'VALIDATING':
      return 'validation';
    case 'PLANNING':
      return 'planning';
    case 'PUBLISHING':
    case 'MERGING':
      return 'delivery';
    default:
      return 'unknown';
  }
}

const count = (value: unknown) =>
  typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : 0;
const languages: Record<string, string> = {
  py: 'Python',
  ts: 'TypeScript',
  tsx: 'TypeScript',
  js: 'JavaScript',
  jsx: 'JavaScript',
  svelte: 'Svelte',
  go: 'Go',
  rs: 'Rust',
  java: 'Java',
  rb: 'Ruby',
  css: 'CSS',
  html: 'HTML',
  sql: 'SQL'
};

/** Derived only from recorded facts. Queue time overlaps task time and is reported separately. */
export class ProcessAccumulator {
  private failedCiChecks = new Set<string>();
  private failedCiSuites = new Set<string>();
  private unknownCi = new Set<string>();
  private ciNotifications = new Set<string>();
  private ciOutcomes = new Set<string>();
  private takeovers = new Set<string>();
  private manualTasks = new Set<string>();
  private files = new Map<string, { path: string; touches: number }>();
  private directories = new Set<string>();
  private tests = new Set<string>();
  private languages = new Set<string>();
  readonly values: ProcessMetrics = {
    time: {
      coding: 0,
      planning: 0,
      validation: 0,
      review: 0,
      human: 0,
      checks: 0,
      blocked: 0,
      paused: 0,
      delivery: 0,
      unstarted: 0,
      unknown: 0
    },
    queueMs: 0,
    unknownQueueRuns: 0,
    repairs: 0,
    validationPassed: 0,
    validationFailed: 0,
    failedChecks: 0,
    reviews: 0,
    humanResponses: 0,
    firstValidation: null,
    ciFailedChecks: 0,
    ciFailedSuites: 0,
    ciUnknown: 0,
    manualTakeovers: 0,
    manualTasks: 0,
    files: 0,
    directories: 0,
    testsChanged: 0,
    added: 0,
    deleted: 0,
    incompleteFiles: false,
    languages: [],
    hotFiles: []
  };

  interval(task: TaskState, elapsed: number) {
    const key = bucket(task);
    if (key) this.values.time[key] += elapsed;
  }

  observe(event: ActivityEvent, start: number) {
    const metrics = this.values;
    if (event.kind === 'VALIDATION_PASSED' || event.kind === 'VALIDATION_FAILED') {
      const passed = event.kind === 'VALIDATION_PASSED';
      metrics[passed ? 'validationPassed' : 'validationFailed']++;
      metrics.firstValidation ??= passed ? 'passed' : 'failed';
    }
    if (event.kind === 'VALIDATION_CHECK_COMPLETED' && event.payload.status !== 'PASSED')
      metrics.failedChecks++;
    if (event.kind === 'REVIEW_RECEIVED') metrics.reviews++;
    if (event.kind === 'HUMAN_RESPONDED') metrics.humanResponses++;
    if (
      event.kind === 'TASK_STATE_CHANGED' &&
      event.payload.action === 'TAKEOVER' &&
      event.payload.from_manual_takeover !== true
    ) {
      this.takeovers.add(`${event.task_id}:${event.payload.version ?? event.sequence}`);
      this.manualTasks.add(event.task_id);
    }
    if (event.kind === 'CI_NOTIFICATION_RECEIVED')
      this.ciNotifications.add(`${event.task_id}:${event.payload.notification_id ?? event.id}`);
    if (event.kind === 'CI_CHECK_UPDATED') {
      if (event.payload.review_cycle_id)
        this.ciOutcomes.add(`${event.task_id}:${event.payload.review_cycle_id}`);
      const key = `${event.task_id}:${event.payload.check_key ?? event.sequence}`;
      if (!event.payload.check_key || event.payload.status === 'UNKNOWN') this.unknownCi.add(key);
      else if (
        ['FAILURE', 'ERROR', 'TIMED_OUT', 'STARTUP_FAILURE'].includes(String(event.payload.status))
      ) {
        const failed =
          event.payload.check_type === 'check_suite' ? this.failedCiSuites : this.failedCiChecks;
        failed.add(key);
      }
    }
    if (event.kind === 'JOB_STARTED') {
      const queued = Date.parse(String(event.payload.queued_at));
      if (Number.isFinite(queued) && event.payload.attempt === 1)
        metrics.queueMs += Math.max(0, Date.parse(event.occurred_at) - Math.max(start, queued));
      else metrics.unknownQueueRuns++;
    }
    if (event.kind !== 'CODE_CHANGED') return;
    metrics.added += count(
      event.payload.lines_added ??
        event.files.reduce((sum, file) => sum + (file.lines_added ?? 0), 0)
    );
    metrics.deleted += count(
      event.payload.lines_deleted ??
        event.files.reduce((sum, file) => sum + (file.lines_deleted ?? 0), 0)
    );
    metrics.incompleteFiles ||=
      event.file_status === 'EXPIRED' ||
      count(event.payload.file_count) > event.files.length ||
      count(event.payload.unknown_line_counts) > 0;
    for (const file of event.files) {
      const key = `${file.repository_id}/${file.path}`;
      const previous = this.files.get(key);
      this.files.set(key, { path: file.path, touches: (previous?.touches ?? 0) + 1 });
      this.directories.add(
        `${file.repository_id}/${file.path.slice(0, file.path.lastIndexOf('/') + 1)}`
      );
      if (/(^|\/)(__tests__|tests?)\/|[._](test|spec)\.|(^|\/)test_/.test(file.path))
        this.tests.add(key);
      const language = languages[file.path.split('.').pop() ?? ''];
      if (language) this.languages.add(language);
      if (file.lines_added === null || file.lines_deleted === null) metrics.incompleteFiles = true;
    }
  }

  result(): ProcessMetrics {
    return {
      ...this.values,
      ciFailedChecks: this.failedCiChecks.size,
      ciFailedSuites: this.failedCiSuites.size,
      ciUnknown:
        this.unknownCi.size +
        [...this.ciNotifications].filter((id) => !this.ciOutcomes.has(id)).length,
      manualTakeovers: this.takeovers.size,
      manualTasks: this.manualTasks.size,
      files: this.files.size,
      directories: this.directories.size,
      testsChanged: this.tests.size,
      languages: [...this.languages].sort(),
      hotFiles: [...this.files.values()]
        .sort((a, b) => b.touches - a.touches || a.path.localeCompare(b.path))
        .slice(0, 5)
    };
  }
}
