from __future__ import annotations

import os
from dataclasses import dataclass

CAPACITY_LEVELS: tuple[int, ...] = (100, 500, 1_000, 2_500, 5_000, 10_000, 25_000, 50_000)


def env_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}.")
    return value


def env_float(name: str, default: float, *, minimum: float = 0.0) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric.") from exc
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}.")
    return value


def validate_capacity_level(users: int) -> int:
    if users not in CAPACITY_LEVELS:
        supported = ", ".join(f"{level:,}" for level in CAPACITY_LEVELS)
        raise ValueError(f"Unsupported capacity level {users:,}. Supported levels: {supported}.")
    return users


def progressive_levels(max_users: int) -> tuple[int, ...]:
    validate_capacity_level(max_users)
    return tuple(level for level in CAPACITY_LEVELS if level <= max_users)


@dataclass(frozen=True)
class CapacityThresholds:
    failure_pct: float
    server_5xx_pct: float
    p95_ms: int
    p99_ms: int
    infrastructure_cpu_pct: float
    infrastructure_ram_pct: float

    @classmethod
    def from_environment(cls) -> CapacityThresholds:
        return cls(
            failure_pct=env_float("CAPACITY_MAX_FAILURE_PCT", 1.0),
            server_5xx_pct=env_float("CAPACITY_MAX_5XX_PCT", 0.5),
            p95_ms=env_int("CAPACITY_MAX_P95_MS", 2_000),
            p99_ms=env_int("CAPACITY_MAX_P99_MS", 4_000),
            infrastructure_cpu_pct=env_float("CAPACITY_MAX_CPU_PCT", 90.0),
            infrastructure_ram_pct=env_float("CAPACITY_MAX_RAM_PCT", 90.0),
        )
