"""ensure the default team has a tester node

Revision ID: 0029_default_team_tester
Revises: 0028_teams
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0029_default_team_tester"
down_revision: str | None = "0028_teams"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO workflow_nodes (
            id, workflow_id, role, label, position_x, position_y, enabled,
            activation_policy, batch_window_seconds, integration_ids, repository_ids,
            provider, model, system_prompt, model_validation_status,
            model_validation_message, model_validated_at, integration_mode,
            poll_interval_seconds, filter_assignee_id, filter_state_ids,
            integration_sync_status, integration_sync_error, integration_last_synced_at
        )
        SELECT
            '10000000-0000-0000-0000-000000000007'::uuid, workflow_id,
            'TESTER', 'Tester', 1210, 280, enabled, activation_policy,
            batch_window_seconds, '[]'::json, repository_ids, provider, model,
            '', 'NOT_CONFIGURED', NULL, NULL, 'manual', 300, '', '[]'::json,
            'IDLE', NULL, NULL
        FROM workflow_nodes
        WHERE id = '10000000-0000-0000-0000-000000000005'::uuid
          AND NOT EXISTS (
            SELECT 1 FROM workflow_nodes
            WHERE id = '10000000-0000-0000-0000-000000000007'::uuid
          );

        DELETE FROM workflow_edges
        WHERE source_node_id = '10000000-0000-0000-0000-000000000005'::uuid
          AND target_node_id = '10000000-0000-0000-0000-000000000006'::uuid;

        INSERT INTO workflow_edges (
            id, workflow_id, source_node_id, target_node_id, outcome, required
        )
        SELECT '20000000-0000-0000-0000-000000000006'::uuid, workflow_definitions.id,
               '10000000-0000-0000-0000-000000000005'::uuid,
               '10000000-0000-0000-0000-000000000007'::uuid, 'success', true
        FROM workflow_definitions
        WHERE team_id = '00000000-0000-0000-0000-000000000001'::uuid
        ON CONFLICT DO NOTHING;

        INSERT INTO workflow_edges (
            id, workflow_id, source_node_id, target_node_id, outcome, required
        )
        SELECT '20000000-0000-0000-0000-000000000007'::uuid, workflow_definitions.id,
               '10000000-0000-0000-0000-000000000007'::uuid,
               '10000000-0000-0000-0000-000000000006'::uuid, 'success', true
        FROM workflow_definitions
        WHERE team_id = '00000000-0000-0000-0000-000000000001'::uuid
        ON CONFLICT DO NOTHING;

        UPDATE workflow_nodes
        SET position_x = 1470
        WHERE id = '10000000-0000-0000-0000-000000000006'::uuid;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM workflow_edges
        WHERE id IN (
            '20000000-0000-0000-0000-000000000006'::uuid,
            '20000000-0000-0000-0000-000000000007'::uuid
        );
        DELETE FROM workflow_nodes
        WHERE id = '10000000-0000-0000-0000-000000000007'::uuid;
        """
    )
