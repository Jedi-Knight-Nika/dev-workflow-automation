import { beforeEach, describe, expect, it, vi } from 'vitest';
import { answerHumanRequest, getQueue, setTaskPriority, type HumanRequest } from './coordination';
import { api } from '$lib/api';
vi.mock('$lib/api', () => ({ api: vi.fn().mockResolvedValue({ status: 'QUEUED' }) }));

describe('human continuation and queue requests', () => {
  beforeEach(() => vi.clearAllMocks());
  it('sends the question identity with the answer so stale replies cannot resume another question', async () => {
    const request = { id: 'question-1', task_id: 'task-1' } as HumanRequest;
    await answerHumanRequest(request, 'Keep mobile support');
    expect(api).toHaveBeenCalledWith('/tasks/task-1/human-request/respond', {
      method: 'POST',
      body: JSON.stringify({ request_id: 'question-1', answer: 'Keep mobile support' })
    });
  });
  it('keeps Team filtering when navigating queue pages', async () => {
    await getQueue('team-1', 200);
    expect(api).toHaveBeenCalledWith('/queue/teams/team-1?offset=200');
  });
  it('changes only task priority without claiming a worker or resuming work', async () => {
    await setTaskPriority('task-1', 1);
    expect(api).toHaveBeenCalledWith('/tasks/task-1/priority', {
      method: 'POST',
      body: JSON.stringify({ priority: 1 })
    });
  });
});
