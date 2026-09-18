"""Bounded-label metrics projected from durable coordination and scheduling records."""

from prometheus_client.core import GaugeMetricFamily, Metric
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def coordination_metrics(session: AsyncSession) -> list[Metric]:
    values: list[Metric] = []
    for name, table in (
        ("events", "coordinator_events"),
        ("runs", "coordinator_runs"),
        ("actions", "coordinator_actions"),
        ("human_requests", "human_requests"),
    ):
        metric = GaugeMetricFamily(
            "aew_coordinator_" + name, "Retained durable records by state", labels=["status"]
        )
        # Identifiers above are constants, never request/model input.
        for status, count in await session.execute(
            text(f"SELECT status,count(*) FROM {table} GROUP BY status LIMIT 40")
        ):
            metric.add_metric([status], count)
        values.append(metric)
    for name, query in (
        (
            "aew_coordinator_oldest_event_seconds",
            "SELECT coalesce(extract(epoch from now()-min(created_at)),0) FROM coordinator_events WHERE status='QUEUED'",
        ),
        (
            "aew_coordinator_events_per_wake",
            "SELECT coalesce(avg(n),0) FROM (SELECT count(*) AS n FROM coordinator_events WHERE run_id IS NOT NULL GROUP BY run_id) batches",
        ),
        (
            "aew_coordinator_known_cost_usd",
            "SELECT coalesce(sum(coalesce(provider_cost_usd,calculated_cost_usd)),0) FROM ai_runs WHERE role_kind='COORDINATOR'",
        ),
        (
            "aew_coordinator_unknown_usage",
            "SELECT count(*) FROM ai_runs WHERE role_kind='COORDINATOR' AND usage_complete IS NOT TRUE",
        ),
        (
            "aew_paid_slots_busy",
            "SELECT count(*) FROM jobs WHERE state IN ('CLAIMED','RUNNING') AND action IN ('INTERPRET_EVENT','THINKER_TURN','DEVELOPER_TURN')",
        ),
        (
            "aew_scheduler_recent_queue_wait_seconds",
            "SELECT coalesce(avg(extract(epoch from started_at-created_at)),0) FROM jobs WHERE started_at > now()-interval '1 day'",
        ),
        (
            "aew_scheduler_waiting_teams",
            "SELECT count(DISTINCT tasks.team_id) FROM jobs JOIN tasks ON tasks.id=jobs.task_id WHERE jobs.state='QUEUED'",
        ),
    ):
        values.append(
            GaugeMetricFamily(
                name,
                "Durable operational projection; unknown spend is excluded",
                value=float(await session.scalar(text(query)) or 0),
            )
        )
    # Ratios with no observations are NaN, never an invented 0% error or 100% quality.
    quality_queries = (
        (
            "aew_coordinator_clarification_rate",
            "Fraction of decided wakes requesting clarification",
            "SELECT count(*) FILTER (WHERE decision->>'action'='ASK_HUMAN')::float / nullif(count(*),0) FROM coordinator_runs WHERE decision IS NOT NULL",
        ),
        (
            "aew_coordinator_reviewed_actions",
            "Latest operator labels; excludes unreviewed actions",
            "SELECT count(DISTINCT payload->>'action_id') FROM task_events WHERE source='dashboard' AND event_type='COORDINATOR_ACTION_REVIEWED'",
        ),
        (
            "aew_coordinator_incorrect_action_rate",
            "Incorrect fraction of operator-reviewed actions only",
            "SELECT count(*) FILTER (WHERE verdict='INCORRECT')::float/nullif(count(*),0) FROM (SELECT DISTINCT ON (payload->>'action_id') payload->>'verdict' AS verdict FROM task_events WHERE source='dashboard' AND event_type='COORDINATOR_ACTION_REVIEWED' ORDER BY payload->>'action_id',id DESC) labels",
        ),
        (
            "aew_coordinator_human_override_rate",
            "Coordinated tasks with observed operator pause, cancel or takeover",
            "SELECT count(DISTINCT e.task_id)::float/nullif(count(DISTINCT r.task_id),0) FROM coordinator_runs r LEFT JOIN task_events e ON e.task_id=r.task_id AND e.event_type='TASK_LIFECYCLE_CHANGED' AND e.payload->>'actor' LIKE 'user:%' AND e.payload->>'action' IN ('PAUSE','CANCEL','TAKEOVER')",
        ),
        (
            "aew_engineering_accepted_task_rate",
            "Merged fraction of terminal tasks that entered engineering",
            "SELECT count(*) FILTER (WHERE status='MERGED')::float/nullif(count(*),0) FROM tasks WHERE status IN ('MERGED','FAILED','CANCELLED') AND started_at IS NOT NULL",
        ),
        (
            "aew_engineering_first_validation_pass_rate",
            "First full validation batch by task and requirement; observed batches only",
            "SELECT count(*) FILTER (WHERE passed='true')::float/nullif(count(*),0) FROM (SELECT DISTINCT ON (task_id,payload->>'requirement_version') payload->>'passed' AS passed FROM task_events WHERE source='engineering' AND event_type='VALIDATION_BATCH_COMPLETED' ORDER BY task_id,payload->>'requirement_version',id) batches",
        ),
        (
            "aew_engineering_validation_batches",
            "Full validation batch observations; historical gaps are not inferred",
            "SELECT count(*) FROM task_events WHERE source='engineering' AND event_type='VALIDATION_BATCH_COMPLETED'",
        ),
        (
            "aew_engineering_repair_rate",
            "Started tasks with validation or review repair requested",
            "SELECT count(DISTINCT e.task_id)::float/nullif(count(DISTINCT t.id),0) FROM tasks t LEFT JOIN task_events e ON e.task_id=t.id AND e.event_type='TASK_LIFECYCLE_CHANGED' AND e.payload->>'action' IN ('VALIDATION_FAILED','REVIEW_FIX') WHERE t.started_at IS NOT NULL",
        ),
        (
            "aew_engineering_human_code_interventions",
            "Tasks with observed manual takeover; not inferred from commits",
            "SELECT count(DISTINCT task_id) FROM task_events WHERE event_type='TASK_LIFECYCLE_CHANGED' AND payload->>'action'='TAKEOVER'",
        ),
        (
            "aew_engineering_time_to_pr_seconds",
            "Mean time from engineering start to first publication",
            "SELECT avg(extract(epoch from p.created_at-t.started_at)) FROM tasks t JOIN (SELECT task_id,min(created_at) AS created_at FROM task_events WHERE event_type='TASK_LIFECYCLE_CHANGED' AND payload->>'action'='PUBLISHED' GROUP BY task_id) p ON p.task_id=t.id WHERE t.started_at IS NOT NULL",
        ),
        (
            "aew_engineering_time_to_merge_seconds",
            "Mean engineering start to merge time",
            "SELECT avg(extract(epoch from completed_at-started_at)) FROM tasks WHERE status='MERGED' AND started_at IS NOT NULL",
        ),
    )
    for name, help_text, query in quality_queries:
        value = await session.scalar(text(query))
        values.append(
            GaugeMetricFamily(
                name, help_text, value=float(value) if value is not None else float("nan")
            )
        )
    # Include failed work in portfolio cost, expose unknown receipts as unavailable.
    for name, expression, missing in (
        (
            "cost_usd",
            "coalesce(r.provider_cost_usd,r.calculated_cost_usd)",
            "coalesce(r.provider_cost_usd,r.calculated_cost_usd) IS NULL",
        ),
        (
            "tokens",
            "r.input_tokens+r.output_tokens",
            "r.input_tokens IS NULL OR r.output_tokens IS NULL",
        ),
    ):
        query = f"""WITH cohort AS (SELECT id,status FROM tasks WHERE status IN ('MERGED','FAILED','CANCELLED') AND started_at IS NOT NULL),
        receipts AS (SELECT r.* FROM ai_runs r JOIN cohort c ON c.id=r.task_id)
        SELECT CASE WHEN count(*)=0 OR bool_or({missing}) OR bool_or(r.status='RUNNING') THEN NULL
          ELSE sum({expression}) / nullif((SELECT count(*) FROM cohort WHERE status='MERGED'),0) END FROM receipts r"""
        value = await session.scalar(text(query))
        values.append(
            GaugeMetricFamily(
                "aew_engineering_" + name + "_per_accepted_delivery",
                "Terminal engineering cohort including failed work; unknown usage is unavailable",
                value=float(value) if value is not None else float("nan"),
            )
        )
    return values
