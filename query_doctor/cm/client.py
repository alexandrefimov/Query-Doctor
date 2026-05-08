"""Bounded Cloudera Manager HTTP client and request builders."""

from __future__ import annotations

import base64
import json
import math
import re
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlsplit, urlunsplit

from query_doctor.cm.models import (
    CMAdapterError,
    CMHttpConfig,
    CMHttpError,
    CMQueryFilters,
    CMTimeSeriesQuery,
    CMUrlOpener,
)
from query_doctor.safety.redaction import sanitize_http_error_message


DEFAULT_MAX_PROFILE_BYTES = 52_428_800
CM_API_VERSION = "v32"
CM_QUERY_SUMMARIES_PATH = (
    f"/api/{CM_API_VERSION}/clusters/{{clusterName}}/services/{{serviceName}}/impalaQueries"
)
CM_PROFILE_TEXT_PATH = (
    f"/api/{CM_API_VERSION}/clusters/{{clusterName}}/services/"
    "{serviceName}/impalaQueries/{queryId}"
)
CM_TIMESERIES_PATH = f"/api/{CM_API_VERSION}/timeseries"
CM_QUERY_DURATION_FILTER_FIELD = "queryDuration"
CM_QUERY_SUMMARY_PAGE_SIZE = 1000
DEFAULT_MAX_TIMESERIES_BYTES = 2 * 1024 * 1024
CM_QUERY_ID_PATH_RE = re.compile(r"^[A-Za-z0-9]+:[A-Za-z0-9]+$")


def normalize_optional_string(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


class CMHttpClient:
    """Small GET-only CM HTTP transport with injectable opener for tests."""

    def __init__(
        self,
        config: CMHttpConfig,
        *,
        opener: CMUrlOpener | None = None,
    ) -> None:
        self.config = config
        self.opener = opener or urllib.request.urlopen

    def build_url(self, path: str, params: dict[str, object] | None = None) -> str:
        parsed_path = urlsplit(path)
        if parsed_path.scheme or parsed_path.netloc:
            raise CMHttpError("Refusing absolute CM API path.")
        if any(segment == ".." for segment in parsed_path.path.split("/")):
            raise CMHttpError("Refusing CM API path with parent traversal.")

        base = self.config.cm_url.rstrip("/") + "/"
        relative = path.lstrip("/")
        url = urljoin(base, relative)
        existing_params = dict(parse_qsl(urlsplit(url).query, keep_blank_values=True))
        for key, value in (params or {}).items():
            if value is None:
                continue
            existing_params[key] = str(value)

        parsed_url = urlsplit(url)
        query = urlencode(existing_params)
        return urlunsplit(
            (
                parsed_url.scheme,
                parsed_url.netloc,
                parsed_url.path,
                query,
                "",
            )
        )

    def build_request(
        self,
        path: str,
        params: dict[str, object] | None = None,
    ) -> urllib.request.Request:
        request = urllib.request.Request(
            self.build_url(path, params),
            method="GET",
            headers={"Accept": "application/json"},
        )
        auth_header = self.authorization_header()
        if auth_header:
            request.add_header("Authorization", auth_header)
        return request

    def authorization_header(self) -> str | None:
        if self.config.token:
            return f"Bearer {self.config.token}"
        if self.config.username and self.config.password:
            raw = f"{self.config.username}:{self.config.password}".encode("utf-8")
            encoded = base64.b64encode(raw).decode("ascii")
            return f"Basic {encoded}"
        return None

    def get_text(
        self,
        path: str,
        params: dict[str, object] | None = None,
        *,
        max_response_bytes: int | None = None,
    ) -> str:
        request = self.build_request(path, params)
        if max_response_bytes is not None and max_response_bytes <= 0:
            raise self.sanitized_error("Maximum response bytes must be a positive integer.")
        try:
            context = self.tls_context()
            with self.opener(
                request,
                timeout=self.config.timeout_sec,
                context=context,
            ) as response:
                if max_response_bytes is None:
                    payload = response.read()
                else:
                    payload = response.read(max_response_bytes + 1)
                    if len(payload) > max_response_bytes:
                        actual_read = len(payload)
                        raise self.sanitized_error(
                            "CM response exceeded maximum allowed bytes: "
                            f"actual at least {actual_read}, limit {max_response_bytes}"
                        )
        except urllib.error.HTTPError as exc:
            raise self.sanitized_error(f"HTTP {exc.code} from CM: {exc}") from exc
        except urllib.error.URLError as exc:
            raise self.sanitized_error(f"CM request failed: {exc}") from exc
        except OSError as exc:
            raise self.sanitized_error(f"CM request failed: {exc}") from exc
        return payload.decode("utf-8", errors="replace")

    def tls_context(self) -> ssl.SSLContext:
        if not self.config.verify_tls:
            return ssl._create_unverified_context()
        try:
            if self.config.ca_bundle:
                return ssl.create_default_context(cafile=self.config.ca_bundle)
            return ssl.create_default_context()
        except OSError as exc:
            if self.config.ca_bundle:
                raise self.sanitized_error(
                    f"Could not load CA bundle {self.config.ca_bundle}: {exc}"
                ) from exc
            raise self.sanitized_error(f"Could not create TLS context: {exc}") from exc

    def get_json(self, path: str, params: dict[str, object] | None = None) -> dict[str, object]:
        text = self.get_text(path, params)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise self.sanitized_error(f"CM returned invalid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise self.sanitized_error("CM returned JSON that is not an object.")
        return payload

    def sanitized_error(self, message: object) -> CMHttpError:
        return CMHttpError(sanitize_http_error_message(message, self.config))


def build_cm_query_summary_page_request(
    filters: CMQueryFilters,
    page_token: str | None = None,
    *,
    now: datetime | None = None,
) -> tuple[str, dict[str, object]]:
    path = CM_QUERY_SUMMARIES_PATH.format(
        clusterName=safe_cm_path_segment(filters.cluster, "cluster"),
        serviceName=safe_cm_path_segment(filters.service, "service"),
    )
    if filters.from_time is not None or filters.to_time is not None:
        if not filters.from_time or not filters.to_time:
            raise CMAdapterError("CM query summary explicit time window requires both from_time and to_time.")
        from_time, to_time = filters.from_time, filters.to_time
    elif filters.since_minutes is not None:
        from_time, to_time = cm_time_window_minutes(filters.since_minutes, now=now)
    else:
        from_time, to_time = cm_time_window(filters.since_hours, now=now)
    params: dict[str, object] = {
        "from": from_time,
        "to": to_time,
        "limit": effective_query_summary_page_size(filters, filters.limit),
    }
    if page_token:
        params["offset"] = page_token
    filter_expression = build_cm_query_filter_expression(filters)
    if filter_expression:
        params["filter"] = filter_expression
    return path, params


def effective_query_summary_page_size(filters: CMQueryFilters, remaining: int) -> int:
    configured = filters.page_size or filters.limit
    return max(1, min(int(configured), int(remaining), CM_QUERY_SUMMARY_PAGE_SIZE))


def safe_cm_path_segment(value: str, field_name: str) -> str:
    normalized = normalize_optional_string(value)
    if not normalized:
        raise CMAdapterError(f"CM {field_name} path segment is required.")
    return quote(normalized, safe="")


def cm_time_window(since_hours: int, *, now: datetime | None = None) -> tuple[str, str]:
    return cm_time_window_minutes(since_hours * 60, now=now)


def cm_time_window_minutes(
    since_minutes: int,
    *,
    now: datetime | None = None,
) -> tuple[str, str]:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc).replace(microsecond=0)
    start = current - timedelta(minutes=since_minutes)
    return format_cm_timestamp(start), format_cm_timestamp(current)


def format_cm_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_cm_query_filter_expression(filters: CMQueryFilters) -> str | None:
    """Build a conservative CM filter expression for supported query params.

    Predicates use the existing CM Impala query list ``filter`` request
    parameter. CDH6-era CM docs show queryDuration with duration literals such
    as ``queryDuration > 5s`` and string attributes such as ``user``/``pool``.
    Client-side filtering remains a backstop after bounded discovery.
    """
    predicates: list[str] = []
    if (
        filters.server_duration_filter
        and filters.min_duration_sec is not None
        and filters.min_duration_sec > 0
    ):
        predicates.append(
            f"{CM_QUERY_DURATION_FILTER_FIELD} > {duration_lower_bound_literal(filters.min_duration_sec)}"
        )
    if filters.server_duration_filter and filters.max_duration_sec is not None:
        predicates.append(
            f"{CM_QUERY_DURATION_FILTER_FIELD} < {duration_upper_bound_literal(filters.max_duration_sec)}"
        )
    if filters.user:
        predicates.append(f"user = {cm_filter_string_literal(filters.user)}")
    if filters.pool:
        predicates.append(f"pool = {cm_filter_string_literal(filters.pool)}")
    if filters.query_type:
        predicates.append(f"query_type = {cm_filter_string_literal(filters.query_type)}")
    if filters.executing is not None:
        predicates.append(f"executing = {str(filters.executing).lower()}")
    return " AND ".join(predicates) if predicates else None


def cm_filter_string_literal(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def duration_lower_bound_literal(seconds: float | int) -> str:
    return f"{max(0, int(math.ceil(float(seconds))))}s"


def duration_upper_bound_literal(seconds: float | int) -> str:
    return f"{max(0, int(math.floor(float(seconds))))}s"


def build_cm_profile_text_request(
    filters: CMQueryFilters,
    query_id: str,
) -> tuple[str, dict[str, object]]:
    normalized_query_id = validate_cm_query_id_path_segment(query_id)

    path = CM_PROFILE_TEXT_PATH.format(
        clusterName=safe_cm_path_segment(filters.cluster, "cluster"),
        serviceName=safe_cm_path_segment(filters.service, "service"),
        queryId=normalized_query_id,
    )
    return path, {"format": "text"}


def validate_cm_query_id_path_segment(query_id: str) -> str:
    normalized_query_id = normalize_optional_string(query_id)
    if not normalized_query_id:
        raise CMAdapterError("CM profile text request requires a query id.")
    if not CM_QUERY_ID_PATH_RE.fullmatch(normalized_query_id):
        raise CMAdapterError(
            "CM profile text request requires query id shape "
            "[A-Za-z0-9]+:[A-Za-z0-9]+ for path usage."
        )
    return normalized_query_id


def build_cm_timeseries_request(
    query: CMTimeSeriesQuery,
    *,
    from_time: str,
    to_time: str,
) -> tuple[str, dict[str, object]]:
    return CM_TIMESERIES_PATH, {
        "query": query.tsquery,
        "from": from_time,
        "to": to_time,
        "contentType": "application/json",
    }
