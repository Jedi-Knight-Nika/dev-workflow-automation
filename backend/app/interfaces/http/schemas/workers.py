from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class WorkerNodeRead(BaseModel):
    id: str
    hostname: str
    process_id: int
    status: str
    online: bool
    capabilities: list[str]
    started_at: datetime
    last_heartbeat: datetime
    stopped_at: datetime | None


class ValidationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    provider: str
    kind: str
    name: str
    status: str
    revision: str
    details_url: str | None
    created_at: datetime
    exit_code: int | None = None
    output_tail: str = ""
    finished_at: datetime | None = None
