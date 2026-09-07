"""Read-only deployment, prompt and high-cost-attempt evidence; no model requests."""
import ast
import asyncio
import json
from pathlib import Path
import urllib.request

from sqlalchemy import select, text
from app.config import get_settings
from app.db.models import JobRole, Task, WorkflowDefinition, WorkflowNode
from app.db.session import SessionLocal
from app.worker import resolve_agent_config

async def main():
    result = {}
    settings = get_settings()
    names = ('scheduler_enabled','scheduler_poll_seconds','scheduler_max_concurrent_jobs','worker_transport','worker_timeout_seconds','worker_lease_seconds','worker_heartbeat_seconds','max_executor_jobs_per_task','max_thinker_jobs_per_task','max_job_attempts','max_job_tokens','max_task_tokens','max_team_tokens','max_job_cost_usd','max_task_cost_usd','max_team_cost_usd')
    result['runtime_settings'] = {name:getattr(settings,name) for name in names}
    module = ast.parse(Path('app/worker.py').read_text())
    result['prompt_constants'] = {node.targets[0].id:ast.literal_eval(node.value) for node in module.body if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and node.targets[0].id in ('PLATFORM_BASE_INSTRUCTIONS','ROLE_INSTRUCTIONS')}
    async with SessionLocal() as s:
        await s.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
        task = await s.scalar(select(Task).where(Task.external_key=='TRELLO-J2mg8B9P'))
        result['task_strategy'] = {'profile':task.execution_profile,'strategy':task.execution_strategy}
        result['resolved_agents'] = []
        nodes = (await s.scalars(select(WorkflowNode).join(WorkflowDefinition).where(WorkflowDefinition.team_id==task.team_id))).all()
        for n in nodes:
            if n.role=='ORCHESTRATOR': continue
            c=await resolve_agent_config(s,task,JobRole(n.role),n.id)
            result['resolved_agents'].append({'name':n.label,'role':n.role,'provider':c.provider,'model':c.model,'system_prompt':c.system_prompt,'configuration':c.configuration,'runtime':c.effective_runtime})
        queries={
            'expensive_call_sequence': "SELECT w.created_at,w.input_tokens,w.output_tokens,w.duration_ms,w.provider_request_id IS NOT NULL AS has_response_id FROM worker_runs w WHERE w.job_id='ed55ae89-1574-4ddb-9fab-9710e9d5ac22' ORDER BY w.created_at,w.id",
            'job_outcomes': "SELECT j.role,j.state,j.result->>'result' AS result,count(distinct j.id) AS jobs,count(w.id) AS calls,sum(w.input_tokens) AS input_tokens,sum(w.output_tokens) AS output_tokens FROM jobs j LEFT JOIN worker_runs w ON w.job_id=j.id GROUP BY j.role,j.state,j.result->>'result' ORDER BY j.role,j.state",
            'blocking_messages': "SELECT t.external_key,m.created_at,m.author_role,m.body FROM task_messages m JOIN tasks t ON t.id=m.task_id WHERE m.author_type='AGENT' AND m.context->>'result' IN ('BLOCKED','NEEDS_HUMAN') ORDER BY m.created_at DESC LIMIT 12",
            'embedding_model': "SELECT configuration->>'embedding_model' AS model FROM integrations WHERE provider_name='openai'",
            'trello_poll': "SELECT configuration->>'poll_interval_seconds' AS seconds,configuration->>'sync_enabled' AS enabled,configuration->'status_mappings' AS status_mappings FROM integrations WHERE provider_name='trello'",
            'worker_status': "SELECT status,last_heartbeat,started_at FROM worker_nodes ORDER BY last_heartbeat DESC LIMIT 5",
            'health': "SELECT resource_type,resource_id,status,circuit_state,consecutive_failures,last_error_class FROM health_states",
        }
        result['queries']={}
        for name,sql in queries.items(): result['queries'][name]={'sql':sql,'rows':[dict(r) for r in (await s.execute(text(sql))).mappings()]}
    result['dashboard']={}
    for period in ('today','7d','30d'):
        with urllib.request.urlopen('http://localhost:8000/api/v1/dashboard/summary?period='+period) as r:
            result['dashboard'][period]=json.load(r)
    with urllib.request.urlopen('http://localhost:8000/api/v1/dashboard/telemetry') as r: result['telemetry']=json.load(r)
    print(json.dumps(result,default=str,ensure_ascii=False))

asyncio.run(main())
