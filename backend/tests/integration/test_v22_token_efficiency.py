from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from app.agent_runtime.infrastructure.models import AIRun, DeveloperContextGeneration
from app.agent_runtime.infrastructure.process import capture
from app.agent_runtime.infrastructure.token_efficiency import SqlTokenEfficiency
from tests.integration.test_v2_enrollment_and_costs import scenario
from tests.integration.test_v2_session_changes import prepare


@pytest.mark.asyncio
async def test_real_checkpoint_rollover_preserves_invoice_and_native_history(
    postgres_session_factory, tmp_path, monkeypatch
):
    async with scenario(postgres_session_factory, tmp_path) as (team_id, _, task_id, settings):
        settings.harness_control_root = tmp_path / "control"
        monkeypatch.setattr(
            "app.agent_runtime.infrastructure.token_efficiency.get_settings", lambda: settings
        )
        async with postgres_session_factory() as session:
            task, native, _, run = await prepare(session, task_id)
            workspace = Path(native.workspace_path)
            workspace.mkdir(parents=True)
            await capture(["git", "init", str(workspace)])
            await capture(
                [
                    "git",
                    "-c",
                    "user.name=Test",
                    "-c",
                    "user.email=test@example.invalid",
                    "commit",
                    "--allow-empty",
                    "-m",
                    "base",
                ],
                cwd=workspace,
            )
            (workspace / "pending.py").write_text("unfinished = True\n")
            lock = settings.harness_control_root / str(task_id) / "workspace.lock"
            lock.parent.mkdir(parents=True)
            lock.touch()
            store = SqlTokenEfficiency(session)
            policy = await store.save_policy(team_id, 0, {"execution_profile": "FAST"})
            assert policy["values"]["active_context_hard_tokens"] == 100000
            result = await store.rollover(
                task_id,
                task.requirement_version,
                "Pending file added. Next: implement behavior and run targeted checks.",
            )
            assert result["generation"] == 2
            await session.refresh(native)
            await session.refresh(run)
            assert task.status == "PAUSED" and native.native_session_id is None
            assert run.calculated_cost_usd == Decimal("0.10") and run.input_tokens == 400
            old = await session.scalar(
                select(DeveloperContextGeneration).where(
                    DeveloperContextGeneration.developer_session_id == native.id,
                    DeveloperContextGeneration.sequence == 1,
                )
            )
            assert old.status == "SEALED" and old.native_thread_id == "existing-thread"
            assert (workspace / "pending.py").read_text() == "unfinished = True\n"
            assert len(await store.checkpoints(task_id)) == 1
            assert (
                len(list(await session.scalars(select(AIRun).where(AIRun.task_id == task_id)))) == 1
            )
            with pytest.raises(ValueError):
                await store.rollover(task_id, task.requirement_version, "Do not buy another run")
