"""Bounded Cloudera Manager time-series collection and summarization."""

from __future__ import annotations

import json
from collections.abc import Iterable

from query_doctor.cm.client import (
    DEFAULT_MAX_TIMESERIES_BYTES,
    CMHttpClient,
    build_cm_timeseries_request,
)
from query_doctor.cm.metrics_catalog import DEFAULT_CM_METRICS_PROFILE, normalize_cm_metrics_profile
from query_doctor.cm.models import (
    CMAdapterError,
    CMClientError,
    CMHttpConfig,
    CMHttpError,
    CMQuerySummary,
    CMTimeSeriesQuery,
    cm_timeseries_query_allowlist,
)
from query_doctor.cm.profile_parsing import first_present, padded_cm_timeseries_window
from query_doctor.safety.redaction import (
    sanitize_adapter_error_message,
    sanitize_http_error_message,
)


DEFAULT_CM_TIMESERIES_PADDING_SEC = 120
DEFAULT_MAX_TIMESERIES_POINTS = 2000


def normalize_timeseries_metrics_profile(metrics_profile: str) -> str:
    try:
        return normalize_cm_metrics_profile(metrics_profile)
    except ValueError as exc:
        raise CMAdapterError(str(exc)) from exc


def fetch_cm_timeseries_json(
    client: CMHttpClient,
    query: CMTimeSeriesQuery,
    *,
    from_time: str,
    to_time: str,
    max_response_bytes: int = DEFAULT_MAX_TIMESERIES_BYTES,
) -> dict[str, object]:
    path, params = build_cm_timeseries_request(query, from_time=from_time, to_time=to_time)
    try:
        text = client.get_text(path, params=params, max_response_bytes=max_response_bytes)
    except CMHttpError as exc:
        config = getattr(client, "config", None)
        if isinstance(config, CMHttpConfig):
            message = sanitize_http_error_message(exc, config)
        else:
            message = sanitize_adapter_error_message(exc)
        raise CMHttpError(message) from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CMAdapterError("CM time-series response was not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise CMAdapterError("CM time-series response must be an object.")
    return payload


def iter_timeseries_data_series(raw: dict[str, object]) -> Iterable[list[float]]:
    containers: list[object] = []
    for key in ("items", "timeSeries", "timeSeriesList", "series"):
        value = raw.get(key)
        if isinstance(value, list):
            containers.extend(value)
    if not containers:
        containers = [raw]

    for item in containers:
        if not isinstance(item, dict):
            continue
        nested = item.get("timeSeries")
        if isinstance(nested, list):
            yield from iter_timeseries_data_series({"items": nested})
        data = item.get("data")
        if not isinstance(data, list):
            continue
        values: list[float] = []
        for point in data:
            if isinstance(point, dict):
                value = first_present(point, ("value", "aggregateValue", "mean", "max"))
            else:
                value = point
            if isinstance(value, bool) or value is None:
                continue
            try:
                values.append(float(value))
            except (TypeError, ValueError):
                continue
        if values:
            yield values


def iter_timeseries_data_points(raw: dict[str, object]) -> Iterable[float]:
    for values in iter_timeseries_data_series(raw):
        yield from values


def summarize_timeseries_series(values: list[float], *, index: int) -> dict[str, object]:
    return {
        "series": f"series_{index:02d}",
        "point_count": len(values),
        "min": min(values),
        "max": max(values),
        "avg": sum(values) / len(values),
        "latest": values[-1],
    }


def summarize_timeseries_response(
    query: CMTimeSeriesQuery,
    raw: dict[str, object],
    *,
    max_points: int,
) -> dict[str, object]:
    values: list[float] = []
    series_summaries: list[dict[str, object]] = []
    truncated = False
    for series_index, series_values in enumerate(iter_timeseries_data_series(raw), start=1):
        if len(values) >= max_points:
            truncated = True
            break
        remaining = max_points - len(values)
        bounded_values = series_values[:remaining]
        if len(bounded_values) < len(series_values):
            truncated = True
        values.extend(bounded_values)
        if bounded_values:
            series_summaries.append(summarize_timeseries_series(bounded_values, index=series_index))
    summary: dict[str, object] = {
        "id": query.query_id,
        "signal_id": query.signal_id,
        "label": query.label,
        "status": "ok" if values else "no_data",
        "point_count": len(values),
        "truncated": truncated,
    }
    if values:
        top_series = sorted(
            series_summaries,
            key=lambda item: float(item.get("max", 0) or 0),
            reverse=True,
        )[:5]
        summary.update(
            {
                "min": min(values),
                "max": max(values),
                "avg": sum(values) / len(values),
                "latest": values[-1],
                "series_count": len(series_summaries),
                "top_series": top_series,
            }
        )
    return summary


def collect_cm_timeseries_context(
    client: CMHttpClient,
    summary: CMQuerySummary,
    *,
    metrics_profile: str = DEFAULT_CM_METRICS_PROFILE,
    padding_sec: int = DEFAULT_CM_TIMESERIES_PADDING_SEC,
    max_response_bytes: int = DEFAULT_MAX_TIMESERIES_BYTES,
    max_points: int = DEFAULT_MAX_TIMESERIES_POINTS,
) -> dict[str, object]:
    normalized_profile = normalize_timeseries_metrics_profile(metrics_profile)
    window = padded_cm_timeseries_window(summary, padding_sec=padding_sec)
    if window is None:
        return {
            "available": False,
            "reason": "query start/end time unavailable",
            "metrics_profile": normalized_profile,
            "limits": {
                "max_response_bytes": max_response_bytes,
                "max_points_per_query": max_points,
            },
            "queries": [],
        }
    from_time, to_time = window
    queries: list[dict[str, object]] = []
    warnings: list[str] = []
    for query in cm_timeseries_query_allowlist(normalized_profile):
        try:
            raw = fetch_cm_timeseries_json(
                client,
                query,
                from_time=from_time,
                to_time=to_time,
                max_response_bytes=max_response_bytes,
            )
            queries.append(summarize_timeseries_response(query, raw, max_points=max_points))
        except (CMClientError, CMAdapterError) as exc:
            warnings.append(f"{query.query_id}: {sanitize_adapter_error_message(exc)}")
            queries.append(
                {
                    "id": query.query_id,
                    "signal_id": query.signal_id,
                    "label": query.label,
                    "status": "unavailable",
                    "point_count": 0,
                    "reason": sanitize_adapter_error_message(exc),
                }
            )
    return {
        "available": any(item.get("status") == "ok" for item in queries),
        "schema_version": 1,
        "source": "cm_timeseries",
        "metrics_profile": normalized_profile,
        "limits": {
            "max_response_bytes": max_response_bytes,
            "max_points_per_query": max_points,
        },
        "window": {
            "from": from_time,
            "to": to_time,
            "padding_sec": padding_sec,
        },
        "queries": queries,
        "warnings": warnings,
    }
