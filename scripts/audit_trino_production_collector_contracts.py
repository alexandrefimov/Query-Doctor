#!/usr/bin/env python3
"""Audit Trino production collector contract closure without enabling support."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.report.safety_validation import (  # noqa: E402
    contains_raw_sql_like_text,
    validate_report_internal_fingerprints,
)
from query_doctor.safety import redaction  # noqa: E402
from query_doctor.safety.handoff_artifacts import (  # noqa: E402
    output_overlaps_inputs_error,
    write_ascii_json_artifact,
)
from query_doctor.trino.production_collector_contracts import (  # noqa: E402
    TRINO_PRODUCTION_COLLECTOR_CONTRACTS_GATE,
    TRINO_PRODUCTION_COLLECTOR_REPRESENTATIVE_EVIDENCE_READY,
    TRINO_PRODUCTION_COLLECTOR_CONTRACTS_STATUS,
    audit_trino_production_collector_contracts,
    production_collector_summary_payload,
)


LOCAL_PATH_RE = re.compile(
    r"(?<![\w/])(?:/private)?/(?:Users|home|tmp|var|etc)/[^\s<>'\"]+"
    r"|(?<![\w/])[A-Za-z]:\\[^\s<>'\"]+"
)
URL_RE = re.compile(r"\bhttps?://\S+", re.IGNORECASE)


class TrinoProductionCollectorInputError(RuntimeError):
    """Raised when collector-audit retained summary input is unsafe."""


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check the Trino production collector contract closure gate. The audit "
            "is dev-only, raw-free, and does not add Running, query-history crawling, "
            "metadata product collection, LLM reports, Query Optimizer jobs, generated "
            "SQL, user SQL execution, or broader Trino production support."
        )
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="Optional raw-free machine summary path. The path is never printed.",
    )
    parser.add_argument(
        "--representative-evidence-summary-json",
        action="append",
        type=Path,
        default=[],
        help=(
            "Optional raw-free trino_representative_evidence_audit_v1 summary JSON "
            "for collector-review handoff checks. Input paths are never printed."
        ),
    )
    parser.add_argument(
        "--require-representative-evidence-summary",
        action="store_true",
        help="Fail unless at least one retained representative-evidence summary is provided.",
    )
    parser.add_argument("--limit", type=positive_int, default=12, help="Maximum issues to print.")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    representative_evidence_summaries: list[dict[str, Any]] = []
    for path in args.representative_evidence_summary_json:
        try:
            representative_evidence_summaries.append(load_summary_payload(path))
        except TrinoProductionCollectorInputError as exc:
            print(f"[trino-production-collector-contracts-audit] rejected: {exc}", file=sys.stderr)
            return 2

    result = audit_trino_production_collector_contracts(
        representative_evidence_summaries=representative_evidence_summaries,
        require_representative_evidence_summary=args.require_representative_evidence_summary,
    )
    status = "ok" if result.ok else "failed"
    summary = production_collector_summary_payload(result, status=status)
    if not write_summary_or_reject(
        args.summary_json,
        args.representative_evidence_summary_json,
        summary,
    ):
        return 2

    print(f"Trino production collector contracts audit: {status}")
    print(
        "Boundary: "
        f"closure_gate={TRINO_PRODUCTION_COLLECTOR_CONTRACTS_GATE}, "
        f"production_collector_contracts={TRINO_PRODUCTION_COLLECTOR_CONTRACTS_STATUS}, "
        "broader_production_closure=not_closed, "
        "trino_sql_execution=not_performed"
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
        "Source contracts: "
        f"{counter_text(result.source_contract_counts) or 'none'}; "
        f"network={counter_text(result.network_access_counts) or 'none'}"
    )
    print(
        "Contract policy: "
        f"auth={counter_text(result.auth_reference_policy_counts) or 'none'}; "
        f"schema={counter_text(result.source_schema_gate_counts) or 'none'}; "
        f"retry={counter_text(result.retry_policy_counts) or 'none'}; "
        f"failure_mode={counter_text(result.failure_mode_counts) or 'none'}"
    )
    print(
        "Reader implementations: "
        f"status={counter_text(result.reader_status_counts) or 'none'}; "
        f"scope={counter_text(result.reader_scope_counts) or 'none'}; "
        f"cli_roles={counter_text(result.reader_cli_role_counts) or 'none'}; "
        f"capabilities={counter_text(result.reader_capability_counts) or 'none'}; "
        f"forbidden_roles={result.forbidden_reader_role_count}; "
        f"forbidden_capabilities={result.forbidden_reader_capability_count}"
    )
    print(
        "Source requirement tracking: "
        f"source_requirements={counter_text(result.source_requirement_tracking_counts) or 'none'}"
    )
    print(
        "Representative evidence: "
        f"status={result.representative_evidence_contract_status}, "
        f"required={str(result.representative_evidence_required).lower()}, "
        f"summaries={result.representative_evidence_summary_count}, "
        f"ready={result.representative_evidence_ready_count}, "
        f"ready_status={TRINO_PRODUCTION_COLLECTOR_REPRESENTATIVE_EVIDENCE_READY}"
    )
    print_issues(result.issues, limit=args.limit)
    return 0 if result.ok else 1


def print_issues(issues: list[tuple[str, Any]], *, limit: int) -> None:
    if not issues:
        print("Issues: none")
        return
    print("Issues:")
    for family_id, issue in issues[:limit]:
        context = f"family={family_id}"
        if issue.source_type is not None:
            context = f"{context}; source={issue.source_type}"
        print(f"- {issue.category}: {context}; {issue.message}")
    remaining = len(issues) - limit
    if remaining > 0:
        print(f"- additional_issues: {remaining}")


def load_summary_payload(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TrinoProductionCollectorInputError("summary JSON input could not be read") from exc
    raw_categories = raw_text_issue_categories(text)
    if raw_categories:
        raise TrinoProductionCollectorInputError("summary JSON input contains raw-like content")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TrinoProductionCollectorInputError("summary JSON input is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise TrinoProductionCollectorInputError("summary JSON input must be a JSON object")
    return payload


def write_summary_or_reject(
    path: Path | None,
    inputs: Iterable[Path],
    payload: dict[str, Any],
) -> bool:
    if path is None:
        return True
    overlap_error = output_overlaps_inputs_error(
        path,
        inputs,
        message="summary JSON output must differ from every input summary",
    )
    if overlap_error:
        print(
            f"[trino-production-collector-contracts-audit] rejected: {overlap_error}",
            file=sys.stderr,
        )
        return False
    raw_categories = raw_text_issue_categories(json.dumps(payload, ensure_ascii=True))
    if raw_categories:
        print(
            "[trino-production-collector-contracts-audit] rejected: summary JSON output "
            "would contain raw-like content",
            file=sys.stderr,
        )
        return False
    try:
        write_ascii_json_artifact(path, payload)
    except OSError:
        print(
            "[trino-production-collector-contracts-audit] rejected: summary JSON output "
            "could not be written",
            file=sys.stderr,
        )
        return False
    return True


def raw_text_issue_categories(text: str) -> tuple[str, ...]:
    categories: list[str] = []
    if contains_raw_sql_like_text(text):
        categories.append("sql")
    if validate_report_internal_fingerprints(text):
        categories.append("internal_fingerprint")
    if redaction.EMAIL_RE.search(text):
        categories.append("email")
    if redaction.IPV4_RE.search(text):
        categories.append("ipv4")
    if redaction.HOSTLIKE_FQDN_RE.search(text):
        categories.append("hostname")
    if URL_RE.search(text):
        categories.append("url")
    if LOCAL_PATH_RE.search(text):
        categories.append("local_path")
    if redaction.SECRET_VALUE_RE.search(text):
        categories.append("secret")
    return tuple(sorted(set(categories)))


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
