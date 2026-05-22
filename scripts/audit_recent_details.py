#!/usr/bin/env python3
"""Audit rendered Recent Details pages for an existing batch summary."""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.web.case_detail_state import build_batch_case_detail_render_context
from query_doctor.web.jobs import WebJobStore
from query_doctor.web.models import WebSettings
from query_doctor.web.presenters.recent_scan_action_candidates import (
    present_recent_scan_action_candidates,
)
from query_doctor.web.presenters.recent_scan_score_reasons import (
    present_recent_scan_score_reasons,
)
from query_doctor.web.ui.pages import render_batch_case_detail_view_page


PROBLEM_SEVERITIES = {"failed", "high", "suspicious"}
FAILED_VERDICT_TITLE = "Processing did not finish - diagnosis is not trustworthy yet"
CLEAN_VERDICT_TITLE = "No supported problem signal is classified yet"
DETAILS_TITLE_RE = re.compile(r'<h2 class="case-verdict-title">(.*?)</h2>', re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
LOCAL_PATH_RE = re.compile(r"(?<![A-Za-z0-9_])(?:/Users/|/private/tmp/|/tmp/)")
FORBIDDEN_BROWSER_FRAGMENTS = (
    "case_dir",
    "BEGIN PROFILE",
    "Query Timeline",
    "SHOW CREATE TABLE",
    "raw stdout",
    "raw stderr",
    "CM_PASSWORD",
    "CM_TOKEN",
    "KRB5CCNAME",
    "metadata_coordinator",
    "metadata_auth",
    "metadata_path",
    "profile_digest.md",
    "analysis_facts.md",
    "original_query.sql",
    "batch_summary.json",
    "impala_context.json",
    "qwen",
    "ollama",
)
REPORT_RUN_LABELS = (
    "Generate LLM report",
    "Generate Python report",
    "Generate report + optimizer",
)
OPTIMIZER_RUN_LABELS = (
    "Run Query LLM optimizer",
    "Run Query optimizer",
    "Generate report + optimizer",
)


@dataclass(frozen=True)
class AuditIssue:
    case_id: str
    severity: str
    message: str


@dataclass(frozen=True)
class AuditObservation:
    case_id: str
    severity: str
    message: str


@dataclass
class DetailsAuditResult:
    summary_path: Path
    total_cases: int
    audited_cases: int
    excluded_overlap_count: int = 0
    overlap_count: int = 0
    severity_counts: Counter[str] = field(default_factory=Counter)
    metadata_counts: Counter[str] = field(default_factory=Counter)
    title_counts: Counter[str] = field(default_factory=Counter)
    action_counts: Counter[str] = field(default_factory=Counter)
    optimizer_counts: Counter[str] = field(default_factory=Counter)
    report_counts: Counter[str] = field(default_factory=Counter)
    issues: list[AuditIssue] = field(default_factory=list)
    observations: list[AuditObservation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


class AuditInputError(RuntimeError):
    """Raised when the summary file is not usable for Details audit."""


def load_summary(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AuditInputError(f"cannot read summary: {path}") from exc
    except json.JSONDecodeError as exc:
        raise AuditInputError(f"summary is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise AuditInputError(f"summary root is not an object: {path}")
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise AuditInputError(f"summary does not contain a cases list: {path}")
    return payload


def summary_cases(summary: dict[str, Any]) -> list[dict[str, Any]]:
    return [case for case in summary.get("cases") or [] if isinstance(case, dict)]


def case_id_for(case: dict[str, Any]) -> str | None:
    try:
        index = int(case.get("case_index"))
    except (TypeError, ValueError):
        return None
    if index <= 0:
        return None
    return f"case-{index:03d}"


def query_identity(case: dict[str, Any]) -> str | None:
    value = case.get("query_id")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def baseline_query_ids(paths: Iterable[Path]) -> set[str]:
    identities: set[str] = set()
    for path in paths:
        summary = load_summary(path)
        for case in summary_cases(summary):
            identity = query_identity(case)
            if identity is not None:
                identities.add(identity)
    return identities


def extract_verdict_title(rendered_html: str) -> str:
    match = DETAILS_TITLE_RE.search(rendered_html)
    if not match:
        return ""
    stripped = TAG_RE.sub("", match.group(1))
    return html.unescape(stripped).strip()


def contains_any(rendered_html: str, labels: Iterable[str]) -> bool:
    return any(label in rendered_html for label in labels)


def forbidden_browser_leaks(rendered_html: str) -> tuple[str, ...]:
    leaks: list[str] = []
    if LOCAL_PATH_RE.search(rendered_html):
        leaks.append("local path")
    for fragment in FORBIDDEN_BROWSER_FRAGMENTS:
        if fragment in rendered_html:
            leaks.append(fragment)
    return tuple(leaks)


def render_details_html(
    settings: WebSettings,
    job_store: WebJobStore,
    case_id: str,
    case: dict[str, Any],
) -> tuple[Any, str]:
    context = build_batch_case_detail_render_context(settings, case_id, case, job_store)
    rendered = render_batch_case_detail_view_page(
        settings,
        context.view,
        optimized_query_state=context.optimized_query_state,
        trusted_report_text=context.trusted_report_text,
        trusted_optimized_query=context.trusted_optimized_query,
        trusted_optimizer_recommendations=context.trusted_optimizer_recommendations,
        optimizer_manual_guidance=context.optimizer_manual_guidance,
        optimizer_validation_result=context.optimizer_validation_result,
        workflow_title=context.workflow_title,
        list_href=context.list_href,
        detail_base_path=context.detail_base_path,
        active_nav=context.active_nav,
    )
    return context, rendered


def audit_summary(
    summary_path: Path,
    *,
    baseline_paths: Iterable[Path] = (),
    exclude_baseline_overlap: bool = False,
    fail_on_overlap: bool = False,
) -> DetailsAuditResult:
    summary_path = summary_path.resolve(strict=True)
    summary = load_summary(summary_path)
    cases = summary_cases(summary)
    baseline_ids = baseline_query_ids(path.resolve(strict=True) for path in baseline_paths)
    settings = WebSettings(config=Path("/dev/null"), batch_summary=summary_path)
    job_store = WebJobStore()
    result = DetailsAuditResult(summary_path=summary_path, total_cases=len(cases), audited_cases=0)

    for case in cases:
        case_id = case_id_for(case)
        severity = str(case.get("score_severity") or "").strip().lower() or "unknown"
        identity = query_identity(case)
        if identity is not None and identity in baseline_ids:
            result.overlap_count += 1
            if exclude_baseline_overlap:
                result.excluded_overlap_count += 1
                continue
        if case_id is None:
            result.issues.append(AuditIssue("case-unknown", severity, "case_index is missing"))
            continue
        audit_case(result, settings, job_store, case_id, case, severity)

    if fail_on_overlap and result.overlap_count:
        result.issues.append(
            AuditIssue(
                "summary",
                "n/a",
                f"baseline overlap is non-zero ({result.overlap_count} cases)",
            )
        )
    return result


def audit_case(
    result: DetailsAuditResult,
    settings: WebSettings,
    job_store: WebJobStore,
    case_id: str,
    case: dict[str, Any],
    severity: str,
) -> None:
    result.audited_cases += 1
    result.severity_counts[severity] += 1
    result.metadata_counts[str(case.get("metadata_status") or "unknown").strip().lower()] += 1
    try:
        context, rendered = render_details_html(settings, job_store, case_id, case)
    except Exception as exc:  # pragma: no cover - includes unexpected renderer regressions.
        result.issues.append(
            AuditIssue(case_id, severity, f"Details rendering failed: {type(exc).__name__}")
        )
        return

    view = context.view
    score_reasons = present_recent_scan_score_reasons(view)
    action_cards = present_recent_scan_action_candidates(view).cards
    optimizer_status = str(context.optimized_query_state.get("status") or "unknown")
    report_status = str(view.report_action.status or "unknown")
    title = extract_verdict_title(rendered)

    result.title_counts[title or "<missing>"] += 1
    result.optimizer_counts[f"{severity}:{optimizer_status}"] += 1
    result.report_counts[f"{severity}:{report_status}"] += 1
    if action_cards:
        for card in action_cards:
            result.action_counts[f"{severity}:{card.title}"] += 1
    else:
        result.action_counts[f"{severity}:<none>"] += 1

    for leak in forbidden_browser_leaks(rendered):
        result.issues.append(
            AuditIssue(case_id, severity, f"forbidden browser text leaked: {leak}")
        )

    if severity in PROBLEM_SEVERITIES:
        audit_problem_case(result, case_id, severity, action_cards, score_reasons)
    if severity == "failed":
        audit_failed_case(
            result,
            case_id,
            severity,
            title,
            rendered,
            report_status,
            optimizer_status,
        )
    elif severity == "clean":
        audit_clean_case(result, case_id, severity, title, rendered, action_cards)
    elif severity in {"high", "suspicious"}:
        audit_actionable_case(result, case_id, severity, optimizer_status)


def audit_problem_case(
    result: DetailsAuditResult,
    case_id: str,
    severity: str,
    action_cards: tuple[Any, ...],
    score_reasons: Any,
) -> None:
    if not action_cards:
        result.issues.append(AuditIssue(case_id, severity, "problem case has no action card"))
    if not getattr(score_reasons, "reasons", ()):
        result.issues.append(AuditIssue(case_id, severity, "problem case has no score reasons"))
    for card in action_cards:
        if not str(getattr(card, "why", "")).strip():
            result.issues.append(AuditIssue(case_id, severity, f"{card.title} has no why text"))
        if not str(getattr(card, "change_direction", "")).strip():
            result.issues.append(
                AuditIssue(case_id, severity, f"{card.title} has no change direction")
            )
        if not str(getattr(card, "verification", "")).strip():
            result.issues.append(AuditIssue(case_id, severity, f"{card.title} has no verification"))
        has_anchor = bool(getattr(card, "source_locators", ())) or bool(
            getattr(card, "supporting_facts", ())
        )
        if not has_anchor:
            result.issues.append(
                AuditIssue(case_id, severity, f"{card.title} has no evidence anchor")
            )
        if severity in {"high", "suspicious"} and not getattr(card, "source_locators", ()):
            result.observations.append(
                AuditObservation(case_id, severity, f"{card.title} uses fact-only evidence anchor")
            )


def audit_failed_case(
    result: DetailsAuditResult,
    case_id: str,
    severity: str,
    title: str,
    rendered: str,
    report_status: str,
    optimizer_status: str,
) -> None:
    if title != FAILED_VERDICT_TITLE:
        result.issues.append(
            AuditIssue(case_id, severity, f"failed verdict title is {title or '<missing>'!r}")
        )
    if report_status not in {
        "unavailable",
        "generated",
        "partial_untrusted",
        "failed",
        "cancelled",
    }:
        result.issues.append(
            AuditIssue(case_id, severity, f"failed report status is {report_status!r}")
        )
    if optimizer_status not in {
        "unavailable",
        "generated",
        "partial_untrusted",
        "failed",
        "cancelled",
    }:
        result.issues.append(
            AuditIssue(case_id, severity, f"failed optimizer status is {optimizer_status!r}")
        )
    if contains_any(rendered, REPORT_RUN_LABELS):
        result.issues.append(AuditIssue(case_id, severity, "failed case offers report run action"))
    if contains_any(rendered, OPTIMIZER_RUN_LABELS):
        result.issues.append(
            AuditIssue(case_id, severity, "failed case offers optimizer run action")
        )


def audit_clean_case(
    result: DetailsAuditResult,
    case_id: str,
    severity: str,
    title: str,
    rendered: str,
    action_cards: tuple[Any, ...],
) -> None:
    if action_cards:
        result.issues.append(AuditIssue(case_id, severity, "clean case has action cards"))
    if title != CLEAN_VERDICT_TITLE:
        result.issues.append(
            AuditIssue(case_id, severity, f"clean verdict title is {title or '<missing>'!r}")
        )
    if contains_any(rendered, REPORT_RUN_LABELS):
        result.issues.append(AuditIssue(case_id, severity, "clean case offers report run action"))
    if "Query LLM optimizer" in rendered or "Query optimizer" in rendered:
        result.issues.append(AuditIssue(case_id, severity, "clean case exposes optimizer UI"))


def audit_actionable_case(
    result: DetailsAuditResult,
    case_id: str,
    severity: str,
    optimizer_status: str,
) -> None:
    if optimizer_status == "unavailable":
        result.observations.append(
            AuditObservation(case_id, severity, "optimizer is unavailable for actionable case")
        )


def print_counter(title: str, counter: Counter[str], *, limit: int = 12) -> None:
    print(f"{title}:")
    if not counter:
        print("  <none>")
        return
    for key, count in counter.most_common(limit):
        print(f"  {key}: {count}")
    remaining = len(counter) - limit
    if remaining > 0:
        print(f"  ... {remaining} more")


def print_result(result: DetailsAuditResult, *, observation_limit: int = 20) -> None:
    print(f"Summary: {result.summary_path}")
    print(f"Cases: total={result.total_cases}, audited={result.audited_cases}")
    if result.overlap_count:
        print(
            "Baseline overlap: "
            f"{result.overlap_count} cases"
            f", excluded={result.excluded_overlap_count}"
        )
    print_counter("Severity", result.severity_counts)
    print_counter("Metadata", result.metadata_counts)
    print_counter("Verdict titles", result.title_counts)
    print_counter("Action cards", result.action_counts)
    print_counter("Optimizer statuses", result.optimizer_counts)
    print_counter("Report statuses", result.report_counts)
    if result.observations:
        print("Observations:")
        for observation in result.observations[:observation_limit]:
            print(f"  {observation.case_id} [{observation.severity}]: {observation.message}")
        if len(result.observations) > observation_limit:
            print(f"  ... {len(result.observations) - observation_limit} more")
    if result.issues:
        print("Issues:")
        for issue in result.issues:
            print(f"  {issue.case_id} [{issue.severity}]: {issue.message}")
    else:
        print("Issues: none")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Render Details for cases in batch_summary.json and fail on missing "
            "problem explanations, unsafe browser text, or invalid action gating."
        )
    )
    parser.add_argument("summary", type=Path, help="Path to batch_summary.json")
    parser.add_argument(
        "--baseline-summary",
        action="append",
        default=[],
        type=Path,
        help="Prior batch_summary.json used only to count or exclude query-id overlap.",
    )
    parser.add_argument(
        "--exclude-baseline-overlap",
        action="store_true",
        help="Skip cases whose query id exists in any baseline summary.",
    )
    parser.add_argument(
        "--fail-on-overlap",
        action="store_true",
        help="Fail if any current case overlaps a baseline summary.",
    )
    parser.add_argument(
        "--observation-limit",
        default=20,
        type=int,
        help="Maximum non-failing observations to print.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        result = audit_summary(
            args.summary,
            baseline_paths=args.baseline_summary,
            exclude_baseline_overlap=args.exclude_baseline_overlap,
            fail_on_overlap=args.fail_on_overlap,
        )
    except AuditInputError as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2
    print_result(result, observation_limit=max(0, args.observation_limit))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
