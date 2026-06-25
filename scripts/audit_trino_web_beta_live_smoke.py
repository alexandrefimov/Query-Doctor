#!/usr/bin/env python3
"""Run a bounded live smoke for local Trino Beta web collectors."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.safety.handoff_artifacts import (  # noqa: E402
    ascii_json_artifact_text,
    output_overlaps_inputs_error,
    write_ascii_json_artifact,
)
from query_doctor.web.config import build_web_settings  # noqa: E402
from query_doctor.web.cluster_selection import (  # noqa: E402
    cluster_trino_beta_recent_ready,
    settings_for_cluster_key,
)
from query_doctor.web.error_contract import web_error_info_from_error  # noqa: E402
from query_doctor.web.models import (  # noqa: E402
    BatchRunConfig,
    WebError,
    WebSettings,
    WebTrinoRecentScanResult,
)
from query_doctor.web.server_args import parse_args as parse_web_args  # noqa: E402
from query_doctor.web.trino_beta_query import ENGINE_TRINO  # noqa: E402
from query_doctor.web.trino_recent import (  # noqa: E402
    run_trino_recent_scan,
    trino_beta_recent_configured,
)


TRINO_WEB_BETA_LIVE_SMOKE_SUMMARY_KIND = "trino_web_beta_live_smoke_v1"


@dataclass
class TrinoWebBetaLiveSmokeResult:
    config_discovered: bool
    recent_window_minutes: int
    selected_query_limit: int
    records_seen: int = 0
    records_selected: int = 0
    records_diagnosed: int = 0
    query_bound: int = 0
    warnings_count: int = 0
    row_status_counts: Counter[str] = field(default_factory=Counter)
    issue_counts: Counter[str] = field(default_factory=Counter)
    safe_error_summary: str = ""
    network_read_attempted: bool = False

    @property
    def ok(self) -> bool:
        return not self.issue_counts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a dev-only live Trino Beta smoke through the local web backend. "
            "The smoke reads one bounded retained query list and diagnoses a small "
            "selected set through bounded pruned QueryInfo. It never submits SQL and "
            "prints no coordinator URL, Query ID, auth reference, local path, or raw payload."
        )
    )
    parser.add_argument("--config", help="Local Query Doctor config path.")
    parser.add_argument(
        "--cluster-key",
        help="Optional local cluster id to select before running the smoke.",
    )
    parser.add_argument(
        "--recent-window-minutes",
        type=positive_int,
        default=1_000_000,
        help="Recent lookback window for the smoke. Default: 1000000.",
    )
    parser.add_argument(
        "--selected-query-limit",
        type=positive_int,
        default=1,
        help="Number of retained queries to diagnose. Default: 1.",
    )
    parser.add_argument(
        "--order",
        choices=(
            "duration-desc",
            "duration-asc",
            "recent",
            "recent-duration-desc",
            "status-priority",
        ),
        default="recent",
        help="Selection order for retained query-list rows. Default: recent.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the raw-free machine summary JSON to stdout.",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        help="Write the raw-free machine summary JSON artifact.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_path = Path(args.config) if args.config else None
    overlap_error = output_overlaps_inputs_error(
        args.summary_json,
        (config_path,),
        message="summary output must not overwrite the input config",
    )
    if overlap_error:
        print(f"Trino web beta live smoke: rejected: {overlap_error}", file=sys.stderr)
        return 2

    result = run_live_smoke(args, config_path=config_path)
    payload = trino_web_beta_live_smoke_summary_payload(result)
    if args.summary_json is not None:
        write_ascii_json_artifact(args.summary_json, payload)

    if args.json:
        print(ascii_json_artifact_text(payload), end="")
    else:
        print(format_trino_web_beta_live_smoke(result))
    return 0 if result.ok else 1


def run_live_smoke(
    args: argparse.Namespace,
    *,
    config_path: Path | None,
) -> TrinoWebBetaLiveSmokeResult:
    result = TrinoWebBetaLiveSmokeResult(
        config_discovered=False,
        recent_window_minutes=args.recent_window_minutes,
        selected_query_limit=args.selected_query_limit,
    )
    try:
        web_args = parse_web_args(["--config", str(config_path)] if config_path else [])
        settings = build_web_settings(web_args, cwd=Path.cwd())
        result.config_discovered = Path(settings.config).is_file()
        settings = live_smoke_settings_for_cluster(settings, args.cluster_key)
        config = BatchRunConfig(
            engine=ENGINE_TRINO,
            recent_window_minutes=args.recent_window_minutes,
            triage_profile_limit=args.selected_query_limit,
            metadata_top_limit=0,
            order=args.order,
            cluster_key=args.cluster_key or "",
        )
        result.network_read_attempted = True
        recent_result = run_trino_recent_scan(config, settings)
        _record_recent_result(result, recent_result)
    except Exception as exc:  # noqa: BLE001 - never echo unsafe details from live failures.
        result.issue_counts["trino_web_beta_live_smoke_failed"] += 1
        result.safe_error_summary = safe_error_summary(exc)
        return result

    if result.records_seen < 1:
        result.issue_counts["trino_recent_empty"] += 1
    if result.records_selected < 1:
        result.issue_counts["trino_recent_selection_empty"] += 1
    if result.records_diagnosed < min(result.selected_query_limit, result.records_selected):
        result.issue_counts["trino_query_id_diagnosis_incomplete"] += 1
    failed_rows = sum(count for status, count in result.row_status_counts.items() if status != "ok")
    if failed_rows:
        result.issue_counts["trino_query_id_row_failed"] += failed_rows
    return result


def live_smoke_settings_for_cluster(settings: WebSettings, cluster_key: str | None) -> WebSettings:
    if cluster_key:
        return settings_for_cluster_key(settings, cluster_key)
    if trino_beta_recent_configured(settings):
        return settings
    ready_clusters = tuple(
        cluster for cluster in settings.clusters if cluster_trino_beta_recent_ready(cluster)
    )
    if len(ready_clusters) == 1:
        return settings_for_cluster_key(settings, ready_clusters[0].key)
    if len(ready_clusters) > 1:
        raise WebError(
            "Multiple Trino Beta Recent sources are configured. Choose one for the live smoke.",
            title="Trino Beta source selection required",
            reason_code="trino_beta.multiple_recent_sources",
            stage="Selecting Trino Beta local source",
            next_step="Pass --cluster-key for the intended Trino Beta Recent source.",
        )
    raise WebError(
        "No Trino Beta Recent source is configured for the live smoke.",
        title="Trino Beta source is unavailable",
        reason_code="trino_beta.not_configured",
        stage="Selecting Trino Beta local source",
        next_step="Run the local-config readiness audit and configure a Trino Beta Recent source.",
    )


def _record_recent_result(
    result: TrinoWebBetaLiveSmokeResult,
    recent_result: WebTrinoRecentScanResult,
) -> None:
    result.records_seen = recent_result.records_seen
    result.records_selected = recent_result.records_selected
    result.records_diagnosed = recent_result.records_diagnosed
    result.query_bound = recent_result.query_bound
    result.warnings_count = len(recent_result.warnings)
    result.row_status_counts.update(row.status for row in recent_result.rows)


def trino_web_beta_live_smoke_summary_payload(
    result: TrinoWebBetaLiveSmokeResult,
) -> dict[str, Any]:
    return {
        "summary_kind": TRINO_WEB_BETA_LIVE_SMOKE_SUMMARY_KIND,
        "mode": "trino_web_beta_live_smoke",
        "status": "ok" if result.ok else "failed",
        "support_claim": "local_production",
        "requirements": {
            "recent_required": True,
            "one_selected_query_required": result.selected_query_limit > 0,
            "selected_query_limit": result.selected_query_limit,
            "recent_window_minutes": result.recent_window_minutes,
        },
        "counts": {
            "config_discovered": result.config_discovered,
            "records_seen": result.records_seen,
            "records_selected": result.records_selected,
            "records_diagnosed": result.records_diagnosed,
            "query_bound": result.query_bound,
            "warnings_count": result.warnings_count,
            "row_status_counts": _counter_payload(result.row_status_counts),
        },
        "surface_boundary": {
            "network_read_attempted": result.network_read_attempted,
            "sql_execution_performed": False,
            "raw_payload_output": False,
            "query_id_output": False,
            "coordinator_url_output": False,
            "auth_reference_output": False,
            "details_python_report_output": "materialized_details_only",
            "optimizer_guidance_output": "materialized_details_only",
            "llm_report_output": "not_wired",
            "optimizer_behavior": "guidance_only",
            "metadata_collection": "not_wired",
            "running_scan": "not_wired",
        },
        "issue_counts": _counter_payload(result.issue_counts),
        "safe_error_summary": result.safe_error_summary,
    }


def format_trino_web_beta_live_smoke(result: TrinoWebBetaLiveSmokeResult) -> str:
    issues = ", ".join(
        f"{key}={count}" for key, count in _counter_payload(result.issue_counts).items()
    )
    if not issues:
        issues = "none"
    row_statuses = ", ".join(
        f"{key}={count}" for key, count in _counter_payload(result.row_status_counts).items()
    )
    if not row_statuses:
        row_statuses = "none"
    lines = [
        f"Trino web beta live smoke: {'ok' if result.ok else 'failed'}",
        f"config_discovered={'yes' if result.config_discovered else 'no'}",
        f"network_read_attempted={'yes' if result.network_read_attempted else 'no'}",
        f"records_seen={result.records_seen}",
        f"records_selected={result.records_selected}",
        f"records_diagnosed={result.records_diagnosed}",
        f"row_statuses: {row_statuses}",
        "sql_execution_performed=no",
        f"issues: {issues}",
    ]
    if result.safe_error_summary:
        lines.append(f"safe_error: {result.safe_error_summary}")
    return "\n".join(lines)


def safe_error_summary(exc: Exception) -> str:
    info = web_error_info_from_error(
        exc,
        default_reason_code="trino_beta.live_smoke_failed",
        default_next_step="",
    )
    parts = [f"type={type(exc).__name__}", f"reason={info.reason_code}"]
    if info.stage:
        parts.append(f"stage={info.stage}")
    return " ".join(parts)


def _counter_payload(counter: Counter[str]) -> dict[str, int]:
    return {key: int(counter[key]) for key in sorted(counter)}


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
