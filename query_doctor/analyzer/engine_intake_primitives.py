"""Shared primitives for bounded engine JSON intake."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from query_doctor.analyzer.engine_facts import EngineFactContractError


SAFE_PACKAGE_LABEL_RE = re.compile(r"^[a-z][a-z0-9_]{2,80}$")
SAFE_CLASS_LABEL_RE = re.compile(r"^[a-z][a-z0-9_]{1,120}$")
UTC_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


def required_mapping(
    payload: Mapping[str, Any],
    field_name: str,
    *,
    missing_message: str,
) -> Mapping[str, Any]:
    value = payload.get(field_name)
    if not isinstance(value, Mapping):
        raise EngineFactContractError(missing_message)
    return value


def required_sequence(
    payload: Mapping[str, Any],
    field_name: str,
    *,
    missing_message: str,
) -> Sequence[Any]:
    value = payload.get(field_name)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise EngineFactContractError(missing_message)
    return value


def required_text(
    payload: Mapping[str, Any],
    field_name: str,
    *,
    missing_message: str,
    strip: bool = True,
) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str):
        raise EngineFactContractError(missing_message)
    normalized = value.strip() if strip else value
    if not normalized:
        raise EngineFactContractError(missing_message)
    return normalized


def safe_package_label(
    payload: Mapping[str, Any],
    field_name: str,
    *,
    missing_message: str,
    unsafe_message: str,
    strip: bool = True,
) -> str:
    value = required_text(payload, field_name, missing_message=missing_message, strip=strip)
    if not SAFE_PACKAGE_LABEL_RE.fullmatch(value):
        raise EngineFactContractError(unsafe_message)
    return value


def safe_class_label(
    payload: Mapping[str, Any],
    field_name: str,
    *,
    missing_message: str,
    unsafe_message: str,
    strip: bool = True,
) -> str:
    value = required_text(payload, field_name, missing_message=missing_message, strip=strip)
    if not SAFE_CLASS_LABEL_RE.fullmatch(value):
        raise EngineFactContractError(unsafe_message)
    return value


def version_text(
    payload: Mapping[str, Any],
    field_name: str,
    *,
    missing_message: str,
    unsupported_message: str,
    max_digits: int = 3,
    strip: bool = True,
) -> str:
    value = required_text(payload, field_name, missing_message=missing_message, strip=strip)
    if not re.fullmatch(rf"[0-9]{{1,{max_digits}}}", value):
        raise EngineFactContractError(unsupported_message)
    return value


def safe_label_list(
    payload: Mapping[str, Any],
    field_name: str,
    *,
    missing_message: str,
    unsafe_message: str,
    empty_message: str,
    label_re: re.Pattern[str] = SAFE_CLASS_LABEL_RE,
    allow_empty: bool,
) -> tuple[str, ...]:
    value = payload.get(field_name)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise EngineFactContractError(missing_message)
    labels: list[str] = []
    for item in value:
        if not isinstance(item, str) or not label_re.fullmatch(item):
            raise EngineFactContractError(unsafe_message)
        labels.append(item)
    if not allow_empty and not labels:
        raise EngineFactContractError(empty_message)
    return tuple(labels)


def utc_date(
    payload: Mapping[str, Any],
    field_name: str,
    *,
    missing_message: str,
    invalid_message: str,
    strip: bool = True,
) -> str:
    value = required_text(payload, field_name, missing_message=missing_message, strip=strip)
    if not UTC_DATE_RE.fullmatch(value):
        raise EngineFactContractError(invalid_message)
    return value


def non_negative_int(
    payload: Mapping[str, Any],
    field_name: str,
    *,
    invalid_message: str,
) -> int:
    value = payload.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EngineFactContractError(invalid_message)
    return value


def json_size(
    payload: Mapping[str, Any],
    *,
    payload_label: str,
    error_message: str | None = None,
    compact: bool,
    ensure_ascii: bool = True,
    sort_keys: bool = True,
) -> int:
    try:
        kwargs: dict[str, Any] = {
            "allow_nan": False,
            "ensure_ascii": ensure_ascii,
            "sort_keys": sort_keys,
        }
        if compact:
            kwargs["separators"] = (",", ":")
        return len(json.dumps(payload, **kwargs).encode("utf-8"))
    except (TypeError, ValueError) as exc:
        message = error_message or f"{payload_label} must be JSON serializable"
        raise EngineFactContractError(message) from exc


def max_json_depth(
    value: Any,
    *,
    depth: int = 0,
    count_scalar: bool,
    sequence_types: tuple[type, ...] = (list,),
) -> int:
    if isinstance(value, Mapping):
        if not value:
            return depth + 1 if count_scalar else depth
        return max(
            max_json_depth(
                nested,
                depth=depth + 1,
                count_scalar=count_scalar,
                sequence_types=sequence_types,
            )
            for nested in value.values()
        )
    if isinstance(value, sequence_types) and not isinstance(value, (str, bytes, bytearray)):
        if not value:
            return depth + 1 if count_scalar else depth
        return max(
            max_json_depth(
                nested,
                depth=depth + 1,
                count_scalar=count_scalar,
                sequence_types=sequence_types,
            )
            for nested in value
        )
    return depth + 1 if count_scalar else depth


def format_safe_labels(labels: Sequence[str]) -> str:
    return ", ".join(labels) if labels else "none"
