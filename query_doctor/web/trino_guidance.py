"""Validated raw-free Trino optimizer guidance rendering."""

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
from query_doctor.web.trino_case_artifacts import (
    TRINO_WEB_OPTIMIZER_BEHAVIOR_STATUS,
    TRINO_WEB_OPTIMIZER_GUIDANCE_STATUS,
)
from query_doctor.web.trino_details import WebTrinoDetailsView, load_trino_details_view
from query_doctor.web.ui.errors import render_error_panel
from query_doctor.web.ui.markdown import render_report_markdown_html
from query_doctor.web.ui.pages import render_page


TRINO_OPTIMIZER_GUIDANCE_DOWNLOAD_FILENAME = "query-doctor-trino-optimizer-guidance.md"
TRINO_GUIDANCE_MAX_CHARS = 64 * 1024
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
GENERATED_QUERY_RE = re.compile(
    r"```|~~~|\b(?:generated "
    r"SQL|SQL draft|candidate "
    r"SQL|optimized "
    r"SQL|rewrite "
    r"SQL|query rewrite|execute this "
    r"SQL|executable query)\b",
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
class TrinoOptimizerGuidanceArtifact:
    text: str
    download_filename: str = TRINO_OPTIMIZER_GUIDANCE_DOWNLOAD_FILENAME


def load_trino_optimizer_guidance(
    settings: WebSettings,
    case_id: str,
) -> TrinoOptimizerGuidanceArtifact:
    view = load_trino_details_view(settings, case_id)
    _validate_optimizer_guidance_wiring(view)
    guidance_text = build_trino_optimizer_guidance_text(view)
    errors = validate_trino_optimizer_guidance_text(guidance_text)
    if errors:
        raise WebError(
            "Trino optimizer guidance failed deterministic validation.",
            title="Trino optimizer guidance unavailable",
            reason_code="trino.optimizer_guidance_validation_failed",
            stage="Validating Trino optimizer guidance",
            next_step="Rerun the Trino diagnosis and open guidance from the new Details page.",
        )
    return TrinoOptimizerGuidanceArtifact(text=guidance_text)


def render_trino_optimizer_guidance_for_request(
    settings: WebSettings,
    case_id: str,
) -> tuple[int, str]:
    try:
        guidance = load_trino_optimizer_guidance(settings, case_id)
    except WebError as exc:
        status = 404 if exc.reason_code == "trino.details_not_found" else 400
        return status, render_trino_optimizer_guidance_error_page(settings, exc)
    return 200, render_trino_optimizer_guidance_page(settings, guidance)


def render_trino_optimizer_guidance_page(
    settings: WebSettings,
    guidance: TrinoOptimizerGuidanceArtifact,
) -> str:
    guidance_html = render_report_markdown_html(guidance.text, with_heading_ids=True)
    section = (
        '<section class="panel batch-panel trino-optimizer-guidance" '
        'aria-label="Trino optimizer guidance">'
        '<div class="batch-head"><div><h1>Trino optimizer guidance</h1>'
        "<p>Deterministic raw-free review guidance for a materialized Trino Details case. "
        "No Query Optimizer job, LLM report, candidate query text, metadata collection, "
        "or SQL execution is used.</p></div>"
        '<div class="case-actions">'
        '<a class="secondary-action" href="?">Back to Details</a>'
        '<a class="secondary-action" href="?guidance=optimizer&amp;download=1" '
        f'download="{html.escape(guidance.download_filename, quote=True)}">Download Markdown</a>'
        "</div></div>"
        f'<div class="report-body">{guidance_html}</div>'
        "</section>"
    )
    return render_page(
        settings,
        active_nav="batch",
        show_run_panel=False,
        extra_sections=[section],
    )


def render_trino_optimizer_guidance_error_page(settings: WebSettings, error: object) -> str:
    return render_page(
        settings,
        active_nav="batch",
        show_run_panel=False,
        extra_sections=[
            render_error_panel(
                error,
                default_title="Trino optimizer guidance unavailable",
                footer="Guidance validation hides raw Trino payloads, identifiers, paths, and credentials.",
            )
        ],
    )


def build_trino_optimizer_guidance_text(view: WebTrinoDetailsView) -> str:
    analysis = _mapping(view.analysis)
    metadata_summary = _mapping(view.metadata_summary)
    status = _mapping(analysis.get("status"))
    attention_areas = _mapping_items(analysis.get("attention_areas"))
    supported_attention = [
        area for area in attention_areas if _safe_token(area.get("state")) == "supported"
    ]

    lines = [
        "# Trino Optimizer Guidance",
        "",
        "## Scope",
        "- Deterministic guidance over materialized safe facts only.",
        "- No Query Optimizer job, LLM report, candidate query text, metadata collection, or SQL execution is used.",
        "- Root cause not claimed.",
        "- Query reference, coordinator locations, local paths, credentials, metadata identifiers, and query text are not included.",
        "",
        "## Safe Context",
        f"- Workflow: {_label_from_id(analysis.get('workflow'), fallback='Unknown')}",
        f"- Lifecycle: {_label_from_id(status.get('lifecycle'), fallback='Unknown')}",
        f"- Parser coverage: {_label_from_id(status.get('parser_coverage'), fallback='Unknown')}",
        f"- Evidence readiness: {_label_from_id(status.get('evidence_readiness'), fallback='Unknown')}",
        f"- Verification scope: {_label_from_id(status.get('verification_scope'), fallback='Unknown')}",
        f"- Supported attention areas: {len(supported_attention)}",
        f"- Metadata collection: {_label_from_id(metadata_summary.get('collection'), fallback='Unknown')}",
        "",
        "## Review Tracks",
    ]

    review_areas = supported_attention or attention_areas
    if review_areas:
        for area in review_areas[:8]:
            lines.extend(_guidance_attention_area_lines(area))
    else:
        lines.append("- No supported Trino attention area was available in the materialized facts.")

    lines.extend(
        [
            "",
            "## Verification",
            "- Change one variable at a time through approved Trino workflows outside Query Doctor.",
            "- Compare only aggregate timing, memory, spill, queue, blocked, retry, or failure signals already materialized as safe facts.",
            "- Use one comparable rerun or the same retained workload window before judging impact.",
            "",
            "## Guardrails",
            "- Treat this guidance as investigation direction, not a proven cause.",
            "- Query Doctor does not produce candidate query text for this Trino case.",
            "- Query Doctor does not perform Trino SQL execution for this guidance.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def validate_trino_optimizer_guidance_text(text: str) -> list[str]:
    errors: list[str] = []
    if not text or len(text) > TRINO_GUIDANCE_MAX_CHARS:
        errors.append("Trino optimizer guidance size is outside the accepted bound")
    errors.extend(validate_report_html_safety(text))
    errors.extend(validate_report_internal_fingerprints(text))
    if contains_raw_sql_like_text(text):
        errors.append("Trino optimizer guidance contains SQL-like text")
    strict_redacted = redact_browser_display_text(
        text,
        redact_field_names=True,
        redact_artifact_markers=True,
        redact_model_names=True,
        redact_sql_snippets=True,
        redact_infrastructure=True,
    )
    if strict_redacted != text:
        errors.append("Trino optimizer guidance contains browser-unsafe text")
    checks = (
        (TRINO_QUERY_ID_RE, "Trino optimizer guidance contains a Query ID"),
        (IMPALA_QUERY_ID_RE, "Trino optimizer guidance contains an Impala Query ID"),
        (URL_RE, "Trino optimizer guidance contains a URL"),
        (LOCAL_PATH_RE, "Trino optimizer guidance contains a local path"),
        (IMPALA_ONLY_RE, "Trino optimizer guidance contains Impala-only wording"),
        (ROOT_CAUSE_OVERCLAIM_RE, "Trino optimizer guidance overclaims a root cause"),
        (GENERATED_QUERY_RE, "Trino optimizer guidance contains generated-query wording"),
        (AUTH_VALUE_RE, "Trino optimizer guidance contains auth material"),
        (CONNECTOR_INTERNAL_RE, "Trino optimizer guidance contains connector internal details"),
    )
    for pattern, message in checks:
        if pattern.search(text):
            errors.append(message)
    return errors


def _validate_optimizer_guidance_wiring(view: WebTrinoDetailsView) -> None:
    analysis = _mapping(view.analysis)
    raw_policy = _mapping(analysis.get("raw_source_policy"))
    if raw_policy.get("optimizer_guidance") != TRINO_WEB_OPTIMIZER_GUIDANCE_STATUS:
        raise WebError(
            "Trino optimizer guidance is not available for this materialized case.",
            title="Trino optimizer guidance unavailable",
            reason_code="trino.optimizer_guidance_not_materialized",
            stage="Checking Trino optimizer guidance case",
            next_step="Rerun the Trino diagnosis and open guidance from the new Details page.",
        )
    if (
        raw_policy.get("optimizer_behavior") != TRINO_WEB_OPTIMIZER_BEHAVIOR_STATUS
        or raw_policy.get("llm_reports") != "not_wired"
        or raw_policy.get("sql_execution") != "not_performed"
    ):
        raise WebError(
            "Trino optimizer guidance rejected the materialized case policy.",
            title="Trino optimizer guidance unavailable",
            reason_code="trino.optimizer_guidance_policy_invalid",
            stage="Checking Trino optimizer guidance case",
            next_step="Rerun the Trino diagnosis and open guidance from the new Details page.",
        )


def _guidance_attention_area_lines(area: Mapping[str, Any]) -> list[str]:
    area_label = _label_from_id(area.get("id"), fallback="Trino attention area")
    summary = _safe_guidance_text(area.get("summary")) or "No summary available."
    direction = _safe_guidance_text(area.get("change_direction")) or (
        "Review this supported area through an approved Trino workflow before changing one variable."
    )
    verification = _safe_guidance_text(area.get("verification")) or (
        "Use a comparable safe rerun before judging the change."
    )
    lines = [
        f"- {area_label}: {summary}",
    ]
    observed = _observed_label(area)
    if observed:
        lines.append(f"  - Observed: {observed}")
    lines.extend(
        [
            f"  - Direction: {direction}",
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


def _safe_guidance_text(value: object) -> str:
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
