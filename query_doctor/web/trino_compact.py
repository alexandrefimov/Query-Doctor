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
        raise WebError("Trino boundary JSON is required.")
    if len(text.encode("utf-8")) > TRINO_BOUNDARY_MAX_JSON_BYTES:
        raise WebError("Trino boundary JSON exceeds the accepted compact payload limit.")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise WebError("Trino boundary JSON is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise WebError("Trino boundary JSON must be an object.")
    return payload


def parse_trino_sample_index_form_value(form: dict[str, list[str]]) -> int | None:
    text = first_form_value(form, "sample_index").strip()
    if not text:
        return None
    try:
        sample_index = int(text, 10)
    except ValueError as exc:
        raise WebError("Trino package sample index must be a non-negative integer.") from exc
    if sample_index < 0:
        raise WebError("Trino package sample index must be a non-negative integer.")
    return sample_index
