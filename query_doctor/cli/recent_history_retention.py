"""CLI for raw-free Recent history retention pruning."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from query_doctor.recent.batch_config import DEFAULT_RECENT_HISTORY_POSTGRES_DSN_ENV
from query_doctor.recent.batch_config import validate_env_var_name
from query_doctor.recent.history_store import (
    RecentHistoryRetentionPolicy,
    RecentHistoryRetentionResult,
    RecentHistoryStoreError,
    safe_label,
)


SUMMARY_KIND = "query_doctor_recent_history_retention_v1"
STATUS_PRUNED = "pruned"
STATUS_BLOCKED = "blocked"


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prune raw-free Recent history storage by retention-day policy. The command "
            "does not contact query engines, discover queries, collect profiles, run "
            "metadata SQL, run LLM reports, or run optimizer jobs."
        )
    )
    parser.add_argument(
        "--backend",
        choices=("sqlite", "postgres"),
        required=True,
        help="Recent history backend to prune.",
    )
    parser.add_argument(
        "--sqlite-db",
        type=Path,
        help="SQLite recent history database path. Required for --backend sqlite.",
    )
    parser.add_argument(
        "--postgres-dsn-env",
        default=DEFAULT_RECENT_HISTORY_POSTGRES_DSN_ENV,
        help="Environment variable name containing the Postgres DSN.",
    )
    parser.add_argument("--summary-retention-days", type=positive_int)
    parser.add_argument("--profile-job-retention-days", type=positive_int)
    parser.add_argument("--analysis-cache-retention-days", type=positive_int)
    parser.add_argument("--profile-artifact-retention-days", type=positive_int)
    parser.add_argument("--json", action="store_true", help="Print raw-free JSON.")
    parser.add_argument(
        "--summary-json",
        type=Path,
        help="Write raw-free retention summary JSON.",
    )
    parser.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Exit non-zero unless pruning completed.",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def retention_policy_from_args(
    args: argparse.Namespace,
    *,
    now: datetime | None = None,
) -> RecentHistoryRetentionPolicy:
    observed_at = now or datetime.now(timezone.utc)
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    observed_at = observed_at.astimezone(timezone.utc).replace(microsecond=0)
    return RecentHistoryRetentionPolicy(
        summary_cutoff_iso=cutoff_iso(observed_at, args.summary_retention_days),
        profile_job_cutoff_iso=cutoff_iso(observed_at, args.profile_job_retention_days),
        analysis_cache_cutoff_iso=cutoff_iso(observed_at, args.analysis_cache_retention_days),
        profile_artifact_cutoff_iso=cutoff_iso(observed_at, args.profile_artifact_retention_days),
    )


def cutoff_iso(now: datetime, days: int | None) -> str | None:
    return (now - timedelta(days=days)).isoformat() if days else None


def retention_enabled(policy: RecentHistoryRetentionPolicy) -> bool:
    return bool(
        policy.summary_cutoff_iso
        or policy.profile_job_cutoff_iso
        or policy.analysis_cache_cutoff_iso
        or policy.profile_artifact_cutoff_iso
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> int:
    args = parse_args(argv)
    effective_env = dict(os.environ if env is None else env)
    policy = retention_policy_from_args(args)
    try:
        result = run_retention(args=args, env=effective_env, policy=policy)
        payload = retention_payload(status=STATUS_PRUNED, policy=policy, result=result)
    except ValueError as exc:
        payload = retention_payload(
            status=STATUS_BLOCKED,
            policy=policy,
            result=RecentHistoryRetentionResult(),
            issue_codes=(safe_label(exc.args[0] if exc.args else "", default="retention_invalid"),),
        )
    except (OSError, RecentHistoryStoreError):
        payload = retention_payload(
            status=STATUS_BLOCKED,
            policy=policy,
            result=RecentHistoryRetentionResult(),
            issue_codes=("recent_history_retention_failed",),
        )

    if args.summary_json:
        try:
            args.summary_json.write_text(retention_payload_json(payload), encoding="utf-8")
        except OSError:
            print(
                "[Recent history retention] ERROR: could not write summary JSON",
                file=sys.stderr,
            )
            return 2
    if args.json:
        sys.stdout.write(retention_payload_json(payload))
    else:
        sys.stdout.write(format_retention_payload(payload))
    if args.fail_on_warning and payload.get("status") != STATUS_PRUNED:
        return 1
    return 0 if payload.get("status") == STATUS_PRUNED else 1


def run_retention(
    *,
    args: argparse.Namespace,
    env: Mapping[str, str],
    policy: RecentHistoryRetentionPolicy,
) -> RecentHistoryRetentionResult:
    if not retention_enabled(policy):
        raise ValueError("recent_history_retention_policy_missing")
    if args.backend == "sqlite":
        if args.sqlite_db is None:
            raise ValueError("recent_history_sqlite_db_missing")
        from query_doctor.recent.sqlite_history_store import SqliteRecentHistoryStore

        store = SqliteRecentHistoryStore(args.sqlite_db)
        return store.prune_history(policy=policy)
    if args.backend == "postgres":
        safe_dsn_env = validate_env_var_name(
            args.postgres_dsn_env,
            name="recent_history_postgres_dsn_env",
        )
        if not env.get(safe_dsn_env):
            raise ValueError("postgres_dsn_env_missing")
        from query_doctor.recent.postgres_history_store import PostgresRecentHistoryStore

        store = PostgresRecentHistoryStore.from_env(safe_dsn_env, env=dict(env))
        return store.prune_history(policy=policy)
    raise ValueError("recent_history_backend_invalid")


def retention_payload(
    *,
    status: str,
    policy: RecentHistoryRetentionPolicy,
    result: RecentHistoryRetentionResult,
    issue_codes: Sequence[str] = (),
) -> dict[str, object]:
    return {
        "summary_kind": SUMMARY_KIND,
        "status": status,
        "backend": "recent_history",
        "policy": {
            "summary_cutoff_configured": bool(policy.summary_cutoff_iso),
            "profile_job_cutoff_configured": bool(policy.profile_job_cutoff_iso),
            "analysis_cache_cutoff_configured": bool(policy.analysis_cache_cutoff_iso),
            "profile_artifact_cutoff_configured": bool(policy.profile_artifact_cutoff_iso),
        },
        "retention": result.safe_payload(),
        "issue_codes": list(dict.fromkeys(issue_codes)),
        "raw_output": False,
        "sensitive_value_echo": False,
    }


def retention_payload_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(dict(payload), sort_keys=True) + "\n"


def format_retention_payload(payload: Mapping[str, Any]) -> str:
    retention = payload.get("retention")
    counts = retention if isinstance(retention, dict) else {}
    lines = [f"Recent history retention: {payload.get('status', 'unknown')}"]
    lines.append(f"- summaries deleted: {counts.get('summaries_deleted', 0)}")
    lines.append(f"- profile jobs deleted: {counts.get('profile_jobs_deleted', 0)}")
    lines.append(f"- analysis-cache rows deleted: {counts.get('analysis_cache_deleted', 0)}")
    lines.append(
        f"- profile-artifact metadata rows deleted: {counts.get('profile_artifacts_deleted', 0)}"
    )
    lines.append(f"- total deleted: {counts.get('total_deleted', 0)}")
    issues = payload.get("issue_codes")
    if isinstance(issues, list) and issues:
        lines.append("issues: " + ",".join(str(issue) for issue in issues))
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
