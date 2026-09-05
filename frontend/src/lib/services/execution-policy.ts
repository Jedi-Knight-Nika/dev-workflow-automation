import { api } from '$lib/api';
import type { ApprovalRequest, ExecutionPolicy } from '$lib/types';

export function getExecutionPolicy(teamId: string): Promise<ExecutionPolicy> {
  return api(`/teams/${teamId}/execution-policy`);
}

export function saveExecutionPolicy(
  teamId: string,
  policy: Omit<ExecutionPolicy, 'isolation_level' | 'execution_environment'>
): Promise<ExecutionPolicy> {
  return api(`/teams/${teamId}/execution-policy`, {
    method: 'PUT',
    body: JSON.stringify(policy)
  });
}

export function listApprovals(state = 'PENDING'): Promise<ApprovalRequest[]> {
  return api(`/approvals?state=${state}`);
}

export function resolveApproval(id: string, approved: boolean): Promise<ApprovalRequest> {
  return api(`/approvals/${id}/${approved ? 'approve' : 'deny'}`, {
    method: 'POST',
    body: JSON.stringify({ resolved_by: 'dashboard-user', scope: 'ONCE' })
  });
}
