"""Raw-free readiness check for the local Trino web lanes."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.trino.coordinator_query_info_target import (
    load_trino_coordinator_query_info_source_contract,
    validate_trino_coordinator_query_info_target,
)
from query_doctor.trino.coordinator_query_list_target import (
    load_trino_coordinator_query_list_source_contract,
    validate_trino_coordinator_query_list_source_contract,
)
from query_doctor.web.cluster_selection import build_web_cluster_configs
from query_doctor.web.config import (
    cluster_has_trino_beta_config,
    load_web_local_config,
    resolve_config_path_value,
    resolve_web_config_path,
)
from query_doctor.web.models import WebClusterConfig, WebError
from query_doctor.web.trino_beta_query import validate_trino_auth_mode


TRINO_WEB_BETA_READINESS_SUMMARY_KIND = "trino_web_beta_readiness_v1"
TRINO_WEB_SUPPORT_CLAIM = "local_production"
TRINO_WEB_BETA_STARTUP_QUERY_ID = "20260603_120102_00001_startup"


@dataclass
class TrinoWebBetaReadinessResult:
    config_discovered: bool
    require_query_id: bool = False
    require_recent: bool = False
    cluster_count: int = 0
    trino_configured_cluster_count: int = 0
    query_id_ready_cluster_count: int = 0
    recent_ready_cluster_count: int = 0
    query_info_contract_checked_count: int = 0
    query_list_contract_checked_count: int = 0
    auth_reference_checked_count: int = 0
    issue_counts: Counter[str] = field(default_factory=Counter)

    @property
    def ok(self) -> bool:
        return not self.issue_counts


def audit_trino_web_beta_readiness(
    config_path: str | Path | None = None,
    *,
    cwd: Path,
    require_query_id: bool = False,
    require_recent: bool = False,
) -> TrinoWebBetaReadinessResult:
    """Check whether local config can show Trino Beta web lanes without network reads."""

    resolved_config_path = _resolved_config_path(config_path, cwd=cwd)
    result = TrinoWebBetaReadinessResult(
        config_discovered=resolved_config_path.is_file(),
        require_query_id=require_query_id,
        require_recent=require_recent,
    )
    try:
        config_values = load_web_local_config(config_path, cwd=cwd)
        clusters = build_web_cluster_configs(config_values)
    except (OSError, ValueError, WebError, EngineFactContractError):
        result.issue_counts["trino_web_config_invalid"] += 1
        _record_required_surface_issues(result)
        return result

    result.cluster_count = len(clusters)
    config_base_dir = resolved_config_path.parent
    for cluster in clusters:
        _audit_cluster(cluster, config_base_dir=config_base_dir, result=result)

    if result.trino_configured_cluster_count == 0:
        result.issue_counts["trino_beta_config_absent"] += 1
    _record_required_surface_issues(result)
    return result


def trino_web_beta_readiness_summary_payload(
    result: TrinoWebBetaReadinessResult,
) -> dict[str, Any]:
    return {
        "summary_kind": TRINO_WEB_BETA_READINESS_SUMMARY_KIND,
        "mode": "trino_web_beta_readiness",
        "status": "ready" if result.ok else "failed",
        "support_claim": TRINO_WEB_SUPPORT_CLAIM,
        "requirements": {
            "query_id_required": result.require_query_id,
            "recent_required": result.require_recent,
        },
        "counts": {
            "config_discovered": result.config_discovered,
            "cluster_count": result.cluster_count,
            "trino_configured_cluster_count": result.trino_configured_cluster_count,
            "query_id_ready_cluster_count": result.query_id_ready_cluster_count,
            "recent_ready_cluster_count": result.recent_ready_cluster_count,
            "query_info_contract_checked_count": result.query_info_contract_checked_count,
            "query_list_contract_checked_count": result.query_list_contract_checked_count,
            "auth_reference_checked_count": result.auth_reference_checked_count,
        },
        "surface_boundary": {
            "network_read_performed": False,
            "sql_execution_performed": False,
            "raw_payload_output": False,
            "details_python_report_output": "materialized_details_only",
            "optimizer_guidance_output": "materialized_details_only",
            "llm_report_output": "not_wired",
            "optimizer_behavior": "guidance_only",
            "metadata_collection": "not_wired",
            "running_scan": "not_wired",
        },
        "issue_counts": _counter_payload(result.issue_counts),
    }


def format_trino_web_beta_readiness(result: TrinoWebBetaReadinessResult) -> str:
    issues = ", ".join(
        f"{key}={count}" for key, count in _counter_payload(result.issue_counts).items()
    )
    if not issues:
        issues = "none"
    return "\n".join(
        (
            f"Trino web beta readiness: {'ready' if result.ok else 'failed'}",
            f"config_discovered={'yes' if result.config_discovered else 'no'}",
            f"clusters_checked={result.cluster_count}",
            f"trino_configured_sources={result.trino_configured_cluster_count}",
            f"query_id_ready_sources={result.query_id_ready_cluster_count}",
            f"recent_ready_sources={result.recent_ready_cluster_count}",
            "network_read_performed=no",
            "sql_execution_performed=no",
            f"issues: {issues}",
        )
    )


def _audit_cluster(
    cluster: WebClusterConfig,
    *,
    config_base_dir: Path,
    result: TrinoWebBetaReadinessResult,
) -> None:
    if not cluster_has_trino_beta_config(cluster):
        return
    result.trino_configured_cluster_count += 1

    if not cluster.trino_beta_enabled:
        result.issue_counts["trino_beta_disabled"] += 1
    if not cluster.trino_coordinator_url:
        result.issue_counts["trino_coordinator_url_missing"] += 1

    query_info_ready = _query_info_contract_ready(
        cluster,
        config_base_dir=config_base_dir,
        result=result,
    )
    auth_ready = _auth_reference_ready(cluster, config_base_dir=config_base_dir, result=result)
    query_ready = bool(
        cluster.trino_beta_enabled
        and cluster.trino_coordinator_url
        and query_info_ready
        and auth_ready
    )
    if query_ready:
        result.query_id_ready_cluster_count += 1

    query_list_ready = _query_list_contract_ready(
        cluster,
        config_base_dir=config_base_dir,
        result=result,
    )
    if query_ready and query_list_ready:
        result.recent_ready_cluster_count += 1


def _query_info_contract_ready(
    cluster: WebClusterConfig,
    *,
    config_base_dir: Path,
    result: TrinoWebBetaReadinessResult,
) -> bool:
    if cluster.trino_query_info_source_contract is None:
        result.issue_counts["trino_query_info_contract_missing"] += 1
        return False
    if not cluster.trino_coordinator_url:
        return False
    try:
        contract = load_trino_coordinator_query_info_source_contract(
            resolve_config_path_value(
                cluster.trino_query_info_source_contract,
                base_dir=config_base_dir,
            )
        )
        validate_trino_coordinator_query_info_target(
            contract,
            coordinator_url=cluster.trino_coordinator_url,
            query_id=TRINO_WEB_BETA_STARTUP_QUERY_ID,
        )
    except (OSError, ValueError, EngineFactContractError):
        result.issue_counts["trino_query_info_contract_invalid"] += 1
        return False
    result.query_info_contract_checked_count += 1
    return True


def _query_list_contract_ready(
    cluster: WebClusterConfig,
    *,
    config_base_dir: Path,
    result: TrinoWebBetaReadinessResult,
) -> bool:
    if cluster.trino_query_list_source_contract is None:
        return False
    try:
        contract = load_trino_coordinator_query_list_source_contract(
            resolve_config_path_value(
                cluster.trino_query_list_source_contract,
                base_dir=config_base_dir,
            )
        )
        validate_trino_coordinator_query_list_source_contract(contract)
    except (OSError, ValueError, EngineFactContractError):
        result.issue_counts["trino_query_list_contract_invalid"] += 1
        return False
    result.query_list_contract_checked_count += 1
    return True


def _auth_reference_ready(
    cluster: WebClusterConfig,
    *,
    config_base_dir: Path,
    result: TrinoWebBetaReadinessResult,
) -> bool:
    kerberos_configured = any(
        (
            cluster.trino_kerberos_principal,
            cluster.trino_krb5_ccname,
            cluster.trino_krb5_config,
            cluster.trino_kerberos_ca_cert,
            cluster.trino_kerberos_insecure_tls,
        )
    )
    if cluster.trino_auth_header_file is None and not kerberos_configured:
        return True
    try:
        validate_trino_auth_mode(
            auth_header_file=(
                resolve_config_path_value(
                    cluster.trino_auth_header_file,
                    base_dir=config_base_dir,
                )
                if cluster.trino_auth_header_file is not None
                else None
            ),
            kerberos_principal=cluster.trino_kerberos_principal,
            kerberos_service_name=cluster.trino_kerberos_service_name,
            krb5_ccname=cluster.trino_krb5_ccname,
            krb5_config=(
                resolve_config_path_value(cluster.trino_krb5_config, base_dir=config_base_dir)
                if cluster.trino_krb5_config is not None
                else None
            ),
            kerberos_ca_cert=(
                resolve_config_path_value(
                    cluster.trino_kerberos_ca_cert,
                    base_dir=config_base_dir,
                )
                if cluster.trino_kerberos_ca_cert is not None
                else None
            ),
            kerberos_insecure_tls=cluster.trino_kerberos_insecure_tls,
        )
    except (OSError, ValueError, EngineFactContractError):
        result.issue_counts["trino_auth_reference_invalid"] += 1
        return False
    result.auth_reference_checked_count += 1
    return True


def _record_required_surface_issues(result: TrinoWebBetaReadinessResult) -> None:
    if result.require_query_id and result.query_id_ready_cluster_count == 0:
        result.issue_counts["trino_query_id_not_ready"] += 1
    if result.require_recent and result.recent_ready_cluster_count == 0:
        result.issue_counts["trino_recent_not_ready"] += 1


def _resolved_config_path(config_path: str | Path | None, *, cwd: Path) -> Path:
    if config_path is None:
        return resolve_web_config_path(None, cwd=cwd).expanduser()
    return resolve_config_path_value(Path(config_path), base_dir=cwd)


def _counter_payload(counter: Counter[str]) -> dict[str, int]:
    return {key: int(counter[key]) for key in sorted(counter)}
