import uuid

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.ports.workflow_designer import NodePosition, WorkflowVersionConflict
from app.db.models import (
    Job,
    JobRole,
    JobState,
    Task,
    Team,
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowNode,
)
from app.infrastructure.persistence.dashboard_queries import SqlAlchemyDashboardQueries
from app.infrastructure.persistence.workflow_designer import SqlAlchemyWorkflowDesigner

pytestmark = pytest.mark.asyncio


async def test_layout_and_activity_are_scoped_and_do_not_publish_routes(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    team_id, workflow_id, task_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    other_team, other_task = uuid.uuid4(), uuid.uuid4()
    first, second, edge_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    try:
        async with postgres_session_factory() as session:
            session.add_all(
                [
                    Team(id=team_id, name=f"layout-{team_id}", enabled=False),
                    Team(id=other_team, name=f"layout-{other_team}", enabled=False),
                ]
            )
            await session.flush()
            session.add(WorkflowDefinition(id=workflow_id, team_id=team_id, version=7))
            await session.flush()
            for node_id in (first, second):
                session.add(
                    WorkflowNode(
                        id=node_id,
                        workflow_id=workflow_id,
                        role="THINKER",
                        label=str(node_id),
                        position_x=0,
                        position_y=0,
                    )
                )
            session.add_all(
                [
                    Task(id=task_id, team_id=team_id, title="Layout test"),
                    Task(id=other_task, team_id=other_team, title="Unrelated team"),
                ]
            )
            await session.flush()
            session.add(
                WorkflowEdge(
                    id=edge_id,
                    workflow_id=workflow_id,
                    source_node_id=first,
                    target_node_id=second,
                    outcome="success",
                )
            )
            session.add_all(
                [
                    Job(
                        task_id=task_id,
                        role=JobRole.THINKER,
                        workflow_node_id=first,
                        action="CREATE_PLAN",
                        state=JobState.RUNNING,
                    ),
                    Job(
                        task_id=task_id,
                        role=JobRole.THINKER,
                        workflow_node_id=second,
                        action="REPLAN",
                        state=JobState.QUEUED,
                    ),
                    Job(
                        task_id=task_id,
                        role=JobRole.THINKER,
                        workflow_node_id=second,
                        action="REPLAN",
                        state=JobState.WAITING_PROVIDER,
                    ),
                    Job(
                        task_id=other_task,
                        role=JobRole.THINKER,
                        workflow_node_id=first,
                        action="OTHER_TEAM",
                        state=JobState.RUNNING,
                    ),
                ]
            )
            await session.commit()
        async with postgres_session_factory() as session:
            designer = SqlAlchemyWorkflowDesigner(session, team_id)
            await designer.save_positions(7, (NodePosition(str(first), 123.5, 75),))
        async with postgres_session_factory() as session:
            node = await session.get(WorkflowNode, first)
            assert node and float(node.position_x) == 123.5
            definition = await session.get(WorkflowDefinition, workflow_id)
            assert definition and definition.version == 7
            edge = await session.get(WorkflowEdge, edge_id)
            assert edge and edge.outcome == "success" and edge.target_node_id == second
            designer = SqlAlchemyWorkflowDesigner(session, team_id)
            activity = {item.node_id: item for item in await designer.activity()}
            assert activity[str(first)].active_jobs == 1
            assert activity[str(first)].current_job_action == "CREATE_PLAN"
            assert activity[str(second)].active_jobs == 0
            assert activity[str(second)].queued_jobs == 1
            assert activity[str(second)].waiting_jobs == 1
            assert activity[str(second)].current_job_action is None
            workers = await SqlAlchemyDashboardQueries(session)._active_workers()
            assert any(item.task_id == str(task_id) for item in workers)
        async with postgres_session_factory() as session:
            designer = SqlAlchemyWorkflowDesigner(session, team_id)
            with pytest.raises(WorkflowVersionConflict):
                await designer.save_positions(6, ())
            await session.rollback()
            with pytest.raises(ValueError, match="outside this workflow"):
                await designer.save_positions(7, (NodePosition(str(uuid.uuid4()), 1, 1),))
    finally:
        async with postgres_session_factory() as session:
            await session.execute(delete(Task).where(Task.id.in_([task_id, other_task])))
            await session.execute(delete(Team).where(Team.id.in_([team_id, other_team])))
            await session.commit()
