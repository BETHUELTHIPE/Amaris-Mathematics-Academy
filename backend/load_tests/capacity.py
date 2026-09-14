from __future__ import annotations

import os
from dataclasses import dataclass

CAPACITY_LEVELS: tuple[int, ...] = (
    100,
    500,
    1_000,
    2_500,
    5_000,
    10_000,
    25_000,
    50_000,
)

MAX_FAILURE_PCT = 1.0
MAX_SERVER_5XX_PCT = 0.1
MAX_P95_MS = 1_000
MAX_P99_MS = 2_000
MAX_INFRASTRUCTURE_CPU_PCT = 90.0
MAX_INFRASTRUCTURE_RAM_PCT = 90.0


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
        raise ValueError(
            f"Unsupported capacity level {users:,}. Supported levels: {supported}."
        )
    return users


def progressive_levels(max_users: int) -> tuple[int, ...]:
    validate_capacity_level(max_users)
    return tuple(level for level in CAPACITY_LEVELS if level <= max_users)


def _reject_weaker_threshold(
    name: str,
    value: float,
    maximum_allowed: float,
) -> float:
    if value > maximum_allowed:
        raise ValueError(
            f"{name}={value} would weaken the capacity gate; "
            f"it must be <= {maximum_allowed}."
        )
    return value


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
        failure_pct = env_float("CAPACITY_MAX_FAILURE_PCT", MAX_FAILURE_PCT)
        server_5xx_pct = env_float(
            "CAPACITY_MAX_5XX_PCT",
            MAX_SERVER_5XX_PCT,
        )
        p95_ms = env_int("CAPACITY_MAX_P95_MS", MAX_P95_MS)
        p99_ms = env_int("CAPACITY_MAX_P99_MS", MAX_P99_MS)
        infrastructure_cpu_pct = env_float(
            "CAPACITY_MAX_CPU_PCT",
            MAX_INFRASTRUCTURE_CPU_PCT,
        )
        infrastructure_ram_pct = env_float(
            "CAPACITY_MAX_RAM_PCT",
            MAX_INFRASTRUCTURE_RAM_PCT,
        )

        _reject_weaker_threshold(
            "CAPACITY_MAX_FAILURE_PCT",
            failure_pct,
            MAX_FAILURE_PCT,
        )
        _reject_weaker_threshold(
            "CAPACITY_MAX_5XX_PCT",
            server_5xx_pct,
            MAX_SERVER_5XX_PCT,
        )
        _reject_weaker_threshold(
            "CAPACITY_MAX_P95_MS",
            float(p95_ms),
            float(MAX_P95_MS),
        )
        _reject_weaker_threshold(
            "CAPACITY_MAX_P99_MS",
            float(p99_ms),
            float(MAX_P99_MS),
        )
        _reject_weaker_threshold(
            "CAPACITY_MAX_CPU_PCT",
            infrastructure_cpu_pct,
            MAX_INFRASTRUCTURE_CPU_PCT,
        )
        _reject_weaker_threshold(
            "CAPACITY_MAX_RAM_PCT",
            infrastructure_ram_pct,
            MAX_INFRASTRUCTURE_RAM_PCT,
        )

        return cls(
            failure_pct=failure_pct,
            server_5xx_pct=server_5xx_pct,
            p95_ms=p95_ms,
            p99_ms=p99_ms,
            infrastructure_cpu_pct=infrastructure_cpu_pct,
            infrastructure_ram_pct=infrastructure_ram_pct,
        )
