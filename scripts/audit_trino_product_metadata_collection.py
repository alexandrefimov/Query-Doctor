#!/usr/bin/env python3
"""Audit Trino product metadata collection closure without enabling support."""

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

from query_doctor.trino.product_metadata_collection import (  # noqa: E402
    TRINO_PRODUCT_METADATA_COLLECTION_GATE,
    TRINO_PRODUCT_METADATA_COLLECTION_STATUS,
    TRINO_PRODUCT_METADATA_PRODUCTION_REVIEW_PROFILE,
    TRINO_PRODUCT_METADATA_SQL_EXECUTION_STATUS,
    TRINO_USER_SQL_EXECUTION_STATUS,
    audit_trino_product_metadata_collection,
    product_metadata_collection_summary_payload,
)


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check the Trino product metadata collection closure gate. The audit is "
            "dev-only, raw-free, and does not read metadata, run Trino CLI, execute "
            "user SQL, enable product metadata collection, add Details/report/"
            "optimizer metadata output, crawl objects, or promote broader Trino "
            "production support."
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
    result = audit_trino_product_metadata_collection()
    status = "ok" if result.ok else "failed"
    summary = product_metadata_collection_summary_payload(result, status=status)
    if not write_summary_or_reject(args.summary_json, summary):
        return 2

    print(f"Trino product metadata collection audit: {status}")
    print(
        "Boundary: "
        f"closure_gate={TRINO_PRODUCT_METADATA_COLLECTION_GATE}, "
        f"product_metadata_collection={TRINO_PRODUCT_METADATA_COLLECTION_STATUS}, "
        "broader_production_closure=not_closed, "
        f"trino_sql_execution={TRINO_USER_SQL_EXECUTION_STATUS}, "
        f"metadata_cli_sql_execution={TRINO_PRODUCT_METADATA_SQL_EXECUTION_STATUS}"
    )
    print(
        "Families: "
        f"total={result.family_count}, "
        f"source_backed={result.source_backed_family_count}, "
        f"requirements={result.source_requirement_count}, "
        f"states={counter_text(result.status_counts) or 'none'}"
    )
    print(
        "Open blockers: "
        f"total={result.open_blocker_count}, "
        f"{counter_text(result.blocker_counts) or 'none'}"
    )
    print(
        "Metadata boundary: "
        f"adapter_metadata_collection={'enabled' if result.adapter_metadata_collection_enabled else 'blocked'}, "
        f"product_capabilities={result.product_capability_count}, "
        f"source_contracts={counter_text(result.source_contract_counts) or 'none'}, "
        f"sql_execution={counter_text(result.sql_execution_counts) or 'none'}"
    )
    print(
        "Product metadata requirement tracking: "
        f"product_metadata_requirements="
        f"{counter_text(result.product_metadata_requirement_tracking_counts) or 'none'}"
    )
    print(
        "Production review profile: "
        f"profile={TRINO_PRODUCT_METADATA_PRODUCTION_REVIEW_PROFILE}, "
        f"status={summary['production_review_profile_status']}, "
        f"requirements={counter_text(result.production_review_tracking_counts) or 'none'}"
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
            "[trino-product-metadata-collection-audit] rejected: summary JSON output "
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
