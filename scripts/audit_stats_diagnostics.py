#!/usr/bin/env python3
"""Audit raw-free stats-diagnostics readiness across a Recent batch summary."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, TextIO


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


ACTIONABLE_STATS_TIERS = {"high", "medium"}
ACTIONABLE_TIER_SCORE_FLOORS = {"medium": 40.0, "high": 70.0}
ACTIONABLE_NEED_TYPES = {"table_stats", "column_stats", "table_and_column_stats"}
ACTIONABLE_CONFIDENCE = {"medium", "high"}
ACTIONABLE_SPEED_BENEFITS = {"medium", "high"}
USABLE_METADATA_STATUSES = {"available", "collected", "done", "ok", "partial"}
DETAIL_KINDS = (
    "partition_stats",
    "join_filter_column_stats",
    "table_stats",
    "column_stats",
    "unknown_detail",
)
GENERIC_COLUMN_STATS_COUNTER_SIGNAL = "column stats gap is not tied to specific join/filter columns"


@dataclass(frozen=True)
class StatsAuditIssue:
    category: str
    message: str


@dataclass
class StatsDiagnosticsAuditResult:
    summary_name: str
    total_cases: int
    stats_candidate_count: int = 0
    actionable_candidate_count: int = 0
    tier_counts: Counter[str] = field(default_factory=Counter)
    need_type_counts: Counter[str] = field(default_factory=Counter)
    metadata_status_counts: Counter[str] = field(default_factory=Counter)
    evidence_detail_counts: Counter[str] = field(default_factory=Counter)
    confirmation_counts: Counter[str] = field(default_factory=Counter)
    review_area_counts: Counter[str] = field(default_factory=Counter)
    issue_counts: Counter[str] = field(default_factory=Counter)
    issues: list[StatsAuditIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


class StatsAuditInputError(RuntimeError):
    """Raised when a batch summary cannot be audited."""


def load_summary(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise StatsAuditInputError(f"cannot read summary: {path}") from exc
    except json.JSONDecodeError as exc:
        raise StatsAuditInputError(f"summary is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise StatsAuditInputError(f"summary root is not an object: {path}")
    if not isinstance(payload.get("cases"), list):
        raise StatsAuditInputError(f"summary does not contain a cases list: {path}")
    return payload


def summary_cases(summary: dict[str, Any]) -> list[dict[str, Any]]:
    return [case for case in summary.get("cases") or [] if isinstance(case, dict)]


def audit_summary(
    summary_path: Path,
    *,
    fail_on_stats_readiness_gaps: bool = False,
) -> StatsDiagnosticsAuditResult:
    summary_path = summary_path.resolve(strict=True)
    summary = load_summary(summary_path)
    cases = summary_cases(summary)
    result = StatsDiagnosticsAuditResult(summary_name=summary_path.name, total_cases=len(cases))

    for case in cases:
        audit_case(result, case)

    if fail_on_stats_readiness_gaps:
        add_readiness_issues(result)
    return result


def audit_case(result: StatsDiagnosticsAuditResult, case: dict[str, Any]) -> None:
    candidate = case.get("stats_optimization_candidate")
    if not isinstance(candidate, dict):
        return
    result.stats_candidate_count += 1

    tier = safe_token(candidate.get("tier"), default="unknown")
    need_type = safe_token(candidate.get("need_type"), default="unknown")
    confidence = safe_token(candidate.get("confidence"), default="unknown")
    speed_benefit = safe_token(candidate.get("speed_benefit"), default="unknown")
    metadata_status = safe_token(case.get("metadata_status"), default="unknown")
    result.tier_counts[tier] += 1
    result.need_type_counts[need_type] += 1
    result.metadata_status_counts[metadata_status] += 1

    if tier not in ACTIONABLE_STATS_TIERS:
        return
    result.actionable_candidate_count += 1

    score = numeric_value(candidate.get("score"))
    score_floor = ACTIONABLE_TIER_SCORE_FLOORS[tier]
    if score is None:
        result.issue_counts["stats_actionable_missing_score"] += 1
    elif score < score_floor:
        result.issue_counts["stats_actionable_score_below_tier_floor"] += 1
    if confidence not in ACTIONABLE_CONFIDENCE:
        result.issue_counts["stats_actionable_low_confidence"] += 1
    if speed_benefit not in ACTIONABLE_SPEED_BENEFITS:
        result.issue_counts["stats_actionable_unknown_speed_benefit"] += 1

    if need_type not in ACTIONABLE_NEED_TYPES:
        result.issue_counts["stats_actionable_unsupported_need_type"] += 1
    if metadata_status not in USABLE_METADATA_STATUSES:
        result.issue_counts["stats_actionable_without_usable_metadata"] += 1

    details = safe_text_list(candidate.get("evidence_detail"))
    kinds = detail_kinds(details) if details else ()
    if details:
        for kind in kinds:
            result.evidence_detail_counts[kind] += 1
    else:
        result.evidence_detail_counts["missing"] += 1
        result.issue_counts["stats_actionable_missing_structured_detail"] += 1

    if details and kinds == ("unknown_detail",):
        result.issue_counts["stats_actionable_without_specific_detail"] += 1
    if need_type == "column_stats" and "join_filter_column_stats" not in set(kinds):
        result.issue_counts["stats_actionable_column_stats_without_join_filter_detail"] += 1
    if has_counter_signal(candidate, GENERIC_COLUMN_STATS_COUNTER_SIGNAL):
        result.issue_counts["stats_actionable_generic_column_stats_evidence"] += 1

    review_areas = safe_text_list(candidate.get("suggested_review_areas"))
    if review_areas:
        result.review_area_counts["present"] += 1
    else:
        result.review_area_counts["missing"] += 1
        result.issue_counts["stats_actionable_missing_review_area"] += 1

    confirmations = safe_text_list(candidate.get("required_confirmation"))
    confirmation_status = confirmation_readiness(confirmations)
    result.confirmation_counts[confirmation_status] += 1
    if confirmation_status != "comparable_rerun":
        result.issue_counts["stats_actionable_missing_comparable_confirmation"] += 1


def detail_kinds(details: tuple[str, ...]) -> tuple[str, ...]:
    kinds: list[str] = []
    for detail in details:
        text = detail.lower()
        if "table/partition row-count" in text:
            kinds.append("table_stats")
        elif "partition row-count" in text or "partitioned table" in text:
            kinds.append("partition_stats")
        elif "join/filter column" in text:
            kinds.append("join_filter_column_stats")
        elif "column stats" in text:
            kinds.append("column_stats")
    if not kinds:
        kinds.append("unknown_detail")
    return tuple(kind for kind in DETAIL_KINDS if kind in set(kinds))


def confirmation_readiness(confirmations: tuple[str, ...]) -> str:
    if not confirmations:
        return "missing"
    text = " ".join(confirmations).lower()
    has_compare = "compare" in text or "comparable" in text
    has_rerun = "rerun" in text or "next scan" in text or "after stats" in text
    return "comparable_rerun" if has_compare and has_rerun else "incomplete"


def add_readiness_issues(result: StatsDiagnosticsAuditResult) -> None:
    for category in (
        "stats_actionable_missing_score",
        "stats_actionable_score_below_tier_floor",
        "stats_actionable_low_confidence",
        "stats_actionable_unknown_speed_benefit",
        "stats_actionable_unsupported_need_type",
        "stats_actionable_without_usable_metadata",
        "stats_actionable_missing_structured_detail",
        "stats_actionable_without_specific_detail",
        "stats_actionable_missing_review_area",
        "stats_actionable_missing_comparable_confirmation",
        "stats_actionable_column_stats_without_join_filter_detail",
        "stats_actionable_generic_column_stats_evidence",
    ):
        count = result.issue_counts.get(category, 0)
        if count:
            add_issue(result, category, f"{category} observed in {count} actionable case(s)")


def add_issue(result: StatsDiagnosticsAuditResult, category: str, message: str) -> None:
    result.issues.append(StatsAuditIssue(category, message))


def safe_text_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            result.append(text[:240])
    return tuple(result)


def safe_token(value: object, *, default: str = "unknown") -> str:
    text = str(value or "").strip().lower()
    text = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in text)
    text = "_".join(part for part in text.split("_") if part)
    return text[:60] if text else default


def numeric_value(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def has_counter_signal(candidate: dict[str, Any], signal: str) -> bool:
    expected = signal.strip().lower()
    return any(
        item.strip().lower() == expected
        for item in safe_text_list(candidate.get("counter_signals"))
    )


def print_counter(title: str, counter: Counter[str], *, out: TextIO, limit: int) -> None:
    print(f"{title}:", file=out)
    if not counter:
        print("  <none>", file=out)
        return
    for key, count in counter.most_common(limit):
        print(f"  {key}: {count}", file=out)


def print_result(
    result: StatsDiagnosticsAuditResult,
    *,
    out: TextIO = sys.stdout,
    limit: int = 12,
) -> None:
    print(f"Summary: {result.summary_name}", file=out)
    print(
        "Cases: "
        f"total={result.total_cases}, stats_candidates={result.stats_candidate_count}, "
        f"actionable_stats_candidates={result.actionable_candidate_count}",
        file=out,
    )
    print_counter("Stats tiers", result.tier_counts, out=out, limit=limit)
    print_counter("Stats need types", result.need_type_counts, out=out, limit=limit)
    print_counter("Metadata statuses", result.metadata_status_counts, out=out, limit=limit)
    print_counter("Evidence detail", result.evidence_detail_counts, out=out, limit=limit)
    print_counter("Review areas", result.review_area_counts, out=out, limit=limit)
    print_counter("Confirmation readiness", result.confirmation_counts, out=out, limit=limit)
    print_counter("Readiness gap counters", result.issue_counts, out=out, limit=limit)
    print("Issues:", file=out)
    if not result.issues:
        print("  none", file=out)
        return
    for issue in result.issues[:limit]:
        print(f"  {issue.category}: {issue.message}", file=out)


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary", type=Path, help="Path to batch_summary.json")
    parser.add_argument("--limit", type=int, default=12, help="Rows to print per section")
    parser.add_argument(
        "--fail-on-stats-readiness-gaps",
        action="store_true",
        help=(
            "Return non-zero when medium/high stats candidates lack score/tier strength, "
            "structured metadata detail, usable metadata status, review areas, or comparable "
            "rerun confirmation."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = audit_summary(
            args.summary,
            fail_on_stats_readiness_gaps=args.fail_on_stats_readiness_gaps,
        )
    except StatsAuditInputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print_result(result, limit=args.limit)
    return 1 if not result.ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
