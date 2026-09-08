from __future__ import annotations

from pydantic import BaseModel

from app.interfaces.http.schemas.tasks import JobRead


class DashboardActivityRead(BaseModel):
    active_job: JobRead | None
    queued_jobs: list[JobRead]
