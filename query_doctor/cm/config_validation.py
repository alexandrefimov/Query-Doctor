"""Validation policy for CM collector configuration."""

from __future__ import annotations

from pathlib import Path

from query_doctor.cm.config_defaults import DEFAULT_RECENT_LIMIT, DEFAULT_RECENT_SELECT, MAX_RECENT_LIMIT, MAX_RECENT_SELECT
from query_doctor.cm.metrics_catalog import normalize_cm_metrics_profile
from query_doctor.config.contract import ConfigError, RECENT_ORDER_CHOICES


def validate_recent_limit(value: int | None) -> int:
    limit = value or DEFAULT_RECENT_LIMIT
    if limit > MAX_RECENT_LIMIT:
        raise ConfigError(
            f"--recent-limit must be <= {MAX_RECENT_LIMIT} for bounded listing."
        )
    return limit


def validate_recent_select(value: int | None, limit_value: int | None) -> int:
    recent_limit = validate_recent_limit(limit_value)
    selected = value or min(DEFAULT_RECENT_SELECT, recent_limit)
    if selected > MAX_RECENT_SELECT:
        raise ConfigError(
            f"--recent-select must be <= {MAX_RECENT_SELECT} for bounded listing."
        )
    if selected > recent_limit:
        raise ConfigError("--recent-select must be <= --recent-limit.")
    return selected


def validate_recent_duration_bounds(
    min_duration_sec: float | None,
    max_duration_sec: float | None,
) -> tuple[float | None, float | None]:
    if (
        min_duration_sec is not None
        and max_duration_sec is not None
        and max_duration_sec < min_duration_sec
    ):
        raise ConfigError(
            "--recent-max-duration-sec must be >= --recent-min-duration-sec."
        )
    return min_duration_sec, max_duration_sec


def validate_recent_order(value: str | None) -> str:
    order = value or "recent"
    if order not in RECENT_ORDER_CHOICES:
        raise ConfigError(
            "recent_order must be one of: " + ", ".join(RECENT_ORDER_CHOICES) + "."
        )
    return order


def validate_cm_metrics_profile(value: str | None) -> str:
    try:
        return normalize_cm_metrics_profile(value)
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc


def validate_output_path(value: str, *, cwd: Path, repo_root: Path) -> Path:
    if value is None or not value.strip():
        raise ConfigError("Missing --out.")

    raw_path = Path(value).expanduser()
    path = raw_path if raw_path.is_absolute() else cwd / raw_path
    resolved = path.resolve(strict=False)

    if resolved == Path(resolved.anchor):
        raise ConfigError("Refusing to use filesystem root as --out.")
    if resolved == repo_root.resolve(strict=False):
        raise ConfigError("Refusing to use the current repository root as --out.")

    return resolved
