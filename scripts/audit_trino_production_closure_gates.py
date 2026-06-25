#!/usr/bin/env python3
"""Audit Trino bounded production claim closure gates."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Iterable, Sequence
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
from query_doctor.trino.production_closure_gates import (  # noqa: E402
    TRINO_CURRENT_TRACKING_SUMMARY_KINDS,
    TRINO_PRODUCTION_CLOSURE_STATUS,
    TRINO_SQL_EXECUTION_STATUS,
    audit_trino_production_closure_gates,
    trino_production_closure_summary_payload,
)
from scripts.audit_trino_support_gap_matrix import (  # noqa: E402
    TRINO_BROADER_PRODUCTION_CLOSURE_GATES,
)


LOCAL_PATH_RE = re.compile(
    r"(?<![\w/])(?:/private)?/(?:Users|home|tmp|var|etc)/[^\s<>'\"]+"
    r"|(?<![\w/])[A-Za-z]:\\[^\s<>'\"]+"
)
URL_RE = re.compile(r"\bhttps?://\S+", re.IGNORECASE)


class TrinoProductionClosureInputError(RuntimeError):
    """Raised when a retained closure summary cannot be accepted safely."""


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check the bounded Trino production claim closure gate set. The audit is "
            "dev-only, raw-free, and does not collect from Trino, run SQL, add "
            "Running, crawl query history, enable product metadata collection, emit "
            "LLM reports, run Query Optimizer jobs, generate SQL, or promote "
            "broader/shared Trino production expansion."
        )
    )
    parser.add_argument(
        "--summary-input-json",
        action="append",
        type=Path,
        default=[],
        help=(
            "Already raw-free closure tracking summary JSON. Repeat for current "
            "tracking gates. Input paths are never printed."
        ),
    )
    parser.add_argument(
        "--require-current-tracking-summaries",
        action="store_true",
        help=(
            "Require one raw-free summary input for every current Trino production "
            "closure tracking summary kind."
        ),
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="Optional raw-free machine summary path. The path is never printed.",
    )
    parser.add_argument("--limit", type=positive_int, default=12, help="Maximum issues to print.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    payloads: list[dict[str, Any]] = []
    for path in args.summary_input_json:
        try:
            payloads.append(load_summary_payload(path))
        except TrinoProductionClosureInputError as exc:
            print(f"[trino-production-closure-audit] rejected: {exc}", file=sys.stderr)
            return 2

    result = audit_trino_production_closure_gates(
        payloads,
        support_gap_gates=TRINO_BROADER_PRODUCTION_CLOSURE_GATES,
        require_current_tracking_summaries=args.require_current_tracking_summaries,
    )
    status = "ok" if result.ok else "failed"
    summary = trino_production_closure_summary_payload(
        result,
        status=status,
        require_current_tracking_summaries=args.require_current_tracking_summaries,
    )
    if not write_summary_or_reject(args.summary_json, args.summary_input_json, summary):
        return 2

    print(f"Trino production closure gates audit: {status}")
    print(
        "Boundary: "
        f"production_closure={summary['production_closure_status']}, "
        f"broader_production_closure={summary['broader_production_closure_status']}, "
        f"closure_gates={result.gate_count}, "
        f"trino_sql_execution={TRINO_SQL_EXECUTION_STATUS}"
    )
    print(
        "Tracking: "
        f"summary_backed_gates={result.summary_backed_gate_count}, "
        f"unbacked_gates={result.unbacked_gate_count}, "
        f"current_summary_kinds={len(TRINO_CURRENT_TRACKING_SUMMARY_KINDS)}, "
        f"summary_inputs={result.summary_input_count}, "
        f"current_tracking_summary={result.current_tracking_summary_status}, "
        f"missing_required_inputs={result.missing_current_tracking_summary_count}, "
        f"invalid_current_tracking_summaries={result.invalid_current_tracking_summary_count}"
    )
    print(
        "Linkage: "
        f"representative_evidence_linkage={result.representative_evidence_linkage_status}, "
        f"representative_evidence_linkage_required={str(result.representative_evidence_linkage_required).lower()}, "
        f"representative_evidence_linkage_ready={result.representative_evidence_linkage_ready_count}, "
        f"representative_evidence_linkage_invalid_summaries={result.representative_evidence_linkage_invalid_summary_count}, "
        f"representative_evidence_linkage_missing_summaries={result.representative_evidence_linkage_missing_summary_count}"
    )
    print(f"Gate tracking: gate_tracking={counter_text(result.gate_tracking_counts) or 'none'}")
    print(
        "Gate states: "
        f"statuses={counter_text(result.status_counts) or 'none'}; "
        f"tracking={counter_text(result.tracking_state_counts) or 'none'}"
    )
    print(
        "Summary inputs: "
        f"kinds={counter_text(result.summary_kind_counts) or 'none'}; "
        f"gate_summaries={counter_text(result.gate_summary_counts) or 'none'}"
    )
    print_issues(result.issues, limit=args.limit)
    return 0 if result.ok else 1


def load_summary_payload(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TrinoProductionClosureInputError("summary JSON input could not be read") from exc
    if raw_text_issue_categories(text):
        raise TrinoProductionClosureInputError("summary JSON input contains raw-like content")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TrinoProductionClosureInputError("summary JSON input is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise TrinoProductionClosureInputError("summary JSON input must be a JSON object")
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
        print(f"[trino-production-closure-audit] rejected: {overlap_error}", file=sys.stderr)
        return False
    if raw_text_issue_categories(json.dumps(payload, ensure_ascii=True, sort_keys=True)):
        print(
            "[trino-production-closure-audit] rejected: summary JSON output would "
            "contain raw-like content",
            file=sys.stderr,
        )
        return False
    try:
        write_ascii_json_artifact(path, payload)
    except OSError:
        print(
            "[trino-production-closure-audit] rejected: summary JSON output could not be written",
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


def print_issues(issues: list[Any], *, limit: int) -> None:
    if not issues:
        print("Issues: none")
        return
    print("Issues:")
    for issue in issues[:limit]:
        context = []
        if issue.gate_id is not None:
            context.append(f"gate={issue.gate_id}")
        if issue.summary_kind is not None:
            context.append(f"summary={issue.summary_kind}")
        context_text = f"{'; '.join(context)}; " if context else ""
        print(f"- {issue.category}: {context_text}{issue.message}")
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
