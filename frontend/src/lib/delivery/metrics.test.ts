import { expect, it } from 'vitest';
import { deploymentMetrics, type DeploymentEvidence } from './metrics';

const at = (minutes: number) =>
  new Date(Date.parse('2026-09-15T00:00:00Z') + minutes * 60000).toISOString();
const event = (
  id: string,
  status: string,
  minutes: number,
  extra: Partial<DeploymentEvidence> = {}
): DeploymentEvidence => ({
  repository_id: 'repository',
  deployment_id: 'deployment',
  observation_id: id,
  environment: 'production',
  status,
  production: true,
  started_at: at(0),
  occurred_at: at(minutes),
  ...extra
});

it('orders provider observations and deduplicates repeated task associations', () => {
  const failure = event('2', 'FAILURE', 2),
    success = event('3', 'SUCCESS', 5);
  expect(deploymentMetrics([success, failure, success, event('created', 'CREATED', 0)])).toEqual({
    observed: 1,
    succeeded: 1,
    failed: 1,
    meanCompletionMs: 300000,
    meanRecoveryMs: 180000,
    recoverySamples: 1,
    unresolvedEnvironments: 0
  });
});

it('keeps recovery scoped to a repository and environment and does not treat cancellation as failure', () => {
  expect(
    deploymentMetrics([
      event('1', 'FAILURE', 1),
      event('2', 'PENDING', 2),
      event('3', 'SUCCESS', 3, { repository_id: 'other' }),
      event('4', 'SUCCESS', 4, { environment: 'staging' }),
      event('5', 'INACTIVE', 5)
    ])
  ).toMatchObject({
    observed: 3,
    failed: 1,
    succeeded: 2,
    recoverySamples: 0,
    unresolvedEnvironments: 1
  });
});
