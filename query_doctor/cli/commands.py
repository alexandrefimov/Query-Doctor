"""Logical CLI role to command prefix mapping."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from os import environ
from pathlib import Path
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class CommandSpec:
    module: str
    console_script: str


COMMAND_SPECS = MappingProxyType(
    {
        "analyze": CommandSpec(
            module="query_doctor.cli.analyze_profile",
            console_script="query-doctor-analyze",
        ),
        "batch_recent": CommandSpec(
            module="query_doctor.cli.batch_recent",
            console_script="query-doctor-batch-recent",
        ),
        "collect_cm": CommandSpec(
            module="query_doctor.cli.collect_cm_profiles",
            console_script="query-doctor-collect-cm-profiles",
        ),
        "cm_events": CommandSpec(
            module="query_doctor.cli.cm_events",
            console_script="query-doctor-cm-events",
        ),
        "deployment_readiness": CommandSpec(
            module="query_doctor.cli.deployment_readiness",
            console_script="query-doctor-deployment-readiness",
        ),
        "collect_impala_context": CommandSpec(
            module="query_doctor.cli.collect_impala_context",
            console_script="query-doctor-collect-impala-context",
        ),
        "collect_impala_profile": CommandSpec(
            module="query_doctor.cli.collect_impala_profile",
            console_script="query-doctor-collect-impala-profile",
        ),
        "collect_spark_history": CommandSpec(
            module="query_doctor.cli.collect_spark_history",
            console_script="query-doctor-collect-spark-history",
        ),
        "diagnose_spark_compact": CommandSpec(
            module="query_doctor.cli.diagnose_spark_compact",
            console_script="query-doctor-diagnose-spark-compact",
        ),
        "build_spark_evidence_package": CommandSpec(
            module="query_doctor.cli.build_spark_evidence_package",
            console_script="query-doctor-build-spark-evidence-package",
        ),
        "export_spark_evidence_fixtures": CommandSpec(
            module="query_doctor.cli.export_spark_evidence_fixtures",
            console_script="query-doctor-export-spark-evidence-fixtures",
        ),
        "validate_spark_evidence_package": CommandSpec(
            module="query_doctor.cli.validate_spark_evidence_package",
            console_script="query-doctor-validate-spark-evidence-package",
        ),
        "diagnose_trino_compact": CommandSpec(
            module="query_doctor.cli.diagnose_trino_compact",
            console_script="query-doctor-diagnose-trino-compact",
        ),
        "optimize_query": CommandSpec(
            module="query_doctor.cli.optimize_query",
            console_script="query-doctor-optimize-query",
        ),
        "pipeline": CommandSpec(
            module="query_doctor.cli.pipeline",
            console_script="query-doctor-pipeline",
        ),
        "report": CommandSpec(
            module="query_doctor.cli.report",
            console_script="query-doctor-report",
        ),
        "recent_history_postgres_readiness": CommandSpec(
            module="query_doctor.cli.recent_history_postgres_readiness",
            console_script="query-doctor-recent-history-postgres-readiness",
        ),
        "recent_history_operator_readiness": CommandSpec(
            module="query_doctor.cli.recent_history_operator_readiness",
            console_script="query-doctor-recent-history-operator-readiness",
        ),
        "recent_history_retention": CommandSpec(
            module="query_doctor.cli.recent_history_retention",
            console_script="query-doctor-recent-history-retention",
        ),
        "recent_profile_remediation": CommandSpec(
            module="query_doctor.cli.recent_profile_remediation",
            console_script="query-doctor-recent-profile-remediation",
        ),
        "recent_profile_worker": CommandSpec(
            module="query_doctor.cli.recent_profile_worker",
            console_script="query-doctor-recent-profile-worker",
        ),
        "trino_coordinator_query_info_target_check": CommandSpec(
            module="query_doctor.cli.trino_coordinator_query_info_target_check",
            console_script="query-doctor-trino-coordinator-query-info-target-check",
        ),
        "trino_coordinator_query_info_pruned_probe": CommandSpec(
            module="query_doctor.cli.trino_coordinator_query_info_pruned_probe",
            console_script="query-doctor-trino-coordinator-query-info-pruned-probe",
        ),
        "trino_coordinator_query_info_pruned_import": CommandSpec(
            module="query_doctor.cli.trino_coordinator_query_info_pruned_import",
            console_script="query-doctor-trino-coordinator-query-info-pruned-import",
        ),
        "trino_event_store_import": CommandSpec(
            module="query_doctor.cli.trino_event_store_import",
            console_script="query-doctor-trino-event-store-import",
        ),
        "trino_event_source_contract_check": CommandSpec(
            module="query_doctor.cli.trino_event_source_contract_check",
            console_script="query-doctor-trino-event-source-contract-check",
        ),
        "trino_http_event_archive_import": CommandSpec(
            module="query_doctor.cli.trino_http_event_archive_import",
            console_script="query-doctor-trino-http-event-archive-import",
        ),
        "trino_http_query_detail_archive_import": CommandSpec(
            module="query_doctor.cli.trino_http_query_detail_archive_import",
            console_script="query-doctor-trino-http-query-detail-archive-import",
        ),
        "trino_import": CommandSpec(
            module="query_doctor.cli.trino_import",
            console_script="query-doctor-trino-import",
        ),
        "trino_metadata_cli_summary": CommandSpec(
            module="query_doctor.cli.trino_metadata_cli_summary",
            console_script="query-doctor-trino-metadata-cli-summary",
        ),
        "trino_metadata_source_contract_check": CommandSpec(
            module="query_doctor.cli.trino_metadata_source_contract_check",
            console_script="query-doctor-trino-metadata-source-contract-check",
        ),
        "trino_metadata_summary_import": CommandSpec(
            module="query_doctor.cli.trino_metadata_summary_import",
            console_script="query-doctor-trino-metadata-summary-import",
        ),
        "trino_query_detail_import": CommandSpec(
            module="query_doctor.cli.trino_query_detail_import",
            console_script="query-doctor-trino-query-detail-import",
        ),
        "trino_query_info_pruned_import": CommandSpec(
            module="query_doctor.cli.trino_query_info_pruned_import",
            console_script="query-doctor-trino-query-info-pruned-import",
        ),
        "trino_query_list_import": CommandSpec(
            module="query_doctor.cli.trino_query_list_import",
            console_script="query-doctor-trino-query-list-import",
        ),
        "trino_statement_stats_import": CommandSpec(
            module="query_doctor.cli.trino_statement_stats_import",
            console_script="query-doctor-trino-statement-stats-import",
        ),
    }
)
COMMAND_BACKENDS = ("module", "console")
COMMAND_BACKEND_ENV = "QD_COMMAND_BACKEND"
DEFAULT_COMMAND_BACKEND = "module"


def command_spec(role: str) -> CommandSpec:
    try:
        return COMMAND_SPECS[role]
    except KeyError as exc:
        known = ", ".join(sorted(COMMAND_SPECS))
        raise ValueError(f"Unknown Query Doctor CLI role {role!r}; known roles: {known}") from exc


def module_name(role: str) -> str:
    return command_spec(role).module


def console_script_name(role: str) -> str:
    return command_spec(role).console_script


def resolve_command_backend(
    backend: str | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> str:
    selected = backend
    if selected is None:
        source_env = environ if env is None else env
        selected = source_env.get(COMMAND_BACKEND_ENV, DEFAULT_COMMAND_BACKEND)
    selected = selected.strip().lower()
    if selected in COMMAND_BACKENDS:
        return selected
    allowed = ", ".join(COMMAND_BACKENDS)
    raise ValueError(f"Unsupported Query Doctor command backend {selected!r}; allowed: {allowed}")


def command_prefix(
    repo_dir: Path,
    role: str,
    *,
    backend: str | None = None,
    env: Mapping[str, str] | None = None,
    python_executable: str | None = None,
) -> list[str]:
    spec = command_spec(role)
    selected = resolve_command_backend(backend, env=env)
    python = sys.executable if python_executable is None else python_executable
    if selected == "module":
        return [python, "-m", spec.module]
    if selected == "console":
        return [spec.console_script]
    raise AssertionError(f"unreachable Query Doctor command backend: {selected}")
