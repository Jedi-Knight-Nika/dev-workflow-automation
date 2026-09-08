-- Frozen initial schema. Generated from the reviewed context-owned models.

CREATE TYPE jobstate AS ENUM ('QUEUED', 'CLAIMED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED', 'TIMED_OUT', 'RETRY_WAIT', 'WAITING_PROVIDER', 'WAITING_INTEGRATION', 'WAITING_CONFIGURATION', 'WAITING_HUMAN');

CREATE TYPE integrationstatus AS ENUM ('DISCONNECTED', 'CONFIGURED', 'CONNECTED', 'ERROR');

CREATE TABLE pricing_catalog (
	id UUID NOT NULL,
	provider VARCHAR(40) NOT NULL,
	model VARCHAR(255) NOT NULL,
	version VARCHAR(80) NOT NULL,
	context_tier VARCHAR(40) NOT NULL,
	service_tier VARCHAR(40) NOT NULL,
	input_per_million NUMERIC(18, 8) NOT NULL,
	output_per_million NUMERIC(18, 8) NOT NULL,
	cached_input_per_million NUMERIC(18, 8),
	cache_write_per_million NUMERIC(18, 8),
	source_url TEXT NOT NULL,
	effective_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_pricing_version UNIQUE (provider, model, version, context_tier, service_tier)
);

CREATE TABLE webhook_deliveries (
	id UUID NOT NULL,
	provider VARCHAR(50) NOT NULL,
	delivery_id VARCHAR(255) NOT NULL,
	event_type VARCHAR(100) NOT NULL,
	action VARCHAR(100),
	repository_external_id VARCHAR(255),
	payload JSON NOT NULL,
	status VARCHAR(50) NOT NULL,
	attempts INTEGER NOT NULL,
	last_error TEXT,
	processed_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_webhook_provider_delivery UNIQUE (provider, delivery_id)
);

CREATE INDEX ix_webhook_deliveries_pending ON webhook_deliveries (provider, status, created_at);

CREATE TABLE account_settings (
	id VARCHAR(50) NOT NULL,
	display_name VARCHAR(120) NOT NULL,
	timezone VARCHAR(100) NOT NULL,
	date_format VARCHAR(30) NOT NULL,
	time_format VARCHAR(10) NOT NULL,
	default_landing_page VARCHAR(50) NOT NULL,
	default_task_view VARCHAR(30) NOT NULL,
	appearance VARCHAR(20) NOT NULL,
	compact_dashboard BOOLEAN NOT NULL,
	settings_version INTEGER NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id)
);

CREATE TABLE settings_audit_events (
	id BIGSERIAL NOT NULL,
	section VARCHAR(50) NOT NULL,
	old_values JSON NOT NULL,
	new_values JSON NOT NULL,
	source VARCHAR(50) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id)
);

CREATE TABLE integrations (
	id UUID NOT NULL,
	provider_type VARCHAR(50) NOT NULL,
	provider_name VARCHAR(50) NOT NULL,
	status integrationstatus NOT NULL,
	configuration JSON NOT NULL,
	encrypted_credentials BYTEA,
	last_error TEXT,
	sync_status VARCHAR(30) NOT NULL,
	last_synced_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (provider_name)
);

CREATE INDEX ix_integrations_sync_due ON integrations (provider_name, sync_status, last_synced_at);

CREATE TABLE worker_nodes (
	id VARCHAR(200) NOT NULL,
	hostname VARCHAR(255) NOT NULL,
	process_id INTEGER NOT NULL,
	status VARCHAR(30) NOT NULL,
	capabilities JSON NOT NULL,
	started_at TIMESTAMP WITH TIME ZONE NOT NULL,
	last_heartbeat TIMESTAMP WITH TIME ZONE NOT NULL,
	stopped_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id)
);

CREATE TABLE repositories (
	id UUID NOT NULL,
	provider VARCHAR(50) NOT NULL,
	external_repo_id VARCHAR(255) NOT NULL,
	owner VARCHAR(255) NOT NULL,
	name VARCHAR(255) NOT NULL,
	clone_url TEXT NOT NULL,
	default_branch VARCHAR(255) NOT NULL,
	enabled BOOLEAN NOT NULL,
	latest_sha VARCHAR(64),
	archived_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_repository_external UNIQUE (provider, external_repo_id)
);

CREATE INDEX ix_repositories_archived_at ON repositories (archived_at);

CREATE TABLE teams (
	id UUID NOT NULL,
	name VARCHAR(120) NOT NULL,
	description TEXT NOT NULL,
	enabled BOOLEAN NOT NULL,
	execution_paused BOOLEAN DEFAULT 'false' NOT NULL,
	max_concurrent_tasks INTEGER NOT NULL,
	repository_ids JSON NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	archived_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id),
	CONSTRAINT ck_team_concurrency CHECK (max_concurrent_tasks BETWEEN 1 AND 32),
	UNIQUE (name)
);

CREATE TABLE tasks (
	id UUID NOT NULL,
	external_key VARCHAR(100),
	title VARCHAR(500) NOT NULL,
	description TEXT NOT NULL,
	priority INTEGER NOT NULL,
	status VARCHAR(24) DEFAULT 'NEW' NOT NULL,
	stage VARCHAR(24) DEFAULT 'INTAKE' NOT NULL,
	wait_reason VARCHAR(40) DEFAULT 'NONE' NOT NULL,
	requirement_version INTEGER DEFAULT '1' NOT NULL,
	lifecycle_version INTEGER DEFAULT '1' NOT NULL,
	current_revision VARCHAR(64),
	repository_id UUID,
	team_id UUID,
	branch_name VARCHAR(255),
	workspace_path TEXT,
	pull_request_number INTEGER,
	pull_request_url TEXT,
	manual_takeover BOOLEAN NOT NULL,
	due_at TIMESTAMP WITH TIME ZONE,
	started_at TIMESTAMP WITH TIME ZONE,
	completed_at TIMESTAMP WITH TIME ZONE,
	archived_at TIMESTAMP WITH TIME ZONE,
	project_name VARCHAR(255),
	labels JSON NOT NULL,
	estimate NUMERIC(8, 2),
	progress_fingerprint JSON,
	no_progress_count INTEGER NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_task_status CHECK (status IN ('NEW','ACTIVE','WAITING_EXTERNAL','WAITING_HUMAN','PAUSED','FAILED','CANCELLED','MERGED')),
	CONSTRAINT ck_task_stage CHECK (stage IN ('INTAKE','PLANNING','DEVELOPING','VALIDATING','PUBLISHING','REVIEWING','FIXING','MERGING','COMPLETE')),
	CONSTRAINT ck_task_versions CHECK (requirement_version >= 1 AND lifecycle_version >= 1),
	CONSTRAINT ck_task_priority CHECK (priority BETWEEN 0 AND 5),
	UNIQUE (external_key),
	FOREIGN KEY(repository_id) REFERENCES repositories (id) ON DELETE SET NULL,
	FOREIGN KEY(team_id) REFERENCES teams (id) ON DELETE SET NULL
);

CREATE INDEX ix_tasks_repository ON tasks (repository_id);

CREATE INDEX ix_tasks_status_priority ON tasks (status, priority);

CREATE INDEX ix_tasks_team_status ON tasks (team_id, status);

CREATE INDEX ix_tasks_archived_at ON tasks (archived_at);

CREATE INDEX ix_tasks_due_at ON tasks (due_at);

CREATE TABLE team_automation_policies (
	team_id UUID NOT NULL,
	version INTEGER NOT NULL,
	configuration JSON NOT NULL,
	PRIMARY KEY (team_id),
	FOREIGN KEY(team_id) REFERENCES teams (id) ON DELETE CASCADE
);

CREATE TABLE team_agent_profiles (
	id UUID NOT NULL,
	team_id UUID NOT NULL,
	role_kind VARCHAR(24) NOT NULL,
	display_name VARCHAR(120) NOT NULL,
	avatar VARCHAR(500) NOT NULL,
	enabled BOOLEAN NOT NULL,
	provider VARCHAR(40) NOT NULL,
	model VARCHAR(255) NOT NULL,
	harness VARCHAR(24),
	effort VARCHAR(20) NOT NULL,
	supplemental_instructions TEXT NOT NULL,
	prompt_version VARCHAR(40) NOT NULL,
	soft_budget_usd NUMERIC(12, 6),
	hard_budget_usd NUMERIC(12, 6),
	version INTEGER NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_team_agent_profile_role UNIQUE (team_id, role_kind),
	CONSTRAINT ck_profile_role CHECK (role_kind IN ('INTERPRETER','DEVELOPER','THINKER','REVIEWER')),
	CONSTRAINT ck_profile_hard_budget CHECK (hard_budget_usd IS NULL OR hard_budget_usd > 0),
	CONSTRAINT ck_profile_soft_budget CHECK (soft_budget_usd IS NULL OR soft_budget_usd > 0),
	CONSTRAINT ck_profile_budget_order CHECK (soft_budget_usd IS NULL OR hard_budget_usd IS NULL OR soft_budget_usd <= hard_budget_usd),
	FOREIGN KEY(team_id) REFERENCES teams (id) ON DELETE CASCADE
);

CREATE TABLE developer_sessions (
	id UUID NOT NULL,
	task_id UUID NOT NULL,
	profile_id UUID,
	generation INTEGER NOT NULL,
	harness VARCHAR(24) NOT NULL,
	harness_version VARCHAR(40) NOT NULL,
	provider VARCHAR(40) NOT NULL,
	model VARCHAR(255) NOT NULL,
	native_session_id VARCHAR(255),
	state VARCHAR(24) NOT NULL,
	workspace_path TEXT NOT NULL,
	state_path TEXT NOT NULL,
	checkpoint JSON NOT NULL,
	requirement_version INTEGER NOT NULL,
	last_revision VARCHAR(64),
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_developer_session_generation UNIQUE (task_id, generation),
	FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE,
	FOREIGN KEY(profile_id) REFERENCES team_agent_profiles (id) ON DELETE SET NULL
);

CREATE TABLE external_status_syncs (
	task_id UUID NOT NULL,
	lifecycle_version INTEGER NOT NULL,
	semantic_status VARCHAR(24) NOT NULL,
	status VARCHAR(32) NOT NULL,
	attempts INTEGER NOT NULL,
	next_attempt_at TIMESTAMP WITH TIME ZONE NOT NULL,
	last_error VARCHAR(255),
	PRIMARY KEY (task_id),
	FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE
);

CREATE INDEX ix_external_status_due ON external_status_syncs (status, next_attempt_at);

CREATE TABLE task_phase_runs (
	id UUID NOT NULL,
	task_id UUID NOT NULL,
	stage VARCHAR(24) NOT NULL,
	status VARCHAR(24) NOT NULL,
	actor VARCHAR(255) NOT NULL,
	wait_reason VARCHAR(40) NOT NULL,
	requirement_version INTEGER NOT NULL,
	started_at TIMESTAMP WITH TIME ZONE NOT NULL,
	finished_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id),
	FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE
);

CREATE INDEX ix_phase_task_started ON task_phase_runs (task_id, started_at);

CREATE TABLE validation_runs (
	id UUID NOT NULL,
	task_id UUID NOT NULL,
	head_sha VARCHAR(64) NOT NULL,
	requirement_version INTEGER NOT NULL,
	command JSON NOT NULL,
	exit_code INTEGER,
	status VARCHAR(24) NOT NULL,
	output_tail TEXT NOT NULL,
	started_at TIMESTAMP WITH TIME ZONE NOT NULL,
	finished_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id),
	FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE
);

CREATE TABLE review_cycles (
	id UUID NOT NULL,
	task_id UUID NOT NULL,
	external_event_id VARCHAR(255) NOT NULL,
	head_sha VARCHAR(64) NOT NULL,
	actor VARCHAR(255) NOT NULL,
	decision VARCHAR(40) NOT NULL,
	feedback JSON NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_review_cycle_event UNIQUE (task_id, external_event_id),
	FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE
);

CREATE TABLE task_repository_scopes (
	id UUID NOT NULL,
	task_id UUID NOT NULL,
	repository_id UUID NOT NULL,
	selected_by VARCHAR(30) NOT NULL,
	reason TEXT NOT NULL,
	confidence NUMERIC(4, 3),
	is_primary BOOLEAN NOT NULL,
	workspace_path TEXT,
	branch_name VARCHAR(255),
	base_revision VARCHAR(64),
	current_revision VARCHAR(64),
	changed BOOLEAN NOT NULL,
	pull_request_number INTEGER,
	pull_request_url TEXT,
	merged_at TIMESTAMP WITH TIME ZONE,
	merge_commit_sha VARCHAR(64),
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_task_repository_scope UNIQUE (task_id, repository_id),
	FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE,
	FOREIGN KEY(repository_id) REFERENCES repositories (id) ON DELETE RESTRICT
);

CREATE INDEX ix_task_repository_scopes_repository ON task_repository_scopes (repository_id);

CREATE INDEX ix_task_repository_scopes_task ON task_repository_scopes (task_id);

CREATE TABLE jobs (
	id UUID NOT NULL,
	task_id UUID NOT NULL,
	action VARCHAR(100) NOT NULL,
	priority INTEGER NOT NULL,
	state jobstate NOT NULL,
	attempt INTEGER NOT NULL,
	payload JSON NOT NULL,
	result JSON,
	worker_id VARCHAR(200),
	lease_token UUID,
	lease_expires_at TIMESTAMP WITH TIME ZONE,
	retry_not_before TIMESTAMP WITH TIME ZONE,
	started_at TIMESTAMP WITH TIME ZONE,
	finished_at TIMESTAMP WITH TIME ZONE,
	failure_reason TEXT,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE
);

CREATE INDEX ix_jobs_retry_not_before ON jobs (retry_not_before);

CREATE INDEX ix_jobs_claim ON jobs (state, priority, created_at);

CREATE INDEX ix_jobs_task ON jobs (task_id);

CREATE TABLE task_events (
	id BIGSERIAL NOT NULL,
	task_id UUID NOT NULL,
	source VARCHAR(50) NOT NULL,
	event_type VARCHAR(100) NOT NULL,
	external_event_id VARCHAR(255),
	payload JSON NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_event_source_external_id UNIQUE (source, external_event_id),
	FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE
);

CREATE INDEX ix_task_events_task ON task_events (task_id);

CREATE TABLE local_model_runs (
	id UUID NOT NULL,
	task_id UUID NOT NULL,
	model VARCHAR(255) NOT NULL,
	status VARCHAR(24) NOT NULL,
	duration_ms INTEGER NOT NULL,
	input_tokens INTEGER,
	output_tokens INTEGER,
	started_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE
);

CREATE INDEX ix_local_model_runs_task_id ON local_model_runs (task_id);

CREATE TABLE external_task_snapshots (
	id UUID NOT NULL,
	task_id UUID NOT NULL,
	provider VARCHAR(50) NOT NULL,
	external_id VARCHAR(255) NOT NULL,
	identifier VARCHAR(100) NOT NULL,
	assignee_id VARCHAR(255),
	state_id VARCHAR(255),
	raw_payload JSON NOT NULL,
	synchronized_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_external_task_provider_id UNIQUE (provider, external_id),
	FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE
);

CREATE INDEX ix_external_task_snapshots_task ON external_task_snapshots (task_id);

CREATE TABLE task_assignments (
	id UUID NOT NULL,
	task_id UUID NOT NULL,
	team_id UUID NOT NULL,
	status VARCHAR(30) NOT NULL,
	queue_position BIGINT NOT NULL,
	reason TEXT NOT NULL,
	assigned_at TIMESTAMP WITH TIME ZONE NOT NULL,
	started_at TIMESTAMP WITH TIME ZONE,
	completed_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id),
	FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE,
	FOREIGN KEY(team_id) REFERENCES teams (id) ON DELETE RESTRICT
);

CREATE INDEX ix_task_assignments_team_queue ON task_assignments (team_id, status, queue_position);

CREATE INDEX ix_task_assignments_task ON task_assignments (task_id);

CREATE UNIQUE INDEX uq_task_assignments_active ON task_assignments (task_id) WHERE status IN ('QUEUED', 'RUNNING');

CREATE TABLE ai_runs (
	id UUID NOT NULL,
	task_id UUID NOT NULL,
	session_id UUID,
	job_id UUID,
	native_turn_id VARCHAR(255),
	native_session_id VARCHAR(255),
	artifact TEXT,
	requirement_version INTEGER DEFAULT '1' NOT NULL,
	role_kind VARCHAR(24) NOT NULL,
	provider VARCHAR(40) NOT NULL,
	model VARCHAR(255) NOT NULL,
	harness VARCHAR(24),
	status VARCHAR(24) NOT NULL,
	input_tokens INTEGER,
	output_tokens INTEGER,
	cache_read_tokens INTEGER,
	cache_write_tokens INTEGER,
	reasoning_tokens INTEGER,
	usage_complete BOOLEAN NOT NULL,
	provider_cost_usd NUMERIC(18, 8),
	calculated_cost_usd NUMERIC(18, 8),
	reserved_cost_usd NUMERIC(18, 8),
	pricing_id UUID,
	provider_duration_ms INTEGER,
	prompt_version VARCHAR(40) NOT NULL,
	raw_usage JSON,
	failure_code VARCHAR(100),
	started_at TIMESTAMP WITH TIME ZONE NOT NULL,
	finished_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id),
	CONSTRAINT uq_ai_run_native_turn UNIQUE (session_id, native_turn_id),
	CONSTRAINT ck_ai_input_tokens CHECK (input_tokens IS NULL OR input_tokens >= 0),
	CONSTRAINT ck_ai_output_tokens CHECK (output_tokens IS NULL OR output_tokens >= 0),
	FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE,
	FOREIGN KEY(session_id) REFERENCES developer_sessions (id) ON DELETE SET NULL,
	FOREIGN KEY(job_id) REFERENCES jobs (id) ON DELETE SET NULL,
	FOREIGN KEY(pricing_id) REFERENCES pricing_catalog (id) ON DELETE RESTRICT
);

CREATE INDEX ix_ai_runs_task_started ON ai_runs (task_id, started_at);

CREATE TABLE task_messages (
	id BIGSERIAL NOT NULL,
	task_id UUID NOT NULL,
	job_id UUID,
	reply_to_id BIGINT,
	author_type VARCHAR(20) NOT NULL,
	author_name VARCHAR(120) NOT NULL,
	author_role VARCHAR(30),
	kind VARCHAR(30) NOT NULL,
	body TEXT NOT NULL,
	context JSON NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE,
	UNIQUE (job_id),
	FOREIGN KEY(job_id) REFERENCES jobs (id) ON DELETE SET NULL,
	FOREIGN KEY(reply_to_id) REFERENCES task_messages (id) ON DELETE SET NULL
);

CREATE INDEX ix_task_messages_task_id_id ON task_messages (task_id, id);

CREATE INDEX ix_task_messages_reply_to_id ON task_messages (reply_to_id);
