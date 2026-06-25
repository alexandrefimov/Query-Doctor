"""Validated raw-free Trino Python report rendering."""

from __future__ import annotations

import html
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from query_doctor.report.safety_validation import (
    contains_raw_sql_like_text,
    validate_report_html_safety,
    validate_report_internal_fingerprints,
)
from query_doctor.safety.browser_display import redact_browser_display_text
from query_doctor.web.models import WebError, WebSettings
from query_doctor.web.trino_case_artifacts import TRINO_WEB_PYTHON_REPORT_STATUS
from query_doctor.web.trino_details import WebTrinoDetailsView, load_trino_details_view
from query_doctor.web.ui.errors import render_error_panel
from query_doctor.web.ui.markdown import render_report_markdown_html
from query_doctor.web.ui.pages import render_page


TRINO_PYTHON_REPORT_DOWNLOAD_FILENAME = "query-doctor-trino-python-report.md"
TRINO_REPORT_MAX_CHARS = 64 * 1024
TRINO_QUERY_ID_RE = re.compile(r"\b\d{8}_\d{6}_\d{5}_[A-Za-z0-9]+\b")
IMPALA_QUERY_ID_RE = re.compile(r"\b[0-9a-f]{16}:[0-9a-f]{16}\b", re.IGNORECASE)
URL_RE = re.compile(r"\b(?:https?|trino)://", re.IGNORECASE)
LOCAL_PATH_RE = re.compile(r"(?<![\w/])(?:/private)?/(?:tmp|Users|var/folders)/[^\s<>'\"]+")
IMPALA_ONLY_RE = re.compile(
    r"\b(?:Impala|impalad|impala-shell|Cloudera Manager|HDFS|admission control|"
    r"fragment|backend)\b",
    re.IGNORECASE,
)
ROOT_CAUSE_OVERCLAIM_RE = re.compile(
    r"\b(?:root cause is|root cause: (?!not claimed)|caused by|due to|primary cause|"
    r"primary bottleneck|bottleneck is|fixes? the issue|will resolve)\b",
    re.IGNORECASE,
)
GENERATED_SQL_RE = re.compile(
    r"```|~~~|\b(?:generated SQL|SQL draft|candidate SQL|optimized SQL|rewrite SQL|"
    r"query rewrite|execute this SQL)\b",
    re.IGNORECASE,
)
AUTH_VALUE_RE = re.compile(
    r"\b(?:Authorization|Bearer|Basic|KRB5CCNAME|keytab|password|secret|token)\b",
    re.IGNORECASE,
)
CONNECTOR_INTERNAL_RE = re.compile(
    r"\b(?:connector internals?|connector plugin|stage-raw-id|task-raw-id|stage id|task id|"
    r"worker-[A-Za-z0-9_.-]+|node id)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TrinoPythonReportArtifact:
    text: str
    download_filename: str = TRINO_PYTHON_REPORT_DOWNLOAD_FILENAME


def load_trino_python_report(settings: WebSettings, case_id: str) -> TrinoPythonReportArtifact:
    view = load_trino_details_view(settings, case_id)
    _validate_python_report_wiring(view)
    report_text = build_trino_python_report_text(view)
    errors = validate_trino_python_report_text(report_text)
    if errors:
        raise WebError(
            "Trino Python Report failed deterministic validation.",
            title="Trino Python Report unavailable",
            reason_code="trino.python_report_validation_failed",
            stage="Validating Trino Python Report",
            next_step="Rerun the Trino diagnosis and open the report from the new Details page.",
        )
    return TrinoPythonReportArtifact(text=report_text)


def render_trino_python_report_for_request(
    settings: WebSettings,
    case_id: str,
) -> tuple[int, str]:
    try:
        report = load_trino_python_report(settings, case_id)
    except WebError as exc:
        status = 404 if exc.reason_code == "trino.details_not_found" else 400
        return status, render_trino_python_report_error_page(settings, exc)
    return 200, render_trino_python_report_page(settings, report)


def render_trino_python_report_page(
    settings: WebSettings,
    report: TrinoPythonReportArtifact,
) -> str:
    report_html = render_report_markdown_html(report.text, with_heading_ids=True)
    section = (
        '<section class="panel batch-panel trino-python-report" '
        'aria-label="Trino Python Report">'
        '<div class="batch-head"><div><h1>Trino Python Report</h1>'
        "<p>Deterministic raw-free report for a materialized Trino Details case. "
        "LLM reports, optimizer actions, candidate query text, metadata collection, "
        "and SQL execution are not used.</p></div>"
        '<div class="case-actions">'
        '<a class="secondary-action" href="?">Back to Details</a>'
        '<a class="secondary-action" href="?report=python&amp;download=1" '
        f'download="{html.escape(report.download_filename, quote=True)}">Download Markdown</a>'
        "</div></div>"
        f'<div class="report-body">{report_html}</div>'
        "</section>"
    )
    return render_page(
        settings,
        active_nav="batch",
        show_run_panel=False,
        extra_sections=[section],
    )


def render_trino_python_report_error_page(settings: WebSettings, error: object) -> str:
    return render_page(
        settings,
        active_nav="batch",
        show_run_panel=False,
        extra_sections=[
            render_error_panel(
                error,
                default_title="Trino Python Report unavailable",
                footer="Report validation hides raw Trino payloads, identifiers, paths, and credentials.",
            )
        ],
    )


def build_trino_python_report_text(view: WebTrinoDetailsView) -> str:
    analysis = _mapping(view.analysis)
    metadata_summary = _mapping(view.metadata_summary)
    status = _mapping(analysis.get("status"))
    attention_areas = _mapping_items(analysis.get("attention_areas"))
    supported_attention = [
        area for area in attention_areas if _safe_token(area.get("state")) == "supported"
    ]

    lines = [
        "# Trino Python Report",
        "",
        "## Summary",
        "- Engine: Trino",
        f"- Workflow: {_label_from_id(analysis.get('workflow'), fallback='Unknown')}",
        f"- Lifecycle: {_label_from_id(status.get('lifecycle'), fallback='Unknown')}",
        f"- Parser coverage: {_label_from_id(status.get('parser_coverage'), fallback='Unknown')}",
        f"- Evidence readiness: {_label_from_id(status.get('evidence_readiness'), fallback='Unknown')}",
        f"- Verification scope: {_label_from_id(status.get('verification_scope'), fallback='Unknown')}",
        "- Root cause not claimed.",
        "- Query reference, coordinator locations, local paths, credentials, metadata identifiers, and query text are not included.",
        "",
        "## Decision Facts",
        f"- Supported attention areas: {len(supported_attention)}",
        f"- Metadata collection: {_label_from_id(metadata_summary.get('collection'), fallback='Unknown')}",
        f"- Metadata stats completeness: {_label_from_id(metadata_summary.get('stats_completeness'), fallback='Unknown')}",
        "- LLM reports, optimizer actions, candidate query text, and SQL execution are not used.",
        "",
        "## Attention Areas",
    ]

    if attention_areas:
        for area in attention_areas[:8]:
            lines.extend(_report_attention_area_lines(area))
    else:
        lines.append("- No supported Trino attention area was available in the materialized facts.")

    lines.extend(
        [
            "",
            "## Verification",
            "- Recheck the same workload window or one comparable rerun before judging any change.",
            "- Compare only aggregate timing, memory, spill, queue, blocked, retry, or failure signals that were already materialized as safe facts.",
            "- Treat every finding as guidance for investigation, not a proven cause.",
            "",
            "## Limitations",
            "- Running scans and query-history crawling are not part of this report.",
            "- Metadata collection is not performed; only aggregate coverage status is shown.",
            "- The report does not produce candidate query text or execute SQL.",
            "- Browser output remains limited to normalized safe facts and compact diagnosis text.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def validate_trino_python_report_text(text: str) -> list[str]:
    errors: list[str] = []
    if not text or len(text) > TRINO_REPORT_MAX_CHARS:
        errors.append("Trino Python Report size is outside the accepted bound")
    errors.extend(validate_report_html_safety(text))
    errors.extend(validate_report_internal_fingerprints(text))
    if contains_raw_sql_like_text(text):
        errors.append("Trino Python Report contains SQL-like text")
    strict_redacted = redact_browser_display_text(
        text,
        redact_field_names=True,
        redact_artifact_markers=True,
        redact_model_names=True,
        redact_sql_snippets=True,
        redact_infrastructure=True,
    )
    if strict_redacted != text:
        errors.append("Trino Python Report contains browser-unsafe text")
    checks = (
        (TRINO_QUERY_ID_RE, "Trino Python Report contains a Query ID"),
        (IMPALA_QUERY_ID_RE, "Trino Python Report contains an Impala Query ID"),
        (URL_RE, "Trino Python Report contains a URL"),
        (LOCAL_PATH_RE, "Trino Python Report contains a local path"),
        (IMPALA_ONLY_RE, "Trino Python Report contains Impala-only wording"),
        (ROOT_CAUSE_OVERCLAIM_RE, "Trino Python Report overclaims a root cause"),
        (GENERATED_SQL_RE, "Trino Python Report contains generated-SQL wording"),
        (AUTH_VALUE_RE, "Trino Python Report contains auth material"),
        (CONNECTOR_INTERNAL_RE, "Trino Python Report contains connector internal details"),
    )
    for pattern, message in checks:
        if pattern.search(text):
            errors.append(message)
    return errors


def _validate_python_report_wiring(view: WebTrinoDetailsView) -> None:
    analysis = _mapping(view.analysis)
    raw_policy = _mapping(analysis.get("raw_source_policy"))
    if raw_policy.get("python_report") != TRINO_WEB_PYTHON_REPORT_STATUS:
        raise WebError(
            "Trino Python Report is not available for this materialized case.",
            title="Trino Python Report unavailable",
            reason_code="trino.python_report_not_materialized",
            stage="Checking Trino Python Report case",
            next_step="Rerun the Trino diagnosis and open the report from the new Details page.",
        )
    if raw_policy.get("llm_reports") != "not_wired":
        raise WebError(
            "Trino Python Report rejected the materialized case policy.",
            title="Trino Python Report unavailable",
            reason_code="trino.python_report_policy_invalid",
            stage="Checking Trino Python Report case",
            next_step="Rerun the Trino diagnosis and open the report from the new Details page.",
        )


def _report_attention_area_lines(area: Mapping[str, Any]) -> list[str]:
    area_label = _label_from_id(area.get("id"), fallback="Trino attention area")
    state = _label_from_id(area.get("state"), fallback="Unknown")
    summary = _safe_report_text(area.get("summary")) or "No summary available."
    verification = _safe_report_text(area.get("verification")) or (
        "Use a comparable safe rerun before judging the change."
    )
    lines = [
        f"- {area_label}: {state}",
        f"  - Finding: {summary}",
    ]
    observed = _observed_label(area)
    if observed:
        lines.append(f"  - Observed: {observed}")
    lines.extend(
        [
            "  - Direction: Review the supported area through an approved Trino workflow before changing one variable.",
            f"  - Verification: {verification}",
        ]
    )
    return lines


def _observed_label(area: Mapping[str, Any]) -> str:
    single = _metric_label(area.get("observed_value"))
    if single:
        return single
    observed_values = _mapping(area.get("observed_values"))
    labels = [_metric_label(value) for value in observed_values.values()]
    return ", ".join(label for label in labels if label)[:240]


def _metric_label(value: object) -> str:
    if not isinstance(value, Mapping):
        return ""
    raw_number = value.get("value")
    if isinstance(raw_number, bool):
        label = "true" if raw_number else "false"
    elif isinstance(raw_number, int) and not isinstance(raw_number, bool):
        label = str(raw_number)
    elif isinstance(raw_number, float):
        label = f"{raw_number:g}"
    else:
        return ""
    unit = _safe_token(value.get("unit"))
    return f"{label} {unit}" if unit else label


def _safe_report_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return redact_browser_display_text(
        value,
        redact_artifact_markers=True,
        redact_field_names=True,
        redact_infrastructure=True,
        redact_model_names=True,
        redact_sql_snippets=True,
        max_chars=400,
    ).strip()


def _label_from_id(value: object, *, fallback: str) -> str:
    token = _safe_token(value)
    if not token:
        return fallback
    words = [word for word in token.replace("-", "_").split("_") if word]
    return " ".join(words).capitalize() if words else fallback


def _safe_token(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return "".join(char for char in value.strip().lower() if char.isalnum() or char in "_-")


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mapping_items(value: object) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))
