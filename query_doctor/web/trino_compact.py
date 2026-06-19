"""Safe web handler for local Trino compact diagnosis."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.trino.diagnosis import (
    build_trino_compact_diagnosis_from_boundary,
    select_trino_boundary_payload,
)
from query_doctor.web.form_helpers import first_form_value
from query_doctor.web.models import WebError, WebSettings
from query_doctor.web.ui.trino import render_trino_compact_page


TRINO_BOUNDARY_MAX_JSON_BYTES = 256 * 1024


def handle_trino_compact_request(
    form: dict[str, list[str]],
    settings: WebSettings,
) -> tuple[int, str]:
    try:
        diagnosis = build_trino_compact_diagnosis_from_boundary(
            select_trino_boundary_payload(
                parse_trino_boundary_form_payload(form),
                parse_trino_sample_index_form_value(form),
            )
        )
    except (EngineFactContractError, ValueError, WebError) as exc:
        return 400, render_trino_compact_page(settings, error=exc)
    return 200, render_trino_compact_page(settings, result=diagnosis)


def parse_trino_boundary_form_payload(form: dict[str, list[str]]) -> Mapping[str, Any]:
    text = first_form_value(form, "boundary_json")
    if not text:
        raise trino_compact_input_error(
            "Trino boundary JSON is required.",
            reason_code="trino_compact.boundary_json_required",
            title="Trino boundary JSON is missing",
            next_step="Paste one already raw-free Trino boundary JSON payload, then retry.",
        )
    if len(text.encode("utf-8")) > TRINO_BOUNDARY_MAX_JSON_BYTES:
        raise trino_compact_input_error(
            "Trino boundary JSON exceeds the accepted compact payload limit.",
            reason_code="trino_compact.boundary_json_too_large",
            title="Trino boundary JSON is too large",
            next_step="Use a compact raw-free boundary payload within the accepted byte limit.",
        )
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise trino_compact_input_error(
            "Trino boundary JSON is not valid JSON.",
            reason_code="trino_compact.boundary_json_invalid",
            title="Trino boundary JSON is invalid",
            next_step="Fix the JSON syntax and resubmit the raw-free boundary payload.",
        ) from exc
    if not isinstance(payload, dict):
        raise trino_compact_input_error(
            "Trino boundary JSON must be an object.",
            reason_code="trino_compact.boundary_json_object_required",
            title="Trino boundary JSON object is required",
            next_step="Submit one boundary JSON object or one accepted package boundary export.",
        )
    return payload


def parse_trino_sample_index_form_value(form: dict[str, list[str]]) -> int | None:
    text = first_form_value(form, "sample_index").strip()
    if not text:
        return None
    try:
        sample_index = int(text, 10)
    except ValueError as exc:
        raise trino_compact_sample_index_error() from exc
    if sample_index < 0:
        raise trino_compact_sample_index_error()
    return sample_index


def trino_compact_input_error(
    message: str,
    *,
    reason_code: str,
    title: str,
    next_step: str,
) -> WebError:
    return WebError(
        message,
        title=title,
        reason_code=reason_code,
        stage="Checking Trino compact input",
        next_step=next_step,
    )


def trino_compact_sample_index_error() -> WebError:
    return trino_compact_input_error(
        "Trino package sample index must be a non-negative integer.",
        reason_code="trino_compact.sample_index_invalid",
        title="Trino sample index is invalid",
        next_step="Use a non-negative integer sample index, or leave it empty for a single boundary.",
    )
