"""Dry-run plan output helpers for the CM profile collector."""

from __future__ import annotations

from query_doctor.cm.models import CollectorConfig, sanitize_cm_url_for_display


def print_dry_run_plan(config: CollectorConfig) -> None:
    print("[CM profile collector] Dry-run plan")
    print(f"CM URL: {sanitize_cm_url_for_display(config.cm_url)}")
    print(f"Cluster: {config.cluster}")
    print(f"Service: {config.service}")
    print(f"Output path: {config.out}")
    print(f"Since hours: {config.since_hours}")
    print(f"Limit: {config.limit}")
    print(f"Max profile bytes: {config.max_profile_bytes}")
    print(f"Minimum duration seconds: {config.min_duration_sec}")
    print("Filters:")
    print(f"  pool: {config.pool or '<any>'}")
    print(f"  user: {config.user or '<any>'}")
    print(f"  status: {config.status}")
    print(f"  query_id: {config.query_id or '<any>'}")
    print(f"  query_type: {config.query_type or '<any>'}")
    print(f"Redaction: {'enabled' if config.redact else 'disabled'}")
    print(f"Identifier redaction: {'enabled' if config.redact_identifiers else 'disabled'}")
    print(f"Host redaction: {'enabled' if config.redact_hosts else 'disabled'}")
    print(f"CM time-series context: {'enabled' if config.collect_cm_timeseries else 'disabled'}")
    if config.collect_cm_timeseries:
        print(f"CM metrics profile: {config.cm_metrics_profile}")
    print(tls_plan_line(config))
    print(ca_bundle_plan_line(config))
    print(f"Credentials: {config.credentials.display()}")
    print("No CM API calls are performed in dry-run mode.")
    print("No output directories or collected profiles are created in dry-run mode.")


def tls_plan_line(config: CollectorConfig) -> str:
    if config.insecure_skip_verify:
        return "TLS verification: disabled by --insecure-skip-verify (UNSAFE)"
    return "TLS verification: enabled"


def ca_bundle_plan_line(config: CollectorConfig) -> str:
    if config.insecure_skip_verify:
        return "CA bundle: ignored because TLS verification is disabled"
    if config.ca_bundle:
        return f"CA bundle: {config.ca_bundle}"
    return "CA bundle: system default trust store"
