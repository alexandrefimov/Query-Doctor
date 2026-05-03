#!/usr/bin/env python3
"""Local Query Doctor config contract and discovery."""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


DEFAULT_CONFIG_PATH = "query-doctor-config.json"
LEGACY_CONFIG_PATH = ".query-doctor-cm.local.json"
EXAMPLE_CONFIG_PATH = "query-doctor-config.example.json"
LEGACY_CONFIG_WARNING = (
    "Using legacy config path .query-doctor-cm.local.json; "
    "please rename it to query-doctor-config.json."
)

STATUS_CHOICES = ("succeeded", "failed", "cancelled", "all")
RECENT_ORDER_CHOICES = ("recent", "duration-desc", "duration-asc", "recent-duration-desc", "status-priority")
METADATA_AUTH_CHOICES = ("kerberos",)
METADATA_PROTOCOL_CHOICES = ("beeswax", "hs2", "hs2-http")

ALLOWED_CONFIG_KEYS = {
    "ca_bundle",
    "cluster",
    "cm_user",
    "cm_url",
    "insecure_skip_verify",
    "krb5ccname",
    "limit",
    "max_profile_bytes",
    "min_duration_sec",
    "out",
    "pool",
    "redact",
    "redact_identifiers",
    "service",
    "since_hours",
    "status",
    "query_type",
    "recent_include_failed",
    "recent_include_running",
    "recent_limit",
    "recent_max_duration_sec",
    "recent_min_duration_sec",
    "recent_order",
    "recent_output_json",
    "recent_pool",
    "recent_parallelism",
    "recent_cm_jobs",
    "recent_cm_summary_limit",
    "recent_metadata_jobs",
    "recent_metadata_top_limit",
    "recent_profile_analysis_limit",
    "recent_select",
    "recent_user",
    "recent_window_minutes",
    "user",
    "username",
    "metadata_krb5ccname",
    "metadata_auth",
    "metadata_ca_cert",
    "metadata_coordinator",
    "metadata_impala_shell",
    "metadata_max_output_bytes",
    "metadata_max_tables",
    "metadata_protocol",
    "metadata_redact",
    "metadata_ssl",
    "metadata_timeout_sec",
}
CONFIG_ALIASES = {
    "cm_user": "username",
    "metadata_krb5ccname": "krb5ccname",
}
SECRET_CONFIG_KEYS_REJECTED = {"CM_PASSWORD", "CM_TOKEN"}
SECRET_CONFIG_KEY_PARTS = (
    "access_token",
    "api_key",
    "auth",
    "authorization",
    "bearer",
    "client_secret",
    "credential",
    "password",
    "passwd",
    "pwd",
    "refresh_token",
    "secret",
    "token",
)


class ConfigError(ValueError):
    """Raised for user-facing local config contract errors."""


@dataclass(frozen=True)
class ConfigLoadResult:
    path: Path | None
    values: dict[str, object]
    source_kind: str
    warning: str | None = None


def resolve_config_path(config_path: str | Path | None, *, cwd: Path) -> Path | None:
    if not config_path:
        return None
    path = Path(config_path).expanduser()
    if not path.is_absolute():
        path = cwd / path
    return path.resolve()


def discover_config_path(
    explicit_path: str | Path | None,
    *,
    cwd: Path = Path("."),
    repo_root: Path | None = None,
    use_repo_default: bool = True,
) -> ConfigLoadResult:
    cwd = Path(cwd)
    if explicit_path:
        return ConfigLoadResult(
            path=resolve_config_path(explicit_path, cwd=cwd),
            values={},
            source_kind="explicit",
        )

    default_path = _discover_default_path(cwd=cwd, repo_root=repo_root, use_repo_default=use_repo_default)
    if default_path is None:
        return ConfigLoadResult(path=None, values={}, source_kind="none")
    if default_path.name == LEGACY_CONFIG_PATH:
        return ConfigLoadResult(
            path=default_path,
            values={},
            source_kind="legacy",
            warning=LEGACY_CONFIG_WARNING,
        )
    return ConfigLoadResult(path=default_path, values={}, source_kind="default")


def _discover_default_path(
    *,
    cwd: Path,
    repo_root: Path | None,
    use_repo_default: bool,
) -> Path | None:
    candidates = [cwd / DEFAULT_CONFIG_PATH]
    if repo_root is not None:
        repo_candidate = Path(repo_root) / DEFAULT_CONFIG_PATH
        if use_repo_default and repo_candidate != candidates[0]:
            candidates.append(repo_candidate)
    candidates.append(cwd / LEGACY_CONFIG_PATH)
    if repo_root is not None:
        repo_legacy_candidate = Path(repo_root) / LEGACY_CONFIG_PATH
        if use_repo_default and repo_legacy_candidate not in candidates:
            candidates.append(repo_legacy_candidate)
    for path in candidates:
        if path.is_file():
            return path
    return None


def discover_default_local_config(
    *,
    cwd: Path,
    repo_root: Path,
    use_repo_default: bool = True,
) -> Path | None:
    return _discover_default_path(cwd=cwd, repo_root=repo_root, use_repo_default=use_repo_default)


def load_local_config(path: str | Path | None, *, cwd: Path = Path(".")) -> dict[str, object]:
    if path is None:
        return {}
    resolved = resolve_config_path(path, cwd=cwd)
    if resolved is None:
        return {}

    try:
        raw_text = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Could not read config file {resolved}: {exc}") from exc

    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in config file {resolved}: {exc.msg}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"Config file {resolved} must contain a JSON object.")
    return normalize_config_keys(raw)


def normalize_config_keys(raw: Mapping[object, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            raise ConfigError("Config file keys must be strings.")
        validate_config_field(key)
        normalized_key = normalize_config_key(key)
        if normalized_key in normalized:
            raise ConfigError(
                f"Config field {key} duplicates normalized field {normalized_key}."
            )
        normalized[normalized_key] = normalize_config_value(normalized_key, value)
    return normalized


def normalize_config_key(key: str) -> str:
    return CONFIG_ALIASES.get(key, key)


def validate_config_field(key: str) -> None:
    key_lower = key.lower()
    if key in SECRET_CONFIG_KEYS_REJECTED:
        raise ConfigError(
            f"Config field {key} looks secret-bearing; use environment variables for credentials."
        )
    if key != "metadata_auth" and any(part in key_lower for part in SECRET_CONFIG_KEY_PARTS):
        raise ConfigError(
            f"Config field {key} looks secret-bearing; use environment variables for credentials."
        )
    if key not in ALLOWED_CONFIG_KEYS:
        raise ConfigError(f"Unknown config field {key}.")


def validate_config_fields(values: Mapping[object, object]) -> None:
    normalize_config_keys(values)


def normalize_config_value(key: str, value: object) -> object:
    if value is None:
        if key in {
            "since_hours",
            "limit",
            "max_profile_bytes",
            "recent_limit",
            "recent_parallelism",
            "recent_cm_jobs",
            "recent_cm_summary_limit",
            "recent_metadata_jobs",
            "recent_profile_analysis_limit",
            "recent_max_duration_sec",
            "recent_min_duration_sec",
            "recent_select",
            "recent_window_minutes",
        }:
            if key in {"recent_max_duration_sec", "recent_min_duration_sec"}:
                raise ConfigError(f"Config field {key} must be a non-negative number.")
            raise ConfigError(f"Config field {key} must be a positive integer.")
        if key == "min_duration_sec":
            raise ConfigError("Config field min_duration_sec must be a non-negative integer.")
        if key == "recent_metadata_top_limit":
            raise ConfigError("Config field recent_metadata_top_limit must be a non-negative integer.")
        if key == "krb5ccname":
            raise ConfigError("Config field krb5ccname must be a non-empty string.")
        if key == "metadata_timeout_sec":
            raise ConfigError("Config field metadata_timeout_sec must be a positive integer.")
        return None
    if key == "krb5ccname":
        if not isinstance(value, str):
            raise ConfigError("Config field krb5ccname must be a string.")
        normalized = value.strip()
        if not normalized:
            raise ConfigError("Config field krb5ccname must be a non-empty string.")
        if any(ord(ch) < 32 or ord(ch) == 127 for ch in normalized):
            raise ConfigError("Config field krb5ccname must not contain control characters.")
        return normalized
    if key in {
        "ca_bundle",
        "cluster",
        "cm_url",
        "out",
        "pool",
        "query_type",
        "recent_output_json",
        "recent_order",
        "recent_pool",
        "recent_user",
        "service",
        "status",
        "user",
        "username",
        "metadata_auth",
        "metadata_ca_cert",
        "metadata_coordinator",
        "metadata_impala_shell",
        "metadata_protocol",
    }:
        if not isinstance(value, str):
            raise ConfigError(f"Config field {key} must be a string.")
        normalized = value.strip()
        if key == "status" and normalized not in STATUS_CHOICES:
            raise ConfigError(
                f"Config field status must be one of: {', '.join(STATUS_CHOICES)}."
            )
        if key == "recent_order" and normalized not in RECENT_ORDER_CHOICES:
            raise ConfigError(
                f"Config field recent_order must be one of: {', '.join(RECENT_ORDER_CHOICES)}."
            )
        if key == "metadata_auth" and normalized not in METADATA_AUTH_CHOICES:
            raise ConfigError(
                f"Config field metadata_auth must be one of: {', '.join(METADATA_AUTH_CHOICES)}."
            )
        if key == "metadata_protocol" and normalized not in METADATA_PROTOCOL_CHOICES:
            raise ConfigError(
                f"Config field metadata_protocol must be one of: {', '.join(METADATA_PROTOCOL_CHOICES)}."
            )
        return normalized or None
    if key in {
        "since_hours",
        "limit",
        "max_profile_bytes",
        "recent_limit",
        "recent_parallelism",
        "recent_cm_jobs",
        "recent_cm_summary_limit",
        "recent_metadata_jobs",
        "recent_profile_analysis_limit",
        "recent_select",
        "recent_window_minutes",
        "metadata_max_output_bytes",
        "metadata_max_tables",
        "metadata_timeout_sec",
    }:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ConfigError(f"Config field {key} must be a positive integer.")
        return value
    if key == "recent_metadata_top_limit":
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ConfigError("Config field recent_metadata_top_limit must be a non-negative integer.")
        return value
    if key in {"recent_max_duration_sec", "recent_min_duration_sec"}:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or value < 0
        ):
            raise ConfigError(f"Config field {key} must be a non-negative number.")
        return float(value)
    if key == "min_duration_sec":
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ConfigError("Config field min_duration_sec must be a non-negative integer.")
        return value
    if key in {
        "insecure_skip_verify",
        "recent_include_failed",
        "recent_include_running",
        "redact",
        "redact_identifiers",
        "metadata_redact",
        "metadata_ssl",
    }:
        if not isinstance(value, bool):
            raise ConfigError(f"Config field {key} must be true or false.")
        return value
    raise ConfigError(f"Unknown config field {key}.")


def load_and_validate_config(
    explicit_path: str | Path | None,
    *,
    cwd: Path = Path("."),
    repo_root: Path | None = None,
    use_repo_default: bool = True,
    warn_legacy: bool = True,
) -> ConfigLoadResult:
    discovered = discover_config_path(
        explicit_path,
        cwd=cwd,
        repo_root=repo_root,
        use_repo_default=use_repo_default,
    )
    if discovered.path is None:
        return discovered
    if discovered.warning and warn_legacy:
        print(f"WARNING: {discovered.warning}", file=sys.stderr)
    values = load_local_config(discovered.path, cwd=cwd)
    return ConfigLoadResult(
        path=discovered.path,
        values=values,
        source_kind=discovered.source_kind,
        warning=discovered.warning,
    )


def merge_kerberos_cache_env(
    base_env: Mapping[str, str],
    config_values: Mapping[str, object] | str | None,
) -> dict[str, str]:
    effective = dict(base_env)
    if effective.get("KRB5CCNAME"):
        return effective
    if isinstance(config_values, str):
        krb5ccname = config_values
    elif config_values is None:
        krb5ccname = None
    else:
        value = config_values.get("krb5ccname")
        krb5ccname = value if isinstance(value, str) else None
    if krb5ccname:
        effective["KRB5CCNAME"] = krb5ccname
    return effective
