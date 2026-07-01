"""Safe Trino coordinator retained query-list validation and bounded read."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.trino.coordinator_query_info_target import (
    TRINO_COORDINATOR_QUERY_ID_RE,
    TRINO_COORDINATOR_QUERY_INFO_AUTH_HEADER_MAX_BYTES,
    TRINO_COORDINATOR_QUERY_INFO_PRUNED_AUTH_KIND,
    TRINO_COORDINATOR_QUERY_INFO_VERSION_FAMILY_RE,
    _request_auth_headers as _query_info_request_auth_headers,
    _validate_coordinator_base_url,
    load_trino_coordinator_query_info_auth_header_file,
)
from query_doctor.trino.source_contract_registry import trino_source_type_for_contract_family
from query_doctor.trino.source_contract_utils import (
    allowed_text,
    bounded_int,
    mapping_required,
    required_boolean,
    required_literal,
    required_text,
    safe_source_label,
    validate_contract_json_size,
    validate_contract_tree,
    validate_exact_keys,
)


TRINO_COORDINATOR_QUERY_LIST_SOURCE_CONTRACT_VERSION = (
    "trino_coordinator_query_list_source_contract_v1"
)
TRINO_COORDINATOR_QUERY_LIST_CONTRACT_VERSION = "trino_coordinator_query_list_v1"
TRINO_COORDINATOR_QUERY_LIST_SOURCE_TYPE = trino_source_type_for_contract_family(
    "coordinator_query_list_source_contract",
    surface_class="contract_gated_coordinator_recent",
)
TRINO_COORDINATOR_QUERY_LIST_ENDPOINT_TEMPLATE = "/v1/query?pruned=true"
TRINO_COORDINATOR_QUERY_LIST_SOURCE_CONTRACT_MAX_BYTES = 16 * 1024
TRINO_COORDINATOR_QUERY_LIST_SOURCE_CONTRACT_MAX_DEPTH = 8
TRINO_COORDINATOR_QUERY_LIST_MAX_BYTES = 512 * 1024
TRINO_COORDINATOR_QUERY_LIST_MAX_DEPTH = 24
TRINO_COORDINATOR_QUERY_LIST_MAX_QUERY_IDS = 100
TRINO_COORDINATOR_QUERY_LIST_MAX_TIMEOUT_SECONDS = 60
TRINO_COORDINATOR_QUERY_LIST_TOP_LEVEL_KEYS = frozenset(
    {
        "source_contract_version",
        "source_type",
        "query_list_contract_version",
        "trino_version_family",
        "auth_reference",
        "query_bound",
        "bounds",
        "redaction",
    }
)
TRINO_COORDINATOR_QUERY_LIST_AUTH_KEYS = frozenset({"kind", "label"})
TRINO_COORDINATOR_QUERY_LIST_AUTH_KINDS = frozenset(
    {
        "external_secret_reference",
        "kerberos_service_reference",
        "operator_managed_reference",
        "tls_client_certificate_reference",
    }
)
TRINO_COORDINATOR_QUERY_LIST_QUERY_BOUND_KEYS = frozenset({"kind", "max_query_ids"})
TRINO_COORDINATOR_QUERY_LIST_BOUNDS_KEYS = frozenset(
    {"max_bytes", "max_query_list_depth", "timeout_seconds"}
)
TRINO_COORDINATOR_QUERY_LIST_REDACTION_KEYS = frozenset(
    {
        "redaction_review_required",
        "raw_payload_storage",
        "normalized_fact_storage",
        "browser_report_output",
    }
)
TRINO_COORDINATOR_QUERY_LIST_RECORD_KEYS = frozenset(
    {
        "queryId",
        "query_id",
        "id",
        "state",
        "createTime",
        "endTime",
        "updateTime",
        "queryStats",
        # Real Trino /v1/query?pruned=true responses include these fields.
        # They are accepted only so the collector can scrub them before the
        # normalized retained-list result; they must never be copied into
        # records, boundary payloads, reports, or browser surfaces.
        "query",
        "queryType",
        "resourceGroupId",
        "retryPolicy",
        "scheduled",
        "self",
        "session",
        "errorCode",
        "errorType",
    }
)
TRINO_COORDINATOR_QUERY_LIST_STATS_KEYS = frozenset(
    {
        "analysisTime",
        "blockedDrivers",
        "blockedReasons",
        "completedDrivers",
        "createTime",
        "elapsedTime",
        "endTime",
        "queuedTime",
        "planningTime",
        "executionTime",
        "totalCpuTime",
        "wallTime",
        "cumulativeUserMemory",
        "failedCpuTime",
        "failedCumulativeUserMemory",
        "failedScheduledTime",
        "finishingTime",
        "internalNetworkInputDataSize",
        "processedInputPositions",
        "processedInputDataSize",
        "physicalInputDataSize",
        "physicalInputReadTime",
        "physicalWrittenDataSize",
        "outputPositions",
        "outputDataSize",
        "peakTotalMemoryReservation",
        "peakUserMemoryReservation",
        "progressPercentage",
        "queuedDrivers",
        "resourceWaitingTime",
        "runningDrivers",
        "runningPercentage",
        "spilledDataSize",
        "fullyBlocked",
        "totalTasks",
        "totalDrivers",
        "totalMemoryReservation",
        "totalScheduledTime",
        "failedTasks",
        "userMemoryReservation",
    }
)
TRINO_COORDINATOR_QUERY_LIST_STATE_RE = re.compile(r"[A-Z_]{2,32}")


@dataclass(frozen=True)
class TrinoCoordinatorQueryListSourceContract:
    source_contract_version: str
    source_type: str
    query_list_contract_version: str
    trino_version_family: str
    auth_reference_kind: str
    auth_reference_label: str
    query_bound_kind: str
    max_query_ids: int
    max_bytes: int
    max_query_list_depth: int
    timeout_seconds: int
    raw_payload_storage: str
    normalized_fact_storage: str
    browser_report_output: str


@dataclass(frozen=True)
class TrinoCoordinatorQueryListRecord:
    query_id: str
    state: str
    create_time: datetime | None = None
    end_time: datetime | None = None
    update_time: datetime | None = None
    elapsed_ms: float | int | None = None


@dataclass(frozen=True)
class TrinoCoordinatorQueryListResult:
    source_contract: TrinoCoordinatorQueryListSourceContract
    endpoint_template: str
    pruned_query_parameter: bool
    records: tuple[TrinoCoordinatorQueryListRecord, ...]
    records_seen: int
    network_read_performed: bool


CoordinatorQueryListFetcher = Callable[..., str]


def load_trino_coordinator_query_list_source_contract(
    path: Path,
    *,
    max_file_bytes: int = TRINO_COORDINATOR_QUERY_LIST_SOURCE_CONTRACT_MAX_BYTES,
    max_contract_bytes: int = TRINO_COORDINATOR_QUERY_LIST_SOURCE_CONTRACT_MAX_BYTES,
    max_contract_depth: int = TRINO_COORDINATOR_QUERY_LIST_SOURCE_CONTRACT_MAX_DEPTH,
) -> TrinoCoordinatorQueryListSourceContract:
    payload = _read_coordinator_query_list_source_contract_payload(
        path,
        max_file_bytes=max_file_bytes,
    )
    return validate_trino_coordinator_query_list_source_contract_payload(
        payload,
        max_contract_bytes=max_contract_bytes,
        max_contract_depth=max_contract_depth,
    )


def load_trino_coordinator_query_list(
    source_contract_path: Path,
    *,
    coordinator_url: str,
    auth_headers: Mapping[str, str] | None = None,
    max_file_bytes: int = TRINO_COORDINATOR_QUERY_LIST_SOURCE_CONTRACT_MAX_BYTES,
    max_contract_bytes: int = TRINO_COORDINATOR_QUERY_LIST_SOURCE_CONTRACT_MAX_BYTES,
    max_contract_depth: int = TRINO_COORDINATOR_QUERY_LIST_SOURCE_CONTRACT_MAX_DEPTH,
    fetcher: CoordinatorQueryListFetcher | None = None,
) -> TrinoCoordinatorQueryListResult:
    source_contract = load_trino_coordinator_query_list_source_contract(
        source_contract_path,
        max_file_bytes=max_file_bytes,
        max_contract_bytes=max_contract_bytes,
        max_contract_depth=max_contract_depth,
    )
    return read_trino_coordinator_query_list(
        source_contract,
        coordinator_url=coordinator_url,
        auth_headers=auth_headers,
        fetcher=fetcher,
    )


def validate_trino_coordinator_query_list_source_contract_payload(
    payload: Mapping[str, Any],
    *,
    max_contract_bytes: int = TRINO_COORDINATOR_QUERY_LIST_SOURCE_CONTRACT_MAX_BYTES,
    max_contract_depth: int = TRINO_COORDINATOR_QUERY_LIST_SOURCE_CONTRACT_MAX_DEPTH,
) -> TrinoCoordinatorQueryListSourceContract:
    if not isinstance(payload, Mapping):
        raise EngineFactContractError("Trino coordinator query-list contract needs a JSON object")
    validate_contract_json_size(
        payload,
        max_contract_bytes=max_contract_bytes,
        payload_label="Trino coordinator query-list contract",
    )
    validate_contract_tree(
        payload,
        max_depth=max_contract_depth,
        payload_label="Trino coordinator query-list contract",
    )
    validate_exact_keys(
        payload,
        TRINO_COORDINATOR_QUERY_LIST_TOP_LEVEL_KEYS,
        "Trino coordinator query-list contract fields are unsupported",
    )
    source_contract_version = required_literal(
        payload,
        "source_contract_version",
        expected=TRINO_COORDINATOR_QUERY_LIST_SOURCE_CONTRACT_VERSION,
        message="Trino coordinator query-list contract version is unsupported",
    )
    source_type = required_literal(
        payload,
        "source_type",
        expected=TRINO_COORDINATOR_QUERY_LIST_SOURCE_TYPE,
        message="Trino coordinator query-list source type is unsupported",
    )
    query_list_contract_version = required_literal(
        payload,
        "query_list_contract_version",
        expected=TRINO_COORDINATOR_QUERY_LIST_CONTRACT_VERSION,
        message="Trino coordinator query-list target contract version is unsupported",
    )
    trino_version_family = required_text(
        payload,
        "trino_version_family",
        payload_label="Trino coordinator query-list contract",
    )
    if not TRINO_COORDINATOR_QUERY_INFO_VERSION_FAMILY_RE.fullmatch(trino_version_family):
        raise EngineFactContractError("Trino coordinator query-list version family is unsupported")

    auth_reference = mapping_required(
        payload,
        "auth_reference",
        "Trino coordinator query-list contract",
    )
    validate_exact_keys(
        auth_reference,
        TRINO_COORDINATOR_QUERY_LIST_AUTH_KEYS,
        "Trino coordinator query-list auth reference fields are unsupported",
    )
    auth_reference_kind = allowed_text(
        auth_reference,
        "kind",
        allowed=TRINO_COORDINATOR_QUERY_LIST_AUTH_KINDS,
        message="Trino coordinator query-list auth reference kind is unsupported",
        payload_label="Trino coordinator query-list contract",
    )
    auth_reference_label = safe_source_label(
        auth_reference,
        "label",
        message="Trino coordinator query-list auth reference label is not safe",
        payload_label="Trino coordinator query-list contract",
    )

    query_bound = mapping_required(payload, "query_bound", "Trino coordinator query-list contract")
    validate_exact_keys(
        query_bound,
        TRINO_COORDINATOR_QUERY_LIST_QUERY_BOUND_KEYS,
        "Trino coordinator query-list query-bound fields are unsupported",
    )
    query_bound_kind = required_literal(
        query_bound,
        "kind",
        expected="bounded_retained_query_list",
        message="Trino coordinator query-list query bound is unsupported",
    )
    max_query_ids = bounded_int(
        query_bound,
        "max_query_ids",
        upper=TRINO_COORDINATOR_QUERY_LIST_MAX_QUERY_IDS,
        message="Trino coordinator query-list query bound is out of bounds",
    )

    bounds = mapping_required(payload, "bounds", "Trino coordinator query-list contract")
    validate_exact_keys(
        bounds,
        TRINO_COORDINATOR_QUERY_LIST_BOUNDS_KEYS,
        "Trino coordinator query-list bounds fields are unsupported",
    )
    max_bytes = bounded_int(
        bounds,
        "max_bytes",
        upper=TRINO_COORDINATOR_QUERY_LIST_MAX_BYTES,
        message="Trino coordinator query-list max bytes is out of bounds",
    )
    max_query_list_depth = bounded_int(
        bounds,
        "max_query_list_depth",
        upper=TRINO_COORDINATOR_QUERY_LIST_MAX_DEPTH,
        message="Trino coordinator query-list depth is out of bounds",
    )
    timeout_seconds = bounded_int(
        bounds,
        "timeout_seconds",
        upper=TRINO_COORDINATOR_QUERY_LIST_MAX_TIMEOUT_SECONDS,
        message="Trino coordinator query-list timeout is out of bounds",
    )

    redaction_contract = mapping_required(
        payload,
        "redaction",
        "Trino coordinator query-list contract",
    )
    validate_exact_keys(
        redaction_contract,
        TRINO_COORDINATOR_QUERY_LIST_REDACTION_KEYS,
        "Trino coordinator query-list redaction fields are unsupported",
    )
    required_boolean(
        redaction_contract,
        "redaction_review_required",
        expected=True,
        message="Trino coordinator query-list redaction review must be required",
    )
    raw_payload_storage = required_literal(
        redaction_contract,
        "raw_payload_storage",
        expected="forbidden",
        message="Trino coordinator query-list raw payload storage must be forbidden",
    )
    normalized_fact_storage = required_literal(
        redaction_contract,
        "normalized_fact_storage",
        expected="allowed",
        message="Trino coordinator query-list normalized fact storage must be allowed",
    )
    browser_report_output = required_literal(
        redaction_contract,
        "browser_report_output",
        expected="blocked",
        message="Trino coordinator query-list browser/report output must be blocked",
    )
    return TrinoCoordinatorQueryListSourceContract(
        source_contract_version=source_contract_version,
        source_type=source_type,
        query_list_contract_version=query_list_contract_version,
        trino_version_family=trino_version_family,
        auth_reference_kind=auth_reference_kind,
        auth_reference_label=auth_reference_label,
        query_bound_kind=query_bound_kind,
        max_query_ids=max_query_ids,
        max_bytes=max_bytes,
        max_query_list_depth=max_query_list_depth,
        timeout_seconds=timeout_seconds,
        raw_payload_storage=raw_payload_storage,
        normalized_fact_storage=normalized_fact_storage,
        browser_report_output=browser_report_output,
    )


def read_trino_coordinator_query_list(
    source_contract: TrinoCoordinatorQueryListSourceContract,
    *,
    coordinator_url: str,
    auth_headers: Mapping[str, str] | None = None,
    fetcher: CoordinatorQueryListFetcher | None = None,
) -> TrinoCoordinatorQueryListResult:
    validate_trino_coordinator_query_list_source_contract(source_contract)
    _validate_coordinator_base_url(coordinator_url)
    selected_fetcher = fetch_trino_coordinator_pruned_query_list_text
    if fetcher is not None:
        selected_fetcher = fetcher
    text = _fetch_query_list_text(
        selected_fetcher,
        coordinator_url,
        max_bytes=source_contract.max_bytes,
        timeout_seconds=source_contract.timeout_seconds,
        auth_headers=auth_headers,
    )
    payload = parse_trino_coordinator_pruned_query_list_payload(
        text,
        max_query_list_depth=source_contract.max_query_list_depth,
    )
    records = _query_list_records(payload, max_query_ids=source_contract.max_query_ids)
    return TrinoCoordinatorQueryListResult(
        source_contract=source_contract,
        endpoint_template=TRINO_COORDINATOR_QUERY_LIST_ENDPOINT_TEMPLATE,
        pruned_query_parameter=True,
        records=records,
        records_seen=len(records),
        network_read_performed=True,
    )


def validate_trino_coordinator_query_list_source_contract(
    source_contract: TrinoCoordinatorQueryListSourceContract,
) -> None:
    if source_contract.source_type != TRINO_COORDINATOR_QUERY_LIST_SOURCE_TYPE:
        raise EngineFactContractError("Trino coordinator query-list source type is unsupported")
    if source_contract.auth_reference_kind != TRINO_COORDINATOR_QUERY_INFO_PRUNED_AUTH_KIND:
        raise EngineFactContractError("Trino coordinator query-list auth reference is unsupported")
    if source_contract.query_bound_kind != "bounded_retained_query_list":
        raise EngineFactContractError("Trino coordinator query-list query bound is unsupported")
    if source_contract.raw_payload_storage != "forbidden":
        raise EngineFactContractError(
            "Trino coordinator query-list raw payload storage is unsupported"
        )
    if source_contract.normalized_fact_storage != "allowed":
        raise EngineFactContractError(
            "Trino coordinator query-list normalized fact storage is unsupported"
        )
    if source_contract.browser_report_output != "blocked":
        raise EngineFactContractError(
            "Trino coordinator query-list browser/report output is blocked"
        )


def load_trino_coordinator_query_list_auth_header_file(
    path: Path,
    *,
    max_file_bytes: int = TRINO_COORDINATOR_QUERY_INFO_AUTH_HEADER_MAX_BYTES,
) -> dict[str, str]:
    return load_trino_coordinator_query_info_auth_header_file(path, max_file_bytes=max_file_bytes)


def fetch_trino_coordinator_pruned_query_list_text(
    coordinator_url: str,
    *,
    max_bytes: int,
    timeout_seconds: int,
    auth_headers: Mapping[str, str] | None = None,
) -> str:
    if max_bytes < 1:
        raise EngineFactContractError("Trino coordinator query-list byte limit must be positive")
    if timeout_seconds < 1:
        raise EngineFactContractError("Trino coordinator query-list timeout must be positive")
    _validate_coordinator_base_url(coordinator_url)
    request = Request(
        _build_pruned_query_list_url(coordinator_url),
        headers=_request_headers(auth_headers),
    )
    try:
        from query_doctor.safety.http_egress import configured_diagnostic_urlopen

        with configured_diagnostic_urlopen(request, timeout=timeout_seconds) as response:
            body = response.read(max_bytes + 1)
    except HTTPError as exc:
        if exc.code in {401, 403}:
            raise EngineFactContractError(
                "Trino coordinator query-list authentication was rejected; refresh the operator-managed auth reference or ticket"
            ) from exc
        raise EngineFactContractError("Trino coordinator query-list could not be read") from exc
    except (OSError, TimeoutError, URLError) as exc:
        raise EngineFactContractError("Trino coordinator query-list could not be read") from exc
    if len(body) > max_bytes:
        raise EngineFactContractError("Trino coordinator query-list payload is too large")
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EngineFactContractError("Trino coordinator query-list must be UTF-8 JSON") from exc


def parse_trino_coordinator_pruned_query_list_payload(
    text: str,
    *,
    max_query_list_depth: int,
) -> Sequence[Mapping[str, Any]]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise EngineFactContractError("Trino coordinator query-list is not valid JSON") from exc
    validate_contract_tree(
        parsed,
        max_depth=max_query_list_depth,
        payload_label="Trino coordinator query-list",
    )
    if isinstance(parsed, list):
        return tuple(_mapping_record(item) for item in parsed)
    if (
        isinstance(parsed, Mapping)
        and set(parsed) == {"queries"}
        and isinstance(parsed["queries"], list)
    ):
        return tuple(_mapping_record(item) for item in parsed["queries"])
    raise EngineFactContractError("Trino coordinator query-list needs a JSON array")


def _request_headers(auth_headers: Mapping[str, str] | None) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if auth_headers is not None:
        headers.update(_request_auth_headers(auth_headers))
    return headers


def _request_auth_headers(auth_headers: Mapping[str, str]) -> dict[str, str]:
    return _query_info_request_auth_headers(auth_headers)


def _fetch_query_list_text(
    fetcher: CoordinatorQueryListFetcher,
    coordinator_url: str,
    *,
    max_bytes: int,
    timeout_seconds: int,
    auth_headers: Mapping[str, str] | None,
) -> str:
    kwargs: dict[str, Any] = {
        "max_bytes": max_bytes,
        "timeout_seconds": timeout_seconds,
    }
    if auth_headers is not None:
        kwargs["auth_headers"] = _request_auth_headers(auth_headers)
    try:
        return fetcher(coordinator_url, **kwargs)
    except EngineFactContractError:
        raise
    except (OSError, TimeoutError, URLError) as exc:
        raise EngineFactContractError("Trino coordinator query-list could not be read") from exc


def _build_pruned_query_list_url(coordinator_url: str) -> str:
    parsed = urlsplit(coordinator_url)
    path = f"{parsed.path.rstrip('/')}/v1/query"
    return urlunsplit((parsed.scheme, parsed.netloc, path, urlencode({"pruned": "true"}), ""))


def _read_coordinator_query_list_source_contract_payload(
    path: Path,
    *,
    max_file_bytes: int,
) -> Mapping[str, Any]:
    if max_file_bytes < 1:
        raise EngineFactContractError(
            "Trino coordinator query-list contract file limit must be positive"
        )
    if path.stat().st_size > max_file_bytes:
        raise EngineFactContractError("Trino coordinator query-list contract file is too large")
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EngineFactContractError(
            "Trino coordinator query-list contract is not valid JSON"
        ) from exc
    if not isinstance(parsed, Mapping):
        raise EngineFactContractError("Trino coordinator query-list contract needs a JSON object")
    return parsed


def _query_list_records(
    payload: Sequence[Mapping[str, Any]],
    *,
    max_query_ids: int,
) -> tuple[TrinoCoordinatorQueryListRecord, ...]:
    if len(payload) > max_query_ids:
        raise EngineFactContractError("Trino coordinator query-list returned too many records")
    records: list[TrinoCoordinatorQueryListRecord] = []
    seen: set[str] = set()
    for item in payload:
        if not set(item).issubset(TRINO_COORDINATOR_QUERY_LIST_RECORD_KEYS):
            raise EngineFactContractError("Trino coordinator query-list fields are unsupported")
        stats = item.get("queryStats")
        if not isinstance(stats, Mapping):
            raise EngineFactContractError("Trino coordinator query-list queryStats is unsupported")
        if not set(stats).issubset(TRINO_COORDINATOR_QUERY_LIST_STATS_KEYS):
            raise EngineFactContractError(
                "Trino coordinator query-list queryStats fields are unsupported"
            )
        query_id = _query_id(item)
        if query_id in seen:
            continue
        seen.add(query_id)
        state = _state(item.get("state"))
        records.append(
            TrinoCoordinatorQueryListRecord(
                query_id=query_id,
                state=state,
                create_time=_timestamp_or_none(item.get("createTime") or stats.get("createTime")),
                end_time=_timestamp_or_none(item.get("endTime") or stats.get("endTime")),
                update_time=_timestamp_or_none(item.get("updateTime") or stats.get("updateTime")),
                elapsed_ms=_duration_millis_or_none(stats.get("elapsedTime")),
            )
        )
    return tuple(records)


def _mapping_record(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EngineFactContractError("Trino coordinator query-list records must be JSON objects")
    return value


def _query_id(item: Mapping[str, Any]) -> str:
    value = item.get("queryId") or item.get("query_id") or item.get("id")
    if not isinstance(value, str) or TRINO_COORDINATOR_QUERY_ID_RE.fullmatch(value) is None:
        raise EngineFactContractError("Trino coordinator query-list Query ID is unsupported")
    return value


def _state(value: Any) -> str:
    if not isinstance(value, str):
        return "UNKNOWN"
    normalized = value.strip().upper().replace("-", "_")
    if TRINO_COORDINATOR_QUERY_LIST_STATE_RE.fullmatch(normalized) is None:
        return "UNKNOWN"
    return normalized


def _timestamp_or_none(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    text = _truncate_iso_fraction_to_microseconds(text)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _truncate_iso_fraction_to_microseconds(text: str) -> str:
    match = re.fullmatch(r"(.+T\d{2}:\d{2}:\d{2})\.(\d+)([+-]\d{2}:\d{2})", text)
    if match is None or len(match.group(2)) <= 6:
        return text
    return f"{match.group(1)}.{match.group(2)[:6]}{match.group(3)}"


def _duration_millis_or_none(value: Any) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value if value >= 0 else None
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"\s*([+]?(?:\d+(?:\.\d*)?|\.\d+))\s*([A-Za-z]+)\s*", value)
    if match is None:
        return None
    number = float(match.group(1))
    unit = match.group(2).lower()
    factors = {
        "ns": 0.000001,
        "us": 0.001,
        "ms": 1.0,
        "s": 1000.0,
        "m": 60_000.0,
        "h": 3_600_000.0,
        "d": 86_400_000.0,
    }
    factor = factors.get(unit)
    if factor is None:
        return None
    value_ms = number * factor
    return int(value_ms) if value_ms.is_integer() else value_ms
