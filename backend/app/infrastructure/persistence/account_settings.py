from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AccountSettings, SettingsAuditEvent

SECTION_FIELDS = {
    "general": (
        "display_name",
        "timezone",
        "date_format",
        "time_format",
        "default_landing_page",
        "default_task_view",
        "appearance",
        "compact_dashboard",
    ),
    "ai": (
        "default_provider_id",
        "default_model",
        "default_reasoning_level",
        "default_max_output_tokens",
        "provider_failure_behavior",
        "structured_output_retry_limit",
    ),
    "execution": (
        "default_execution_mode",
        "default_worker_runtime",
        "max_concurrent_workers",
        "default_job_timeout_seconds",
    ),
    "safety": (
        "default_merge_policy",
        "default_unknown_network_policy",
        "default_dependency_install_policy",
        "default_push_task_branch_policy",
    ),
    "knowledge": (
        "auto_index_repositories",
        "incremental_index_after_merge",
        "index_source_code",
        "index_tests",
        "index_documentation",
        "ignore_generated_files",
        "context_strategy",
    ),
    "storage": (
        "completed_workspace_retention_days",
        "failed_workspace_retention_days",
        "worker_log_retention_days",
        "audit_event_retention_days",
        "monthly_cost_warning",
        "monthly_cost_hard_stop",
    ),
}


class SqlAlchemyAccountSettingsStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _record(self, *, lock: bool = False) -> AccountSettings:
        record = await self._session.get(AccountSettings, "default", with_for_update=lock)
        if record is None:
            record = AccountSettings(id="default")
            self._session.add(record)
            await self._session.flush()
        return record

    async def get(self) -> dict[str, Any]:
        existing = await self._session.get(AccountSettings, "default")
        record = await self._record()
        if existing is None:
            await self._session.commit()
        return self._view(record)

    async def update(self, section: str, values: dict[str, Any]) -> dict[str, Any]:
        fields = SECTION_FIELDS.get(section)
        if fields is None:
            raise ValueError("Unknown settings section")
        record = await self._record(lock=True)
        old_values = {field: self._audit_value(getattr(record, field)) for field in fields}
        for field in fields:
            setattr(record, field, values[field])
        record.settings_version += 1
        self._session.add(
            SettingsAuditEvent(
                section=section,
                old_values=old_values,
                new_values={field: self._audit_value(getattr(record, field)) for field in fields},
            )
        )
        await self._session.commit()
        return self._view(record)

    @staticmethod
    def _audit_value(value: object) -> object:
        return float(value) if isinstance(value, Decimal) else value

    @staticmethod
    def _view(record: AccountSettings) -> dict[str, Any]:
        sections = {
            section: {field: getattr(record, field) for field in fields}
            for section, fields in SECTION_FIELDS.items()
        }
        return {
            **sections,
            "settings_version": record.settings_version,
            "updated_at": record.updated_at,
            "security": {
                "secret_masking_enabled": True,
                "fresh_session_per_job": True,
                "locked_rules": [
                    {
                        "key": "host_filesystem_escape",
                        "effective_value": "DENY",
                        "source": "PLATFORM",
                        "editable": False,
                    },
                    {
                        "key": "privilege_escalation",
                        "effective_value": "DENY",
                        "source": "PLATFORM",
                        "editable": False,
                    },
                    {
                        "key": "docker_socket_access",
                        "effective_value": "DENY",
                        "source": "PLATFORM",
                        "editable": False,
                    },
                    {
                        "key": "agent_self_permission_changes",
                        "effective_value": "DENY",
                        "source": "PLATFORM",
                        "editable": False,
                    },
                ],
            },
        }
