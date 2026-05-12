"""Small HTML rendering primitives for Query Doctor web UI."""

from __future__ import annotations

import html
from typing import Any

from query_doctor.web.presenters.recent_scan import numeric_value


class SafeHtml(str):
    pass


def metadata_rows(fields: list[tuple[str, Any]]) -> str:
    return "".join(
        '<div class="meta-row">'
        f"<span>{html.escape(label)}</span><strong>{value if isinstance(value, SafeHtml) else escape_value(value)}</strong>"
        "</div>"
        for label, value in fields
    )


def compact_cell(value: Any) -> str:
    return f'<td class="batch-cell--compact">{value if isinstance(value, SafeHtml) else escape_value(value)}</td>'


def reason_cell(value: Any) -> str:
    return f'<td class="batch-cell--reason">{escape_value(value)}</td>'


def score_badge(case: dict[str, Any]) -> SafeHtml:
    return score_badge_from_values(
        case.get("score"),
        case.get("collection_status"),
        case.get("analysis_status"),
        severity=case.get("score_severity"),
    )


def score_badge_from_values(
    score_value: Any,
    collection_status: Any,
    analysis_status: Any,
    *,
    severity: str | None = None,
) -> SafeHtml:
    score = numeric_value(score_value)
    severity = (severity or "").strip().lower()
    if severity == "failed" or collection_status == "failed" or analysis_status == "failed":
        label = f"{display_score(score_value)} failed"
        class_name = "batch-severity--failed"
    elif severity == "high" or (not severity and score >= 20):
        label = f"{display_score(score_value)} high"
        class_name = "batch-severity--high"
    elif severity == "suspicious" or (not severity and score > 0):
        label = f"{display_score(score_value)} suspicious"
        class_name = "batch-severity--suspicious"
    else:
        label = f"{display_score(score_value)} clean"
        class_name = "batch-severity--clean"
    return badge_html(label, class_name)


def status_badge(value: Any) -> SafeHtml:
    text = "unknown" if value is None else str(value)
    normalized = text.lower()
    if normalized in {"ok", "collected", "passed"}:
        class_name = "batch-status--ok"
    elif normalized == "failed":
        class_name = "batch-status--failed"
    elif normalized in {"skipped", "not_run", "not_observed", "unknown"}:
        class_name = "batch-status--neutral"
    else:
        class_name = "batch-status--warning"
    return badge_html(text, class_name)


def cm_metric_status_badge(value: Any) -> SafeHtml:
    text = "unknown" if value is None else str(value)
    normalized = text.lower()
    if normalized in {"available", "ok", "correlated"}:
        class_name = "batch-status--ok"
    elif normalized == "observed":
        class_name = "batch-status--warning"
    elif normalized in {"not_observed", "unknown", "unavailable", "context_only"}:
        class_name = "batch-status--neutral"
    else:
        class_name = "batch-status--warning"
    return badge_html(text, class_name)


def report_badge(value: str) -> SafeHtml:
    normalized = value.lower()
    if "partial" in normalized or "untrusted" in normalized:
        class_name = "batch-report--untrusted"
    elif "validated" in normalized or normalized == "passed":
        class_name = "batch-report--passed"
    elif normalized == "not_run":
        class_name = "batch-report--neutral"
    else:
        class_name = "batch-report--generated"
    return badge_html(value, class_name)


def badge_html(label: Any, class_name: str) -> SafeHtml:
    return SafeHtml(f'<span class="batch-mini-badge {class_name}">{escape_value(label)}</span>')


def display_score(value: Any) -> str:
    if value is None:
        return "unknown"
    return str(value)


def escape_value(value: Any) -> str:
    if value is None:
        return "unknown"
    if value is True:
        return "true"
    if value is False:
        return "false"
    return html.escape(str(value))
