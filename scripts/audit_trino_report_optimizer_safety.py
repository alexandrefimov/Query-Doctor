#!/usr/bin/env python3
"""Audit Trino report and optimizer safety without enabling broader support."""

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

from query_doctor.trino.report_optimizer_safety import (  # noqa: E402
    TRINO_REPORT_OPTIMIZER_GENERATED_SQL_STATUS,
    TRINO_REPORT_OPTIMIZER_LLM_REPORTS_STATUS,
    TRINO_REPORT_OPTIMIZER_PRODUCTION_REVIEW_PROFILE,
    TRINO_REPORT_OPTIMIZER_QUERY_OPTIMIZER_JOBS_STATUS,
    TRINO_REPORT_OPTIMIZER_SAFETY_GATE,
    TRINO_REPORT_OPTIMIZER_SAFETY_STATUS,
    TRINO_REPORT_OPTIMIZER_SOURCE_BOUNDARY,
    TRINO_REPORT_OPTIMIZER_SQL_EXECUTION_STATUS,
    audit_trino_report_optimizer_safety,
    report_optimizer_safety_summary_payload,
)


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check the Trino report/optimizer safety closure gate. The audit is "
            "dev-only, raw-free, and does not load Trino case artifacts, run LLM "
            "reports, create Query Optimizer jobs, generate SQL, execute SQL, or "
            "promote broader Trino production support."
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
    result = audit_trino_report_optimizer_safety()
    status = "ok" if result.ok else "failed"
    summary = report_optimizer_safety_summary_payload(result, status=status)
    if not write_summary_or_reject(args.summary_json, summary):
        return 2

    print(f"Trino report optimizer safety audit: {status}")
    print(
        "Boundary: "
        f"closure_gate={TRINO_REPORT_OPTIMIZER_SAFETY_GATE}, "
        f"report_optimizer_safety={TRINO_REPORT_OPTIMIZER_SAFETY_STATUS}, "
        "broader_production_closure=not_closed, "
        f"source_boundary={TRINO_REPORT_OPTIMIZER_SOURCE_BOUNDARY}, "
        f"llm_reports={TRINO_REPORT_OPTIMIZER_LLM_REPORTS_STATUS}, "
        f"query_optimizer_jobs={TRINO_REPORT_OPTIMIZER_QUERY_OPTIMIZER_JOBS_STATUS}, "
        f"generated_sql={TRINO_REPORT_OPTIMIZER_GENERATED_SQL_STATUS}, "
        f"trino_sql_execution={TRINO_REPORT_OPTIMIZER_SQL_EXECUTION_STATUS}"
    )
    print(
        "Families: "
        f"total={result.family_count}, "
        f"required_capabilities={result.required_capability_count}, "
        f"product_capabilities={result.product_capability_count}, "
        f"states={counter_text(result.status_counts) or 'none'}"
    )
    print(
        "Validation: "
        f"policy_fields={result.policy_field_count}, "
        f"sentinels={result.validation_sentinel_count}, "
        f"validator_checks={result.validator_check_count}, "
        f"validator_rejections={counter_text(result.validator_rejection_counts) or 'none'}"
    )
    print(
        "Report optimizer requirement tracking: "
        f"report_optimizer_requirements="
        f"{counter_text(result.report_optimizer_requirement_tracking_counts) or 'none'}"
    )
    print(
        "Production review profile: "
        f"profile={TRINO_REPORT_OPTIMIZER_PRODUCTION_REVIEW_PROFILE}, "
        f"status={summary['production_review_profile_status']}, "
        f"requirements={counter_text(result.production_review_tracking_counts) or 'none'}"
    )
    print(
        "Open blockers: "
        f"total={result.open_blocker_count}, "
        f"{counter_text(result.blocker_counts) or 'none'}"
    )
    print_issues(result.issues, limit=args.limit)
    return 0 if result.ok else 1


def write_summary_or_reject(path: Path | None, payload: dict[str, Any]) -> bool:
    if path is None:
        return True
    try:
        path.write_text(
            json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n", encoding="utf-8"
        )
    except OSError:
        print(
            "[trino-report-optimizer-safety-audit] rejected: summary JSON output "
            "could not be written",
            file=sys.stderr,
        )
        return False
    return True


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
