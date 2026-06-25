"""Raw-free Trino web case artifact materialization."""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.report.safety_validation import (
    contains_raw_sql_like_text,
    validate_report_internal_fingerprints,
)
from query_doctor.safety.browser_display import redact_browser_display_text
from query_doctor.safety.handoff_artifacts import write_ascii_json_artifact
from query_doctor.web.case_files import resolve_under_repo
from query_doctor.web.models import WebSettings, WebTrinoCaseArtifacts


TRINO_WEB_CASE_ANALYSIS_SCHEMA_VERSION = "trino_web_case_analysis_v1"
TRINO_WEB_METADATA_SUMMARY_SCHEMA_VERSION = "trino_web_metadata_summary_v1"
TRINO_WEB_PYTHON_REPORT_STATUS = "raw_free_materialized"
TRINO_WEB_OPTIMIZER_GUIDANCE_STATUS = "raw_free_materialized"
TRINO_WEB_OPTIMIZER_BEHAVIOR_STATUS = "guidance_only"
TRINO_WEB_TRUSTED_REPORTS_STATUS = "python_report_only"
TRINO_WEB_CASE_ID_RE = re.compile(r"trino-[a-f0-9]{32}")


def materialize_trino_web_case_artifacts(
    *,
    settings: WebSettings,
    boundary: Mapping[str, Any],
    diagnosis: Mapping[str, Any],
    workflow: str,
    support_mode: str,
) -> WebTrinoCaseArtifacts:
    case_id = f"trino-{uuid.uuid4().hex}"
    case_dir = _trino_case_root(settings) / case_id
    artifacts = WebTrinoCaseArtifacts(
        case_id=case_id,
        case_dir=case_dir,
        boundary_path=case_dir / "boundary.json",
        compact_diagnosis_path=case_dir / "compact_diagnosis.json",
        metadata_summary_path=case_dir / "metadata_summary.json",
        analysis_path=case_dir / "analysis.json",
        analysis_facts_path=case_dir / "analysis_facts.md",
    )
    analysis = trino_web_case_analysis_payload(
        case_id=case_id,
        diagnosis=diagnosis,
        workflow=workflow,
        support_mode=support_mode,
    )
    metadata_summary = trino_web_metadata_summary_payload()
    facts_text = trino_web_analysis_facts_text(analysis)

    _validate_artifact_payload("boundary", boundary)
    _validate_artifact_payload("compact diagnosis", diagnosis)
    _validate_artifact_payload("metadata summary", metadata_summary)
    _validate_artifact_payload("analysis", analysis)
    _validate_artifact_text("analysis facts", facts_text)

    write_ascii_json_artifact(artifacts.boundary_path, boundary)
    write_ascii_json_artifact(artifacts.compact_diagnosis_path, diagnosis)
    write_ascii_json_artifact(artifacts.metadata_summary_path, metadata_summary)
    write_ascii_json_artifact(artifacts.analysis_path, analysis)
    artifacts.analysis_facts_path.write_text(facts_text, encoding="utf-8")
    return artifacts


def trino_web_case_analysis_payload(
    *,
    case_id: str,
    diagnosis: Mapping[str, Any],
    workflow: str,
    support_mode: str,
) -> dict[str, Any]:
    diagnostic_lane = _mapping(diagnosis.get("diagnostic_lane"))
    return {
        "schema_version": TRINO_WEB_CASE_ANALYSIS_SCHEMA_VERSION,
        "case_id": case_id,
        "engine": "trino",
        "workflow": _safe_token(workflow, fallback="query_id"),
        "support_mode": _safe_token(support_mode, fallback="beta"),
        "query_reference": {
            "kind": "explicit_query_id",
            "value": "hidden",
        },
        "status": {
            "lifecycle": _safe_token(diagnosis.get("lifecycle"), fallback="unknown"),
            "parser_coverage": _safe_token(
                diagnosis.get("parser_coverage"),
                fallback="unknown",
            ),
            "support_status": _safe_token(
                diagnosis.get("support_status"),
                fallback="unknown",
            ),
            "supported_attention_area_count": _safe_int(
                diagnostic_lane.get("supported_attention_area_count")
            ),
            "source_granularity": _safe_token(
                diagnostic_lane.get("source_granularity"),
                fallback="unknown",
            ),
            "evidence_readiness": _safe_token(
                diagnostic_lane.get("evidence_readiness"),
                fallback="unknown",
            ),
            "verification_scope": _safe_token(
                diagnostic_lane.get("verification_scope"),
                fallback="unknown",
            ),
        },
        "attention_areas": [
            _analysis_attention_area(area)
            for area in _mapping_items(diagnosis.get("attention_areas"))
        ],
        "limitations": [
            _analysis_limitation(limitation)
            for limitation in _mapping_items(diagnosis.get("limitations"))
        ],
        "diagnosis_boundary": _diagnosis_boundary_payload(diagnosis.get("diagnosis_boundary")),
        "metadata_summary": trino_web_metadata_summary_payload(),
        "raw_source_policy": {
            "raw_query_info_storage": "forbidden",
            "raw_query_list_storage": "forbidden",
            "raw_sql_storage": "forbidden",
            "browser_paths": "forbidden",
            "python_report": TRINO_WEB_PYTHON_REPORT_STATUS,
            "optimizer_guidance": TRINO_WEB_OPTIMIZER_GUIDANCE_STATUS,
            "llm_reports": "not_wired",
            "trusted_reports": TRINO_WEB_TRUSTED_REPORTS_STATUS,
            "optimizer_behavior": TRINO_WEB_OPTIMIZER_BEHAVIOR_STATUS,
            "sql_execution": "not_performed",
        },
    }


def trino_web_metadata_summary_payload() -> dict[str, Any]:
    return {
        "schema_version": TRINO_WEB_METADATA_SUMMARY_SCHEMA_VERSION,
        "collection": "not_collected",
        "relation_identifiers": "hidden",
        "metadata_values": "hidden",
        "connector_scope": "not_collected",
        "stats_completeness": "unknown",
        "coverage": {
            "relations_checked": 0,
            "columns_checked": 0,
            "column_stats_present": 0,
            "column_stats_missing": 0,
        },
    }


def trino_web_analysis_facts_text(analysis: Mapping[str, Any]) -> str:
    status = _mapping(analysis.get("status"))
    boundary = _mapping(analysis.get("diagnosis_boundary"))
    attention_ids = [
        _safe_token(area.get("id"), fallback="unknown")
        for area in _mapping_items(analysis.get("attention_areas"))
    ][:8]
    attention = ", ".join(attention_ids) if attention_ids else "none"
    return (
        "# Trino Case Facts\n\n"
        "- Engine: trino\n"
        f"- Workflow: {_safe_token(analysis.get('workflow'), fallback='query_id')}\n"
        "- Query reference: explicit_query_id_hidden\n"
        f"- Lifecycle: {_safe_token(status.get('lifecycle'), fallback='unknown')}\n"
        f"- Parser coverage: {_safe_token(status.get('parser_coverage'), fallback='unknown')}\n"
        "- Root cause: "
        f"{_safe_token(boundary.get('root_cause'), fallback='not_claimed')}\n"
        "- Details LLM report surface: "
        f"{_safe_token(boundary.get('details_trusted_report_surface'), fallback='not_wired')}\n"
        "- Python report: raw_free_materialized\n"
        "- Optimizer guidance: raw_free_materialized\n"
        "- LLM reports: not_wired\n"
        "- Optimizer behavior: "
        f"{TRINO_WEB_OPTIMIZER_BEHAVIOR_STATUS}\n"
        "- Trino SQL execution: "
        f"{_safe_token(boundary.get('trino_sql_execution'), fallback='not_performed')}\n"
        "- Metadata collection: not_collected\n"
        "- Raw SQL: not_stored\n"
        f"- Supported attention area count: {_safe_int(status.get('supported_attention_area_count'))}\n"
        f"- Attention area IDs: {attention}\n"
    )


def _trino_case_root(settings: WebSettings) -> Path:
    return trino_web_case_root(settings)


def trino_web_case_root(settings: WebSettings) -> Path:
    return resolve_under_repo(settings.repo_dir, settings.corpus_dir) / "trino-web-cases"


def safe_trino_case_details_href(case_artifacts: object) -> str:
    case_id = getattr(case_artifacts, "case_id", "")
    if not isinstance(case_id, str) or TRINO_WEB_CASE_ID_RE.fullmatch(case_id) is None:
        return ""
    return f"/trino/details/{case_id}"


def _analysis_attention_area(area: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": _safe_token(area.get("id"), fallback="unknown"),
        "state": _safe_token(area.get("state"), fallback="unknown"),
        "summary": _safe_text(area.get("summary")),
        "change_direction": _safe_text(area.get("change_direction")),
        "verification": _safe_text(area.get("verification")),
        "observed_value": _safe_observed(area.get("observed_value")),
        "observed_values": {
            _safe_token(key, fallback="observed"): _safe_observed(value)
            for key, value in _mapping(area.get("observed_values")).items()
            if _safe_observed(value)
        },
        "evidence_fact_ids": [
            _safe_token(value, fallback="unknown")
            for value in _sequence(area.get("evidence_fact_ids"))
        ][:16],
    }


def _analysis_limitation(limitation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": _safe_token(limitation.get("id"), fallback="unknown"),
        "state": _safe_token(limitation.get("state"), fallback="unknown"),
        "summary": _safe_text(limitation.get("summary")),
    }


def _diagnosis_boundary_payload(value: object) -> dict[str, str]:
    boundary = _mapping(value)
    return {
        "root_cause": _safe_token(boundary.get("root_cause"), fallback="not_claimed"),
        "details_trusted_report_surface": _safe_token(
            boundary.get("details_trusted_report_surface"),
            fallback="not_wired",
        ),
        "optimizer_behavior": _safe_token(
            boundary.get("optimizer_behavior"),
            fallback="not_wired",
        ),
        "trino_sql_execution": _safe_token(
            boundary.get("trino_sql_execution"),
            fallback="not_performed",
        ),
        "live_recent_scan": _safe_token(
            boundary.get("live_recent_scan"),
            fallback="not_wired",
        ),
        "live_known_query_diagnosis": _safe_token(
            boundary.get("live_known_query_diagnosis"),
            fallback="not_wired",
        ),
    }


def _safe_observed(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    observed: dict[str, object] = {}
    raw_number = value.get("value")
    if isinstance(raw_number, bool):
        observed["value"] = raw_number
    elif isinstance(raw_number, int) and not isinstance(raw_number, bool):
        observed["value"] = raw_number
    elif isinstance(raw_number, float):
        observed["value"] = raw_number
    unit = _safe_token(value.get("unit"), fallback="")
    if unit:
        observed["unit"] = unit
    return observed


def _validate_artifact_payload(label: str, payload: Mapping[str, Any]) -> None:
    _validate_artifact_text(label, json.dumps(payload, ensure_ascii=True, sort_keys=True))


def _validate_artifact_text(label: str, text: str) -> None:
    errors = validate_report_internal_fingerprints(text)
    if contains_raw_sql_like_text(text):
        errors.append(f"{label} contains SQL-like text")
    redacted = redact_browser_display_text(
        text,
        redact_artifact_markers=True,
        redact_field_names=True,
        redact_infrastructure=True,
        redact_model_names=True,
        redact_sql_snippets=True,
    )
    if redacted != text:
        errors.append(f"{label} contains browser-unsafe text")
    if errors:
        raise EngineFactContractError("Trino web case artifact failed raw-free validation")


def _safe_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return redact_browser_display_text(
        value,
        redact_artifact_markers=True,
        redact_field_names=True,
        redact_infrastructure=True,
        redact_model_names=True,
        redact_sql_snippets=True,
        max_chars=2000,
    )


def _safe_token(value: object, *, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback
    safe = "".join(char for char in value.strip().lower() if char.isalnum() or char in "_-")
    return safe or fallback


def _safe_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value if value >= 0 else 0


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mapping_items(value: object) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _sequence(value: object) -> tuple[object, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return ()
    return tuple(value)
