#!/usr/bin/env python3
"""Audit Trino query-linked fact coverage closure without enabling support."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.trino.query_linked_fact_coverage import (  # noqa: E402
    TRINO_QUERY_LINKED_OPERATOR_CONNECTOR_TELEMETRY_PROFILE,
    TRINO_QUERY_LINKED_PRODUCTION_REVIEW_PROFILE,
    TRINO_QUERY_LINKED_FACT_COVERAGE_GATE,
    TRINO_QUERY_LINKED_FACT_COVERAGE_STATUS,
    TRINO_SQL_EXECUTION_STATUS,
    audit_trino_query_linked_fact_coverage,
    query_linked_fact_coverage_summary_payload,
)


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check the Trino query-linked fact coverage closure gate. The audit is "
            "dev-only, raw-free, and does not collect from Trino, enable Running, "
            "crawl query history, add product metadata collection, emit LLM reports, "
            "run Query Optimizer jobs, generate SQL, execute SQL, or promote broader "
            "Trino production support."
        )
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="Optional raw-free machine summary path. The path is never printed.",
    )
    parser.add_argument("--limit", type=positive_int, default=12, help="Maximum issues to print.")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    result = audit_trino_query_linked_fact_coverage()
    status = "ok" if result.ok else "failed"
    summary = query_linked_fact_coverage_summary_payload(result, status=status)
    if not write_summary_or_reject(args.summary_json, summary):
        return 2

    print(f"Trino query-linked fact coverage audit: {status}")
    print(
        "Boundary: "
        f"closure_gate={TRINO_QUERY_LINKED_FACT_COVERAGE_GATE}, "
        f"query_linked_fact_coverage={TRINO_QUERY_LINKED_FACT_COVERAGE_STATUS}, "
        "broader_production_closure=not_closed, "
        f"trino_sql_execution={TRINO_SQL_EXECUTION_STATUS}"
    )
    print(
        "Families: "
        f"total={result.family_count}, "
        f"source_backed={result.source_backed_family_count}, "
        f"fact_requirements={result.fact_requirement_count}, "
        f"source_requirements={result.source_requirement_count}, "
        f"states={counter_text(result.status_counts) or 'none'}"
    )
    print(
        "Open blockers: "
        f"total={result.open_blocker_count}, "
        f"{counter_text(result.blocker_counts) or 'none'}"
    )
    print(
        "Fact/source coverage: "
        f"fact_scopes={counter_text(result.fact_scope_counts) or 'none'}; "
        f"source_contracts={counter_text(result.source_contract_counts) or 'none'}; "
        f"source_granularity={counter_text(result.source_granularity_counts) or 'none'}; "
        f"linkage_scopes={counter_text(result.linkage_scope_counts) or 'none'}"
    )
    print(
        "Coverage profile: "
        f"profile={TRINO_QUERY_LINKED_PRODUCTION_REVIEW_PROFILE}, "
        f"status={summary['coverage_profile_status']}, "
        f"requirements={counter_text(result.coverage_profile_tracking_counts) or 'none'}"
    )
    print(
        "Operator/connector/telemetry decisions: "
        f"profile={TRINO_QUERY_LINKED_OPERATOR_CONNECTOR_TELEMETRY_PROFILE}, "
        f"status={summary['operator_connector_telemetry_profile_status']}, "
        "decisions="
        f"{counter_text(result.operator_connector_telemetry_decision_counts) or 'none'}, "
        "tracking="
        f"{counter_text(result.operator_connector_telemetry_decision_tracking_counts) or 'none'}"
    )
    print(
        "Query-linked requirement tracking: "
        f"query_linked_requirements="
        f"{counter_text(result.query_linked_requirement_tracking_counts) or 'none'}"
    )
    print_issues(result.issues, limit=args.limit)
    return 0 if result.ok else 1


def print_issues(issues: list[tuple[str, Any]], *, limit: int) -> None:
    if not issues:
        print("Issues: none")
        return
    print("Issues:")
    for family_id, issue in issues[:limit]:
        print(f"- {issue.category}: family={family_id}; {issue.message}")
    remaining = len(issues) - limit
    if remaining > 0:
        print(f"- additional_issues: {remaining}")


def write_summary_or_reject(path: Path | None, payload: dict[str, Any]) -> bool:
    if path is None:
        return True
    try:
        path.write_text(
            json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n", encoding="utf-8"
        )
    except OSError:
        print(
            "[trino-query-linked-fact-coverage-audit] rejected: summary JSON output "
            "could not be written",
            file=sys.stderr,
        )
        return False
    return True


def counter_text(counter: Counter[str]) -> str:
    return ", ".join(f"{key}={counter[key]}" for key in sorted(counter))


def positive_int(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if value < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
