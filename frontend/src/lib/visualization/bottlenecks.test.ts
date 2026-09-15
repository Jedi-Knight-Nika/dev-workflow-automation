import { expect, it } from 'vitest';
import { bottlenecks } from './bottlenecks';
import { ProcessAccumulator } from './process-metrics';
import type { CapacityEvidence } from './types';

const at = (seconds: number) => new Date(seconds * 1000).toISOString();
const evidence: CapacityEvidence = {
  as_of: at(30),
  truncated: false,
  teams: [
    {
      id: 'team',
      name: 'Team',
      limits: [
        { at: at(10), capacity: 1 },
        { at: at(20), capacity: 2 }
      ],
      jobs: [
        { id: 'a', task_id: 'a', start: at(5), end: at(25), complete: true },
        { id: 'a-overlap', task_id: 'a', start: at(12), end: at(18), complete: true },
        { id: 'b', task_id: 'b', start: at(15), end: at(30), complete: true }
      ]
    }
  ]
};

it('uses historical capacity changes, preserves unknown time and deduplicates concurrent tasks', () => {
  const result = bottlenecks(new ProcessAccumulator().result(), [], evidence, 0, 30_000);
  expect(result.reviewPercent).toBeNull();
  expect(result.capacity[0]).toMatchObject({
    observedMs: 20_000,
    unknownMs: 10_000,
    saturatedMs: 15_000,
    availableSlotMs: 30_000,
    utilizedSlotMs: 30_000,
    peak: 2,
    partial: false
  });
});

it('never extrapolates frozen capacity evidence into live time', () => {
  const metrics = new ProcessAccumulator().result();
  expect(bottlenecks(metrics, [], evidence, 0, 90_000).capacity).toEqual(
    bottlenecks(metrics, [], evidence, 0, 30_000).capacity
  );
  metrics.time.review = 30;
  metrics.time.human = 10;
  metrics.time.coding = 60;
  expect(bottlenecks(metrics, [], undefined, 0, 100)).toMatchObject({
    reviewPercent: 30,
    humanPercent: 10,
    unknownPercent: 0
  });
});
