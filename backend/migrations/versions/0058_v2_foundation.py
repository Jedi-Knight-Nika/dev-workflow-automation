"""Add opt-in V2 lifecycle, fixed profiles and immutable execution evidence.

No legacy records are removed or retrospectively repriced. Existing tasks stay
on execution_version=1; their V2 state remains unknown until explicitly migrated.
"""

from alembic import op

revision = "0058_v2_foundation"
down_revision = "0057_health_defaults"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""ALTER TABLE tasks
        ADD COLUMN execution_version INTEGER NOT NULL DEFAULT 1,
        ADD COLUMN status VARCHAR(24),
        ADD COLUMN stage VARCHAR(24),
        ADD COLUMN wait_reason VARCHAR(40),
        ADD COLUMN requirement_version INTEGER NOT NULL DEFAULT 1,
        ADD COLUMN lifecycle_version INTEGER NOT NULL DEFAULT 1
    """)
    op.execute("""CREATE TABLE team_agent_profiles (
        id UUID PRIMARY KEY,
        team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
        role_kind VARCHAR(24) NOT NULL CHECK (role_kind IN ('INTERPRETER','DEVELOPER','THINKER','REVIEWER')),
        display_name VARCHAR(120) NOT NULL,
        avatar VARCHAR(500) NOT NULL DEFAULT '',
        enabled BOOLEAN NOT NULL DEFAULT TRUE,
        provider VARCHAR(40) NOT NULL,
        model VARCHAR(255) NOT NULL,
        harness VARCHAR(24),
        effort VARCHAR(20) NOT NULL DEFAULT 'medium',
        supplemental_instructions TEXT NOT NULL DEFAULT '',
        prompt_version VARCHAR(40) NOT NULL DEFAULT 'v2.1',
        soft_budget_usd NUMERIC(12,6) CHECK (soft_budget_usd > 0),
        hard_budget_usd NUMERIC(12,6) CHECK (hard_budget_usd > 0),
        version INTEGER NOT NULL DEFAULT 1,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT uq_team_agent_profile_role UNIQUE (team_id, role_kind),
        CONSTRAINT ck_profile_budget_order CHECK (soft_budget_usd IS NULL OR hard_budget_usd IS NULL OR soft_budget_usd <= hard_budget_usd)
    )""")
    op.execute("""CREATE TABLE developer_sessions (
        id UUID PRIMARY KEY,
        task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        profile_id UUID REFERENCES team_agent_profiles(id) ON DELETE SET NULL,
        generation INTEGER NOT NULL DEFAULT 1,
        harness VARCHAR(24) NOT NULL,
        harness_version VARCHAR(40) NOT NULL,
        provider VARCHAR(40) NOT NULL,
        model VARCHAR(255) NOT NULL,
        native_session_id VARCHAR(255),
        state VARCHAR(24) NOT NULL DEFAULT 'CREATED',
        workspace_path TEXT NOT NULL,
        state_path TEXT NOT NULL,
        checkpoint JSON NOT NULL DEFAULT '{}',
        requirement_version INTEGER NOT NULL DEFAULT 1,
        last_revision VARCHAR(64),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT uq_developer_session_generation UNIQUE (task_id,generation)
    )""")
    op.execute("""CREATE TABLE pricing_catalog (
        id UUID PRIMARY KEY,
        provider VARCHAR(40) NOT NULL,
        model VARCHAR(255) NOT NULL,
        version VARCHAR(80) NOT NULL,
        context_tier VARCHAR(40) NOT NULL DEFAULT 'standard',
        service_tier VARCHAR(40) NOT NULL DEFAULT 'standard',
        input_per_million NUMERIC(18,8) NOT NULL,
        output_per_million NUMERIC(18,8) NOT NULL,
        cached_input_per_million NUMERIC(18,8),
        cache_write_per_million NUMERIC(18,8),
        source_url TEXT NOT NULL,
        effective_at TIMESTAMPTZ NOT NULL,
        CONSTRAINT uq_pricing_version UNIQUE(provider,model,version,context_tier,service_tier)
    )""")
    op.execute("""CREATE TABLE ai_runs (
        id UUID PRIMARY KEY,
        task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        session_id UUID REFERENCES developer_sessions(id) ON DELETE SET NULL,
        job_id UUID REFERENCES jobs(id) ON DELETE SET NULL,
        native_turn_id VARCHAR(255),
        role_kind VARCHAR(24) NOT NULL,
        provider VARCHAR(40) NOT NULL,
        model VARCHAR(255) NOT NULL,
        harness VARCHAR(24),
        status VARCHAR(24) NOT NULL DEFAULT 'RUNNING',
        input_tokens INTEGER CHECK(input_tokens >= 0),
        output_tokens INTEGER CHECK(output_tokens >= 0),
        cache_read_tokens INTEGER,
        cache_write_tokens INTEGER,
        reasoning_tokens INTEGER,
        usage_complete BOOLEAN NOT NULL DEFAULT FALSE,
        provider_cost_usd NUMERIC(18,8),
        calculated_cost_usd NUMERIC(18,8),
        pricing_id UUID REFERENCES pricing_catalog(id) ON DELETE RESTRICT,
        provider_duration_ms INTEGER,
        prompt_version VARCHAR(40) NOT NULL,
        raw_usage JSON,
        failure_code VARCHAR(100),
        started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        finished_at TIMESTAMPTZ,
        CONSTRAINT uq_ai_run_native_turn UNIQUE(session_id,native_turn_id)
    )""")
    op.execute("""CREATE TABLE task_phase_runs (
        id UUID PRIMARY KEY,
        task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        stage VARCHAR(24) NOT NULL,
        status VARCHAR(24) NOT NULL,
        actor VARCHAR(255) NOT NULL,
        wait_reason VARCHAR(40) NOT NULL DEFAULT 'NONE',
        requirement_version INTEGER NOT NULL DEFAULT 1,
        started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        finished_at TIMESTAMPTZ
    )""")
    op.execute("""CREATE TABLE validation_runs (
        id UUID PRIMARY KEY,
        task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        head_sha VARCHAR(64) NOT NULL,
        requirement_version INTEGER NOT NULL,
        command JSON NOT NULL,
        exit_code INTEGER,
        status VARCHAR(24) NOT NULL,
        output_tail TEXT NOT NULL DEFAULT '',
        started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        finished_at TIMESTAMPTZ
    )""")
    op.execute("""CREATE TABLE review_cycles (
        id UUID PRIMARY KEY,
        task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        external_event_id VARCHAR(255) NOT NULL,
        head_sha VARCHAR(64) NOT NULL,
        actor VARCHAR(255) NOT NULL,
        decision VARCHAR(40) NOT NULL,
        feedback JSON NOT NULL DEFAULT '{}',
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT uq_review_cycle_event UNIQUE(task_id,external_event_id)
    )""")
    op.create_index("ix_ai_runs_task_started", "ai_runs", ["task_id", "started_at"])
    op.create_index("ix_phase_task_started", "task_phase_runs", ["task_id", "started_at"])
    # Profile migration is an explicit preview/apply operation in the application.
    # Ambiguous legacy agents are not silently guessed; old prompts are retained.


def downgrade() -> None:
    # Downgrades containing V2 evidence require a backup and explicit retention decision.
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM developer_sessions)
          OR EXISTS (SELECT 1 FROM ai_runs)
          OR EXISTS (SELECT 1 FROM task_phase_runs)
          OR EXISTS (SELECT 1 FROM validation_runs)
          OR EXISTS (SELECT 1 FROM review_cycles)
          OR EXISTS (SELECT 1 FROM team_agent_profiles)
          OR EXISTS (SELECT 1 FROM pricing_catalog)
          OR EXISTS (SELECT 1 FROM tasks WHERE execution_version = 2)
        THEN RAISE EXCEPTION 'V2 data exists: back up and migrate it before downgrade';
        END IF;
    END $$""")
    op.drop_table("review_cycles")
    op.drop_table("validation_runs")
    op.drop_table("task_phase_runs")
    op.drop_table("ai_runs")
    op.drop_table("pricing_catalog")
    op.drop_table("developer_sessions")
    op.drop_table("team_agent_profiles")
    op.drop_column("tasks", "lifecycle_version")
    op.drop_column("tasks", "requirement_version")
    op.drop_column("tasks", "wait_reason")
    op.drop_column("tasks", "stage")
    op.drop_column("tasks", "status")
    op.drop_column("tasks", "execution_version")
