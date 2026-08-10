"""Bounded Impala `/admission?json` collection for safe pool context."""

from __future__ import annotations

import http.client
import json
import re
import urllib.error
import urllib.request
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from query_doctor.cm.models import CMAdapterError, CMClientError
from query_doctor.impala.profile_source import (
    DEFAULT_IMPALA_PROFILE_PORT,
    DEFAULT_IMPALA_PROFILE_SCHEME,
    DEFAULT_IMPALA_PROFILE_TIMEOUT_SEC,
    UrlOpener,
    normalize_impala_profile_hosts,
    normalize_impala_profile_scheme,
)
from query_doctor.safety.http_egress import configured_diagnostic_urlopen


ADMISSION_CONTEXT_PATH = "/admission?json"
ADMISSION_CONTEXT_FILENAME = "admission_context.json"
DEFAULT_MAX_ADMISSION_CONTEXT_BYTES = 2 * 1024 * 1024
SAFE_REASON_CODES = {"request_failed", "response_too_large", "invalid_json", "no_pool_entries"}
QUEUE_HIGH_DEPTH = 10
QUEUE_MEDIUM_DEPTH = 1
QUEUE_HIGH_MS = 30_000.0
QUEUE_MEDIUM_MS = 5_000.0
STALE_AGE_MS = 300_000.0
FRESH_AGE_MS = 60_000.0


@dataclass(frozen=True)
class AdmissionPoolEntry:
    name: str | None
    payload: Mapping[object, object]


@dataclass(frozen=True)
class ImpalaAdmissionContextFetchResult:
    context: dict[str, object]
    attempted_endpoints: int


def impala_admission_context_urls(
    hosts: Iterable[str],
    *,
    port: int = DEFAULT_IMPALA_PROFILE_PORT,
    scheme: str = DEFAULT_IMPALA_PROFILE_SCHEME,
) -> tuple[str, ...]:
    normalized_scheme = normalize_impala_profile_scheme(scheme)
    urls: list[str] = []
    for host in normalize_impala_profile_hosts(tuple(hosts)):
        netloc = host if ":" in host else f"{host}:{port}"
        urls.append(f"{normalized_scheme}://{netloc}{ADMISSION_CONTEXT_PATH}")
    return tuple(urls)


def fetch_impala_admission_context(
    *,
    hosts: Iterable[str],
    port: int = DEFAULT_IMPALA_PROFILE_PORT,
    scheme: str = DEFAULT_IMPALA_PROFILE_SCHEME,
    timeout_sec: int = DEFAULT_IMPALA_PROFILE_TIMEOUT_SEC,
    max_admission_context_bytes: int = DEFAULT_MAX_ADMISSION_CONTEXT_BYTES,
    target_pool: str | None = None,
    opener: UrlOpener = configured_diagnostic_urlopen,
) -> ImpalaAdmissionContextFetchResult:
    urls = impala_admission_context_urls(hosts, port=port, scheme=scheme)
    if not urls:
        raise CMAdapterError(
            "Impala admission context collection requires at least one impalad host."
        )

    attempted = 0
    last_reason = "request_failed"
    for url in urls:
        attempted += 1
        try:
            payload = fetch_admission_context_payload(
                url,
                timeout_sec=timeout_sec,
                max_admission_context_bytes=max_admission_context_bytes,
                opener=opener,
            )
        except CMClientError as exc:
            last_reason = safe_reason(str(exc))
            continue
        context = build_admission_context(payload, target_pool=target_pool)
        if context.get("status") == "available":
            return ImpalaAdmissionContextFetchResult(context=context, attempted_endpoints=attempted)
        last_reason = safe_reason(context.get("reason"))
    return ImpalaAdmissionContextFetchResult(
        context=unavailable_admission_context(last_reason),
        attempted_endpoints=attempted,
    )


def fetch_admission_context_payload(
    url: str,
    *,
    timeout_sec: int,
    max_admission_context_bytes: int,
    opener: UrlOpener,
) -> object:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with opener(request, timeout=timeout_sec) as response:
            raw = response.read(max_admission_context_bytes + 1)
    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
        OSError,
        http.client.HTTPException,
    ) as exc:
        raise CMClientError("request_failed") from exc
    if len(raw) > max_admission_context_bytes:
        raise CMClientError("response_too_large")
    try:
        return json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise CMClientError("invalid_json") from exc


def build_admission_context(
    payload: object, *, target_pool: str | None = None
) -> dict[str, object]:
    pools = admission_pool_entries(payload)
    if not pools:
        return unavailable_admission_context("no_pool_entries")

    normalized_target = normalize_pool_name(target_pool)
    selected = [
        pool
        for pool in pools
        if normalized_target and normalize_pool_name(pool.name) == normalized_target
    ]
    if normalized_target and selected:
        scoped_pools = selected
        scope = "selected_pool"
    elif normalized_target:
        scoped_pools = pools
        scope = "all_pools_selected_pool_not_found"
    else:
        scoped_pools = pools
        scope = "all_pools"

    queued_counts = [
        value
        for value in (pool_queued_count(pool.payload) for pool in scoped_pools)
        if value is not None
    ]
    running_counts = [
        value
        for value in (pool_running_count(pool.payload) for pool in scoped_pools)
        if value is not None
    ]
    queue_times = [
        value
        for value in (pool_queue_time_ms(pool.payload) for pool in scoped_pools)
        if value is not None
    ]
    max_queue_depth = max(queued_counts) if queued_counts else None
    max_running = max(running_counts) if running_counts else None
    max_queue_time_ms = max(queue_times) if queue_times else None
    queue_present = yes_no_unknown(any(value > 0 for value in queued_counts), queued_counts)
    running_present = yes_no_unknown(any(value > 0 for value in running_counts), running_counts)
    freshness = admission_context_freshness(payload)
    limitations = [
        "Admission debug context is aggregate pool context. It must not promote runtime_admission without selected-query admission wait or result evidence."
    ]
    if scope == "all_pools_selected_pool_not_found":
        limitations.append(
            "Selected-query pool was not found in the admission debug context; only all-pool aggregate context is available."
        )
    if freshness == "stale":
        limitations.append(
            "Admission debug context may be stale according to the safe statestore freshness signal."
        )
    if max_queue_depth is None and max_queue_time_ms is None:
        limitations.append(
            "Admission debug context did not expose a safe queue depth or queue-time aggregate."
        )

    return {
        "schema_version": 1,
        "available": True,
        "status": "available",
        "source": "impala_admission_debug",
        "source_label": "Impala admission debug endpoint",
        "scope": scope,
        "pool_count": len(pools),
        "matched_pool_count": len(selected),
        "queue_present": queue_present,
        "running_present": running_present,
        "queued_pool_count": sum(1 for value in queued_counts if value > 0),
        "running_pool_count": sum(1 for value in running_counts if value > 0),
        "max_queue_depth_bucket": count_bucket(max_queue_depth),
        "max_running_bucket": count_bucket(max_running),
        "avg_queue_time_bucket": duration_bucket_ms(max_queue_time_ms),
        "pool_pressure": pool_pressure(max_queue_depth, max_queue_time_ms),
        "freshness": freshness,
        "guardrail": (
            "Admission context is bounded aggregate evidence only. Raw queued/running query lists, "
            "pool names, users, SQL, hosts, and paths are not stored."
        ),
        "limitations": limitations,
    }


def unavailable_admission_context(reason: object) -> dict[str, object]:
    return {
        "schema_version": 1,
        "available": False,
        "status": "unavailable",
        "source": "impala_admission_debug",
        "source_label": "Impala admission debug endpoint",
        "scope": "unknown",
        "pool_count": 0,
        "matched_pool_count": 0,
        "queue_present": "unknown",
        "running_present": "unknown",
        "queued_pool_count": 0,
        "running_pool_count": 0,
        "max_queue_depth_bucket": "unknown",
        "max_running_bucket": "unknown",
        "avg_queue_time_bucket": "unknown",
        "pool_pressure": "unknown",
        "freshness": "unknown",
        "reason": safe_reason(reason),
        "guardrail": (
            "Admission context is bounded aggregate evidence only. Raw queued/running query lists, "
            "pool names, users, SQL, hosts, and paths are not stored."
        ),
        "limitations": [
            "Impala admission debug context was unavailable or unmapped; keep pool/admission context unknown."
        ],
    }


def admission_pool_entries(payload: object) -> list[AdmissionPoolEntry]:
    if not isinstance(payload, Mapping):
        return []
    entries: list[AdmissionPoolEntry] = []
    for key, value in payload.items():
        key_text = str(key or "")
        if pool_container_key(key_text):
            entries.extend(pool_entries_from_container(value))
    if not entries:
        entries.extend(pool_entries_from_container(payload))
    return dedupe_pool_entries(entries)


def pool_entries_from_container(value: object) -> list[AdmissionPoolEntry]:
    entries: list[AdmissionPoolEntry] = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, Mapping) and looks_like_pool_entry(item):
                entries.append(AdmissionPoolEntry(pool_name(item), item))
    elif isinstance(value, Mapping):
        if looks_like_pool_entry(value):
            entries.append(AdmissionPoolEntry(pool_name(value), value))
        else:
            for key, item in value.items():
                if isinstance(item, Mapping) and looks_like_pool_entry(item):
                    entries.append(AdmissionPoolEntry(pool_name(item) or str(key), item))
    return entries


def dedupe_pool_entries(entries: list[AdmissionPoolEntry]) -> list[AdmissionPoolEntry]:
    deduped: list[AdmissionPoolEntry] = []
    seen: set[int] = set()
    for entry in entries:
        identity = id(entry.payload)
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(entry)
    return deduped


def pool_container_key(key: str) -> bool:
    normalized = normalize_key(key)
    return normalized in {
        "pools",
        "poolstats",
        "pool_stats",
        "resourcepools",
        "resource_pools",
        "admissionpools",
        "admission_pools",
    } or ("pool" in normalized and normalized.endswith(("s", "stats")))


def looks_like_pool_entry(payload: Mapping[object, object]) -> bool:
    keys = {normalize_key(str(key or "")) for key in payload.keys()}
    return any("pool" in key for key in keys) or any(
        marker in key for key in keys for marker in ("queued", "queue", "running", "admitted")
    )


def pool_name(payload: Mapping[object, object]) -> str | None:
    for key in ("pool_name", "poolName", "pool", "name", "resource_pool", "resourcePool"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def pool_queued_count(payload: Mapping[object, object]) -> int | None:
    return count_value(
        payload, include=("queued", "queue", "inqueue"), exclude=("time", "wait", "hist")
    )


def pool_running_count(payload: Mapping[object, object]) -> int | None:
    return count_value(
        payload, include=("running", "admittedrunning", "numrunning"), exclude=("hist",)
    )


def count_value(
    payload: Mapping[object, object],
    *,
    include: tuple[str, ...],
    exclude: tuple[str, ...],
) -> int | None:
    best: int | None = None
    for key, value in nested_items(payload):
        normalized = normalize_key(str(key or ""))
        if not any(marker in normalized for marker in include):
            continue
        if any(marker in normalized for marker in exclude):
            continue
        if isinstance(value, list):
            candidate = len(value)
        else:
            candidate = nonnegative_int(value)
        if candidate is None:
            continue
        best = candidate if best is None else max(best, candidate)
    return best


def pool_queue_time_ms(payload: Mapping[object, object]) -> float | None:
    best: float | None = None
    for key, value in nested_items(payload):
        normalized = normalize_key(str(key or ""))
        if "queue" not in normalized and "wait" not in normalized:
            continue
        if not any(marker in normalized for marker in ("time", "wait", "avg", "ema")):
            continue
        candidate = duration_ms(value, key=normalized)
        if candidate is None:
            continue
        best = candidate if best is None else max(best, candidate)
    return best


def admission_context_freshness(payload: object) -> str:
    stale_observed = False
    fresh_observed = False
    for key, value in nested_items(payload if isinstance(payload, Mapping) else {}):
        normalized = normalize_key(str(key or ""))
        if any(marker in normalized for marker in ("stale", "disconnected")):
            if bool_value(value) is True:
                stale_observed = True
            elif bool_value(value) is False:
                fresh_observed = True
            elif isinstance(value, str) and re.search(r"\b(stale|disconnect)", value, re.I):
                stale_observed = True
        if "statestore" in normalized and any(
            marker in normalized for marker in ("age", "last", "update")
        ):
            age_ms = duration_ms(value, key=normalized)
            if age_ms is not None:
                if age_ms >= STALE_AGE_MS:
                    stale_observed = True
                elif age_ms <= FRESH_AGE_MS:
                    fresh_observed = True
    if stale_observed:
        return "stale"
    if fresh_observed:
        return "fresh"
    return "unknown"


def nested_items(payload: Mapping[object, object], *, max_depth: int = 3):
    stack: list[tuple[Mapping[object, object], int]] = [(payload, 0)]
    while stack:
        current, depth = stack.pop()
        for key, value in current.items():
            yield key, value
            if depth < max_depth and isinstance(value, Mapping):
                stack.append((value, depth + 1))


def count_bucket(value: int | None) -> str:
    if value is None:
        return "unknown"
    if value <= 0:
        return "none"
    if value == 1:
        return "1"
    if value < 5:
        return "2_4"
    if value < 10:
        return "5_9"
    return "10_plus"


def duration_bucket_ms(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value <= 0:
        return "none"
    if value < 1_000:
        return "lt_1s"
    if value < 5_000:
        return "1s_5s"
    if value < 30_000:
        return "5s_30s"
    return "30s_plus"


def pool_pressure(queue_depth: int | None, queue_time_ms: float | None) -> str:
    if queue_depth is None and queue_time_ms is None:
        return "unknown"
    if (queue_depth is not None and queue_depth >= QUEUE_HIGH_DEPTH) or (
        queue_time_ms is not None and queue_time_ms >= QUEUE_HIGH_MS
    ):
        return "high"
    if (queue_depth is not None and queue_depth >= QUEUE_MEDIUM_DEPTH) or (
        queue_time_ms is not None and queue_time_ms >= QUEUE_MEDIUM_MS
    ):
        return "medium"
    return "low"


def yes_no_unknown(observed: bool, values: list[int]) -> str:
    if not values:
        return "unknown"
    return "yes" if observed else "no"


def normalize_pool_name(value: object) -> str:
    return str(value or "").strip().lower()


def normalize_key(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum() or ch == "_")


def nonnegative_int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return max(0, int(float(value)))
    text = str(value).strip()
    if not text:
        return None
    try:
        return max(0, int(float(text)))
    except ValueError:
        return None


def duration_ms(value: object, *, key: str = "") -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = max(0.0, float(value))
        return number * 1000.0 if key.endswith("s") and not key.endswith("ms") else number
    text = str(value).strip().lower()
    if not text:
        return None
    number_match = re.search(r"(\d+(?:\.\d+)?)", text)
    if not number_match:
        return None
    number = float(number_match.group(1))
    if "us" in text:
        return max(0.0, number / 1000.0)
    if "ms" in text:
        return max(0.0, number)
    if "sec" in text or re.search(r"\bs\b", text):
        return max(0.0, number * 1000.0)
    if "min" in text:
        return max(0.0, number * 60_000.0)
    return max(0.0, number)


def bool_value(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"true", "yes", "y", "1"}:
        return True
    if text in {"false", "no", "n", "0"}:
        return False
    return None


def safe_reason(value: object) -> str:
    text = str(value or "").strip().lower()
    return text if text in SAFE_REASON_CODES else "request_failed"


def write_admission_context(case_dir: Path, context: Mapping[str, object]) -> None:
    (case_dir / ADMISSION_CONTEXT_FILENAME).write_text(
        json.dumps(dict(context), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
