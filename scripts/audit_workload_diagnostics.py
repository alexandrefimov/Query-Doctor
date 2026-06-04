#!/usr/bin/env python3
"""Audit raw-free workload diagnostics across a Recent batch summary."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, TextIO


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.web.action_outcomes import (  # noqa: E402
    DEFAULT_METRIC_MIN_APPLIED,
    WorkloadOutcomeMetric,
    load_action_outcomes,
    summarize_workload_action_outcomes,
)
from query_doctor.report.safety_validation import contains_raw_sql_like_text  # noqa: E402
from query_doctor.safety import redaction  # noqa: E402
from query_doctor.web.presenters.recent_scan import present_recent_scan_summary  # noqa: E402
from query_doctor.web.presenters.workload_detail import present_workload_detail  # noqa: E402


COMPARABLE_COMPARISON_TERMS = (
    "compare",
    "comparable",
)
COMPARABLE_RERUN_TERMS = (
    "next scan",
    "next run",
    "rerun",
    "re-run",
    "comparable load",
    "comparable scan",
    "under comparable",
)
REGRESSION_LABELS = {"strong", "mild", "none", "unknown"}
URL_RE = re.compile(r"\bhttps?://", re.IGNORECASE)
LOCAL_PATH_RE = re.compile(r"(?<![\w/])(?:/private)?/tmp/|(?<![\w/])/Users/")


@dataclass(frozen=True)
class WorkloadAuditIssue:
    category: str
    message: str


@dataclass
class WorkloadDiagnosticsAuditResult:
    summary_name: str
    total_cases: int
    row_count: int = 0
    workload_group_count: int = 0
    workload_detail_count: int = 0
    repeated_case_count: int = 0
    action_queue_count: int = 0
    workload_history_counts: Counter[str] = field(default_factory=Counter)
    group_regression_counts: Counter[str] = field(default_factory=Counter)
    group_baseline_counts: Counter[str] = field(default_factory=Counter)
    group_member_count_buckets: Counter[str] = field(default_factory=Counter)
    detail_representative_counts: Counter[str] = field(default_factory=Counter)
    detail_action_hint_counts: Counter[str] = field(default_factory=Counter)
    detail_limitation_counts: Counter[str] = field(default_factory=Counter)
    action_queue_signal_counts: Counter[str] = field(default_factory=Counter)
    action_queue_verification_counts: Counter[str] = field(default_factory=Counter)
    action_outcome_source_counts: Counter[str] = field(default_factory=Counter)
    action_outcome_group_coverage_counts: Counter[str] = field(default_factory=Counter)
    action_outcome_family_counts: Counter[str] = field(default_factory=Counter)
    action_queue_outcome_counts: Counter[str] = field(default_factory=Counter)
    detail_action_hint_outcome_counts: Counter[str] = field(default_factory=Counter)
    issue_counts: Counter[str] = field(default_factory=Counter)
    issues: list[WorkloadAuditIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


class WorkloadAuditInputError(RuntimeError):
    """Raised when a batch summary cannot be audited."""


def load_summary(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise WorkloadAuditInputError(f"cannot read summary: {path}") from exc
    except json.JSONDecodeError as exc:
        raise WorkloadAuditInputError(f"summary is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise WorkloadAuditInputError(f"summary root is not an object: {path}")
    if not isinstance(payload.get("cases"), list):
        raise WorkloadAuditInputError(f"summary does not contain a cases list: {path}")
    return payload


def audit_summary(
    summary_path: Path,
    *,
    fail_on_workload_readiness_gaps: bool = False,
    action_outcomes_path: Path | None = None,
    fail_on_action_outcome_readiness_gaps: bool = False,
    action_outcome_min_applied: int = DEFAULT_METRIC_MIN_APPLIED,
) -> WorkloadDiagnosticsAuditResult:
    summary_path = summary_path.resolve(strict=True)
    summary = load_summary(summary_path)
    action_outcome_metrics = load_workload_outcome_metrics(
        result_path=action_outcomes_path,
        min_applied=action_outcome_min_applied,
    )
    audit_action_outcome_feedback = (
        action_outcomes_path is not None or fail_on_action_outcome_readiness_gaps
    )
    scan = present_recent_scan_summary(summary, workload_outcome_metrics=action_outcome_metrics)
    result = WorkloadDiagnosticsAuditResult(
        summary_name=summary_path.name,
        total_cases=len(summary.get("cases") or ()),
        row_count=len(scan.rows),
        workload_group_count=len(scan.workload_groups.groups),
        action_queue_count=len(scan.workload_digest.action_queue),
    )

    if audit_action_outcome_feedback:
        audit_action_outcome_source(result, action_outcomes_path, action_outcome_metrics)
    audit_workload_history(result, scan.workload_history)
    grouped_rows = {
        group.fingerprint: tuple(
            row for row in scan.rows if row.workload_fingerprint == group.fingerprint
        )
        for group in scan.workload_groups.groups
    }
    for group in scan.workload_groups.groups:
        rows = grouped_rows.get(group.fingerprint, ())
        audit_workload_group(
            result,
            summary,
            group,
            rows,
            action_outcome_metrics=action_outcome_metrics,
            audit_action_outcome_feedback=audit_action_outcome_feedback,
        )
    for entry in scan.workload_digest.action_queue:
        audit_action_queue_entry(
            result,
            entry,
            audit_action_outcome_feedback=audit_action_outcome_feedback,
        )

    if fail_on_workload_readiness_gaps:
        add_readiness_issues(result)
    if fail_on_action_outcome_readiness_gaps:
        add_action_outcome_readiness_issues(result)
    return result


def load_workload_outcome_metrics(
    *,
    result_path: Path | None,
    min_applied: int,
) -> dict[str, WorkloadOutcomeMetric]:
    if result_path is None:
        return {}
    records = load_action_outcomes(path=result_path, limit=1_000_000)
    return summarize_workload_action_outcomes(records, min_applied=max(1, min_applied))


def audit_action_outcome_source(
    result: WorkloadDiagnosticsAuditResult,
    action_outcomes_path: Path | None,
    metrics: dict[str, WorkloadOutcomeMetric],
) -> None:
    if action_outcomes_path is None:
        result.action_outcome_source_counts["not_supplied"] += 1
        return
    result.action_outcome_source_counts["supplied"] += 1
    result.action_outcome_source_counts[f"workloads_{count_bucket(len(metrics))}"] += 1
    if not metrics:
        result.issue_counts["action_outcomes_empty"] += 1
    if action_outcomes_raw_free_violations(action_outcomes_path):
        result.issue_counts["action_outcomes_raw_like"] += 1


def action_outcomes_raw_free_violations(path: Path) -> tuple[str, ...]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ()
    violations: list[str] = []
    if contains_raw_sql_like_text(text):
        violations.append("sql")
    if URL_RE.search(text):
        violations.append("url")
    if LOCAL_PATH_RE.search(text):
        violations.append("local_path")
    if redaction.EMAIL_RE.search(text):
        violations.append("email")
    if redaction.IPV4_RE.search(text):
        violations.append("ipv4")
    if redaction.HOSTLIKE_FQDN_RE.search(text):
        violations.append("hostname")
    if redaction.SECRET_VALUE_RE.search(text):
        violations.append("secret")
    return tuple(sorted(set(violations)))


def audit_workload_history(result: WorkloadDiagnosticsAuditResult, history: object) -> None:
    if history is None:
        result.workload_history_counts["missing"] += 1
        return
    enabled = "enabled" if getattr(history, "enabled", False) else "disabled"
    append_status = safe_token(getattr(history, "append_status", "unknown"))
    result.workload_history_counts[enabled] += 1
    result.workload_history_counts[f"append_{append_status}"] += 1
    loaded = int_value(getattr(history, "loaded_record_count", 0))
    result.workload_history_counts[f"loaded_{count_bucket(loaded)}"] += 1


def audit_workload_group(
    result: WorkloadDiagnosticsAuditResult,
    summary: dict[str, Any],
    group: Any,
    rows: tuple[Any, ...],
    *,
    action_outcome_metrics: dict[str, WorkloadOutcomeMetric],
    audit_action_outcome_feedback: bool,
) -> None:
    result.repeated_case_count += int_value(getattr(group, "member_count", 0))
    regression = safe_regression(getattr(group, "regression", "unknown"))
    baseline_count = int_value(getattr(group, "baseline_sample_count", 0))
    result.group_regression_counts[regression] += 1
    result.group_baseline_counts["available" if baseline_count > 0 else "missing"] += 1
    result.group_member_count_buckets[
        count_bucket(int_value(getattr(group, "member_count", 0)))
    ] += 1

    if len(rows) < int_value(getattr(group, "member_count", 0)):
        result.issue_counts["workload_group_row_gap"] += 1
    if regression in {"strong", "mild"} and baseline_count <= 0:
        result.issue_counts["regression_without_baseline"] += 1
    if audit_action_outcome_feedback:
        audit_workload_outcome_metric(
            result,
            action_outcome_metrics.get(str(getattr(group, "fingerprint", ""))),
        )

    detail = present_workload_detail(
        summary,
        getattr(group, "fingerprint", ""),
        workload_outcome_metrics=action_outcome_metrics,
    )
    if detail is None:
        result.issue_counts["workload_detail_missing"] += 1
        return
    result.workload_detail_count += 1
    representative_count = len(detail.representatives)
    result.detail_representative_counts[count_bucket(representative_count)] += 1
    if representative_count <= 0:
        result.issue_counts["workload_representatives_missing"] += 1
    action_hint_count = len(detail.action_hints)
    result.detail_action_hint_counts[count_bucket(action_hint_count)] += 1
    if audit_action_outcome_feedback:
        result.action_outcome_group_coverage_counts[
            outcome_summary_bucket(detail.outcome_summary)
        ] += 1
    for limitation in detail.limitations:
        result.detail_limitation_counts[classify_limitation(limitation)] += 1
    for hint in detail.action_hints:
        audit_action_hint(
            result,
            hint,
            audit_action_outcome_feedback=audit_action_outcome_feedback,
        )


def audit_workload_outcome_metric(
    result: WorkloadDiagnosticsAuditResult,
    metric: WorkloadOutcomeMetric | None,
) -> None:
    if metric is None or metric.total_records <= 0:
        result.issue_counts["workload_action_outcome_feedback_missing"] += 1
        return
    result.action_outcome_family_counts[safe_signal(metric.family_signal.recommendation_id)] += 1
    result.action_outcome_family_counts[
        "family_sample_met"
        if metric.family_signal.min_sample_met
        else "family_sample_below_threshold"
    ] += 1
    if not metric.family_signal.min_sample_met:
        result.issue_counts["workload_action_outcome_sample_below_threshold"] += 1
    if metric.applied_count + metric.not_applied_count <= 0:
        result.issue_counts["workload_action_outcome_no_apply_decision"] += 1


def audit_action_hint(
    result: WorkloadDiagnosticsAuditResult,
    hint: Any,
    *,
    audit_action_outcome_feedback: bool,
) -> None:
    missing_fields = [
        field
        for field in (
            "where_to_look",
            "change_direction",
            "verification_metric",
            "verification",
        )
        if not str(getattr(hint, field, "") or "").strip()
    ]
    if missing_fields:
        result.issue_counts["workload_action_hint_incomplete"] += 1
    combined = " ".join(
        str(getattr(hint, field, "") or "")
        for field in ("change_direction", "verification_metric", "verification")
    )
    if not has_comparable_verification(combined):
        result.issue_counts["workload_action_hint_without_comparable_verification"] += 1
    if audit_action_outcome_feedback:
        result.detail_action_hint_outcome_counts[
            outcome_summary_bucket(getattr(hint, "outcome_summary", ""))
        ] += 1


def audit_action_queue_entry(
    result: WorkloadDiagnosticsAuditResult,
    entry: Any,
    *,
    audit_action_outcome_feedback: bool,
) -> None:
    result.action_queue_signal_counts[safe_signal(getattr(entry, "signal", ""))] += 1
    combined = " ".join(
        str(getattr(entry, field, "") or "")
        for field in ("next_step", "review_anchor", "verification_metric", "verification")
    )
    has_verification = has_comparable_verification(combined)
    result.action_queue_verification_counts[
        "comparable_or_rerun" if has_verification else "missing_comparable"
    ] += 1
    if not has_verification:
        result.issue_counts["workload_action_queue_without_comparable_verification"] += 1
    if audit_action_outcome_feedback:
        result.action_queue_outcome_counts[
            outcome_summary_bucket(getattr(entry, "outcome_summary", ""))
        ] += 1


def add_readiness_issues(result: WorkloadDiagnosticsAuditResult) -> None:
    if result.workload_group_count <= 0:
        return
    if result.workload_history_counts.get("missing", 0):
        add_issue(
            result,
            "workload_history_missing",
            "strict workload calibration requires workload history status in the summary",
        )
    for category in (
        "workload_group_row_gap",
        "regression_without_baseline",
        "workload_detail_missing",
        "workload_representatives_missing",
        "workload_action_hint_incomplete",
        "workload_action_hint_without_comparable_verification",
        "workload_action_queue_without_comparable_verification",
    ):
        count = result.issue_counts.get(category, 0)
        if count:
            add_issue(result, category, f"{category} observed in {count} workload group(s)")


def add_action_outcome_readiness_issues(result: WorkloadDiagnosticsAuditResult) -> None:
    if result.workload_group_count <= 0:
        return
    if result.action_outcome_source_counts.get("not_supplied", 0):
        add_issue(
            result,
            "action_outcomes_not_supplied",
            "strict action outcome calibration requires an explicit local action-outcomes JSONL input",
        )
    for category in (
        "action_outcomes_empty",
        "action_outcomes_raw_like",
        "workload_action_outcome_feedback_missing",
        "workload_action_outcome_sample_below_threshold",
        "workload_action_outcome_no_apply_decision",
    ):
        count = result.issue_counts.get(category, 0)
        if count:
            add_issue(result, category, f"{category} observed in {count} workload group(s)")


def add_issue(result: WorkloadDiagnosticsAuditResult, category: str, message: str) -> None:
    result.issues.append(WorkloadAuditIssue(category, message))


def has_comparable_verification(value: str) -> bool:
    text = value.strip().lower()
    has_comparison = any(term in text for term in COMPARABLE_COMPARISON_TERMS)
    has_rerun_context = any(term in text for term in COMPARABLE_RERUN_TERMS)
    return has_comparison and has_rerun_context


def outcome_summary_bucket(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text or text == "none":
        return "missing"
    if "feedback sample threshold met" in text:
        return "sample_met"
    if "feedback sample below threshold" in text:
        return "sample_below_threshold"
    return "recorded"


def classify_limitation(value: object) -> str:
    text = str(value or "").strip().lower()
    if "baseline" in text:
        return "baseline_missing"
    if "failed" in text or "collection" in text or "analysis" in text:
        return "status_incomplete"
    if "dominant primary" in text:
        return "primary_unknown"
    if "selected analyzed cases" in text:
        return "selected_cases_only"
    if "members are not available" in text:
        return "member_rows_missing"
    return "other"


def safe_signal(value: object) -> str:
    return safe_token(value, default="unknown_signal")


def safe_regression(value: object) -> str:
    token = safe_token(value)
    return token if token in REGRESSION_LABELS else "unknown"


def safe_token(value: object, *, default: str = "unknown") -> str:
    text = str(value or "").strip().lower()
    text = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in text)
    text = "_".join(part for part in text.split("_") if part)
    return text[:60] if text else default


def int_value(value: object) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(float(str(value).strip())))
    except (TypeError, ValueError):
        return 0


def count_bucket(count: int) -> str:
    if count <= 0:
        return "0"
    if count == 1:
        return "1"
    if count <= 3:
        return "2_3"
    if count <= 5:
        return "4_5"
    return "6_plus"


def print_counter(title: str, counter: Counter[str], *, out: TextIO, limit: int) -> None:
    print(f"{title}:", file=out)
    if not counter:
        print("  <none>", file=out)
        return
    for key, count in counter.most_common(limit):
        print(f"  {key}: {count}", file=out)


def print_result(
    result: WorkloadDiagnosticsAuditResult,
    *,
    out: TextIO = sys.stdout,
    limit: int = 12,
) -> None:
    print(f"Summary: {result.summary_name}", file=out)
    print(
        "Cases: "
        f"total={result.total_cases}, rows={result.row_count}, "
        f"workload_groups={result.workload_group_count}, "
        f"details={result.workload_detail_count}, "
        f"action_queue={result.action_queue_count}",
        file=out,
    )
    print_counter("Workload history", result.workload_history_counts, out=out, limit=limit)
    print_counter("Group regressions", result.group_regression_counts, out=out, limit=limit)
    print_counter("Group baselines", result.group_baseline_counts, out=out, limit=limit)
    print_counter("Group member counts", result.group_member_count_buckets, out=out, limit=limit)
    print_counter(
        "Detail representatives", result.detail_representative_counts, out=out, limit=limit
    )
    print_counter("Detail action hints", result.detail_action_hint_counts, out=out, limit=limit)
    print_counter("Detail limitations", result.detail_limitation_counts, out=out, limit=limit)
    print_counter("Action queue signals", result.action_queue_signal_counts, out=out, limit=limit)
    print_counter(
        "Action queue verification",
        result.action_queue_verification_counts,
        out=out,
        limit=limit,
    )
    if has_action_outcome_counters(result):
        print_counter(
            "Action outcome source",
            result.action_outcome_source_counts,
            out=out,
            limit=limit,
        )
        print_counter(
            "Action outcome group coverage",
            result.action_outcome_group_coverage_counts,
            out=out,
            limit=limit,
        )
        print_counter(
            "Action outcome family signals",
            result.action_outcome_family_counts,
            out=out,
            limit=limit,
        )
        print_counter(
            "Action queue outcomes",
            result.action_queue_outcome_counts,
            out=out,
            limit=limit,
        )
        print_counter(
            "Detail action hint outcomes",
            result.detail_action_hint_outcome_counts,
            out=out,
            limit=limit,
        )
    print_counter("Readiness gap counters", result.issue_counts, out=out, limit=limit)
    print("Issues:", file=out)
    if not result.issues:
        print("  none", file=out)
        return
    for issue in result.issues[:limit]:
        print(f"  {issue.category}: {issue.message}", file=out)


def has_action_outcome_counters(result: WorkloadDiagnosticsAuditResult) -> bool:
    return any(
        (
            result.action_outcome_source_counts,
            result.action_outcome_group_coverage_counts,
            result.action_outcome_family_counts,
            result.action_queue_outcome_counts,
            result.detail_action_hint_outcome_counts,
        )
    )


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary", type=Path, help="Path to batch_summary.json")
    parser.add_argument("--limit", type=int, default=12, help="Rows to print per section")
    parser.add_argument(
        "--fail-on-workload-readiness-gaps",
        action="store_true",
        help=(
            "Return non-zero when repeated workload diagnostics lack history, detail rows, "
            "representatives, baselines for regressions, or compare-plus-rerun/scan "
            "verification guidance."
        ),
    )
    parser.add_argument(
        "--action-outcomes",
        type=Path,
        help="Optional local action_outcomes.jsonl used only for aggregate workload outcome calibration.",
    )
    parser.add_argument(
        "--fail-on-action-outcome-readiness-gaps",
        action="store_true",
        help=(
            "Return non-zero when repeated workload action queues/details lack explicit "
            "local action-outcome feedback or enough applied feedback samples for outcome calibration."
        ),
    )
    parser.add_argument(
        "--action-outcome-min-applied",
        type=int,
        default=DEFAULT_METRIC_MIN_APPLIED,
        help="Applied-record sample threshold for action outcome summaries.",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = audit_summary(
            args.summary,
            fail_on_workload_readiness_gaps=args.fail_on_workload_readiness_gaps,
            action_outcomes_path=args.action_outcomes,
            fail_on_action_outcome_readiness_gaps=args.fail_on_action_outcome_readiness_gaps,
            action_outcome_min_applied=args.action_outcome_min_applied,
        )
    except WorkloadAuditInputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print_result(result, limit=args.limit)
    return 1 if not result.ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
