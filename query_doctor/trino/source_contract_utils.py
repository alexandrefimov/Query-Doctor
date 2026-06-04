"""Shared helpers for compact Trino source-contract validation."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from typing import Any

from query_doctor.analyzer.engine_facts import EngineFactContractError


SAFE_SOURCE_LABEL_RE = re.compile(r"[a-z][a-z0-9_]{1,80}")
UNSAFE_SOURCE_LABEL_PARTS = frozenset(
    {
        "access",
        "catalog",
        "cluster",
        "cookie",
        "coordinator",
        "database",
        "db",
        "endpoint",
        "host",
        "hostname",
        "key",
        "password",
        "passwd",
        "prod",
        "pwd",
        "schema",
        "secret",
        "server",
        "table",
        "token",
        "topic",
        "uri",
        "url",
        "user",
        "worker",
    }
)


def validate_contract_json_size(
    payload: Mapping[str, Any],
    *,
    max_contract_bytes: int,
    payload_label: str,
) -> None:
    if max_contract_bytes < 1:
        raise EngineFactContractError(f"{payload_label} byte limit must be positive")
    try:
        encoded = json.dumps(payload, sort_keys=True, allow_nan=False).encode("utf-8")
    except ValueError as exc:
        raise EngineFactContractError(f"{payload_label} contains invalid numeric values") from exc
    if len(encoded) > max_contract_bytes:
        raise EngineFactContractError(f"{payload_label} is too large")


def validate_contract_tree(value: Any, *, max_depth: int, payload_label: str) -> None:
    if max_depth < 1:
        raise EngineFactContractError(f"{payload_label} depth limit must be positive")
    _validate_tree(value, depth=0, max_depth=max_depth, payload_label=payload_label)


def validate_exact_keys(payload: Mapping[str, Any], expected: frozenset[str], message: str) -> None:
    if set(payload) != expected:
        raise EngineFactContractError(message)


def mapping_required(
    payload: Mapping[str, Any],
    field_name: str,
    payload_label: str,
) -> Mapping[str, Any]:
    value = payload.get(field_name)
    if not isinstance(value, Mapping):
        raise EngineFactContractError(f"{payload_label} missing {field_name}")
    return value


def required_text(payload: Mapping[str, Any], field_name: str, *, payload_label: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise EngineFactContractError(f"{payload_label} missing {field_name}")
    return value.strip()


def allowed_text(
    payload: Mapping[str, Any],
    field_name: str,
    *,
    allowed: frozenset[str],
    message: str,
    payload_label: str,
) -> str:
    value = required_text(payload, field_name, payload_label=payload_label)
    if value not in allowed:
        raise EngineFactContractError(message)
    return value


def safe_source_label(
    payload: Mapping[str, Any], field_name: str, *, message: str, payload_label: str
) -> str:
    value = required_text(payload, field_name, payload_label=payload_label)
    if not SAFE_SOURCE_LABEL_RE.fullmatch(value):
        raise EngineFactContractError(message)
    parts = frozenset(value.split("_"))
    if parts & UNSAFE_SOURCE_LABEL_PARTS:
        raise EngineFactContractError(message)
    return value


def bounded_int(
    payload: Mapping[str, Any],
    field_name: str,
    *,
    upper: int,
    message: str,
) -> int:
    value = payload.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise EngineFactContractError(message)
    if value < 1 or value > upper:
        raise EngineFactContractError(message)
    return value


def required_boolean(
    payload: Mapping[str, Any],
    field_name: str,
    *,
    expected: bool,
    message: str,
) -> None:
    value = payload.get(field_name)
    if value is not expected:
        raise EngineFactContractError(message)


def required_literal(
    payload: Mapping[str, Any],
    field_name: str,
    *,
    expected: str,
    message: str,
) -> str:
    value = payload.get(field_name)
    if value != expected:
        raise EngineFactContractError(message)
    return value


def _validate_tree(value: Any, *, depth: int, max_depth: int, payload_label: str) -> None:
    if depth > max_depth:
        raise EngineFactContractError(f"{payload_label} is too deeply nested")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise EngineFactContractError(f"{payload_label} keys must be strings")
            _validate_tree(item, depth=depth + 1, max_depth=max_depth, payload_label=payload_label)
    elif isinstance(value, list):
        for item in value:
            _validate_tree(item, depth=depth + 1, max_depth=max_depth, payload_label=payload_label)
    elif isinstance(value, float) and not math.isfinite(value):
        raise EngineFactContractError(f"{payload_label} contains invalid numeric values")
    elif not isinstance(value, (str, int, float, bool, type(None))):
        raise EngineFactContractError(f"{payload_label} contains non-JSON values")
