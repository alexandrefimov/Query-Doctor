"""Raw-free Trino Details loading for materialized local web cases."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from query_doctor.report.safety_validation import (
    contains_raw_sql_like_text,
    validate_report_internal_fingerprints,
)
from query_doctor.safety.browser_display import redact_browser_display_text
from query_doctor.web.models import WebError, WebSettings
from query_doctor.web.trino_case_artifacts import (
    TRINO_WEB_CASE_ANALYSIS_SCHEMA_VERSION,
    TRINO_WEB_CASE_ID_RE,
    TRINO_WEB_METADATA_SUMMARY_SCHEMA_VERSION,
    TRINO_WEB_OPTIMIZER_BEHAVIOR_STATUS,
    TRINO_WEB_OPTIMIZER_GUIDANCE_STATUS,
    TRINO_WEB_PYTHON_REPORT_STATUS,
    TRINO_WEB_TRUSTED_REPORTS_STATUS,
    trino_web_case_root,
)
from query_doctor.web.ui.trino import render_trino_details_error_page, render_trino_details_page


TRINO_COMPACT_DIAGNOSIS_SCHEMA_VERSION = "trino_compact_diagnosis_v1"
TRINO_DETAILS_JSON_MAX_BYTES = 512 * 1024


@dataclass(frozen=True)
class WebTrinoDetailsView:
    analysis: Mapping[str, Any]
    diagnosis: Mapping[str, Any]
    metadata_summary: Mapping[str, Any]


def render_trino_detail_for_request(
    settings: WebSettings,
    case_id: str,
) -> tuple[int, str]:
    try:
        view = load_trino_details_view(settings, case_id)
    except WebError as exc:
        status = 404 if exc.reason_code == "trino.details_not_found" else 400
        return status, render_trino_details_error_page(settings, exc)
    return 200, render_trino_details_page(settings, view)


def load_trino_details_view(settings: WebSettings, case_id: str) -> WebTrinoDetailsView:
    case_dir = trino_details_case_dir(settings, case_id)
    analysis = _read_json_artifact(case_dir / "analysis.json", label="analysis")
    diagnosis = _read_json_artifact(case_dir / "compact_diagnosis.json", label="diagnosis")
    metadata_summary = _read_json_artifact(
        case_dir / "metadata_summary.json",
        label="metadata summary",
    )
    _validate_analysis(analysis)
    _validate_diagnosis(diagnosis)
    _validate_metadata_summary(metadata_summary)
    return WebTrinoDetailsView(
        analysis=analysis,
        diagnosis=diagnosis,
        metadata_summary=metadata_summary,
    )


def trino_details_case_dir(settings: WebSettings, case_id: str) -> Path:
    if TRINO_WEB_CASE_ID_RE.fullmatch(str(case_id or "")) is None:
        raise WebError(
            "Trino Details case reference was rejected.",
            title="Trino Details unavailable",
            reason_code="trino.details_case_id_invalid",
            stage="Checking Trino Details case",
            next_step="Open Details from a materialized Trino result row.",
        )
    root = trino_web_case_root(settings).resolve(strict=False)
    case_dir = (root / case_id).resolve(strict=False)
    try:
        case_dir.relative_to(root)
    except ValueError as exc:
        raise WebError(
            "Trino Details case reference was rejected.",
            title="Trino Details unavailable",
            reason_code="trino.details_case_id_invalid",
            stage="Checking Trino Details case",
            next_step="Open Details from a materialized Trino result row.",
        ) from exc
    if not case_dir.is_dir():
        raise WebError(
            "Trino Details case was not found.",
            title="Trino Details unavailable",
            reason_code="trino.details_not_found",
            stage="Loading Trino Details case",
            next_step="Rerun the Trino diagnosis and open Details from the new result row.",
        )
    return case_dir


def _read_json_artifact(path: Path, *, label: str) -> Mapping[str, Any]:
    try:
        size = path.stat().st_size
        if size > TRINO_DETAILS_JSON_MAX_BYTES:
            raise OSError("artifact too large")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WebError(
            "Trino Details could not load the materialized case artifacts.",
            title="Trino Details unavailable",
            reason_code="trino.details_artifact_unavailable",
            stage="Loading Trino Details case",
            next_step="Rerun the Trino diagnosis and open Details from the new result row.",
        ) from exc
    if not isinstance(payload, Mapping):
        raise WebError(
            "Trino Details rejected the materialized case artifacts.",
            title="Trino Details unavailable",
            reason_code="trino.details_artifact_invalid",
            stage="Checking Trino Details case",
            next_step="Rerun the Trino diagnosis and open Details from the new result row.",
        )
    _validate_browser_safe_payload(payload, label=label)
    return payload


def _validate_analysis(payload: Mapping[str, Any]) -> None:
    if (
        payload.get("schema_version") != TRINO_WEB_CASE_ANALYSIS_SCHEMA_VERSION
        or payload.get("engine") != "trino"
    ):
        raise _invalid_artifact_error()
    query_reference = payload.get("query_reference")
    if not isinstance(query_reference, Mapping) or query_reference.get("value") != "hidden":
        raise _invalid_artifact_error()
    raw_policy = payload.get("raw_source_policy")
    if not isinstance(raw_policy, Mapping):
        raise _invalid_artifact_error()
    required = {
        "raw_query_info_storage": "forbidden",
        "raw_query_list_storage": "forbidden",
        "raw_sql_storage": "forbidden",
        "sql_execution": "not_performed",
    }
    if any(raw_policy.get(key) != expected for key, expected in required.items()):
        raise _invalid_artifact_error()
    optimizer_behavior = raw_policy.get("optimizer_behavior")
    if optimizer_behavior not in {"not_wired", TRINO_WEB_OPTIMIZER_BEHAVIOR_STATUS}:
        raise _invalid_artifact_error()
    trusted_reports = raw_policy.get("trusted_reports")
    if trusted_reports not in {"not_wired", TRINO_WEB_TRUSTED_REPORTS_STATUS}:
        raise _invalid_artifact_error()
    if (
        "python_report" in raw_policy
        and raw_policy.get("python_report") != TRINO_WEB_PYTHON_REPORT_STATUS
    ):
        raise _invalid_artifact_error()
    if (
        "optimizer_guidance" in raw_policy
        and raw_policy.get("optimizer_guidance") != TRINO_WEB_OPTIMIZER_GUIDANCE_STATUS
    ):
        raise _invalid_artifact_error()
    if "llm_reports" in raw_policy and raw_policy.get("llm_reports") != "not_wired":
        raise _invalid_artifact_error()


def _validate_diagnosis(payload: Mapping[str, Any]) -> None:
    if (
        payload.get("schema_version") != TRINO_COMPACT_DIAGNOSIS_SCHEMA_VERSION
        or payload.get("engine") != "trino"
    ):
        raise _invalid_artifact_error()
    boundary = payload.get("diagnosis_boundary")
    if not isinstance(boundary, Mapping):
        raise _invalid_artifact_error()
    if boundary.get("root_cause") != "not_claimed":
        raise _invalid_artifact_error()
    if boundary.get("optimizer_behavior") != "not_wired":
        raise _invalid_artifact_error()
    if boundary.get("trino_sql_execution") != "not_performed":
        raise _invalid_artifact_error()


def _validate_metadata_summary(payload: Mapping[str, Any]) -> None:
    if (
        payload.get("schema_version") != TRINO_WEB_METADATA_SUMMARY_SCHEMA_VERSION
        or payload.get("collection") != "not_collected"
    ):
        raise _invalid_artifact_error()
    if payload.get("relation_identifiers") != "hidden":
        raise _invalid_artifact_error()
    if payload.get("metadata_values") != "hidden":
        raise _invalid_artifact_error()


def _validate_browser_safe_payload(payload: Mapping[str, Any], *, label: str) -> None:
    text = json.dumps(payload, ensure_ascii=True, sort_keys=True)
    unsafe = (
        contains_raw_sql_like_text(text)
        or bool(validate_report_internal_fingerprints(text))
        or redact_browser_display_text(
            text,
            redact_field_names=True,
            redact_artifact_markers=True,
            redact_model_names=True,
            redact_sql_snippets=True,
            redact_infrastructure=True,
        )
        != text
    )
    if unsafe:
        raise WebError(
            "Trino Details rejected the materialized case artifacts.",
            title="Trino Details unavailable",
            reason_code=f"trino.details_{label.replace(' ', '_')}_unsafe",
            stage="Checking Trino Details case",
            next_step="Rerun the Trino diagnosis and open Details from the new result row.",
        )


def _invalid_artifact_error() -> WebError:
    return WebError(
        "Trino Details rejected the materialized case artifacts.",
        title="Trino Details unavailable",
        reason_code="trino.details_artifact_invalid",
        stage="Checking Trino Details case",
        next_step="Rerun the Trino diagnosis and open Details from the new result row.",
    )
