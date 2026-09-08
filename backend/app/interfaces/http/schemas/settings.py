from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GeneralSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(min_length=1, max_length=120)
    timezone: str = "UTC"
    date_format: Literal["YYYY-MM-DD", "DD/MM/YYYY", "MM/DD/YYYY"] = "YYYY-MM-DD"
    time_format: Literal["12H", "24H"] = "24H"
    default_landing_page: Literal["dashboard", "tasks", "teams"] = "dashboard"
    default_task_view: Literal["board", "list"] = "board"
    appearance: Literal["system", "light", "dark"] = "system"
    compact_dashboard: bool = False

    @model_validator(mode="after")
    def validate_timezone(self) -> "GeneralSettings":
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return self


SETTINGS_SECTION_SCHEMAS: dict[str, type[BaseModel]] = {"general": GeneralSettings}
