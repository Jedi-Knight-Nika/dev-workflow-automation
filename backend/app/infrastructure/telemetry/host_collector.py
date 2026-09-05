import os
import time

import psutil

from app.application.ports.telemetry import HostTelemetry


class PsutilHostTelemetryCollector:
    def snapshot(self) -> HostTelemetry:
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        try:
            one, five, fifteen = os.getloadavg()
            load = (float(one), float(five), float(fifteen))
        except OSError:
            load = None
        return HostTelemetry(
            cpu_percent=psutil.cpu_percent(interval=None),
            memory_used_bytes=memory.used,
            memory_total_bytes=memory.total,
            memory_percent=memory.percent,
            disk_used_bytes=disk.used,
            disk_total_bytes=disk.total,
            disk_percent=disk.percent,
            load_average=load,
            uptime_seconds=max(0, round(time.time() - psutil.boot_time())),
        )
