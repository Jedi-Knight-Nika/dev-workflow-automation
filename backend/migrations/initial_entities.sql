-- Initial entities only: no example tickets, job history, credentials, or guessed prices.

INSERT INTO teams (id, name, description, enabled, max_concurrent_tasks, repository_ids, created_at, updated_at, archived_at)
VALUES ('00000000-0000-0000-0000-000000000001', 'Default team', 'Native engineering team', TRUE, 1, '[]', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL);

INSERT INTO account_settings (id, display_name, timezone, date_format, time_format, default_landing_page, default_task_view, appearance, compact_dashboard, settings_version, created_at, updated_at)
VALUES ('default', 'Local user', 'UTC', 'YYYY-MM-DD', '24H', 'dashboard', 'board', 'system', FALSE, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

INSERT INTO team_agent_profiles (id, team_id, role_kind, display_name, avatar, enabled, provider, model, harness, effort, supplemental_instructions, prompt_version, soft_budget_usd, hard_budget_usd, version, created_at, updated_at)
VALUES ('d21cdbfb-c07b-5f9f-97ef-c36a180843fb', '00000000-0000-0000-0000-000000000001', 'INTERPRETER', 'Interpreter', '', TRUE, 'ollama', 'qwen3:4b', NULL, 'none', '', 'v2.1', NULL, NULL, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

INSERT INTO team_agent_profiles (id, team_id, role_kind, display_name, avatar, enabled, provider, model, harness, effort, supplemental_instructions, prompt_version, soft_budget_usd, hard_budget_usd, version, created_at, updated_at)
VALUES ('0c44ccc1-32cc-5dd0-b422-02b3743d0554', '00000000-0000-0000-0000-000000000001', 'DEVELOPER', 'Developer', '', TRUE, 'openai', 'gpt-5.6-terra', 'codex', 'medium', '', 'v2.1', NULL, NULL, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

INSERT INTO team_agent_profiles (id, team_id, role_kind, display_name, avatar, enabled, provider, model, harness, effort, supplemental_instructions, prompt_version, soft_budget_usd, hard_budget_usd, version, created_at, updated_at)
VALUES ('85d6de1a-c2f6-57e1-9639-335d38376bfa', '00000000-0000-0000-0000-000000000001', 'THINKER', 'Thinker', '', FALSE, 'openai', 'gpt-5.6-sol', 'codex', 'high', '', 'v2.1', NULL, NULL, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

INSERT INTO team_agent_profiles (id, team_id, role_kind, display_name, avatar, enabled, provider, model, harness, effort, supplemental_instructions, prompt_version, soft_budget_usd, hard_budget_usd, version, created_at, updated_at)
VALUES ('33365eea-f101-55dc-b14d-98e163da23f1', '00000000-0000-0000-0000-000000000001', 'REVIEWER', 'Reviewer', '', FALSE, 'openai', 'gpt-5.6-terra', 'codex', 'high', '', 'v2.1', NULL, NULL, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

INSERT INTO team_automation_policies (team_id, version, configuration)
VALUES ('00000000-0000-0000-0000-000000000001', 1, '{"enrollment_enabled": false, "auto_merge": false, "repository_ids": [], "authorized_reviewer_ids": [], "required_checks": [], "task_budget_usd": "2", "team_budget_usd": "20", "require_formal_approval": true}');

INSERT INTO integrations (id, provider_type, provider_name, status, configuration, encrypted_credentials, last_error, sync_status, last_synced_at, created_at, updated_at)
VALUES ('76d8e5fb-d890-5fbc-935b-c3ea51579a7f', 'source_control', 'github', 'DISCONNECTED', '{}', NULL, NULL, 'IDLE', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

INSERT INTO integrations (id, provider_type, provider_name, status, configuration, encrypted_credentials, last_error, sync_status, last_synced_at, created_at, updated_at)
VALUES ('41cd2743-6477-56c2-87a1-034a144065cd', 'task_management', 'linear', 'DISCONNECTED', '{}', NULL, NULL, 'IDLE', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

INSERT INTO integrations (id, provider_type, provider_name, status, configuration, encrypted_credentials, last_error, sync_status, last_synced_at, created_at, updated_at)
VALUES ('fe38bc0d-cf5e-5dd4-b302-5b80e54edfb8', 'task_management', 'trello', 'DISCONNECTED', '{}', NULL, NULL, 'IDLE', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

INSERT INTO integrations (id, provider_type, provider_name, status, configuration, encrypted_credentials, last_error, sync_status, last_synced_at, created_at, updated_at)
VALUES ('e4f7e82b-5746-50f7-b2c8-e0e31485940a', 'task_management', 'slack', 'DISCONNECTED', '{}', NULL, NULL, 'IDLE', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

INSERT INTO integrations (id, provider_type, provider_name, status, configuration, encrypted_credentials, last_error, sync_status, last_synced_at, created_at, updated_at)
VALUES ('560824b0-a643-5e87-9440-cda1bf559c43', 'ai', 'openai', 'DISCONNECTED', '{}', NULL, NULL, 'IDLE', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

INSERT INTO integrations (id, provider_type, provider_name, status, configuration, encrypted_credentials, last_error, sync_status, last_synced_at, created_at, updated_at)
VALUES ('d5c0c54d-71ff-584a-9531-67e8c2168f36', 'ai', 'anthropic', 'DISCONNECTED', '{}', NULL, NULL, 'IDLE', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

INSERT INTO integrations (id, provider_type, provider_name, status, configuration, encrypted_credentials, last_error, sync_status, last_synced_at, created_at, updated_at)
VALUES ('ea06bda7-eb22-5df3-961d-f37de43b1199', 'ai', 'deepseek', 'DISCONNECTED', '{}', NULL, NULL, 'IDLE', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
