"""Config value readers for CM collector settings."""

from __future__ import annotations

from pathlib import Path

from query_doctor.cm.client import normalize_optional_string
from query_doctor.config.contract import ConfigError, load_and_validate_config


def load_effective_local_config(
    config_path: str | None,
    *,
    cwd: Path,
    repo_root: Path,
    use_repo_default: bool = True,
) -> dict[str, object]:
    result = load_and_validate_config(
        config_path,
        cwd=cwd,
        repo_root=repo_root,
        use_repo_default=use_repo_default,
    )
    return result.values


def string_setting(
    name: str,
    *,
    cli_value: str | None,
    config_values: dict[str, object],
    env_value: str | None = None,
    default: str | None = None,
) -> str | None:
    for value in (cli_value, env_value, config_values.get(name), default):
        if value is None:
            continue
        normalized = str(value).strip()
        if normalized:
            return normalized
    return None


def path_string_setting(
    name: str,
    *,
    cli_value: str | None,
    config_values: dict[str, object],
    env_value: str | None = None,
    default: str | None = None,
) -> str | None:
    value = string_setting(
        name,
        cli_value=cli_value,
        config_values=config_values,
        env_value=env_value,
        default=default,
    )
    return str(Path(value).expanduser()) if value else None


def int_setting(
    name: str,
    *,
    cli_value: int | None,
    config_values: dict[str, object],
    env_value: str | None = None,
    default: int,
) -> int:
    if cli_value is not None:
        return cli_value
    if env_value is not None:
        if not env_value.strip():
            raise ConfigError(f"Environment value for {name} must be a positive integer.")
        try:
            parsed = int(env_value.strip())
        except ValueError as exc:
            raise ConfigError(f"Environment value for {name} must be an integer.") from exc
        if parsed <= 0:
            raise ConfigError(f"Environment value for {name} must be a positive integer.")
        return parsed
    if name in config_values:
        return int(config_values[name])
    return default


def float_setting(
    name: str,
    *,
    cli_value: float | None,
    config_values: dict[str, object],
    default: float | None = None,
) -> float | None:
    if cli_value is not None:
        return cli_value
    if name in config_values:
        return float(config_values[name])
    return default


def bool_setting(
    name: str,
    *,
    cli_value: bool | None,
    config_values: dict[str, object],
    default: bool,
) -> bool:
    if cli_value is not None:
        return bool(cli_value)
    value = config_values.get(name, default)
    return bool(value)


def resolve_optional_output_json(value: str | None, *, cwd: Path) -> Path | None:
    normalized = normalize_optional_string(value)
    if not normalized:
        return None
    path = Path(normalized).expanduser()
    if not path.is_absolute():
        path = cwd / path
    if path.exists() and path.is_dir():
        raise ConfigError("--recent-output-json must point to a file, not a directory.")
    return path
