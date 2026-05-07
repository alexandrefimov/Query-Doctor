"""CM profile/query-summary fetch adapters over the bounded HTTP client."""

from __future__ import annotations

from query_doctor.cm.client import (
    DEFAULT_MAX_PROFILE_BYTES,
    CMHttpClient,
    build_cm_profile_text_request,
    build_cm_query_summary_page_request,
)
from query_doctor.cm.models import (
    CMAdapterError,
    CMHttpConfig,
    CMHttpError,
    CMQueryFilters,
    CMQueryPage,
    CMQuerySummary,
)
from query_doctor.cm.profile_parsing import (
    parse_cm_query_details_summary,
    parse_cm_query_summary_page,
)
from query_doctor.safety.redaction import (
    sanitize_adapter_error_message,
    sanitize_http_error_message,
)


def fetch_cm_query_summary_page(
    client: CMHttpClient,
    filters: CMQueryFilters,
    page_token: str | None = None,
) -> CMQueryPage:
    path, params = build_cm_query_summary_page_request(filters, page_token)
    try:
        raw = client.get_json(path, params=params)
        return parse_cm_query_summary_page(raw)
    except CMHttpError as exc:
        config = getattr(client, "config", None)
        if isinstance(config, CMHttpConfig):
            message = sanitize_http_error_message(exc, config)
        else:
            message = sanitize_adapter_error_message(exc)
        raise CMHttpError(message) from exc
    except CMAdapterError as exc:
        raise CMAdapterError(sanitize_adapter_error_message(exc)) from exc


def fetch_cm_profile_text(
    client: CMHttpClient,
    filters: CMQueryFilters,
    query_id: str,
    *,
    max_profile_bytes: int = DEFAULT_MAX_PROFILE_BYTES,
) -> str:
    path, params = build_cm_profile_text_request(filters, query_id)
    try:
        profile_text = client.get_text(
            path,
            params=params,
            max_response_bytes=max_profile_bytes,
        )
        enforce_profile_text_size(profile_text, max_profile_bytes=max_profile_bytes)
        return profile_text
    except CMHttpError as exc:
        config = getattr(client, "config", None)
        if isinstance(config, CMHttpConfig):
            message = sanitize_http_error_message(exc, config)
        else:
            message = sanitize_adapter_error_message(exc)
        raise CMHttpError(message) from exc


def fetch_cm_query_details_summary(
    client: CMHttpClient,
    filters: CMQueryFilters,
    query_id: str,
) -> CMQuerySummary:
    path, _ = build_cm_profile_text_request(filters, query_id)
    try:
        raw = client.get_json(path, params=None)
        return parse_cm_query_details_summary(raw, query_id)
    except CMHttpError as exc:
        config = getattr(client, "config", None)
        if isinstance(config, CMHttpConfig):
            message = sanitize_http_error_message(exc, config)
        else:
            message = sanitize_adapter_error_message(exc)
        raise CMHttpError(message) from exc
    except CMAdapterError as exc:
        raise CMAdapterError(sanitize_adapter_error_message(exc)) from exc


def enforce_profile_text_size(profile_text: str, *, max_profile_bytes: int) -> None:
    if max_profile_bytes <= 0:
        raise CMAdapterError("Maximum profile bytes must be a positive integer.")
    actual_bytes = len(profile_text.encode("utf-8"))
    if actual_bytes > max_profile_bytes:
        raise CMAdapterError(
            "CM profile text exceeded maximum allowed bytes: "
            f"actual {actual_bytes}, limit {max_profile_bytes}"
        )
