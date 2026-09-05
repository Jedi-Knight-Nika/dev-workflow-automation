import builtins
import uuid

from app.application.ports.team_management import (
    AssignTaskCommand,
    SaveTeamCommand,
    TaskAssignmentView,
    TeamManagementWorkflow,
    TeamNotFound,
    TeamView,
)


class ManageTeams:
    def __init__(self, workflow: TeamManagementWorkflow) -> None:
        self._workflow = workflow

    async def list(self) -> list[TeamView]:
        return await self._workflow.list()

    async def get(self, team_id: uuid.UUID) -> TeamView:
        team = await self._workflow.get(team_id)
        if team is None:
            raise TeamNotFound("Team not found")
        return team

    async def create(self, command: SaveTeamCommand) -> TeamView:
        return await self._workflow.create(command)

    async def update(self, team_id: uuid.UUID, command: SaveTeamCommand) -> TeamView:
        return await self._workflow.update(team_id, command)

    async def archive(self, team_id: uuid.UUID) -> None:
        await self._workflow.archive(team_id)

    async def assign(self, command: AssignTaskCommand) -> TaskAssignmentView:
        return await self._workflow.assign(command)

    async def unassign(self, task_id: uuid.UUID) -> None:
        await self._workflow.unassign(task_id)

    async def assignments(self, team_id: uuid.UUID) -> builtins.list[TaskAssignmentView]:
        await self.get(team_id)
        return await self._workflow.assignments(team_id)
