"""Durable Coordinator decisions and human requests; reuse existing messages/jobs/AI receipts."""

from alembic import op

revision = "0008_coordinator"
down_revision = "0007_observer"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE coordinator_runs (\n\tid UUID NOT NULL, \n\ttask_id UUID NOT NULL, \n\tmode VARCHAR(16) NOT NULL, \n\tstatus VARCHAR(24) NOT NULL, \n\trequirement_revision INTEGER NOT NULL, \n\tlifecycle_revision INTEGER NOT NULL, \n\tdecision JSON, \n\tevidence JSON NOT NULL, \n\terror VARCHAR(500), \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tfinished_at TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE\n)"
    )
    op.execute("CREATE INDEX ix_coordinator_run_task ON coordinator_runs (task_id, created_at)")
    op.execute(
        "CREATE TABLE coordinator_events (\n\tid UUID NOT NULL, \n\ttask_id UUID NOT NULL, \n\tprovider VARCHAR(30) NOT NULL, \n\tdelivery_key VARCHAR(255) NOT NULL, \n\tkind VARCHAR(40) NOT NULL, \n\tactor VARCHAR(120) NOT NULL, \n\tcontext JSON NOT NULL, \n\tstatus VARCHAR(24) NOT NULL, \n\trun_id UUID, \n\tavailable_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_coordinator_delivery UNIQUE (provider, delivery_key), \n\tFOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE, \n\tFOREIGN KEY(run_id) REFERENCES coordinator_runs (id) ON DELETE SET NULL\n)"
    )
    op.execute("CREATE INDEX ix_coordinator_event_due ON coordinator_events (status, available_at)")
    op.execute("CREATE INDEX ix_coordinator_event_task ON coordinator_events (task_id, created_at)")
    op.execute(
        "CREATE TABLE coordinator_actions (\n\tid UUID NOT NULL, \n\trun_id UUID NOT NULL, \n\ttask_id UUID NOT NULL, \n\tkind VARCHAR(32) NOT NULL, \n\tstatus VARCHAR(24) NOT NULL, \n\targuments JSON NOT NULL, \n\tprovider_effect_ref VARCHAR(255), \n\terror VARCHAR(500), \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tattempted_at TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (id), \n\tUNIQUE (run_id), \n\tFOREIGN KEY(run_id) REFERENCES coordinator_runs (id) ON DELETE CASCADE, \n\tFOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE\n)"
    )
    op.execute(
        "CREATE INDEX ix_coordinator_action_status ON coordinator_actions (status, created_at)"
    )
    op.execute(
        "CREATE TABLE human_requests (\n\tid UUID NOT NULL, \n\ttask_id UUID NOT NULL, \n\trun_id UUID NOT NULL, \n\tcategory VARCHAR(32) NOT NULL, \n\tquestion TEXT NOT NULL, \n\treason TEXT NOT NULL, \n\tchoices JSON NOT NULL, \n\tstatus VARCHAR(20) NOT NULL, \n\trequirement_revision INTEGER NOT NULL, \n\tlifecycle_revision INTEGER NOT NULL, \n\tanswer TEXT, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tanswered_at TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE, \n\tUNIQUE (run_id), \n\tFOREIGN KEY(run_id) REFERENCES coordinator_runs (id) ON DELETE CASCADE\n)"
    )
    op.execute("CREATE INDEX ix_human_request_open ON human_requests (task_id, status)")


def downgrade() -> None:
    op.drop_table("human_requests")
    op.drop_table("coordinator_actions")
    op.drop_table("coordinator_events")
    op.drop_table("coordinator_runs")
