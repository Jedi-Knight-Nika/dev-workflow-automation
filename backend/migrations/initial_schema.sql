-- Frozen initial application schema. No MVP upgrade or pgvector dependency.
-- Do not regenerate this snapshot once deployed; subsequent schema changes need an explicit revision.

CREATE TYPE indexstatus AS ENUM ('NOT_INDEXED', 'QUEUED', 'INDEXING', 'READY', 'FAILED');

CREATE TYPE integrationstatus AS ENUM ('DISCONNECTED', 'CONFIGURED', 'CONNECTED', 'ERROR');

CREATE TYPE jobrole AS ENUM ('ORCHESTRATOR', 'INTAKE', 'THINKER', 'EXECUTOR', 'REVIEWER', 'TESTER', 'DELIVERER');

CREATE TYPE jobstate AS ENUM ('QUEUED', 'CLAIMED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED', 'TIMED_OUT', 'RETRY_WAIT', 'WAITING_PROVIDER', 'WAITING_INTEGRATION', 'WAITING_CONFIGURATION', 'WAITING_HUMAN');

CREATE TYPE taskstate AS ENUM ('NEW', 'CONTEXT_PENDING', 'PLANNING', 'PLAN_READY', 'QUEUED_FOR_EXECUTION', 'IMPLEMENTING', 'LOCAL_VALIDATION', 'INTERNAL_REVIEW', 'WAITING_GITHUB', 'READY_TO_MERGE', 'NEEDS_HUMAN', 'PAUSED', 'CANCELLED', 'FAILED', 'MERGED');

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
	default_provider_id VARCHAR(50), 
	default_model VARCHAR(255), 
	default_reasoning_level VARCHAR(20) NOT NULL, 
	default_max_output_tokens INTEGER, 
	provider_failure_behavior VARCHAR(40) NOT NULL, 
	structured_output_retry_limit INTEGER NOT NULL, 
	default_execution_mode VARCHAR(30) NOT NULL, 
	default_worker_runtime VARCHAR(30) NOT NULL, 
	max_concurrent_workers INTEGER NOT NULL, 
	default_job_timeout_seconds INTEGER NOT NULL, 
	default_merge_policy VARCHAR(30) NOT NULL, 
	default_unknown_network_policy VARCHAR(30) NOT NULL, 
	default_dependency_install_policy VARCHAR(30) NOT NULL, 
	default_push_task_branch_policy VARCHAR(30) NOT NULL, 
	auto_index_repositories BOOLEAN NOT NULL, 
	incremental_index_after_merge BOOLEAN NOT NULL, 
	index_source_code BOOLEAN NOT NULL, 
	index_tests BOOLEAN NOT NULL, 
	index_documentation BOOLEAN NOT NULL, 
	ignore_generated_files BOOLEAN NOT NULL, 
	context_strategy VARCHAR(20) NOT NULL, 
	completed_workspace_retention_days INTEGER NOT NULL, 
	failed_workspace_retention_days INTEGER NOT NULL, 
	worker_log_retention_days INTEGER NOT NULL, 
	audit_event_retention_days INTEGER NOT NULL, 
	monthly_cost_warning NUMERIC(14, 2), 
	monthly_cost_hard_stop NUMERIC(14, 2), 
	settings_version INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE agent_configs (
	role jobrole NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	provider VARCHAR(50) NOT NULL, 
	model VARCHAR(255) NOT NULL, 
	configuration JSON NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (role)
);

CREATE TABLE agent_knowledge_sources (
	id UUID NOT NULL, 
	role jobrole NOT NULL, 
	title VARCHAR(255) NOT NULL, 
	content TEXT NOT NULL, 
	chunk_count INTEGER NOT NULL, 
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

CREATE TABLE repositories (
	id UUID NOT NULL, 
	provider VARCHAR(50) NOT NULL, 
	external_repo_id VARCHAR(255) NOT NULL, 
	owner VARCHAR(255) NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	clone_url TEXT NOT NULL, 
	default_branch VARCHAR(255) NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	local_path TEXT, 
	latest_sha VARCHAR(64), 
	indexed_sha VARCHAR(64), 
	indexed_at TIMESTAMP WITH TIME ZONE, 
	index_status indexstatus NOT NULL, 
	index_error TEXT, 
	archived_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_repository_external UNIQUE (provider, external_repo_id)
);

CREATE INDEX ix_repositories_archived_at ON repositories (archived_at);

CREATE TABLE roles (
	id UUID NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	category VARCHAR(30) NOT NULL, 
	description TEXT NOT NULL, 
	system_instructions TEXT NOT NULL, 
	capabilities JSON NOT NULL, 
	permissions JSON NOT NULL, 
	allowed_results JSON NOT NULL, 
	knowledge_collection_ids JSON NOT NULL, 
	default_provider VARCHAR(50), 
	default_model VARCHAR(255), 
	default_reasoning_effort VARCHAR(20) NOT NULL, 
	default_timeout_minutes INTEGER NOT NULL, 
	default_max_retries INTEGER NOT NULL, 
	runtime_profile JSON NOT NULL, 
	override_policy JSON NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	built_in BOOLEAN NOT NULL, 
	version INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	archived_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	UNIQUE (name)
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

CREATE TABLE teams (
	id UUID NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	description TEXT NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	max_concurrent_tasks INTEGER NOT NULL, 
	repository_ids JSON NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	archived_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_team_concurrency CHECK (max_concurrent_tasks BETWEEN 1 AND 32), 
	UNIQUE (name)
);

CREATE TABLE telegram_connection_tokens (
	id UUID NOT NULL, 
	user_id VARCHAR(255) NOT NULL, 
	token_hash VARCHAR(64) NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	used_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (token_hash)
);

CREATE TABLE telegram_connections (
	id UUID NOT NULL, 
	user_id VARCHAR(255) NOT NULL, 
	telegram_user_id VARCHAR(40) NOT NULL, 
	telegram_chat_id VARCHAR(40) NOT NULL, 
	telegram_username VARCHAR(255), 
	enabled BOOLEAN NOT NULL, 
	connected_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_delivery_at TIMESTAMP WITH TIME ZONE, 
	last_delivery_error TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (user_id), 
	UNIQUE (telegram_chat_id)
);

CREATE TABLE telegram_updates (
	update_id BIGSERIAL NOT NULL, 
	processed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (update_id)
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

CREATE TABLE agent_knowledge_chunks (
	id UUID NOT NULL, 
	source_id UUID NOT NULL, 
	role jobrole NOT NULL, 
	chunk_index INTEGER NOT NULL, 
	content TEXT NOT NULL, 
	embedding TEXT NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(source_id) REFERENCES agent_knowledge_sources (id) ON DELETE CASCADE
);

CREATE INDEX ix_agent_knowledge_chunks_role ON agent_knowledge_chunks (role);

CREATE INDEX ix_agent_knowledge_chunks_source ON agent_knowledge_chunks (source_id);

CREATE TABLE ai_agents (
	id UUID NOT NULL, 
	team_id UUID NOT NULL, 
	role_id UUID NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	provider VARCHAR(50), 
	model VARCHAR(255), 
	custom_instructions TEXT NOT NULL, 
	permission_overrides JSON NOT NULL, 
	knowledge_collection_ids JSON NOT NULL, 
	runtime_overrides JSON NOT NULL, 
	config_version INTEGER NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_ai_agent_team_name UNIQUE (team_id, name), 
	FOREIGN KEY(team_id) REFERENCES teams (id) ON DELETE CASCADE, 
	FOREIGN KEY(role_id) REFERENCES roles (id) ON DELETE RESTRICT
);

CREATE INDEX ix_ai_agents_role ON ai_agents (role_id);

CREATE TABLE execution_policies (
	id UUID NOT NULL, 
	team_id UUID NOT NULL, 
	mode VARCHAR(30) NOT NULL, 
	settings JSON NOT NULL, 
	approved_hosts JSON NOT NULL, 
	max_command_timeout_seconds INTEGER NOT NULL, 
	max_output_bytes INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (team_id), 
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

CREATE TABLE team_automation_policies (
	team_id UUID NOT NULL, 
	version INTEGER NOT NULL, 
	configuration JSON NOT NULL, 
	PRIMARY KEY (team_id), 
	FOREIGN KEY(team_id) REFERENCES teams (id) ON DELETE CASCADE
);

CREATE TABLE workflow_definitions (
	id UUID NOT NULL, 
	team_id UUID, 
	version INTEGER NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	entry_node_id UUID, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (team_id), 
	FOREIGN KEY(team_id) REFERENCES teams (id) ON DELETE CASCADE
);

CREATE TABLE tasks (
	id UUID NOT NULL, 
	external_key VARCHAR(100), 
	title VARCHAR(500) NOT NULL, 
	description TEXT NOT NULL, 
	priority INTEGER NOT NULL, 
	state taskstate NOT NULL, 
	execution_version INTEGER DEFAULT '1' NOT NULL, 
	status VARCHAR(24), 
	stage VARCHAR(24), 
	wait_reason VARCHAR(40), 
	requirement_version INTEGER DEFAULT '1' NOT NULL, 
	lifecycle_version INTEGER DEFAULT '1' NOT NULL, 
	current_revision VARCHAR(64), 
	repository_id UUID, 
	team_id UUID, 
	workflow_id UUID, 
	workflow_version INTEGER, 
	current_workflow_node_id UUID, 
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
	execution_profile JSON, 
	execution_strategy JSON, 
	progress_fingerprint JSON, 
	no_progress_count INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (external_key), 
	FOREIGN KEY(repository_id) REFERENCES repositories (id) ON DELETE SET NULL, 
	FOREIGN KEY(team_id) REFERENCES teams (id) ON DELETE SET NULL, 
	FOREIGN KEY(workflow_id) REFERENCES workflow_definitions (id) ON DELETE SET NULL
);

CREATE INDEX ix_tasks_archived_at ON tasks (archived_at);

CREATE INDEX ix_tasks_due_at ON tasks (due_at);

CREATE INDEX ix_tasks_repository ON tasks (repository_id);

CREATE INDEX ix_tasks_state_priority ON tasks (state, priority);

CREATE INDEX ix_tasks_team_state ON tasks (team_id, state);

CREATE INDEX ix_tasks_workflow ON tasks (workflow_id);

CREATE TABLE workflow_nodes (
	id UUID NOT NULL, 
	workflow_id UUID NOT NULL, 
	agent_id UUID, 
	role VARCHAR(30) NOT NULL, 
	node_type VARCHAR(30) NOT NULL, 
	system_node_type VARCHAR(30), 
	label VARCHAR(100) NOT NULL, 
	position_x NUMERIC(12, 3) NOT NULL, 
	position_y NUMERIC(12, 3) NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	activation_policy VARCHAR(20) NOT NULL, 
	batch_window_seconds INTEGER NOT NULL, 
	integration_ids JSON NOT NULL, 
	repository_ids JSON NOT NULL, 
	provider VARCHAR(50) NOT NULL, 
	model VARCHAR(255) NOT NULL, 
	system_prompt TEXT NOT NULL, 
	model_validation_status VARCHAR(30) NOT NULL, 
	model_validation_message TEXT, 
	model_validated_at TIMESTAMP WITH TIME ZONE, 
	integration_mode VARCHAR(20) NOT NULL, 
	poll_interval_seconds INTEGER NOT NULL, 
	filter_assignee_id VARCHAR(255) NOT NULL, 
	filter_state_ids JSON NOT NULL, 
	integration_sync_status VARCHAR(30) NOT NULL, 
	integration_sync_error TEXT, 
	integration_last_synced_at TIMESTAMP WITH TIME ZONE, 
	reasoning_effort VARCHAR(20) NOT NULL, 
	max_output_tokens INTEGER, 
	temperature NUMERIC(4, 2), 
	timeout_minutes INTEGER NOT NULL, 
	max_retries INTEGER NOT NULL, 
	max_review_cycles INTEGER NOT NULL, 
	context_depth VARCHAR(20) NOT NULL, 
	rag_retrieval_depth VARCHAR(20) NOT NULL, 
	fallback_provider VARCHAR(50), 
	fallback_model VARCHAR(255), 
	PRIMARY KEY (id), 
	FOREIGN KEY(workflow_id) REFERENCES workflow_definitions (id) ON DELETE CASCADE, 
	FOREIGN KEY(agent_id) REFERENCES ai_agents (id) ON DELETE SET NULL
);

CREATE INDEX ix_workflow_nodes_agent ON workflow_nodes (agent_id);

CREATE INDEX ix_workflow_nodes_workflow ON workflow_nodes (workflow_id);

CREATE TABLE workflow_revisions (
	id UUID NOT NULL, 
	workflow_id UUID NOT NULL, 
	version INTEGER NOT NULL, 
	graph JSON NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_workflow_revision_version UNIQUE (workflow_id, version), 
	FOREIGN KEY(workflow_id) REFERENCES workflow_definitions (id) ON DELETE CASCADE
);

CREATE INDEX ix_workflow_revisions_workflow ON workflow_revisions (workflow_id);

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

CREATE TABLE jobs (
	id UUID NOT NULL, 
	task_id UUID NOT NULL, 
	role jobrole NOT NULL, 
	workflow_node_id UUID, 
	agent_id UUID, 
	team_workflow_version INTEGER, 
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
	FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE, 
	FOREIGN KEY(agent_id) REFERENCES ai_agents (id) ON DELETE SET NULL
);

CREATE INDEX ix_jobs_agent ON jobs (agent_id);

CREATE INDEX ix_jobs_claim ON jobs (state, priority, created_at);

CREATE INDEX ix_jobs_retry_not_before ON jobs (retry_not_before);

CREATE INDEX ix_jobs_task ON jobs (task_id);

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

CREATE INDEX ix_task_assignments_task ON task_assignments (task_id);

CREATE INDEX ix_task_assignments_team_queue ON task_assignments (team_id, status, queue_position);

CREATE UNIQUE INDEX uq_task_assignments_active ON task_assignments (task_id) WHERE status IN ('QUEUED', 'RUNNING');

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

CREATE TABLE terminal_sessions (
	id UUID NOT NULL, 
	task_id UUID NOT NULL, 
	node_id UUID, 
	status VARCHAR(30) NOT NULL, 
	token_hash VARCHAR(64) NOT NULL, 
	cols INTEGER NOT NULL, 
	rows INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	closed_at TIMESTAMP WITH TIME ZONE, 
	exit_code INTEGER, 
	runtime_owner_id VARCHAR(255), 
	runtime_heartbeat_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE
);

CREATE INDEX ix_terminal_sessions_task ON terminal_sessions (task_id);

CREATE TABLE validation_records (
	id UUID NOT NULL, 
	task_id UUID NOT NULL, 
	provider VARCHAR(50) NOT NULL, 
	kind VARCHAR(50) NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	status VARCHAR(50) NOT NULL, 
	revision VARCHAR(64) NOT NULL, 
	details_url TEXT, 
	payload JSON NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE
);

CREATE INDEX ix_validation_task_revision ON validation_records (task_id, revision);

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

CREATE TABLE workflow_edges (
	id UUID NOT NULL, 
	workflow_id UUID NOT NULL, 
	source_node_id UUID NOT NULL, 
	target_node_id UUID NOT NULL, 
	outcome VARCHAR(30) NOT NULL, 
	required BOOLEAN NOT NULL, 
	job_type VARCHAR(100), 
	internal_task_state VARCHAR(50), 
	external_status_key VARCHAR(100), 
	priority_override INTEGER, 
	configuration JSON NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_workflow_edge_route UNIQUE (workflow_id, source_node_id, target_node_id, outcome), 
	FOREIGN KEY(workflow_id) REFERENCES workflow_definitions (id) ON DELETE CASCADE, 
	FOREIGN KEY(source_node_id) REFERENCES workflow_nodes (id) ON DELETE CASCADE, 
	FOREIGN KEY(target_node_id) REFERENCES workflow_nodes (id) ON DELETE CASCADE
);

CREATE INDEX ix_workflow_edges_source ON workflow_edges (source_node_id);

CREATE INDEX ix_workflow_edges_target ON workflow_edges (target_node_id);

CREATE TABLE agent_checkpoints (
	id UUID NOT NULL, 
	task_id UUID NOT NULL, 
	job_id UUID NOT NULL, 
	agent_id UUID, 
	role_id UUID, 
	role jobrole NOT NULL, 
	checkpoint_type VARCHAR(50) NOT NULL, 
	repository_sha VARCHAR(64), 
	summary TEXT NOT NULL, 
	structured_data JSON NOT NULL, 
	token_estimate INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE, 
	UNIQUE (job_id), 
	FOREIGN KEY(job_id) REFERENCES jobs (id) ON DELETE CASCADE, 
	FOREIGN KEY(agent_id) REFERENCES ai_agents (id) ON DELETE SET NULL, 
	FOREIGN KEY(role_id) REFERENCES roles (id) ON DELETE SET NULL
);

CREATE INDEX ix_agent_checkpoints_agent ON agent_checkpoints (agent_id);

CREATE INDEX ix_agent_checkpoints_role_id ON agent_checkpoints (role_id);

CREATE INDEX ix_checkpoints_task_role_created ON agent_checkpoints (task_id, role, created_at);

CREATE TABLE ai_runs (
	id UUID NOT NULL, 
	task_id UUID NOT NULL, 
	session_id UUID, 
	job_id UUID, 
	native_turn_id VARCHAR(255), 
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

CREATE TABLE approval_requests (
	id UUID NOT NULL, 
	team_id UUID NOT NULL, 
	task_id UUID NOT NULL, 
	job_id UUID NOT NULL, 
	agent_id UUID, 
	tool VARCHAR(80) NOT NULL, 
	action VARCHAR(120) NOT NULL, 
	arguments JSON NOT NULL, 
	arguments_hash VARCHAR(64) NOT NULL, 
	reason TEXT NOT NULL, 
	state VARCHAR(30) NOT NULL, 
	resolution_scope VARCHAR(30), 
	resolved_by VARCHAR(255), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	resolved_at TIMESTAMP WITH TIME ZONE, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(team_id) REFERENCES teams (id) ON DELETE CASCADE, 
	FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE, 
	FOREIGN KEY(job_id) REFERENCES jobs (id) ON DELETE CASCADE, 
	FOREIGN KEY(agent_id) REFERENCES ai_agents (id) ON DELETE SET NULL
);

CREATE INDEX ix_approval_pending ON approval_requests (state, expires_at);

CREATE INDEX ix_approvals_job ON approval_requests (job_id);

CREATE INDEX ix_approvals_task ON approval_requests (task_id);

CREATE INDEX ix_approvals_team_state ON approval_requests (team_id, state);

CREATE TABLE failure_events (
	id UUID NOT NULL, 
	task_id UUID, 
	job_id UUID, 
	resource_type VARCHAR(40), 
	resource_id VARCHAR(255), 
	failure_class VARCHAR(80) NOT NULL, 
	fingerprint VARCHAR(255) NOT NULL, 
	error_code VARCHAR(100), 
	safe_message TEXT NOT NULL, 
	technical_details_json JSON NOT NULL, 
	retryable BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE SET NULL, 
	FOREIGN KEY(job_id) REFERENCES jobs (id) ON DELETE SET NULL
);

CREATE INDEX ix_failure_events_fingerprint ON failure_events (fingerprint);

CREATE INDEX ix_failure_events_job_created ON failure_events (job_id, created_at);

CREATE TABLE health_states (
	id UUID NOT NULL, 
	resource_type VARCHAR(40) NOT NULL, 
	resource_id VARCHAR(255) NOT NULL, 
	status VARCHAR(30) NOT NULL, 
	circuit_state VARCHAR(20) NOT NULL, 
	consecutive_failures INTEGER NOT NULL, 
	last_success_at TIMESTAMP WITH TIME ZONE, 
	last_failure_at TIMESTAMP WITH TIME ZONE, 
	next_probe_at TIMESTAMP WITH TIME ZONE, 
	last_error_class VARCHAR(80), 
	failure_fingerprint VARCHAR(255), 
	probe_job_id UUID, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_health_resource UNIQUE (resource_type, resource_id), 
	FOREIGN KEY(probe_job_id) REFERENCES jobs (id) ON DELETE SET NULL
);

CREATE INDEX ix_health_probe ON health_states (circuit_state, next_probe_at);

CREATE TABLE incidents (
	id UUID NOT NULL, 
	fingerprint VARCHAR(255) NOT NULL, 
	type VARCHAR(100) NOT NULL, 
	severity VARCHAR(30) NOT NULL, 
	status VARCHAR(30) NOT NULL, 
	team_id UUID, 
	task_id UUID, 
	job_id UUID, 
	integration_id UUID, 
	title VARCHAR(500) NOT NULL, 
	summary TEXT NOT NULL, 
	root_resource_type VARCHAR(40), 
	root_resource_id VARCHAR(255), 
	occurrence_count INTEGER NOT NULL, 
	metadata_json JSON NOT NULL, 
	first_seen_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	acknowledged_at TIMESTAMP WITH TIME ZONE, 
	resolved_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (fingerprint), 
	FOREIGN KEY(team_id) REFERENCES teams (id) ON DELETE SET NULL, 
	FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE SET NULL, 
	FOREIGN KEY(job_id) REFERENCES jobs (id) ON DELETE SET NULL, 
	FOREIGN KEY(integration_id) REFERENCES integrations (id) ON DELETE SET NULL
);

CREATE INDEX ix_incidents_integration ON incidents (integration_id);

CREATE INDEX ix_incidents_job ON incidents (job_id);

CREATE INDEX ix_incidents_status_severity ON incidents (status, severity);

CREATE INDEX ix_incidents_task ON incidents (task_id);

CREATE INDEX ix_incidents_team ON incidents (team_id);

CREATE TABLE job_contexts (
	id UUID NOT NULL, 
	job_id UUID NOT NULL, 
	compiler_version VARCHAR(30) NOT NULL, 
	task_memory_version INTEGER, 
	repository_sha VARCHAR(64), 
	checkpoint_ids JSON NOT NULL, 
	plan_job_id UUID, 
	finding_ids JSON NOT NULL, 
	rag_chunk_ids JSON NOT NULL, 
	estimated_input_tokens INTEGER NOT NULL, 
	compilation_duration_ms INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (job_id), 
	FOREIGN KEY(job_id) REFERENCES jobs (id) ON DELETE CASCADE, 
	FOREIGN KEY(plan_job_id) REFERENCES jobs (id) ON DELETE SET NULL
);

CREATE INDEX ix_job_contexts_plan_job ON job_contexts (plan_job_id);

CREATE TABLE job_retry_states (
	job_id UUID NOT NULL, 
	provider_retry_count INTEGER NOT NULL, 
	integration_retry_count INTEGER NOT NULL, 
	worker_retry_count INTEGER NOT NULL, 
	protocol_retry_count INTEGER NOT NULL, 
	engineering_retry_count INTEGER NOT NULL, 
	next_retry_at TIMESTAMP WITH TIME ZONE, 
	last_failure_fingerprint VARCHAR(255), 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (job_id), 
	FOREIGN KEY(job_id) REFERENCES jobs (id) ON DELETE CASCADE
);

CREATE TABLE review_findings (
	id UUID NOT NULL, 
	task_id UUID NOT NULL, 
	reviewer_job_id UUID NOT NULL, 
	workspace_fingerprint VARCHAR(64) NOT NULL, 
	finding_fingerprint VARCHAR(64), 
	occurrence_count INTEGER NOT NULL, 
	severity VARCHAR(20) NOT NULL, 
	file_path TEXT, 
	line INTEGER, 
	message TEXT NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen_at TIMESTAMP WITH TIME ZONE, 
	resolved_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE, 
	FOREIGN KEY(reviewer_job_id) REFERENCES jobs (id) ON DELETE CASCADE
);

CREATE INDEX ix_review_findings_fingerprint ON review_findings (task_id, finding_fingerprint);

CREATE INDEX ix_review_findings_reviewer_job ON review_findings (reviewer_job_id);

CREATE INDEX ix_review_findings_task_status ON review_findings (task_id, status);

CREATE TABLE task_memories (
	task_id UUID NOT NULL, 
	goal TEXT NOT NULL, 
	known_facts JSON NOT NULL, 
	decisions JSON NOT NULL, 
	rejected_approaches JSON NOT NULL, 
	invariants JSON NOT NULL, 
	important_files JSON NOT NULL, 
	important_symbols JSON NOT NULL, 
	open_questions JSON NOT NULL, 
	open_finding_ids JSON NOT NULL, 
	resolved_finding_summaries JSON NOT NULL, 
	current_plan_job_id UUID, 
	current_sha VARCHAR(64), 
	version INTEGER NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (task_id), 
	FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE, 
	FOREIGN KEY(current_plan_job_id) REFERENCES jobs (id) ON DELETE SET NULL
);

CREATE INDEX ix_task_memories_plan_job ON task_memories (current_plan_job_id);

CREATE TABLE task_messages (
	id BIGSERIAL NOT NULL, 
	task_id UUID NOT NULL, 
	job_id UUID, 
	reply_to_id BIGINT, 
	agent_id UUID, 
	author_type VARCHAR(20) NOT NULL, 
	author_name VARCHAR(120) NOT NULL, 
	author_role VARCHAR(30), 
	kind VARCHAR(30) NOT NULL, 
	body TEXT NOT NULL, 
	context JSON NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	edited_at TIMESTAMP WITH TIME ZONE, 
	deleted_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE, 
	UNIQUE (job_id), 
	FOREIGN KEY(job_id) REFERENCES jobs (id) ON DELETE SET NULL, 
	FOREIGN KEY(reply_to_id) REFERENCES task_messages (id) ON DELETE SET NULL, 
	FOREIGN KEY(agent_id) REFERENCES ai_agents (id) ON DELETE SET NULL
);

CREATE INDEX ix_task_messages_agent_id ON task_messages (agent_id);

CREATE INDEX ix_task_messages_reply_to_id ON task_messages (reply_to_id);

CREATE INDEX ix_task_messages_task_id_id ON task_messages (task_id, id);

CREATE TABLE terminal_events (
	id BIGSERIAL NOT NULL, 
	session_id UUID NOT NULL, 
	sequence INTEGER NOT NULL, 
	event_type VARCHAR(30) NOT NULL, 
	payload JSON NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(session_id) REFERENCES terminal_sessions (id) ON DELETE CASCADE
);

CREATE INDEX ix_terminal_events_session_sequence ON terminal_events (session_id, sequence);

CREATE TABLE worker_runs (
	id UUID NOT NULL, 
	job_id UUID NOT NULL, 
	role jobrole NOT NULL, 
	provider VARCHAR(50) NOT NULL, 
	model VARCHAR(255) NOT NULL, 
	input_tokens INTEGER, 
	output_tokens INTEGER, 
	estimated_cost_usd NUMERIC(14, 6), 
	duration_ms INTEGER NOT NULL, 
	provider_request_id VARCHAR(255), 
	agent_id UUID, 
	role_id UUID, 
	role_version INTEGER, 
	effective_permissions JSON NOT NULL, 
	effective_knowledge_scope JSON NOT NULL, 
	effective_runtime_config JSON NOT NULL, 
	effective_runtime_config_hash VARCHAR(64), 
	model_capability_version VARCHAR(30), 
	agent_config_version INTEGER, 
	strategy_version VARCHAR(30), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(job_id) REFERENCES jobs (id) ON DELETE CASCADE, 
	FOREIGN KEY(agent_id) REFERENCES ai_agents (id) ON DELETE SET NULL, 
	FOREIGN KEY(role_id) REFERENCES roles (id) ON DELETE SET NULL
);

CREATE INDEX ix_worker_runs_agent ON worker_runs (agent_id);

CREATE INDEX ix_worker_runs_job ON worker_runs (job_id);

CREATE INDEX ix_worker_runs_role ON worker_runs (role_id);

CREATE TABLE workflow_transitions (
	id UUID NOT NULL, 
	task_id UUID NOT NULL, 
	job_id UUID NOT NULL, 
	workflow_id UUID NOT NULL, 
	workflow_version INTEGER NOT NULL, 
	from_node_id UUID NOT NULL, 
	result_type VARCHAR(80) NOT NULL, 
	matched_edge_id UUID, 
	to_node_id UUID, 
	new_job_type VARCHAR(100), 
	internal_state VARCHAR(50), 
	external_status_key VARCHAR(100), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE, 
	FOREIGN KEY(job_id) REFERENCES jobs (id) ON DELETE CASCADE, 
	FOREIGN KEY(workflow_id) REFERENCES workflow_definitions (id) ON DELETE CASCADE
);

CREATE INDEX ix_workflow_transitions_job ON workflow_transitions (job_id);

CREATE INDEX ix_workflow_transitions_task_created ON workflow_transitions (task_id, created_at);

CREATE INDEX ix_workflow_transitions_workflow ON workflow_transitions (workflow_id);

CREATE TABLE workspace_leases (
	task_id UUID NOT NULL, 
	job_id UUID NOT NULL, 
	token UUID NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (task_id), 
	FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE, 
	FOREIGN KEY(job_id) REFERENCES jobs (id) ON DELETE CASCADE
);

CREATE INDEX ix_workspace_leases_job ON workspace_leases (job_id);

CREATE TABLE notifications (
	id UUID NOT NULL, 
	user_id VARCHAR(255) NOT NULL, 
	incident_id UUID, 
	team_id UUID, 
	task_id UUID, 
	job_id UUID, 
	type VARCHAR(100) NOT NULL, 
	severity VARCHAR(30) NOT NULL, 
	title VARCHAR(500) NOT NULL, 
	message TEXT NOT NULL, 
	status VARCHAR(30) NOT NULL, 
	action_type VARCHAR(80), 
	action_target TEXT, 
	metadata_json JSON NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	read_at TIMESTAMP WITH TIME ZONE, 
	acknowledged_at TIMESTAMP WITH TIME ZONE, 
	resolved_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(incident_id) REFERENCES incidents (id) ON DELETE SET NULL, 
	FOREIGN KEY(team_id) REFERENCES teams (id) ON DELETE SET NULL, 
	FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE SET NULL, 
	FOREIGN KEY(job_id) REFERENCES jobs (id) ON DELETE SET NULL
);

CREATE INDEX ix_notifications_incident ON notifications (incident_id);

CREATE INDEX ix_notifications_job ON notifications (job_id);

CREATE INDEX ix_notifications_task ON notifications (task_id);

CREATE INDEX ix_notifications_team ON notifications (team_id);

CREATE INDEX ix_notifications_user_status ON notifications (user_id, status);

CREATE TABLE tool_execution_events (
	id UUID NOT NULL, 
	team_id UUID NOT NULL, 
	task_id UUID NOT NULL, 
	job_id UUID NOT NULL, 
	worker_run_id UUID, 
	agent_id UUID, 
	role_id UUID, 
	tool VARCHAR(80) NOT NULL, 
	action VARCHAR(120) NOT NULL, 
	decision VARCHAR(30) NOT NULL, 
	policy_rule VARCHAR(255) NOT NULL, 
	arguments_sanitized JSON NOT NULL, 
	exit_code INTEGER, 
	duration_ms INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(team_id) REFERENCES teams (id) ON DELETE CASCADE, 
	FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE, 
	FOREIGN KEY(job_id) REFERENCES jobs (id) ON DELETE CASCADE, 
	FOREIGN KEY(worker_run_id) REFERENCES worker_runs (id) ON DELETE SET NULL, 
	FOREIGN KEY(agent_id) REFERENCES ai_agents (id) ON DELETE SET NULL, 
	FOREIGN KEY(role_id) REFERENCES roles (id) ON DELETE SET NULL
);

CREATE INDEX ix_tool_events_job ON tool_execution_events (job_id);

CREATE INDEX ix_tool_events_task_created ON tool_execution_events (task_id, created_at);

CREATE INDEX ix_tool_events_team ON tool_execution_events (team_id);

CREATE TABLE notification_deliveries (
	id UUID NOT NULL, 
	notification_id UUID NOT NULL, 
	channel VARCHAR(30) NOT NULL, 
	recipient_ref VARCHAR(255) NOT NULL, 
	state VARCHAR(30) NOT NULL, 
	attempt_count INTEGER NOT NULL, 
	last_attempt_at TIMESTAMP WITH TIME ZONE, 
	next_attempt_at TIMESTAMP WITH TIME ZONE, 
	delivered_at TIMESTAMP WITH TIME ZONE, 
	failure_code VARCHAR(100), 
	failure_message TEXT, 
	external_message_id VARCHAR(255), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(notification_id) REFERENCES notifications (id) ON DELETE CASCADE
);

CREATE INDEX ix_notification_deliveries_notification ON notification_deliveries (notification_id);

CREATE INDEX ix_notification_deliveries_retry_due ON notification_deliveries (channel, state, next_attempt_at);
