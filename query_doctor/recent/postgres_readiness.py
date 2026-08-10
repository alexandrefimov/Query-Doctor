"""Raw-free readiness checks for Recent history Postgres storage."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from query_doctor.recent.batch_config import (
    DEFAULT_RECENT_HISTORY_POSTGRES_DSN_ENV,
    validate_env_var_name,
)
from query_doctor.recent.history_store import RecentHistoryStoreError, safe_label
from query_doctor.recent.postgres_history_store import ConnectFactory, PostgresRecentHistoryStore


SUMMARY_KIND = "query_doctor_recent_history_postgres_readiness_v1"
STATUS_READY = "ready"
STATUS_BLOCKED = "blocked"
STATUS_WARNING = "warning"


@dataclass(frozen=True)
class RecentHistoryPostgresReadinessResult:
    status: str
    checks: tuple[dict[str, str], ...]
    issue_codes: tuple[str, ...]
    schema_initialized: bool = False

    def payload(self) -> dict[str, object]:
        return {
            "summary_kind": SUMMARY_KIND,
            "status": self.status,
            "backend": "postgres",
            "schema_initialized": self.schema_initialized,
            "checks": list(self.checks),
            "issue_codes": list(self.issue_codes),
            "raw_output": False,
            "sensitive_value_echo": False,
        }


def recent_history_postgres_readiness(
    *,
    dsn_env: str = DEFAULT_RECENT_HISTORY_POSTGRES_DSN_ENV,
    env: Mapping[str, str],
    connect: ConnectFactory | None = None,
) -> RecentHistoryPostgresReadinessResult:
    checks: list[dict[str, str]] = []
    issues: list[str] = []
    try:
        safe_dsn_env = validate_env_var_name(dsn_env, name="recent_history_postgres_dsn_env")
    except ValueError:
        checks.append(
            readiness_check(
                "dsn_env_name",
                STATUS_BLOCKED,
                "Postgres DSN environment variable name is invalid",
            )
        )
        issues.append("postgres_dsn_env_name_invalid")
        return readiness_result(checks, issues, schema_initialized=False)

    if not env.get(safe_dsn_env):
        checks.append(
            readiness_check(
                "dsn_env",
                STATUS_BLOCKED,
                "Postgres DSN environment variable is not configured",
            )
        )
        issues.append("postgres_dsn_env_missing")
        return readiness_result(checks, issues, schema_initialized=False)
    checks.append(readiness_check("dsn_env", STATUS_READY, "Postgres DSN env is configured"))

    try:
        store = PostgresRecentHistoryStore.from_env(safe_dsn_env, env=dict(env), connect=connect)
        store.initialize()
    except RecentHistoryStoreError as exc:
        code = recent_history_store_error_code(exc)
        checks.append(
            readiness_check(
                "schema_initialize",
                STATUS_BLOCKED,
                "Recent history schema could not be initialized",
            )
        )
        issues.append(code)
        return readiness_result(checks, issues, schema_initialized=False)

    checks.append(
        readiness_check(
            "schema_initialize",
            STATUS_READY,
            "Recent history schema initialized or already present",
        )
    )
    return readiness_result(checks, issues, schema_initialized=True)


def readiness_result(
    checks: list[dict[str, str]],
    issues: list[str],
    *,
    schema_initialized: bool,
) -> RecentHistoryPostgresReadinessResult:
    return RecentHistoryPostgresReadinessResult(
        status=STATUS_BLOCKED if issues else STATUS_READY,
        checks=tuple(checks),
        issue_codes=tuple(dict.fromkeys(issues)),
        schema_initialized=schema_initialized,
    )


def readiness_check(check_id: str, status: str, summary: str) -> dict[str, str]:
    return {
        "id": safe_label(check_id, default="unknown"),
        "status": safe_label(status, default=STATUS_WARNING),
        "summary": safe_summary(summary),
    }


def safe_summary(value: object) -> str:
    text = str(value or "").strip()
    return text[:160] if text else "not available"


def recent_history_store_error_code(exc: BaseException) -> str:
    current: BaseException | None = exc
    while current is not None:
        if isinstance(current, RecentHistoryStoreError) and current.args:
            code = safe_label(current.args[0], default="")
            if code:
                return code[:128]
        current = current.__cause__
    return "postgres_recent_history_unavailable"


def readiness_payload_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(dict(payload), sort_keys=True) + "\n"


def format_recent_history_postgres_readiness(payload: Mapping[str, Any]) -> str:
    lines = [f"Recent history Postgres readiness: {payload.get('status', 'unknown')}"]
    checks = payload.get("checks")
    if isinstance(checks, list):
        for check in checks:
            if not isinstance(check, dict):
                continue
            lines.append(
                "[{status}] {check_id}: {summary}".format(
                    status=check.get("status", "unknown"),
                    check_id=check.get("id", "unknown"),
                    summary=check.get("summary", ""),
                )
            )
    issues = payload.get("issue_codes")
    if isinstance(issues, list) and issues:
        lines.append("issues: " + ",".join(str(issue) for issue in issues))
    return "\n".join(lines) + "\n"
