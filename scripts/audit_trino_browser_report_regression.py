#!/usr/bin/env python3
"""Audit Trino browser/report regression coverage without enabling support."""

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

from query_doctor.trino.browser_report_regression import (  # noqa: E402
    TRINO_BROWSER_REPORT_LLM_REPORTS,
    TRINO_BROWSER_REPORT_PRODUCTION_REVIEW_PROFILE,
    TRINO_BROWSER_REPORT_RAW_OUTPUT_STATUS,
    TRINO_BROWSER_REPORT_REGRESSION_GATE,
    TRINO_BROWSER_REPORT_REGRESSION_STATUS,
    TRINO_BROWSER_REPORT_SQL_EXECUTION,
    audit_trino_browser_report_regression,
    browser_report_regression_summary_payload,
)


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check the Trino browser/report regression closure gate. The audit is "
            "dev-only, raw-free, and reads only source/test catalogs and capability "
            "metadata. It does not render browser pages, load case artifacts, collect "
            "from Trino, run report jobs, run optimizer jobs, generate SQL, execute "
            "SQL, or promote broader Trino production support."
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
    result = audit_trino_browser_report_regression(repo_root=ROOT)
    status = "ok" if result.ok else "failed"
    summary = browser_report_regression_summary_payload(result, status=status)
    if not write_summary_or_reject(args.summary_json, summary):
        return 2

    print(f"Trino browser/report regression audit: {status}")
    print(
        "Boundary: "
        f"closure_gate={TRINO_BROWSER_REPORT_REGRESSION_GATE}, "
        f"browser_report_regression={TRINO_BROWSER_REPORT_REGRESSION_STATUS}, "
        "broader_production_closure=not_closed, "
        f"llm_reports={TRINO_BROWSER_REPORT_LLM_REPORTS}, "
        f"raw_outputs={TRINO_BROWSER_REPORT_RAW_OUTPUT_STATUS}, "
        f"trino_sql_execution={TRINO_BROWSER_REPORT_SQL_EXECUTION}"
    )
    print(
        "Coverage: "
        f"families={result.family_count}, "
        f"required_tests={result.required_test_count}, "
        f"present_tests={result.present_test_count}, "
        f"source_files={result.source_file_count}, "
        f"route_capabilities={result.required_route_capability_count}"
    )
    print(
        "Routes: "
        f"product_capabilities={result.product_capability_count}, "
        f"route_counts={counter_text(result.route_capability_counts) or 'none'}"
    )
    print(
        "Browser/report requirement tracking: "
        f"browser_report_requirements="
        f"{counter_text(result.browser_report_requirement_tracking_counts) or 'none'}"
    )
    print(
        "Production review profile: "
        f"profile={TRINO_BROWSER_REPORT_PRODUCTION_REVIEW_PROFILE}, "
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
            "[trino-browser-report-regression-audit] rejected: summary JSON output "
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
