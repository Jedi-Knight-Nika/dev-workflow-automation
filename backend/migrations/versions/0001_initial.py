"""Initial schema and safe default entities for a fresh installation.

This replaces the discarded MVP upgrade chain, not an existing database. The
SQL snapshots are frozen so changing a Python model cannot rewrite this revision.
"""

from pathlib import Path

from alembic import op
from sqlalchemy import inspect

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def _apply_snapshot(name: str) -> None:
    # These frozen snapshots delimit simple DDL/INSERT statements with ;\n.
    # They contain no procedural SQL or multiline literals. Execute individually for asyncpg
    # integration tests as well as psycopg and offline SQL generation.
    source = Path(__file__).resolve().parents[1].joinpath(name).read_text()
    for statement in source.split(";\n"):
        if statement.strip():
            op.execute(statement.strip())


def upgrade() -> None:
    if not op.get_context().as_sql:
        existing = set(inspect(op.get_bind()).get_table_names()) - {"alembic_version"}
        if existing:
            raise RuntimeError(
                "Initial setup requires an empty database/schema. Existing data was not changed. "
                "Back it up and explicitly provision a fresh database; do not stamp or reset it here."
            )
    _apply_snapshot("initial_schema.sql")
    _apply_snapshot("initial_entities.sql")


def downgrade() -> None:
    raise RuntimeError(
        "Initial setup has no destructive downgrade. Back up and explicitly replace the "
        "database only when a full reset is intended."
    )
