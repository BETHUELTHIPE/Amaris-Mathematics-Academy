"""Conservative web defaults based on container limits, not host CPU count."""

import math
import os
from pathlib import Path


def recommended_workers(cgroup: Path = Path("/sys/fs/cgroup")) -> int:
    cpu_limit = float(os.cpu_count() or 1)
    memory_mb = 1024
    try:
        quota, period = (cgroup / "cpu.max").read_text().split()
        if quota != "max":
            cpu_limit = min(cpu_limit, int(quota) / int(period))
    except (OSError, ValueError, ZeroDivisionError):
        pass
    try:
        memory_limit = (cgroup / "memory.max").read_text().strip()
        if memory_limit != "max":
            memory_mb = int(memory_limit) // (1024 * 1024)
    except (OSError, ValueError):
        pass
    # Reserve space for the master, proxy and (when enabled) notification worker/Beat.
    reserved_mb = 256
    if os.getenv("AMARIS_COLOCATE_NOTIFICATIONS", "").lower() in {"1", "true", "yes"}:
        reserved_mb += 512
    memory_workers = max(1, (memory_mb - reserved_mb) // 192)
    return max(1, min(4, math.ceil(cpu_limit * 2), memory_workers))
