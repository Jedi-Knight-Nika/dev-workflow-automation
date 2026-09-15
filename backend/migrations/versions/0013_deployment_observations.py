"""Immutable GitHub deployment observations, independent of execution."""

from alembic import op

revision = "0013_deployment_observations"
down_revision = "0012_task_dependencies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE deployment_observations (
        id BIGSERIAL PRIMARY KEY,
        repository_id UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
        deployment_id VARCHAR(30) NOT NULL,
        observation_id VARCHAR(30) NOT NULL,
        sha VARCHAR(64) NOT NULL,
        environment VARCHAR(255) NOT NULL,
        production BOOLEAN,
        status VARCHAR(20) NOT NULL,
        started_at TIMESTAMP WITH TIME ZONE NOT NULL,
        occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
        recorded_at TIMESTAMP WITH TIME ZONE NOT NULL,
        CONSTRAINT uq_deployment_observation UNIQUE (repository_id, deployment_id, observation_id)
    )""")
    op.create_index(
        "ix_deployment_repository_time",
        "deployment_observations",
        ["repository_id", "occurred_at", "id"],
    )
    op.create_index("ix_deployment_time", "deployment_observations", ["occurred_at", "id"])


def downgrade() -> None:
    op.drop_table("deployment_observations")
