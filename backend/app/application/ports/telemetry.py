from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class HostTelemetry:
    cpu_percent: float
    memory_used_bytes: int
    memory_total_bytes: int
    memory_percent: float
    disk_used_bytes: int
    disk_total_bytes: int
    disk_percent: float
    load_average: tuple[float, float, float] | None
    uptime_seconds: int


class TelemetryCollector(Protocol):
    def snapshot(self) -> HostTelemetry: ...
