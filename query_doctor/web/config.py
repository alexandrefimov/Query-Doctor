"""Web startup config loading and settings assembly."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from query_doctor.cli import collect_cm_profiles as cm_collector
from query_doctor.config.contract import load_and_validate_config
from query_doctor.web.cluster_selection import build_web_cluster_configs, settings_for_cluster_key
from query_doctor.web.models import (
    DEFAULT_HOST,
    DEFAULT_IMPALA_PROFILE_PORT,
    DEFAULT_IMPALA_PROFILE_SCHEME,
    DEFAULT_IMPALA_PROFILE_TIMEOUT_SEC,
    DEFAULT_METADATA_AUTH,
    DEFAULT_METADATA_PROTOCOL,
    DEFAULT_METADATA_TIMEOUT_SEC,
    DEFAULT_OPTIMIZER_MODEL,
    DEFAULT_PORT,
    DEFAULT_QUERY_PROFILE_SOURCE,
    WebError,
    WebClusterConfig,
    WebSettings,
)
from query_doctor.prometheus.timeseries import (
    DEFAULT_PROMETHEUS_METRICS_PROFILE,
    DEFAULT_PROMETHEUS_STEP_SEC,
    DEFAULT_PROMETHEUS_TIMESERIES_PADDING_SEC,
)


_REPO_ROOT = Path(__file__).resolve().parents[2]
LOCAL_BIND_HOSTS = {"127.0.0.1", "localhost", "::1"}


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def validate_bind_host(host: str, *, allow_nonlocal_web_bind: bool) -> None:
    if host in LOCAL_BIND_HOSTS:
        return
    if allow_nonlocal_web_bind:
        return
    raise WebError(
        "Refusing non-local bind. Use --host 127.0.0.1 or pass "
        "--allow-nonlocal-web-bind explicitly for a local web risk review."
    )


def metadata_configured(settings: WebSettings) -> bool:
    return bool(settings.metadata_coordinator)


def impala_profile_source_configured(settings: WebSettings) -> bool:
    return settings.query_profile_source == "impala" and bool(settings.impala_profile_hosts)


def resolve_web_config_path(config_path: str | Path | None, *, cwd: Path) -> Path:
    if config_path:
        return Path(config_path).expanduser()
    default_path = cm_collector.discover_default_local_config(
        cwd=cwd,
        repo_root=_REPO_ROOT,
    )
    return default_path or (cwd / cm_collector.DEFAULT_LOCAL_CONFIG_NAME)


def load_web_local_config(config_path: str | Path | None, *, cwd: Path) -> dict[str, object]:
    if config_path:
        path = Path(config_path).expanduser()
        if not path.is_absolute():
            path = cwd / path
        if not path.is_file():
            return {}
        return cm_collector.load_local_config(str(path), cwd=cwd)
    result = load_and_validate_config(
        None,
        cwd=cwd,
        repo_root=_REPO_ROOT,
    )
    return result.values


def load_krb5ccname_from_local_config(config_path: Path, *, cwd: Path) -> str | None:
    values = load_web_local_config(config_path, cwd=cwd)
    value = values.get("krb5ccname")
    return value if isinstance(value, str) else None


def validate_web_startup_config(
    config_path: Path,
    *,
    cwd: Path,
    env: dict[str, str] | os._Environ[str] | None = None,
    require_cm: bool = True,
) -> list[str]:
    if not require_cm:
        return []
    env = os.environ if env is None else env
    config_values = load_web_local_config(config_path, cwd=cwd)
    clusters = build_web_cluster_configs(config_values)
    clusters_to_validate = clusters or (
        WebClusterConfig(
            key="default",
            label="Configured cluster",
            cm_url=optional_config_string(config_values, "cm_url"),
            cm_cluster=optional_config_string(config_values, "cluster"),
            cm_service=optional_config_string(config_values, "service"),
            cm_username=optional_config_string(config_values, "username"),
            ca_bundle=optional_config_string(config_values, "ca_bundle"),
            insecure_skip_verify=optional_config_bool(config_values, "insecure_skip_verify") is True,
            query_profile_source=first_string_value(
                optional_config_string(config_values, "query_profile_source"),
                DEFAULT_QUERY_PROFILE_SOURCE,
            )
            or DEFAULT_QUERY_PROFILE_SOURCE,
            impala_profile_hosts=optional_config_string_list(config_values, "impala_profile_hosts"),
        ),
    )
    missing: list[str] = []
    cm_clusters = [cluster for cluster in clusters_to_validate if cluster.query_profile_source != "impala"]
    for cluster in clusters_to_validate:
        if cluster.query_profile_source == "impala":
            if not cluster.impala_profile_hosts:
                raise WebError(
                    "Missing required Impala startup setting(s): impala_profile_hosts. "
                    "Provide one or more impalad web hosts in local config."
                )
            if optional_config_bool(config_values, "collect_prometheus_timeseries") and not optional_config_string(
                config_values,
                "prometheus_url",
            ):
                raise WebError(
                    "collect_prometheus_timeseries=true requires prometheus_url in local config."
                )
            continue
        if not first_string_value(cluster.cm_url, env.get("CM_URL")):
            missing.append("cm_url")
        if not cluster.cm_cluster:
            missing.append("cluster")
        if not cluster.cm_service:
            missing.append("service")
    if cm_clusters and not first_string_value(
        optional_config_string(config_values, "username"), env.get("CM_USERNAME")
    ) and not any(cluster.cm_username for cluster in cm_clusters):
        missing.append("username/cm_user")
    if cm_clusters and not ((env.get("CM_PASSWORD") or "").strip() or (env.get("CM_TOKEN") or "").strip()):
        missing.append("CM_PASSWORD/CM_TOKEN environment variable")
    missing = list(dict.fromkeys(missing))
    if missing:
        raise WebError(
            "Missing required CM startup setting(s): "
            + ", ".join(missing)
            + ". Provide non-secret CM settings in local config and CM_PASSWORD or CM_TOKEN via environment variables."
        )

    warnings: list[str] = []
    for cluster in clusters_to_validate:
        if cluster.query_profile_source == "impala":
            continue
        ca_bundle = cluster.ca_bundle
        insecure_skip_verify = cluster.insecure_skip_verify
        if ca_bundle:
            ca_path = Path(ca_bundle).expanduser()
            if not ca_path.is_absolute():
                ca_path = cwd / ca_path
            if not ca_path.is_file() or not os.access(ca_path, os.R_OK):
                raise WebError(f"Configured ca_bundle is not readable: {ca_bundle}")
            if insecure_skip_verify:
                warnings.append(
                    "insecure_skip_verify=true is set; CM TLS verification will be disabled even though ca_bundle is configured."
                )
        elif insecure_skip_verify:
            warnings.append("insecure_skip_verify=true is set; CM TLS verification will be disabled.")
    return warnings


def optional_config_string(config_values: dict[str, object], key: str) -> str | None:
    value = config_values.get(key)
    return value if isinstance(value, str) and value else None


def optional_config_int(config_values: dict[str, object], key: str) -> int | None:
    value = config_values.get(key)
    return value if isinstance(value, int) else None


def optional_config_bool(config_values: dict[str, object], key: str) -> bool | None:
    value = config_values.get(key)
    return value if isinstance(value, bool) else None


def optional_config_string_list(config_values: dict[str, object], key: str) -> tuple[str, ...]:
    value = config_values.get(key)
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return tuple(item for item in value if item)
    return ()


def first_string_value(*values: str | None) -> str | None:
    for value in values:
        if value:
            return value
    return None


def first_int_value(*values: int | None, default: int | None) -> int | None:
    for value in values:
        if value is not None:
            return value
    return default


def merged_bool_setting(cli_value: bool, config_value: bool | None, *, default: bool = False) -> bool:
    return bool(cli_value) or (config_value if config_value is not None else default)


def build_web_settings(args: argparse.Namespace, *, cwd: Path) -> WebSettings:
    config_path = resolve_web_config_path(args.config, cwd=cwd)
    config_values = load_web_local_config(args.config, cwd=cwd)
    clusters = build_web_cluster_configs(config_values)
    settings = WebSettings(
        config=config_path,
        host=first_string_value(
            args.host,
            optional_config_string(config_values, "host"),
            DEFAULT_HOST,
        )
        or DEFAULT_HOST,
        cm_url=first_string_value(
            optional_config_string(config_values, "cm_url"),
        ),
        cm_cluster=first_string_value(
            optional_config_string(config_values, "cluster"),
        ),
        cm_service=first_string_value(
            optional_config_string(config_values, "service"),
        ),
        cm_username=first_string_value(
            optional_config_string(config_values, "username"),
        ),
        ca_bundle=first_string_value(
            optional_config_string(config_values, "ca_bundle"),
        ),
        insecure_skip_verify=optional_config_bool(config_values, "insecure_skip_verify") is True,
        clusters=clusters,
        active_cluster_key=clusters[0].key if clusters else None,
        port=first_int_value(
            args.port,
            optional_config_int(config_values, "port"),
            default=DEFAULT_PORT,
        ),
        allow_nonlocal_web_bind=args.allow_nonlocal_web_bind,
        max_profile_bytes=first_int_value(
            args.max_profile_bytes,
            optional_config_int(config_values, "max_profile_bytes"),
            default=None,
        ),
        model=args.model,
        optimizer_model=first_string_value(
            args.optimizer_model,
            optional_config_string(config_values, "optimizer_model"),
            DEFAULT_OPTIMIZER_MODEL,
            args.model,
        ),
        timeout_sec=args.timeout_sec,
        batch_summary=Path(args.batch_summary).expanduser() if args.batch_summary else None,
        query_profile_source=first_string_value(
            optional_config_string(config_values, "query_profile_source"),
            DEFAULT_QUERY_PROFILE_SOURCE,
        )
        or DEFAULT_QUERY_PROFILE_SOURCE,
        impala_profile_hosts=optional_config_string_list(config_values, "impala_profile_hosts"),
        impala_profile_port=first_int_value(
            optional_config_int(config_values, "impala_profile_port"),
            default=DEFAULT_IMPALA_PROFILE_PORT,
        )
        or DEFAULT_IMPALA_PROFILE_PORT,
        impala_profile_scheme=first_string_value(
            optional_config_string(config_values, "impala_profile_scheme"),
            DEFAULT_IMPALA_PROFILE_SCHEME,
        )
        or DEFAULT_IMPALA_PROFILE_SCHEME,
        impala_profile_timeout_sec=first_int_value(
            optional_config_int(config_values, "impala_profile_timeout_sec"),
            default=DEFAULT_IMPALA_PROFILE_TIMEOUT_SEC,
        )
        or DEFAULT_IMPALA_PROFILE_TIMEOUT_SEC,
        collect_prometheus_timeseries=optional_config_bool(config_values, "collect_prometheus_timeseries") is True,
        prometheus_url=optional_config_string(config_values, "prometheus_url"),
        prometheus_metrics_profile=first_string_value(
            optional_config_string(config_values, "prometheus_metrics_profile"),
            DEFAULT_PROMETHEUS_METRICS_PROFILE,
        )
        or DEFAULT_PROMETHEUS_METRICS_PROFILE,
        prometheus_step_sec=first_int_value(
            optional_config_int(config_values, "prometheus_step_sec"),
            default=DEFAULT_PROMETHEUS_STEP_SEC,
        )
        or DEFAULT_PROMETHEUS_STEP_SEC,
        prometheus_timeseries_padding_sec=first_int_value(
            optional_config_int(config_values, "prometheus_timeseries_padding_sec"),
            default=DEFAULT_PROMETHEUS_TIMESERIES_PADDING_SEC,
        )
        or DEFAULT_PROMETHEUS_TIMESERIES_PADDING_SEC,
        metadata_coordinator=first_string_value(
            args.metadata_coordinator,
            optional_config_string(config_values, "metadata_coordinator"),
        ),
        metadata_impala_shell=first_string_value(
            args.metadata_impala_shell,
            optional_config_string(config_values, "metadata_impala_shell"),
        ),
        metadata_auth=first_string_value(
            args.metadata_auth,
            optional_config_string(config_values, "metadata_auth"),
            DEFAULT_METADATA_AUTH,
        )
        or DEFAULT_METADATA_AUTH,
        metadata_protocol=first_string_value(
            args.metadata_protocol,
            optional_config_string(config_values, "metadata_protocol"),
            DEFAULT_METADATA_PROTOCOL,
        )
        or DEFAULT_METADATA_PROTOCOL,
        metadata_kerberos_service_name=first_string_value(
            args.metadata_kerberos_service_name,
            optional_config_string(config_values, "metadata_kerberos_service_name"),
            optional_config_string(config_values, "impala_kerberos_service_name"),
        ),
        metadata_ssl=merged_bool_setting(
            args.metadata_ssl,
            optional_config_bool(config_values, "metadata_ssl"),
        ),
        metadata_ca_cert=first_string_value(
            args.metadata_ca_cert,
            optional_config_string(config_values, "metadata_ca_cert"),
        ),
        metadata_timeout_sec=first_int_value(
            args.metadata_timeout_sec,
            optional_config_int(config_values, "metadata_timeout_sec"),
            default=DEFAULT_METADATA_TIMEOUT_SEC,
        ),
        metadata_max_tables=first_int_value(
            args.metadata_max_tables,
            optional_config_int(config_values, "metadata_max_tables"),
            default=None,
        ),
        metadata_max_output_bytes=first_int_value(
            args.metadata_max_output_bytes,
            optional_config_int(config_values, "metadata_max_output_bytes"),
            default=None,
        ),
        metadata_redact=merged_bool_setting(
            args.metadata_redact,
            optional_config_bool(config_values, "metadata_redact"),
        ),
        krb5ccname=optional_config_string(config_values, "krb5ccname"),
    )
    if clusters:
        return settings_for_cluster_key(settings, clusters[0].key)
    return settings
