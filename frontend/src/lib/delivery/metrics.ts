export type DeploymentEvidence = {
  repository_id: string;
  deployment_id: string;
  observation_id: string;
  environment: string;
  status: string;
  started_at: string;
  occurred_at: string;
  production: boolean | null;
};

export function deploymentEvidence(
  payload: Record<string, unknown>,
  at: string
): DeploymentEvidence | null {
  for (const key of [
    'repository_id',
    'deployment_id',
    'observation_id',
    'environment',
    'status',
    'started_at'
  ])
    if (typeof payload[key] !== 'string') return null;
  if (!Number.isFinite(Date.parse(at)) || !Number.isFinite(Date.parse(String(payload.started_at))))
    return null;
  return { ...payload, occurred_at: at } as DeploymentEvidence;
}

/** Metrics describe observed outcomes, not an inferred DORA change-failure rate. */
export function deploymentMetrics(events: DeploymentEvidence[]) {
  const seen = new Set<string>(),
    deployments = new Set<string>(),
    successes = new Set<string>(),
    failures = new Set<string>();
  const failing = new Map<string, number>();
  const completionMs: number[] = [],
    recoveryMs: number[] = [];
  for (const event of [...events].sort(
    (a, b) =>
      Date.parse(a.occurred_at) - Date.parse(b.occurred_at) ||
      a.observation_id.localeCompare(b.observation_id, undefined, { numeric: true })
  )) {
    const deployment = JSON.stringify([
      event.repository_id,
      event.environment,
      event.deployment_id
    ]);
    const observation = JSON.stringify([deployment, event.observation_id]);
    if (seen.has(observation)) continue;
    seen.add(observation);
    deployments.add(deployment);
    const environment = JSON.stringify([event.repository_id, event.environment]);
    const at = Date.parse(event.occurred_at);
    if (event.status === 'FAILURE' || event.status === 'ERROR') {
      failures.add(deployment);
      if (!failing.has(environment)) failing.set(environment, at);
    }
    if (event.status === 'SUCCESS') {
      if (!successes.has(deployment)) {
        successes.add(deployment);
        completionMs.push(Math.max(0, at - Date.parse(event.started_at)));
      }
      const failedAt = failing.get(environment);
      if (failedAt !== undefined) {
        recoveryMs.push(Math.max(0, at - failedAt));
        failing.delete(environment);
      }
    }
  }
  const mean = (values: number[]) =>
    values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
  return {
    observed: deployments.size,
    succeeded: successes.size,
    failed: failures.size,
    meanCompletionMs: mean(completionMs),
    meanRecoveryMs: mean(recoveryMs),
    recoverySamples: recoveryMs.length,
    unresolvedEnvironments: failing.size
  };
}
