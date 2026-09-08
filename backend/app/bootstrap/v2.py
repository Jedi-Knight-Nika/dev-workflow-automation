from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_session
from app.teams.application.automation import AutomationAdmin
from app.teams.application.profiles import TeamProfiles
from app.teams.infrastructure.automation_admin import SqlAutomationAdmin
from app.teams.infrastructure.profiles import SqlTeamProfiles


def team_profiles(session: Annotated[AsyncSession, Depends(get_session)]) -> TeamProfiles:
    return SqlTeamProfiles(session)


def automation_admin(session: Annotated[AsyncSession, Depends(get_session)]) -> AutomationAdmin:
    return SqlAutomationAdmin(session, get_settings())
