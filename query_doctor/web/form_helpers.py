"""Form parsing helpers for the local web UI."""

from __future__ import annotations

import math

from query_doctor.cli import collect_cm_profiles as cm_collector

from query_doctor.web.models import WebError


def first_form_value(form: dict[str, list[str]], name: str) -> str:
    values = form.get(name, [])
    if not values:
        return ""
    return values[0].strip()


def form_flag_enabled(form: dict[str, list[str]], name: str) -> bool:
    return first_form_value(form, name).lower() in {"1", "true", "yes", "on"}


def parse_positive_form_int(
    form: dict[str, list[str]],
    name: str,
    *,
    default: int,
    maximum: int | None = None,
) -> int:
    text = first_form_value(form, name)
    if not text:
        value = default
    else:
        try:
            value = int(text)
        except ValueError as exc:
            raise WebError(f"{name} must be a positive integer.") from exc
    if value <= 0:
        raise WebError(f"{name} must be a positive integer.")
    if maximum is not None and value > maximum:
        raise WebError(f"{name} must be <= {maximum}.")
    return value


def parse_cm_metrics_profile(form: dict[str, list[str]]) -> str:
    value = first_form_value(form, "cm_metrics_profile") or cm_collector.DEFAULT_CM_METRICS_PROFILE
    try:
        return cm_collector.validate_cm_metrics_profile(value)
    except cm_collector.ConfigError as exc:
        raise WebError(str(exc)) from exc


def parse_non_negative_form_int(
    form: dict[str, list[str]],
    name: str,
    *,
    default: int,
    maximum: int | None = None,
) -> int:
    text = first_form_value(form, name)
    if not text:
        value = default
    else:
        try:
            value = int(text)
        except ValueError as exc:
            raise WebError(f"{name} must be a non-negative integer.") from exc
    if value < 0:
        raise WebError(f"{name} must be a non-negative integer.")
    if maximum is not None and value > maximum:
        raise WebError(f"{name} must be <= {maximum}.")
    return value


def parse_non_negative_form_float(
    form: dict[str, list[str]], name: str, *, default: float
) -> float:
    text = first_form_value(form, name)
    if not text:
        value = default
    else:
        try:
            value = float(text)
        except ValueError as exc:
            raise WebError(f"{name} must be a non-negative number.") from exc
    if value < 0:
        raise WebError(f"{name} must be a non-negative number.")
    if not math.isfinite(value):
        raise WebError(f"{name} must be a finite non-negative number.")
    return value


def parse_optional_non_negative_form_float(form: dict[str, list[str]], name: str) -> float | None:
    text = first_form_value(form, name)
    if not text:
        return None
    try:
        value = float(text)
    except ValueError as exc:
        raise WebError(f"{name} must be a non-negative number.") from exc
    if value < 0:
        raise WebError(f"{name} must be a non-negative number.")
    if not math.isfinite(value):
        raise WebError(f"{name} must be a finite non-negative number.")
    return value
