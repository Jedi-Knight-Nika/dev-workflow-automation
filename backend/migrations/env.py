from logging.config import fileConfig

from alembic import context
from alembic.script import ScriptDirectory
from sqlalchemy import engine_from_config, inspect, pool, text

from app.platform.configuration.settings import get_settings
from app.platform.persistence import registry  # noqa: F401
from app.platform.persistence.base import Base

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url_sync)
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section), prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with connectable.connect() as connection:
        if "alembic_version" in inspect(connection).get_table_names():
            versions = set(connection.scalars(text("SELECT version_num FROM alembic_version")))
            known = {item.revision for item in ScriptDirectory.from_config(config).walk_revisions()}
            if versions - known:
                raise RuntimeError(
                    "This database has an incompatible schema revision. No data was changed. "
                    "Provision an empty database for initial setup; never bypass schema validation."
                )
        # Inspection starts an implicit SQLAlchemy transaction; close it before
        # Alembic owns the DDL transaction (otherwise setup would roll back on exit).
        connection.rollback()
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            # Multiple API replicas may start together. One owns initial setup;
            # the others then see the committed revision and do nothing.
            connection.execute(text("SELECT pg_advisory_xact_lock(1672927024)"))
            context.run_migrations()


run_migrations_offline() if context.is_offline_mode() else run_migrations_online()
