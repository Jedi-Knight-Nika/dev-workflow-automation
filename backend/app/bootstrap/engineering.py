from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_runtime.application.sessions import SessionAdministration
from app.agent_runtime.application.token_efficiency import TokenEfficiencyQueries
from app.agent_runtime.infrastructure.sessions import SqlSessionAdministration
from app.agent_runtime.infrastructure.token_efficiency import SqlTokenEfficiency
from app.platform.configuration.settings import get_settings
from app.platform.persistence.session import get_session
from app.teams.application.automation import AutomationAdmin
from app.teams.application.profiles import TeamProfiles
from app.teams.infrastructure.automation_admin import SqlAutomationAdmin
from app.teams.infrastructure.profiles import SqlTeamProfiles


def token_efficiency(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TokenEfficiencyQueries:
    return SqlTokenEfficiency(session)


def team_profiles(session: Annotated[AsyncSession, Depends(get_session)]) -> TeamProfiles:
    return SqlTeamProfiles(session)


def automation_admin(session: Annotated[AsyncSession, Depends(get_session)]) -> AutomationAdmin:
    return SqlAutomationAdmin(session, get_settings())


def session_administration(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SessionAdministration:
    return SqlSessionAdministration(session)
