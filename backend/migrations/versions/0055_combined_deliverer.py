"""Consolidate active Intake/Delivery configuration; retain historical job roles.

The small configuration snapshot makes the data migration reversible. Stop workers
before upgrading/downgrading. Downgrade restores pre-upgrade configuration, not
subsequent configuration edits; task/job history is never deleted.
"""

import json
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0055_combined_deliverer"
down_revision = "0054_reviewer_result_contract"
branch_labels = None
depends_on = None

TABLES = (
    "roles",
    "ai_agents",
    "workflow_definitions",
    "workflow_nodes",
    "workflow_edges",
    "agent_configs",
)


def upgrade() -> None:
    connection = op.get_bind()
    op.create_table(
        "deliverer_configuration_backup",
        sa.Column("table_name", sa.String(80), primary_key=True),
        sa.Column("rows", JSONB, nullable=False),
    )
    for table in TABLES:
        connection.execute(
            sa.text(
                f"INSERT INTO deliverer_configuration_backup SELECT :name, "
                f"coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb) FROM {table} t"
            ),
            {"name": table},
        )
    # These were protocol-repair counts before live tool turns existed. Keep
    # repair retries separate and give built-in specialists a bounded tool loop.
    connection.execute(
        sa.text("""
        UPDATE roles SET runtime_profile=jsonb_set(runtime_profile::jsonb, '{max_model_turns}', '20'::jsonb)::json
        WHERE built_in AND coalesce((runtime_profile->>'max_model_turns')::integer, 3)=3
    """)
    )
    for table in ("agent_knowledge_sources", "agent_knowledge_chunks"):
        connection.execute(
            sa.text(
                f"INSERT INTO deliverer_configuration_backup SELECT :name, coalesce(jsonb_agg(jsonb_build_object('id', id)), '[]'::jsonb) FROM {table} WHERE role='INTAKE'"
            ),
            {"name": table},
        )
        connection.execute(sa.text(f"UPDATE {table} SET role='DELIVERER' WHERE role='INTAKE'"))
    roles = (
        connection.execute(
            sa.text("SELECT * FROM roles WHERE built_in AND name IN ('Intake', 'Deliverer')")
        )
        .mappings()
        .all()
    )
    by_name = {row["name"]: row for row in roles}
    if "Intake" in by_name and "Deliverer" in by_name:
        incoming, delivery = by_name["Intake"], by_name["Deliverer"]
        profile = dict(incoming["runtime_profile"] or {})
        profile.update(
            reasoning_default="LOW",
            reasoning_max="MEDIUM",
            dynamic_reasoning_allowed=False,
            max_model_turns=6,
        )
        connection.execute(
            sa.text("""
            UPDATE roles SET capabilities=CAST(:capabilities AS json), permissions=CAST(:permissions AS json),
            allowed_results=CAST(:results AS json), runtime_profile=CAST(:profile AS json),
            knowledge_collection_ids=CAST(:knowledge AS json),
            description='Receives tasks and messages, selects repository scope, and manages GitHub delivery.',
            system_instructions=:instructions, version=version+1 WHERE id=:id
        """),
            {
                "id": delivery["id"],
                "capabilities": json.dumps(
                    sorted(set(incoming["capabilities"] + delivery["capabilities"]))
                ),
                "permissions": json.dumps(
                    sorted(set(incoming["permissions"] + delivery["permissions"]))
                ),
                "results": json.dumps(
                    sorted(set(incoming["allowed_results"] + delivery["allowed_results"]))
                ),
                "profile": json.dumps(profile),
                "knowledge": json.dumps(
                    sorted(
                        set(
                            (incoming["knowledge_collection_ids"] or [])
                            + (delivery["knowledge_collection_ids"] or [])
                        )
                    )
                ),
                "instructions": "Coordinate incoming tasks and messages and outgoing delivery. Interpret intent accurately; never restart implementation for a metadata-only request. Use the runtime's typed GitHub actions and merge gates.",
            },
        )
        connection.execute(
            sa.text(
                "UPDATE ai_agents SET role_id=:delivery, config_version=config_version+1 WHERE role_id=:incoming"
            ),
            {"delivery": delivery["id"], "incoming": incoming["id"]},
        )
        connection.execute(
            sa.text("UPDATE roles SET enabled=false, archived_at=now() WHERE id=:id"),
            {"id": incoming["id"]},
        )
    nodes = (
        connection.execute(sa.text("SELECT * FROM workflow_nodes WHERE role='INTAKE'"))
        .mappings()
        .all()
    )
    for node in nodes:
        parameters = {"workflow": node["workflow_id"], "keep": node["id"]}
        old_nodes = (
            connection.execute(
                sa.text(
                    "SELECT id, agent_id, integration_ids FROM workflow_nodes WHERE workflow_id=:workflow AND role='DELIVERER'"
                ),
                parameters,
            )
            .mappings()
            .all()
        )
        integration_ids = set(node["integration_ids"] or [])
        for old in old_nodes:
            parameters["old"] = old["id"]
            integration_ids.update(old["integration_ids"] or [])
            # Redirect both ends, retaining route metadata. Only redundant/self
            # connections disappear; the backup retains the exact original graph.
            edges = (
                connection.execute(
                    sa.text(
                        "SELECT * FROM workflow_edges WHERE workflow_id=:workflow AND (source_node_id=:old OR target_node_id=:old)"
                    ),
                    parameters,
                )
                .mappings()
                .all()
            )
            for edge in edges:
                source = (
                    node["id"] if edge["source_node_id"] == old["id"] else edge["source_node_id"]
                )
                target = (
                    node["id"] if edge["target_node_id"] == old["id"] else edge["target_node_id"]
                )
                duplicate = connection.scalar(
                    sa.text(
                        "SELECT id FROM workflow_edges WHERE workflow_id=:workflow AND source_node_id=:source AND target_node_id=:target AND outcome=:outcome AND id<>:edge"
                    ),
                    {
                        **parameters,
                        "source": source,
                        "target": target,
                        "outcome": edge["outcome"],
                        "edge": edge["id"],
                    },
                )
                if source == target or duplicate:
                    connection.execute(
                        sa.text("DELETE FROM workflow_edges WHERE id=:id"), {"id": edge["id"]}
                    )
                else:
                    connection.execute(
                        sa.text(
                            "UPDATE workflow_edges SET source_node_id=:source, target_node_id=:target WHERE id=:id"
                        ),
                        {"source": source, "target": target, "id": edge["id"]},
                    )
            connection.execute(
                sa.text(
                    "UPDATE tasks SET current_workflow_node_id=:keep WHERE current_workflow_node_id=:old"
                ),
                parameters,
            )
            connection.execute(sa.text("DELETE FROM workflow_nodes WHERE id=:old"), parameters)
            if old["agent_id"] and old["agent_id"] != node["agent_id"]:
                connection.execute(
                    sa.text("UPDATE ai_agents SET enabled=false WHERE id=:id"),
                    {"id": old["agent_id"]},
                )
        connection.execute(
            sa.text("""
            UPDATE workflow_nodes SET role='DELIVERER',
            label=CASE WHEN label='Intake' THEN 'Deliverer' ELSE label END,
            integration_ids=CAST(:integrations AS json) WHERE id=:keep
        """),
            {**parameters, "integrations": json.dumps(sorted(integration_ids))},
        )
        connection.execute(
            sa.text(
                "UPDATE jobs SET role='DELIVERER' WHERE role='INTAKE' AND workflow_node_id=:keep AND state NOT IN ('SUCCEEDED','FAILED','CANCELLED','TIMED_OUT')"
            ),
            parameters,
        )
    connection.execute(sa.text("UPDATE agent_configs SET enabled=false WHERE role='INTAKE'"))
    connection.execute(
        sa.text("""
        UPDATE jobs SET result=jsonb_set(result::jsonb, '{role}', '"DELIVERER"'::jsonb)::json
        WHERE role='DELIVERER' AND result->>'role'='INTAKE'
        AND state NOT IN ('SUCCEEDED','FAILED','CANCELLED','TIMED_OUT')
    """)
    )
    for workflow in connection.execute(sa.text("SELECT id FROM workflow_definitions")).scalars():
        current = (
            connection.execute(
                sa.text(
                    "SELECT id, role FROM workflow_nodes WHERE workflow_id=:workflow AND node_type='AGENT'"
                ),
                {"workflow": workflow},
            )
            .mappings()
            .all()
        )
        controller = next((item["id"] for item in current if item["role"] == "ORCHESTRATOR"), None)
        if controller is None:
            continue
        for node in current:
            if node["id"] == controller:
                continue
            for source, target in ((node["id"], controller), (controller, node["id"])):
                connection.execute(
                    sa.text("""
                    INSERT INTO workflow_edges (id, workflow_id, source_node_id, target_node_id, outcome, required, configuration)
                    VALUES (:id, :workflow, :source, :target, 'consultation', false, '{"kind":"consultation"}'::json)
                    ON CONFLICT DO NOTHING
                """),
                    {
                        "id": uuid.uuid5(workflow, f"consult:{source}:{target}"),
                        "workflow": workflow,
                        "source": source,
                        "target": target,
                    },
                )
        _publish_revision(connection, workflow)


def _publish_revision(connection, workflow) -> None:
    previous = connection.scalar(
        sa.text("SELECT version FROM workflow_definitions WHERE id=:id"), {"id": workflow}
    )
    version = previous + 1
    connection.execute(
        sa.text("UPDATE workflow_definitions SET version=:version, updated_at=now() WHERE id=:id"),
        {"id": workflow, "version": version},
    )
    # An operational migration deliberately moves unfinished work onto the combined
    # graph. Completed jobs and all previous revision snapshots remain unchanged.
    connection.execute(
        sa.text("""
        UPDATE jobs SET team_workflow_version=:version
        WHERE team_workflow_version=:previous AND task_id IN
        (SELECT t.id FROM tasks t JOIN workflow_definitions w ON w.team_id=t.team_id WHERE w.id=:id)
        AND state NOT IN ('SUCCEEDED','FAILED','CANCELLED','TIMED_OUT')
    """),
        {"id": workflow, "version": version, "previous": previous},
    )
    connection.execute(
        sa.text("""
        UPDATE tasks SET workflow_version=:version WHERE workflow_version=:previous
        AND team_id=(SELECT team_id FROM workflow_definitions WHERE id=:id)
        AND state NOT IN ('MERGED','CANCELLED','FAILED')
    """),
        {"id": workflow, "version": version, "previous": previous},
    )
    connection.execute(
        sa.text("""
        INSERT INTO workflow_revisions (id, workflow_id, version, graph, created_at)
        SELECT :revision, :id, :version, jsonb_build_object(
            'version', CAST(:version AS integer),
            'nodes', (SELECT coalesce(jsonb_agg(to_jsonb(n)-'workflow_id'), '[]'::jsonb) FROM workflow_nodes n WHERE n.workflow_id=:id),
            'edges', (SELECT coalesce(jsonb_agg(to_jsonb(e)-'workflow_id'), '[]'::jsonb) FROM workflow_edges e WHERE e.workflow_id=:id)
        ), now()
    """),
        {
            "id": workflow,
            "version": version,
            "revision": uuid.uuid5(workflow, f"combined-deliverer:{version}"),
        },
    )


def downgrade() -> None:
    connection = op.get_bind()
    definitions = (
        connection.execute(
            sa.text("""
        SELECT d.id, d.team_id, d.version FROM deliverer_configuration_backup b,
        jsonb_populate_recordset(NULL::workflow_definitions, b.rows) d
        WHERE b.table_name='workflow_definitions'
    """)
        )
        .mappings()
        .all()
    )
    for definition in definitions:
        completed = connection.scalar(
            sa.text("""
            SELECT count(*) FROM jobs WHERE team_workflow_version=:version
            AND task_id IN (SELECT id FROM tasks WHERE team_id=:team)
            AND state IN ('SUCCEEDED','FAILED','CANCELLED','TIMED_OUT')
        """),
            {"version": definition["version"] + 1, "team": definition["team_id"]},
        )
        if completed:
            raise RuntimeError(
                "Cannot restore pre-consolidation configuration after new work completed; use a forward migration to preserve history"
            )
        connection.execute(
            sa.text("""
            UPDATE jobs SET team_workflow_version=:previous WHERE team_workflow_version=:current
            AND task_id IN (SELECT id FROM tasks WHERE team_id=:team)
        """),
            {
                "previous": definition["version"],
                "current": definition["version"] + 1,
                "team": definition["team_id"],
            },
        )
        connection.execute(
            sa.text(
                "UPDATE tasks SET workflow_version=:previous WHERE team_id=:team AND workflow_version=:current"
            ),
            {
                "previous": definition["version"],
                "current": definition["version"] + 1,
                "team": definition["team_id"],
            },
        )
        connection.execute(
            sa.text("DELETE FROM workflow_revisions WHERE id=:id"),
            {"id": uuid.uuid5(definition["id"], f"combined-deliverer:{definition['version'] + 1}")},
        )
    # These tables hold configuration only. Restore the exact pre-upgrade rows.
    for table in ("workflow_edges", "workflow_nodes"):
        connection.execute(sa.text(f"DELETE FROM {table}"))
    inspector = sa.inspect(connection)
    for table in TABLES:
        columns = [column["name"] for column in inspector.get_columns(table)]
        key = "role" if table == "agent_configs" else "id"
        updates = ", ".join(
            f'"{column}"=EXCLUDED."{column}"' for column in columns if column != key
        )
        connection.execute(
            sa.text(
                f"INSERT INTO {table} SELECT restored.* FROM deliverer_configuration_backup b, "
                f"jsonb_populate_recordset(NULL::{table}, b.rows) restored WHERE b.table_name=:name "
                f"ON CONFLICT ({key}) DO UPDATE SET {updates}"
            ),
            {"name": table},
        )
    connection.execute(
        sa.text(
            "UPDATE jobs SET role='INTAKE' WHERE role='DELIVERER' AND state NOT IN ('SUCCEEDED','FAILED','CANCELLED','TIMED_OUT') AND workflow_node_id IN (SELECT id FROM workflow_nodes WHERE role='INTAKE')"
        )
    )
    for table in ("agent_knowledge_sources", "agent_knowledge_chunks"):
        connection.execute(
            sa.text(
                f"UPDATE {table} SET role='INTAKE' WHERE id IN (SELECT (item->>'id')::uuid FROM deliverer_configuration_backup b, jsonb_array_elements(b.rows) item WHERE b.table_name=:name)"
            ),
            {"name": table},
        )
    op.drop_table("deliverer_configuration_backup")
