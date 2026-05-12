#!/usr/bin/env python3
"""Local Query Doctor config contract and discovery."""

from __future__ import annotations

import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit


DEFAULT_CONFIG_PATH = "query-doctor-config.json"
LEGACY_CONFIG_PATH = ".query-doctor-cm.local.json"
EXAMPLE_CONFIG_PATH = "query-doctor-config.example.json"
LEGACY_CONFIG_WARNING = (
    "Using legacy config path .query-doctor-cm.local.json; "
    "please rename it to query-doctor-config.json."
)

STATUS_CHOICES = ("succeeded", "failed", "cancelled", "all")
RECENT_ORDER_CHOICES = (
    "recent",
    "duration-desc",
    "duration-asc",
    "recent-duration-desc",
    "status-priority",
)
METADATA_AUTH_CHOICES = ("kerberos",)
METADATA_PROTOCOL_CHOICES = ("beeswax", "hs2", "hs2-http")
QUERY_PROFILE_SOURCE_CHOICES = ("cm", "impala")
IMPALA_PROFILE_SCHEME_CHOICES = ("http", "https")
KERBEROS_SERVICE_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")

ALLOWED_CONFIG_KEYS = {
    "ca_bundle",
    "cluster",
    "clusters",
    "cm_user",
    "cm_url",
    "collect_cm_timeseries",
    "collect_prometheus_timeseries",
    "cm_metrics_profile",
    "cm_timeseries_padding_sec",
    "host",
    "impala_kerberos_service_name",
    "impala_profile_hosts",
    "impala_profile_port",
    "impala_profile_scheme",
    "impala_profile_timeout_sec",
    "insecure_skip_verify",
    "krb5ccname",
    "limit",
    "max_profile_bytes",
    "max_timeseries_bytes",
    "max_timeseries_points",
    "min_duration_sec",
    "optimizer_model",
    "out",
    "pool",
    "port",
    "prometheus_metrics_profile",
    "prometheus_step_sec",
    "prometheus_timeseries_padding_sec",
    "prometheus_url",
    "redact",
    "redact_identifiers",
    "service",
    "since_hours",
    "status",
    "query_profile_source",
    "query_type",
    "recent_include_failed",
    "recent_include_running",
    "recent_collect_cm_timeseries",
    "recent_limit",
    "recent_max_duration_sec",
    "recent_min_duration_sec",
    "recent_order",
    "recent_output_json",
    "recent_pool",
    "recent_parallelism",
    "recent_cm_jobs",
    "recent_cm_summary_limit",
    "recent_collect_cm_events",
    "recent_cm_events_max_events",
    "recent_metadata_jobs",
    "recent_metadata_top_limit",
    "recent_cm_timeseries_top_limit",
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
    "metadata_kerberos_service_name",
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
CLUSTER_CONFIG_KEYS = {
    "ca_bundle",
    "cluster",
    "cm_metrics_profile",
    "cm_url",
    "id",
    "collect_prometheus_timeseries",
    "impala_kerberos_service_name",
    "impala_profile_hosts",
    "impala_profile_port",
    "impala_profile_scheme",
    "impala_profile_timeout_sec",
    "insecure_skip_verify",
    "krb5ccname",
    "label",
    "metadata_auth",
    "metadata_ca_cert",
    "metadata_coordinator",
    "metadata_impala_shell",
    "metadata_kerberos_service_name",
    "metadata_max_output_bytes",
    "metadata_max_tables",
    "metadata_protocol",
    "metadata_redact",
    "metadata_ssl",
    "metadata_timeout_sec",
    "prometheus_metrics_profile",
    "prometheus_step_sec",
    "prometheus_timeseries_padding_sec",
    "prometheus_url",
    "query_profile_source",
    "service",
    "username",
}
CLUSTER_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
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

    default_path = _discover_default_path(
        cwd=cwd, repo_root=repo_root, use_repo_default=use_repo_default
    )
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
            raise ConfigError(f"Config field {key} duplicates normalized field {normalized_key}.")
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


def validate_cluster_config_field(key: str) -> None:
    if key in {"id", "label"}:
        return
    validate_config_field(key)
    if normalize_config_key(key) not in CLUSTER_CONFIG_KEYS:
        raise ConfigError(f"Unknown cluster config field {key}.")


def validate_config_fields(values: Mapping[object, object]) -> None:
    normalize_config_keys(values)


def normalize_config_value(key: str, value: object) -> object:
    if key == "clusters":
        return normalize_clusters_config(value)
    if value is None:
        if key in {
            "impala_profile_port",
            "impala_profile_timeout_sec",
            "since_hours",
            "limit",
            "max_profile_bytes",
            "recent_limit",
            "recent_parallelism",
            "recent_cm_jobs",
            "recent_cm_events_max_events",
            "recent_cm_summary_limit",
            "recent_metadata_jobs",
            "recent_profile_analysis_limit",
            "recent_max_duration_sec",
            "recent_min_duration_sec",
            "recent_select",
            "recent_window_minutes",
            "prometheus_step_sec",
        }:
            if key in {"recent_max_duration_sec", "recent_min_duration_sec"}:
                raise ConfigError(f"Config field {key} must be a non-negative number.")
            raise ConfigError(f"Config field {key} must be a positive integer.")
        if key == "min_duration_sec":
            raise ConfigError("Config field min_duration_sec must be a non-negative integer.")
        if key in {"recent_metadata_top_limit", "recent_cm_timeseries_top_limit"}:
            raise ConfigError(f"Config field {key} must be a non-negative integer.")
        if key == "krb5ccname":
            raise ConfigError("Config field krb5ccname must be a non-empty string.")
        if key == "metadata_timeout_sec":
            raise ConfigError("Config field metadata_timeout_sec must be a positive integer.")
        if key == "prometheus_timeseries_padding_sec":
            raise ConfigError(
                "Config field prometheus_timeseries_padding_sec must be a non-negative integer."
            )
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
        "cm_metrics_profile",
        "cm_url",
        "host",
        "impala_kerberos_service_name",
        "impala_profile_scheme",
        "optimizer_model",
        "out",
        "pool",
        "prometheus_metrics_profile",
        "prometheus_url",
        "query_type",
        "recent_output_json",
        "recent_order",
        "recent_pool",
        "recent_user",
        "service",
        "status",
        "query_profile_source",
        "user",
        "username",
        "metadata_auth",
        "metadata_ca_cert",
        "metadata_coordinator",
        "metadata_impala_shell",
        "metadata_kerberos_service_name",
        "metadata_protocol",
    }:
        if not isinstance(value, str):
            raise ConfigError(f"Config field {key} must be a string.")
        normalized = value.strip()
        if key == "status" and normalized not in STATUS_CHOICES:
            raise ConfigError(f"Config field status must be one of: {', '.join(STATUS_CHOICES)}.")
        if key == "query_profile_source" and normalized not in QUERY_PROFILE_SOURCE_CHOICES:
            raise ConfigError(
                "Config field query_profile_source must be one of: "
                f"{', '.join(QUERY_PROFILE_SOURCE_CHOICES)}."
            )
        if key == "impala_profile_scheme" and normalized not in IMPALA_PROFILE_SCHEME_CHOICES:
            raise ConfigError(
                "Config field impala_profile_scheme must be one of: "
                f"{', '.join(IMPALA_PROFILE_SCHEME_CHOICES)}."
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
        if key == "prometheus_url":
            validate_safe_http_url(normalized, field_name="prometheus_url")
        if key in {"impala_kerberos_service_name", "metadata_kerberos_service_name"}:
            validate_kerberos_service_name(normalized, field_name=key)
        return normalized or None
    if key in {
        "since_hours",
        "limit",
        "max_profile_bytes",
        "max_timeseries_bytes",
        "max_timeseries_points",
        "impala_profile_port",
        "impala_profile_timeout_sec",
        "recent_limit",
        "recent_parallelism",
        "recent_cm_jobs",
        "recent_cm_events_max_events",
        "recent_cm_summary_limit",
        "recent_metadata_jobs",
        "recent_profile_analysis_limit",
        "recent_select",
        "recent_window_minutes",
        "metadata_max_output_bytes",
        "metadata_max_tables",
        "metadata_timeout_sec",
        "port",
        "prometheus_step_sec",
    }:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ConfigError(f"Config field {key} must be a positive integer.")
        return value
    if key == "impala_profile_hosts":
        if isinstance(value, str):
            hosts = [item.strip() for item in value.split(",")]
        elif isinstance(value, list):
            hosts = [item.strip() for item in value if isinstance(item, str)]
            if len(hosts) != len(value):
                raise ConfigError("Config field impala_profile_hosts must contain strings only.")
        else:
            raise ConfigError("Config field impala_profile_hosts must be a list of strings.")
        hosts = [host for host in hosts if host]
        for host in hosts:
            if any(ord(ch) < 32 or ord(ch) == 127 for ch in host):
                raise ConfigError(
                    "Config field impala_profile_hosts must not contain control characters."
                )
            if any(marker in host for marker in ("/", "\\", "@", "?", "#")):
                raise ConfigError(
                    "Config field impala_profile_hosts must contain hostnames or host:port only."
                )
        return hosts
    if key in {"recent_metadata_top_limit", "recent_cm_timeseries_top_limit"}:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ConfigError(f"Config field {key} must be a non-negative integer.")
        return value
    if key in {"cm_timeseries_padding_sec", "prometheus_timeseries_padding_sec"}:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ConfigError(f"Config field {key} must be a non-negative integer.")
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
        "collect_cm_timeseries",
        "collect_prometheus_timeseries",
        "recent_collect_cm_events",
        "recent_collect_cm_timeseries",
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


def normalize_clusters_config(value: object) -> list[dict[str, object]]:
    if isinstance(value, Mapping):
        raw_items = []
        for raw_key, raw_value in value.items():
            if not isinstance(raw_key, str):
                raise ConfigError("Cluster config ids must be strings.")
            raw_items.append((raw_key, raw_value))
    elif isinstance(value, list):
        raw_items = [(None, raw_value) for raw_value in value]
    else:
        raise ConfigError("Config field clusters must be a non-empty object or list.")
    if not raw_items:
        raise ConfigError("Config field clusters must contain at least one cluster.")

    normalized_clusters: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for index, (mapping_id, raw_cluster) in enumerate(raw_items):
        if not isinstance(raw_cluster, Mapping):
            raise ConfigError("Each clusters entry must be a JSON object.")
        cluster = normalize_cluster_config(raw_cluster, mapping_id=mapping_id, index=index)
        cluster_id = str(cluster["id"])
        if cluster_id in seen_ids:
            raise ConfigError(f"Duplicate cluster id {cluster_id}.")
        seen_ids.add(cluster_id)
        normalized_clusters.append(cluster)
    return normalized_clusters


def normalize_cluster_config(
    raw_cluster: Mapping[object, object],
    *,
    mapping_id: str | None,
    index: int,
) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for raw_key, raw_value in raw_cluster.items():
        if not isinstance(raw_key, str):
            raise ConfigError("Cluster config keys must be strings.")
        validate_cluster_config_field(raw_key)
        normalized_key = normalize_config_key(raw_key)
        if normalized_key in normalized:
            raise ConfigError(
                f"Cluster config field {raw_key} duplicates normalized field {normalized_key}."
            )
        if normalized_key == "id":
            normalized[normalized_key] = normalize_cluster_id(raw_value)
        elif normalized_key == "label":
            normalized[normalized_key] = normalize_cluster_label(raw_value)
        else:
            normalized[normalized_key] = normalize_config_value(normalized_key, raw_value)

    if mapping_id is not None:
        mapped_id = normalize_cluster_id(mapping_id)
        explicit_id = normalized.get("id")
        if explicit_id is not None and explicit_id != mapped_id:
            raise ConfigError("Cluster config id must match its clusters object key.")
        normalized["id"] = mapped_id
    elif "id" not in normalized:
        raise ConfigError(f"Cluster config entry at index {index} must include id.")
    return normalized


def normalize_cluster_id(value: object) -> str:
    if not isinstance(value, str):
        raise ConfigError("Cluster config id must be a string.")
    normalized = value.strip()
    if not CLUSTER_ID_RE.match(normalized):
        raise ConfigError(
            "Cluster config id must be 1-64 characters using only letters, digits, '.', '_' or '-'."
        )
    return normalized


def normalize_cluster_label(value: object) -> str | None:
    if not isinstance(value, str):
        raise ConfigError("Cluster config label must be a string.")
    normalized = value.strip()
    if not normalized:
        return None
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in normalized):
        raise ConfigError("Cluster config label must not contain control characters.")
    return normalized


def validate_safe_http_url(value: str, *, field_name: str) -> None:
    if not value:
        return
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ConfigError(f"Config field {field_name} must be an http or https URL.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ConfigError(
            f"Config field {field_name} must not include credentials, query parameters, or fragments."
        )


def validate_kerberos_service_name(value: str, *, field_name: str) -> None:
    if not value:
        return
    if not KERBEROS_SERVICE_NAME_RE.fullmatch(value):
        raise ConfigError(
            f"Config field {field_name} must be a short token such as hive or impala."
        )


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
