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


def form_validation_error(
    message: str,
    *,
    reason_code: str,
    field_name: str,
    next_step: str = "Correct the highlighted form value and retry.",
) -> WebError:
    return WebError(
        message,
        title="Form input was rejected",
        reason_code=reason_code,
        stage=f"Checking form field {field_name}",
        next_step=next_step,
    )


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
            raise form_validation_error(
                f"{name} must be a positive integer.",
                reason_code="web.form_positive_integer_required",
                field_name=name,
            ) from exc
    if value <= 0:
        raise form_validation_error(
            f"{name} must be a positive integer.",
            reason_code="web.form_positive_integer_required",
            field_name=name,
        )
    if maximum is not None and value > maximum:
        raise form_validation_error(
            f"{name} must be <= {maximum}.",
            reason_code="web.form_value_above_maximum",
            field_name=name,
            next_step=f"Set {name} to {maximum} or lower and retry.",
        )
    return value


def parse_cm_metrics_profile(form: dict[str, list[str]]) -> str:
    value = first_form_value(form, "cm_metrics_profile") or cm_collector.DEFAULT_CM_METRICS_PROFILE
    try:
        return cm_collector.validate_cm_metrics_profile(value)
    except cm_collector.ConfigError as exc:
        raise form_validation_error(
            str(exc),
            reason_code="web.form_cm_metrics_profile_invalid",
            field_name="cm_metrics_profile",
            next_step="Choose one of the supported CM metrics profiles and retry.",
        ) from exc


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
            raise form_validation_error(
                f"{name} must be a non-negative integer.",
                reason_code="web.form_non_negative_integer_required",
                field_name=name,
            ) from exc
    if value < 0:
        raise form_validation_error(
            f"{name} must be a non-negative integer.",
            reason_code="web.form_non_negative_integer_required",
            field_name=name,
        )
    if maximum is not None and value > maximum:
        raise form_validation_error(
            f"{name} must be <= {maximum}.",
            reason_code="web.form_value_above_maximum",
            field_name=name,
            next_step=f"Set {name} to {maximum} or lower and retry.",
        )
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
            raise form_validation_error(
                f"{name} must be a non-negative number.",
                reason_code="web.form_non_negative_number_required",
                field_name=name,
            ) from exc
    if value < 0:
        raise form_validation_error(
            f"{name} must be a non-negative number.",
            reason_code="web.form_non_negative_number_required",
            field_name=name,
        )
    if not math.isfinite(value):
        raise form_validation_error(
            f"{name} must be a finite non-negative number.",
            reason_code="web.form_finite_number_required",
            field_name=name,
        )
    return value


def parse_optional_non_negative_form_float(form: dict[str, list[str]], name: str) -> float | None:
    text = first_form_value(form, name)
    if not text:
        return None
    try:
        value = float(text)
    except ValueError as exc:
        raise form_validation_error(
            f"{name} must be a non-negative number.",
            reason_code="web.form_non_negative_number_required",
            field_name=name,
        ) from exc
    if value < 0:
        raise form_validation_error(
            f"{name} must be a non-negative number.",
            reason_code="web.form_non_negative_number_required",
            field_name=name,
        )
    if not math.isfinite(value):
        raise form_validation_error(
            f"{name} must be a finite non-negative number.",
            reason_code="web.form_finite_number_required",
            field_name=name,
        )
    return value
