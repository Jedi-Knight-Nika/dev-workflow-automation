"""Read-only operational report queries. Run inside the backend environment."""
import asyncio
import json

from sqlalchemy import text

from app.db.session import SessionLocal

QUERIES = {
    "capture": "SELECT now() AS captured_at, current_database() AS database, current_setting('TimeZone') AS timezone, (SELECT version_num FROM alembic_version) AS migration",
    "totals": "SELECT count(*) AS calls, count(distinct job_id) AS jobs, sum(input_tokens) AS input_tokens, sum(output_tokens) AS output_tokens, sum(estimated_cost_usd) AS estimated_cost, count(estimated_cost_usd) AS priced_calls, count(*) FILTER (WHERE input_tokens IS NULL OR output_tokens IS NULL) AS missing_usage, sum(duration_ms) AS duration_ms, min(created_at) AS first_call, max(created_at) AS last_call FROM worker_runs",
    "roles": "SELECT role, provider, model, count(*) AS calls, count(distinct job_id) AS jobs, sum(input_tokens) AS input_tokens, sum(output_tokens) AS output_tokens, sum(duration_ms) AS duration_ms, max(input_tokens) AS largest_input FROM worker_runs GROUP BY role,provider,model ORDER BY sum(input_tokens+output_tokens) DESC",
    "tasks": "SELECT t.id,t.external_key,t.state,t.created_at,t.completed_at,t.manual_takeover,t.archived_at,count(w.id) AS calls,count(distinct w.job_id) AS billed_jobs,coalesce(sum(w.input_tokens),0) AS input_tokens,coalesce(sum(w.output_tokens),0) AS output_tokens FROM tasks t LEFT JOIN jobs j ON j.task_id=t.id LEFT JOIN worker_runs w ON w.job_id=j.id GROUP BY t.id ORDER BY sum(w.input_tokens+w.output_tokens) DESC NULLS LAST",
    "task_roles": "SELECT t.external_key,w.role,count(*) AS calls,count(distinct w.job_id) AS jobs,sum(w.input_tokens) AS input_tokens,sum(w.output_tokens) AS output_tokens FROM worker_runs w JOIN jobs j ON j.id=w.job_id JOIN tasks t ON t.id=j.task_id GROUP BY t.external_key,w.role ORDER BY t.external_key,sum(w.input_tokens+w.output_tokens) DESC",
    "jobs": "SELECT j.id,t.external_key,j.role,j.action,j.state,j.attempt,j.created_at,j.started_at,j.finished_at,j.result->>'result' AS result,j.result->>'outcome' AS outcome,count(w.id) AS calls,coalesce(sum(w.input_tokens),0) AS input_tokens,coalesce(sum(w.output_tokens),0) AS output_tokens FROM jobs j JOIN tasks t ON t.id=j.task_id LEFT JOIN worker_runs w ON w.job_id=j.id GROUP BY j.id,t.external_key ORDER BY j.created_at",
    "daily": "SELECT date_trunc('day',created_at) AS day,count(*) AS calls,sum(input_tokens) AS input_tokens,sum(output_tokens) AS output_tokens FROM worker_runs GROUP BY 1 ORDER BY 1",
    "quality": "SELECT count(*) AS rows,count(provider_request_id) AS with_request_id,count(distinct provider_request_id) AS distinct_request_ids,count(*) FILTER (WHERE input_tokens<0 OR output_tokens<0) AS negative_usage,count(*) FILTER (WHERE effective_runtime_config_hash IS NOT NULL) AS runtime_snapshots FROM worker_runs",
    "contexts": "SELECT j.role,count(*) AS contexts,min(c.estimated_input_tokens) AS minimum_estimated_tokens,round(avg(c.estimated_input_tokens)) AS average_estimated_tokens,max(c.estimated_input_tokens) AS maximum_estimated_tokens,round(avg(c.compilation_duration_ms)) AS average_compilation_ms FROM job_contexts c JOIN jobs j ON j.id=c.job_id GROUP BY j.role ORDER BY j.role",
    "agents": "SELECT a.id,a.name,a.enabled,a.provider,a.model,a.custom_instructions,a.runtime_overrides,a.config_version,r.name AS role,r.version AS role_version,r.system_instructions,r.permissions,r.capabilities,r.runtime_profile,r.override_policy FROM ai_agents a JOIN roles r ON r.id=a.role_id ORDER BY a.enabled DESC,r.name",
    "nodes": "SELECT n.id,n.label,n.role,n.enabled,n.provider,n.model,n.system_prompt,n.reasoning_effort,n.max_output_tokens,n.timeout_minutes,n.max_retries,n.max_review_cycles,n.context_depth,n.rag_retrieval_depth,n.model_validation_status,n.poll_interval_seconds,n.integration_mode FROM workflow_nodes n ORDER BY n.id",
    "workflow": "SELECT w.team_id,w.version,s.role AS source,t.role AS target,e.outcome,e.job_type,e.internal_task_state,e.external_status_key,e.configuration FROM workflow_edges e JOIN workflow_definitions w ON w.id=e.workflow_id JOIN workflow_nodes s ON s.id=e.source_node_id JOIN workflow_nodes t ON t.id=e.target_node_id ORDER BY s.role,e.outcome,t.role",
    "teams": "SELECT id,name,enabled,max_concurrent_tasks,repository_ids FROM teams",
    "settings": "SELECT timezone,default_reasoning_level,default_max_output_tokens,max_concurrent_workers,default_job_timeout_seconds,default_merge_policy,auto_index_repositories,incremental_index_after_merge,context_strategy,monthly_cost_warning,monthly_cost_hard_stop FROM account_settings",
    "pricing": "SELECT role,configuration->>'input_cost_per_million' AS input_rate,configuration->>'output_cost_per_million' AS output_rate FROM agent_configs ORDER BY role",
    "integrations": "SELECT provider_name,status,sync_status,last_synced_at FROM integrations ORDER BY provider_name",
    "repositories": "SELECT id,owner,name,enabled,latest_sha,indexed_sha,index_status,indexed_at FROM repositories",
    "knowledge": "SELECT repository_id,count(*) AS chunks,count(distinct file_path) AS files,count(distinct commit_sha) AS revisions,count(embedding) AS embedded_chunks FROM knowledge_chunks GROUP BY repository_id",
    "manual_knowledge": "SELECT role,count(*) AS chunks,count(distinct source_id) AS sources FROM agent_knowledge_chunks GROUP BY role",
    "vector_ddl": "SELECT table_name,column_name,udt_name FROM information_schema.columns WHERE table_name IN ('knowledge_chunks','agent_knowledge_chunks') AND column_name='embedding'",
    "vector_indexes": "SELECT tablename,indexname,indexdef FROM pg_indexes WHERE tablename IN ('knowledge_chunks','agent_knowledge_chunks')",
    "failures": "SELECT failure_class,count(*) AS events,count(distinct job_id) AS jobs FROM failure_events GROUP BY failure_class ORDER BY count(*) DESC",
    "events": "SELECT event_type,count(*) AS events FROM task_events GROUP BY event_type ORDER BY count(*) DESC",
    "retry_counters": "SELECT sum(provider_retry_count) AS provider,sum(integration_retry_count) AS integration,sum(worker_retry_count) AS worker,sum(protocol_retry_count) AS protocol,sum(engineering_retry_count) AS engineering FROM job_retry_states",
    "scopes": "SELECT t.external_key,r.name,s.changed,s.pull_request_number,s.base_revision,s.current_revision,s.merged_at FROM task_repository_scopes s JOIN tasks t ON t.id=s.task_id JOIN repositories r ON r.id=s.repository_id ORDER BY t.external_key",
    "messages": "SELECT author_type,author_role,kind,count(*) AS messages FROM task_messages WHERE deleted_at IS NULL GROUP BY author_type,author_role,kind ORDER BY author_type,author_role",
}


async def main():
    result = {}
    async with SessionLocal() as session:
        await session.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
        for name, sql in QUERIES.items():
            rows = (await session.execute(text(sql))).mappings().all()
            result[name] = {"sql": sql, "rows": [dict(row) for row in rows]}
    print(json.dumps(result, default=str, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
