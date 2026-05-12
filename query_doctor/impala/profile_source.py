"""Direct Impala daemon profile collection for one explicit query id."""

from __future__ import annotations

import html
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from query_doctor.cm.client import validate_cm_query_id_path_segment
from query_doctor.cm.models import CMAdapterError, CMClientError


DEFAULT_IMPALA_PROFILE_PORT = 25000
DEFAULT_IMPALA_PROFILE_SCHEME = "http"
DEFAULT_IMPALA_PROFILE_TIMEOUT_SEC = 15
PROFILE_MARKER_SCAN_CHARS = 128 * 1024
IMPALA_PROFILE_PATHS = (
    "/query_profile?query_id={query_id}&format=text",
    "/query_profile?query_id={query_id}",
)
PROFILE_NOT_FOUND_MARKERS = (
    "Could not find query",
    "Query id not found",
    "Invalid query id",
    "No profile available",
)
PROFILE_CONTENT_MARKERS = (
    "query runtime profile",
    "query timeline",
    "planner timeline",
    "impala query profile",
)
PROFILE_STRUCTURAL_MARKERS = (
    "plan:",
    "fragment ",
    "fragment_instance_id",
    "query state:",
)
PRE_RE = re.compile(r"<pre[^>]*>(?P<body>.*?)</pre>", re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")


UrlOpener = Callable[..., object]


@dataclass(frozen=True)
class ImpalaProfileFetchResult:
    query_id: str
    profile_text: str
    attempted_endpoints: int


def normalize_impala_profile_scheme(value: str | None) -> str:
    scheme = (value or DEFAULT_IMPALA_PROFILE_SCHEME).strip().lower()
    if scheme not in {"http", "https"}:
        raise CMAdapterError("Impala profile scheme must be http or https.")
    return scheme


def normalize_impala_profile_hosts(values: object) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        raw_values = [item.strip() for item in values.split(",")]
    elif isinstance(values, (list, tuple)):
        raw_values = [str(item).strip() for item in values]
    else:
        raise CMAdapterError("Impala profile hosts must be a list of hostnames.")
    hosts = tuple(host for host in raw_values if host)
    for host in hosts:
        validate_impala_profile_host(host)
    return hosts


def validate_impala_profile_host(host: str) -> None:
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in host):
        raise CMAdapterError("Impala profile host must not contain control characters.")
    if any(marker in host for marker in ("/", "\\", "@", "?", "#")):
        raise CMAdapterError("Impala profile host must be a hostname or host:port only.")


def impala_profile_urls(
    hosts: Iterable[str],
    *,
    query_id: str,
    port: int = DEFAULT_IMPALA_PROFILE_PORT,
    scheme: str = DEFAULT_IMPALA_PROFILE_SCHEME,
) -> tuple[str, ...]:
    normalized_query_id = validate_cm_query_id_path_segment(query_id)
    normalized_scheme = normalize_impala_profile_scheme(scheme)
    encoded_query_id = urllib.parse.quote(normalized_query_id, safe="")
    urls: list[str] = []
    for host in normalize_impala_profile_hosts(tuple(hosts)):
        netloc = host if ":" in host else f"{host}:{port}"
        for path in IMPALA_PROFILE_PATHS:
            urls.append(f"{normalized_scheme}://{netloc}{path.format(query_id=encoded_query_id)}")
    return tuple(urls)


def fetch_impala_profile_text(
    *,
    query_id: str,
    hosts: Iterable[str],
    port: int = DEFAULT_IMPALA_PROFILE_PORT,
    scheme: str = DEFAULT_IMPALA_PROFILE_SCHEME,
    timeout_sec: int = DEFAULT_IMPALA_PROFILE_TIMEOUT_SEC,
    max_profile_bytes: int,
    opener: UrlOpener = urllib.request.urlopen,
) -> ImpalaProfileFetchResult:
    urls = impala_profile_urls(hosts, query_id=query_id, port=port, scheme=scheme)
    if not urls:
        raise CMAdapterError("Impala profile collection requires at least one impalad host.")
    attempted = 0
    last_error = "profile endpoint unavailable"
    for url in urls:
        attempted += 1
        try:
            text = fetch_profile_url(
                url,
                timeout_sec=timeout_sec,
                max_profile_bytes=max_profile_bytes,
                opener=opener,
            )
        except CMClientError as exc:
            last_error = str(exc)
            continue
        if profile_response_is_not_found(text):
            last_error = "profile was not found on one impalad endpoint"
            continue
        if profile_text_looks_like_runtime_profile(text):
            return ImpalaProfileFetchResult(
                query_id=validate_cm_query_id_path_segment(query_id),
                profile_text=text,
                attempted_endpoints=attempted,
            )
        if text.strip():
            last_error = "profile endpoint returned non-profile content"
    raise CMAdapterError(
        "Impala profile was not found on the configured impalad endpoints. "
        f"Attempted endpoints: {attempted}. Last safe error: {last_error}."
    )


def fetch_profile_url(
    url: str,
    *,
    timeout_sec: int,
    max_profile_bytes: int,
    opener: UrlOpener,
) -> str:
    request = urllib.request.Request(url, headers={"Accept": "text/plain,text/html"})
    try:
        with opener(request, timeout=timeout_sec) as response:
            raw = response.read(max_profile_bytes + 1)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
        raise CMClientError("Impala profile endpoint request failed safely.") from exc
    if len(raw) > max_profile_bytes:
        raise CMClientError("Impala profile endpoint response exceeded the configured byte limit.")
    text = raw.decode("utf-8", errors="replace")
    return extract_profile_text_from_response(text)


def extract_profile_text_from_response(text: str) -> str:
    pre_match = PRE_RE.search(text)
    if pre_match:
        return html.unescape(pre_match.group("body")).strip() + "\n"
    if "<html" in text[:512].lower() or "<body" in text[:512].lower():
        return html.unescape(TAG_RE.sub("\n", text)).strip() + "\n"
    return text


def profile_response_is_not_found(text: str) -> bool:
    normalized = text.lower()
    return any(marker.lower() in normalized for marker in PROFILE_NOT_FOUND_MARKERS)


def profile_text_looks_like_runtime_profile(text: str) -> bool:
    normalized = text[:PROFILE_MARKER_SCAN_CHARS].lower()
    if any(marker in normalized for marker in PROFILE_CONTENT_MARKERS):
        return True
    if "query id:" in normalized and any(marker in normalized for marker in PROFILE_STRUCTURAL_MARKERS):
        return True
    return False
