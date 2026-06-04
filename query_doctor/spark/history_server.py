"""Bounded Spark History Server compact summary collection.

This module collects only summary-level REST JSON from Spark's `/api/v1`
surface and emits a raw-free compact payload for the Spark fact contract. It
does not download event logs, fetch environment/configuration dumps, request
SQL plan descriptions, execute Spark jobs, or register Spark as a supported
Query Doctor engine.
"""

from __future__ import annotations

import json
import ipaddress
import re
import urllib.error
import urllib.request
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import quote, urlencode, urlsplit, urlunsplit

from query_doctor.analyzer.spark_fixture_schema import (
    SPARK_FAILURE_CATEGORIES,
    SPARK_HISTORY_COMPACT_FIXTURE_MAX_JSON_BYTES,
    SPARK_HISTORY_SERVER_COMPACT_SOURCE_CONTRACT,
    SPARK_HISTORY_SERVER_MAX_RESPONSE_BYTES,
    validate_spark_history_server_compact_payload,
)
from query_doctor.cm.models import CMAdapterError, CMClientError
from query_doctor.safety.http_egress import (
    NoRedirectHandler,
    UnsafeHttpTargetError,
    configured_diagnostic_urlopen,
    public_urlopen_no_redirect,
)


DEFAULT_SPARK_HISTORY_TIMEOUT_SEC = 15
DEFAULT_MAX_SPARK_HISTORY_RESPONSE_BYTES = 2 * 1024 * 1024
DEFAULT_SPARK_HISTORY_MAX_SQL_EXECUTIONS = 10
DEFAULT_SPARK_HISTORY_MAX_APPLICATION_ATTEMPTS = 16
DEFAULT_SPARK_HISTORY_MAX_JOBS = 200
DEFAULT_SPARK_HISTORY_MAX_STAGES = 500
DEFAULT_SPARK_HISTORY_MAX_TASK_SUMMARIES = 32
DEFAULT_SPARK_HISTORY_MAX_TASKS_SAMPLED = 256
SPARK_HISTORY_SKEW_RATIO_THRESHOLD = 3.0
SPARK_TASK_DURATION_BUCKET_KEYS = (
    "under_1s",
    "1s_to_10s",
    "10s_to_1m",
    "over_1m",
)
SPARK_HISTORY_BLOCKED_HOSTNAMES = frozenset(
    {
        "metadata",
    }
)
SPARK_HISTORY_BLOCKED_METADATA_SUFFIX = ".".join(("metadata", "google", "internal"))
SPARK_HISTORY_BLOCKED_TARGET_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in (
        "0.0.0.0/8",
        "169.254.0.0/16",
        "192.0.2.0/24",
        "198.18.0.0/15",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "224.0.0.0/4",
        "240.0.0.0/4",
        "::/128",
        "2001:db8::/32",
        "fe80::/10",
        "ff00::/8",
    )
)
SPARK_HISTORY_LOCAL_TARGET_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in (
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "::1/128",
        "fc00::/7",
    )
)

UrlOpener = Callable[..., Any]


class SparkHistoryNoRedirectHandler(NoRedirectHandler):
    """Disable redirects so every Spark target hop is explicitly selected."""


def spark_history_urlopen_no_redirect(request: Any, *, timeout: int) -> Any:
    return public_urlopen_no_redirect(request, timeout=timeout)


def spark_history_urlopen_allow_local_no_redirect(request: Any, *, timeout: int) -> Any:
    return configured_diagnostic_urlopen(request, timeout=timeout)


@dataclass(frozen=True)
class SparkHistoryServerCompactResult:
    payload: dict[str, Any]
    warnings: tuple[str, ...]
    attempted_endpoints: int
    successful_endpoints: int


@dataclass(frozen=True)
class SparkHistoryServerClient:
    base_url: str
    timeout_sec: int = DEFAULT_SPARK_HISTORY_TIMEOUT_SEC
    max_response_bytes: int = DEFAULT_MAX_SPARK_HISTORY_RESPONSE_BYTES
    allow_local_targets: bool = False
    opener: UrlOpener = spark_history_urlopen_no_redirect

    def build_url(
        self,
        segments: Iterable[str],
        *,
        params: Mapping[str, object] | None = None,
    ) -> str:
        parsed = normalized_history_base_url(
            self.base_url,
            allow_local_targets=self.allow_local_targets,
        )
        base_path = parsed.path.rstrip("/")
        if base_path.endswith("/api/v1"):
            api_path = base_path
        else:
            api_path = f"{base_path}/api/v1" if base_path else "/api/v1"
        path = "/".join(
            [api_path.rstrip("/"), *[safe_path_segment(segment) for segment in segments]]
        )
        query = urlencode({key: str(value) for key, value in (params or {}).items()})
        return urlunsplit((parsed.scheme, parsed.netloc, path, query, ""))

    def get_json(
        self,
        segments: Iterable[str],
        *,
        params: Mapping[str, object] | None = None,
    ) -> Any:
        url = self.build_url(segments, params=params)
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        opener = self.opener
        if opener is spark_history_urlopen_no_redirect and self.allow_local_targets:
            opener = spark_history_urlopen_allow_local_no_redirect
        try:
            with opener(request, timeout=self.timeout_sec) as response:
                raw = response.read(self.max_response_bytes + 1)
        except UnsafeHttpTargetError as exc:
            raise CMAdapterError(spark_history_target_error_message(exc)) from exc
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
            raise CMClientError("Spark History Server endpoint request failed safely.") from exc
        if len(raw) > self.max_response_bytes:
            raise CMClientError(
                "Spark History Server endpoint response exceeded the configured byte limit."
            )
        text = raw.decode("utf-8", errors="replace")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise CMClientError("Spark History Server endpoint did not return JSON.") from exc


def normalized_history_base_url(base_url: str, *, allow_local_targets: bool = False):
    parsed = urlsplit(base_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise CMAdapterError("Spark History Server URL must be an http or https base URL.")
    if parsed.username or parsed.password:
        raise CMAdapterError("Spark History Server URL must not contain credentials.")
    if parsed.query or parsed.fragment:
        raise CMAdapterError("Spark History Server URL must not contain query or fragment parts.")
    try:
        parsed.port
    except ValueError as exc:
        raise CMAdapterError("Spark History Server URL port must be valid.") from exc
    validate_history_server_target_host(
        parsed.hostname,
        allow_local_targets=allow_local_targets,
    )
    return parsed


def validate_history_server_target_host(
    host: str | None,
    *,
    allow_local_targets: bool,
) -> None:
    if not host:
        raise CMAdapterError("Spark History Server URL must include a host.")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in host):
        raise CMAdapterError("Spark History Server URL host must not contain controls.")
    normalized_host = host.rstrip(".").lower()
    if "%" in normalized_host:
        raise CMAdapterError("Spark History Server URL target is not allowed.")
    if (
        normalized_host in SPARK_HISTORY_BLOCKED_HOSTNAMES
        or normalized_host == SPARK_HISTORY_BLOCKED_METADATA_SUFFIX
        or normalized_host.endswith(f".{SPARK_HISTORY_BLOCKED_METADATA_SUFFIX}")
    ):
        raise CMAdapterError("Spark History Server URL target is not allowed.")
    if normalized_host == "localhost" or normalized_host.endswith(".localhost"):
        if not allow_local_targets:
            raise CMAdapterError(
                "Spark History Server local or private targets require explicit opt-in."
            )
        return
    try:
        target_ip = ipaddress.ip_address(normalized_host)
    except ValueError:
        return
    mapped_ipv4 = getattr(target_ip, "ipv4_mapped", None)
    if mapped_ipv4 is not None:
        target_ip = mapped_ipv4
    if _ip_in_networks(target_ip, SPARK_HISTORY_BLOCKED_TARGET_NETWORKS):
        raise CMAdapterError("Spark History Server URL target is not allowed.")
    if _ip_in_networks(target_ip, SPARK_HISTORY_LOCAL_TARGET_NETWORKS):
        if not allow_local_targets:
            raise CMAdapterError(
                "Spark History Server local or private targets require explicit opt-in."
            )


def spark_history_target_error_message(error: UnsafeHttpTargetError) -> str:
    message = str(error)
    if "loopback target requires explicit opt-in" in message:
        return "Spark History Server local or private targets require explicit opt-in."
    if "private target requires explicit opt-in" in message:
        return "Spark History Server local or private targets require explicit opt-in."
    if "could not be resolved" in message or "did not resolve" in message:
        return "Spark History Server URL target could not be resolved safely."
    return "Spark History Server URL target is not allowed."


def _ip_in_networks(
    value: ipaddress.IPv4Address | ipaddress.IPv6Address,
    networks: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...],
) -> bool:
    return any(value.version == network.version and value in network for network in networks)


def safe_path_segment(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CMAdapterError("Spark History Server path segment is required.")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise CMAdapterError("Spark History Server path segment must not contain controls.")
    if value in {".", ".."}:
        raise CMAdapterError("Spark History Server path segment must not traverse paths.")
    return quote(value, safe="")


def application_path_segments(application_id: str) -> tuple[str, ...]:
    segments = tuple(part for part in application_id.strip().split("/") if part)
    if not segments:
        raise CMAdapterError("Spark application id is required.")
    if any(part in {".", ".."} for part in segments):
        raise CMAdapterError("Spark application id must not traverse paths.")
    return segments


def collect_spark_history_server_compact_summary(
    *,
    history_server_url: str,
    application_id: str,
    sql_execution_id: str | None = None,
    timeout_sec: int = DEFAULT_SPARK_HISTORY_TIMEOUT_SEC,
    max_response_bytes: int = DEFAULT_MAX_SPARK_HISTORY_RESPONSE_BYTES,
    max_application_attempts: int = DEFAULT_SPARK_HISTORY_MAX_APPLICATION_ATTEMPTS,
    max_sql_executions: int = DEFAULT_SPARK_HISTORY_MAX_SQL_EXECUTIONS,
    max_jobs: int = DEFAULT_SPARK_HISTORY_MAX_JOBS,
    max_stages: int = DEFAULT_SPARK_HISTORY_MAX_STAGES,
    max_task_summaries: int = DEFAULT_SPARK_HISTORY_MAX_TASK_SUMMARIES,
    max_tasks_sampled: int = DEFAULT_SPARK_HISTORY_MAX_TASKS_SAMPLED,
    allow_local_targets: bool = False,
    opener: UrlOpener = spark_history_urlopen_no_redirect,
) -> SparkHistoryServerCompactResult:
    if (
        max_application_attempts <= 0
        or max_sql_executions <= 0
        or max_jobs <= 0
        or max_stages <= 0
        or max_task_summaries <= 0
        or max_tasks_sampled <= 0
        or max_response_bytes <= 0
    ):
        raise CMAdapterError("Spark History Server collection bounds must be positive.")
    if max_response_bytes > SPARK_HISTORY_SERVER_MAX_RESPONSE_BYTES:
        raise CMAdapterError("Spark History Server response byte bound exceeds the compact cap.")
    client = SparkHistoryServerClient(
        history_server_url,
        timeout_sec=timeout_sec,
        max_response_bytes=max_response_bytes,
        allow_local_targets=allow_local_targets,
        opener=opener,
    )
    app_segments = application_path_segments(application_id)

    warnings: list[str] = []
    attempted = 0
    successful = 0

    version, ok = _optional_json(client, ("version",), warnings, "version")
    attempted += 1
    successful += int(ok)

    application_payload, ok = _optional_json(
        client,
        ("applications", *app_segments),
        warnings,
        "application",
    )
    attempted += 1
    successful += int(ok)

    sql_payload: Any
    if sql_execution_id:
        sql_segments = ("applications", *app_segments, "sql", sql_execution_id)
        sql_params = {"details": "false", "planDescription": "false"}
    else:
        sql_segments = ("applications", *app_segments, "sql")
        sql_params = {
            "details": "false",
            "planDescription": "false",
            "offset": 0,
            "length": max_sql_executions,
        }
    sql_payload, ok = _optional_json(client, sql_segments, warnings, "sql", params=sql_params)
    attempted += 1
    successful += int(ok)

    jobs_payload, ok = _optional_json(
        client,
        ("applications", *app_segments, "jobs"),
        warnings,
        "jobs",
    )
    attempted += 1
    successful += int(ok)

    stages_payload, ok = _optional_json(
        client,
        ("applications", *app_segments, "stages"),
        warnings,
        "stages",
        params={"withSummaries": "true", "quantiles": "0.0,0.5,1.0"},
    )
    attempted += 1
    successful += int(ok)

    executors_payload, ok = _optional_json(
        client,
        ("applications", *app_segments, "allexecutors"),
        warnings,
        "executors",
    )
    attempted += 1
    successful += int(ok)

    if successful == 0:
        raise CMAdapterError(
            "Spark History Server compact collection did not find a readable JSON endpoint."
        )

    selected_sql = select_sql_execution(sql_payload, sql_execution_id=sql_execution_id)
    if sql_execution_id and not selected_sql:
        warnings.append("spark_history_sql_execution_not_found")
    requested_job_ids = linked_job_ids(selected_sql)
    jobs = summarize_jobs(jobs_payload, requested_job_ids=requested_job_ids, max_jobs=max_jobs)
    summarized_job_ids = jobs.pop("_summarized_job_ids")
    summarized_stage_ids = jobs.pop("_summarized_stage_ids")
    stage_filter_job_ids = summarized_job_ids or requested_job_ids
    sql = summarize_sql_execution(selected_sql, linked_job_count=len(stage_filter_job_ids))
    stages = summarize_stages(
        stages_payload,
        requested_job_ids=stage_filter_job_ids,
        requested_stage_ids=summarized_stage_ids,
        max_stages=max_stages,
        max_tasks_sampled=max_tasks_sampled,
    )
    task_summary_payloads, task_summary_warning, task_summary_attempted, task_summary_successful = (
        collect_stage_task_summaries(
            client,
            app_segments,
            stages["stage_records"],
            max_task_summaries=max_task_summaries,
        )
    )
    attempted += task_summary_attempted
    successful += task_summary_successful
    if task_summary_warning:
        warnings.append(task_summary_warning)
    if task_summary_payloads:
        stages = attach_stage_task_summaries(
            stages,
            task_summary_payloads,
            max_tasks_sampled=max_tasks_sampled,
        )
    tasks = summarize_tasks(stages, max_tasks_sampled=max_tasks_sampled)
    executors = summarize_executors(executors_payload)
    application, application_warning = summarize_application(
        application_payload,
        max_application_attempts=max_application_attempts,
    )
    if application_warning:
        warnings.append(application_warning)
    query_linkage = "exact_query" if sql_execution_id and selected_sql else "same_application"

    payload = {
        "fixtureVersion": "spark_history_server_compact_v1",
        "sourceContract": SPARK_HISTORY_SERVER_COMPACT_SOURCE_CONTRACT,
        "provenance": {
            "fixtureProvenance": "live_history_server",
            "sparkVersionFamily": spark_version_family(version),
            "exportSurface": "compact_history_server_summary",
            "redactionStatus": "raw_free",
            "queryLinkage": query_linkage,
            "freshness": "unknown",
            "timeWindow": "explicit_application",
            "bounds": {
                "maxApplications": 1,
                "maxApplicationAttempts": max_application_attempts,
                "maxSqlExecutions": max_sql_executions,
                "maxJobs": max_jobs,
                "maxStages": max_stages,
                "maxTaskSummaries": max_task_summaries,
                "maxTasksSampled": max_tasks_sampled,
                "maxJsonBytes": SPARK_HISTORY_COMPACT_FIXTURE_MAX_JSON_BYTES,
                "maxResponseBytes": max_response_bytes,
            },
        },
        "sourceCoverage": spark_history_source_coverage(warnings, attempted, successful),
        "application": application,
        "sqlExecution": sql,
        "jobs": jobs,
        "stages": stages["summary"],
        "tasks": tasks,
        "executors": executors,
        "redaction": {
            "eventLogRecords": "not_written",
            "sqlText": "not_written",
            "planText": "not_written",
            "driverLogs": "not_written",
            "executorLogs": "not_written",
            "runtimeIds": "not_written",
            "paths": "not_written",
            "environmentValues": "not_written",
            "generatedArtifacts": "not_written",
        },
        "limitations": spark_history_server_limitations(executors, warnings),
    }
    validate_spark_history_server_compact_payload(payload)
    return SparkHistoryServerCompactResult(
        payload=payload,
        warnings=tuple(warnings),
        attempted_endpoints=attempted,
        successful_endpoints=successful,
    )


def _optional_json(
    client: SparkHistoryServerClient,
    segments: Iterable[str],
    warnings: list[str],
    label: str,
    *,
    params: Mapping[str, object] | None = None,
) -> tuple[Any, bool]:
    try:
        return client.get_json(segments, params=params), True
    except CMAdapterError:
        raise
    except CMClientError:
        warnings.append(f"spark_history_{label}_unavailable")
        return None, False


def collect_stage_task_summaries(
    client: SparkHistoryServerClient,
    app_segments: tuple[str, ...],
    stage_records: Iterable[Any],
    *,
    max_task_summaries: int,
) -> tuple[dict[tuple[str, str], Mapping[str, Any]], str | None, int, int]:
    summaries: dict[tuple[str, str], Mapping[str, Any]] = {}
    attempted = 0
    successful = 0
    failed = False
    for stage in stage_records:
        if attempted >= max_task_summaries:
            break
        if not isinstance(stage, Mapping):
            continue
        selector = stage_attempt_selector(stage)
        if selector is None:
            continue
        attempted += 1
        stage_id_value, attempt_id_value = selector
        try:
            payload = client.get_json(
                (
                    "applications",
                    *app_segments,
                    "stages",
                    stage_id_value,
                    attempt_id_value,
                    "taskSummary",
                ),
                params={"quantiles": "0.0,0.5,1.0"},
            )
        except CMAdapterError:
            raise
        except CMClientError:
            failed = True
            continue
        successful += 1
        if isinstance(payload, Mapping):
            summaries[selector] = payload
        else:
            failed = True
    warning = "spark_history_task_summary_unavailable" if failed else None
    return summaries, warning, attempted, successful


def attach_stage_task_summaries(
    stages_summary: Mapping[str, Any],
    task_summary_payloads: Mapping[tuple[str, str], Mapping[str, Any]],
    *,
    max_tasks_sampled: int,
) -> dict[str, Any]:
    records: list[Any] = []
    for stage in tuple(stages_summary.get("stage_records") or ()):
        if not isinstance(stage, Mapping):
            records.append(stage)
            continue
        selector = stage_attempt_selector(stage)
        task_summary = task_summary_payloads.get(selector) if selector is not None else None
        if task_summary is None or task_runtime_quantiles(stage) is not None:
            records.append(stage)
            continue
        merged = dict(stage)
        merged["taskMetricsDistributions"] = task_summary
        records.append(merged)
    summary = dict(stages_summary.get("summary") or {})
    summary["skewSummary"] = summarize_stage_skew(
        [stage for stage in records if isinstance(stage, Mapping)],
        max_tasks_sampled=max_tasks_sampled,
    )
    return {
        "summary": summary,
        "stage_records": tuple(records),
        "taskCount": _int_or_zero(stages_summary.get("taskCount")),
        "failedTaskCount": _int_or_zero(stages_summary.get("failedTaskCount")),
    }


def select_sql_execution(payload: Any, *, sql_execution_id: str | None) -> Mapping[str, Any]:
    if isinstance(payload, Mapping):
        return payload
    candidates = [item for item in _as_list(payload) if isinstance(item, Mapping)]
    if not candidates:
        return {}
    if sql_execution_id is not None:
        for item in candidates:
            if str(_first_present(item, ("id", "executionId", "execution_id"))) == sql_execution_id:
                return item
        return {}
    return max(candidates, key=lambda item: _number_or_zero(_duration_ms(item)))


def summarize_sql_execution(
    sql_execution: Mapping[str, Any],
    *,
    linked_job_count: int,
) -> dict[str, Any]:
    if not sql_execution:
        return {
            "factState": "unknown",
            "lifecycle": "unknown",
            "failureCategoryState": "unknown",
            "failureCategory": "unknown",
            "elapsedTimeMillis": 0,
            "linkedJobCount": 0,
            "planShapeCoverage": "not_collected",
            "adaptiveExecution": {"checked": False, "enabled": False, "planChanged": False},
        }
    elapsed = _duration_ms(sql_execution)
    status = _first_present(sql_execution, ("status", "state"))
    lifecycle = spark_lifecycle(status)
    fact_state = "supported" if elapsed is not None or lifecycle != "unknown" else "unknown"
    category_state, category = summarize_failure_category(
        sql_execution,
        status=status,
        lifecycle=lifecycle,
        fact_state=fact_state,
    )
    return {
        "factState": fact_state,
        "lifecycle": lifecycle,
        "failureCategoryState": category_state,
        "failureCategory": category,
        "elapsedTimeMillis": elapsed or 0,
        "linkedJobCount": linked_job_count,
        "planShapeCoverage": "not_collected",
        "adaptiveExecution": summarize_adaptive_execution(sql_execution),
    }


def summarize_failure_category(
    sql_execution: Mapping[str, Any],
    *,
    status: Any,
    lifecycle: str,
    fact_state: str,
) -> tuple[str, str]:
    if fact_state != "supported" or lifecycle == "unknown":
        return "unknown", "unknown"
    if lifecycle != "failed":
        return "not_observed", "none"

    explicit = _first_present(
        sql_execution,
        ("failureCategory", "failure_category", "failureClassification"),
    )
    category = spark_failure_category(explicit)
    if category is not None:
        return "supported", category
    if str(status or "").strip().lower() == "killed":
        return "supported", "cancelled"
    return "unknown", "unknown"


def spark_failure_category(value: Any) -> str | None:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if text in SPARK_FAILURE_CATEGORIES:
        return text
    return None


def summarize_adaptive_execution(sql_execution: Mapping[str, Any]) -> dict[str, bool]:
    nested = sql_execution.get("adaptiveExecution")
    if isinstance(nested, Mapping):
        checked = _boolean_marker(nested, ("checked", "adaptiveExecutionChecked"))
        if checked is False:
            return {"checked": False, "enabled": False, "planChanged": False}
        parsed = _adaptive_execution_markers(nested)
        if parsed["checked"]:
            return parsed

    checked = _boolean_marker(sql_execution, ("adaptiveExecutionChecked",))
    if checked is False:
        return {"checked": False, "enabled": False, "planChanged": False}
    return _adaptive_execution_markers(sql_execution)


def _adaptive_execution_markers(raw: Mapping[str, Any]) -> dict[str, bool]:
    enabled = _boolean_marker(
        raw,
        (
            "enabled",
            "adaptiveExecutionEnabled",
            "adaptiveEnabled",
            "isAdaptive",
        ),
    )
    plan_changed = _boolean_marker(
        raw,
        (
            "planChanged",
            "adaptivePlanChanged",
            "adaptiveExecutionPlanChanged",
        ),
    )
    if enabled is None or plan_changed is None:
        return {"checked": False, "enabled": False, "planChanged": False}
    return {"checked": True, "enabled": enabled, "planChanged": plan_changed}


def _boolean_marker(raw: Mapping[str, Any], keys: tuple[str, ...]) -> bool | None:
    value = _first_present(raw, keys)
    return value if isinstance(value, bool) else None


def summarize_application(
    payload: Any,
    *,
    max_application_attempts: int,
) -> tuple[dict[str, Any], str | None]:
    application = select_application(payload)
    if not application:
        return _unknown_application_summary(), None
    attempts = application_attempts(application)
    if not attempts:
        return _unknown_application_summary(), None
    if len(attempts) > max_application_attempts:
        return _unknown_application_summary(), "spark_history_application_attempts_exceeded_bounds"
    attempt_count = len(attempts)
    attempt_state = summarize_application_attempt_state(attempts)
    lifecycle = lifecycle_from_summary(application)
    if lifecycle == "unknown":
        lifecycle = attempt_state
    return (
        {
            "factState": "supported",
            "lifecycle": lifecycle,
            "attemptState": attempt_state,
            "attemptCount": attempt_count,
        },
        None,
    )


def select_application(payload: Any) -> Mapping[str, Any]:
    if isinstance(payload, Mapping):
        return payload
    candidates = [item for item in _as_list(payload) if isinstance(item, Mapping)]
    return candidates[0] if candidates else {}


def application_attempts(application: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    attempts = application.get("attempts")
    if isinstance(attempts, list):
        return tuple(item for item in attempts if isinstance(item, Mapping))
    return ()


def summarize_application_attempt_state(attempts: tuple[Mapping[str, Any], ...]) -> str:
    states = tuple(lifecycle_from_summary(attempt) for attempt in attempts)
    if not states:
        return "unknown"
    if any(state == "running" for state in states):
        return "running"
    if any(state == "failed" for state in states):
        return "failed"
    if all(state == "finished" for state in states):
        return "finished"
    return "unknown"


def lifecycle_from_summary(payload: Mapping[str, Any]) -> str:
    lifecycle = spark_lifecycle(
        _first_present(payload, ("status", "state", "attemptState", "lifecycle"))
    )
    if lifecycle != "unknown":
        return lifecycle
    completed = _first_present(payload, ("completed", "complete"))
    if completed is True:
        return "finished"
    if completed is False:
        return "running"
    return "unknown"


def summarize_jobs(
    payload: Any,
    *,
    requested_job_ids: frozenset[str],
    max_jobs: int,
) -> dict[str, Any]:
    jobs = [item for item in _as_list(payload) if isinstance(item, Mapping)]
    if requested_job_ids:
        jobs = [
            job
            for job in jobs
            if str(_first_present(job, ("jobId", "job_id", "id"))) in requested_job_ids
        ]
    else:
        jobs = []
    truncated = len(jobs) > max_jobs
    jobs = jobs[:max_jobs]
    state_counts = {"failed": 0, "finished": 0, "running": 0, "skipped": 0, "unknown": 0}
    summarized_ids: set[str] = set()
    summarized_stage_ids: set[str] = set()
    for job in jobs:
        job_id = _first_present(job, ("jobId", "job_id", "id"))
        if job_id is not None:
            summarized_ids.add(str(job_id))
        summarized_stage_ids.update(job_stage_ids(job))
        state_counts[spark_job_state(_first_present(job, ("status", "state")))] += 1
    fact_state = "supported" if jobs and not truncated else "unknown"
    if not jobs and not requested_job_ids:
        fact_state = "unknown"
    return {
        "factState": fact_state,
        "linkedJobCount": len(jobs) if fact_state == "supported" else len(requested_job_ids),
        "stateCounts": state_counts if fact_state == "supported" else _zero_job_counts(),
        "_summarized_job_ids": frozenset(summarized_ids)
        if fact_state == "supported"
        else frozenset(),
        "_summarized_stage_ids": frozenset(summarized_stage_ids)
        if fact_state == "supported"
        else frozenset(),
    }


def summarize_stages(
    payload: Any,
    *,
    requested_job_ids: frozenset[str],
    requested_stage_ids: frozenset[str],
    max_stages: int,
    max_tasks_sampled: int,
) -> dict[str, Any]:
    stages = [item for item in _as_list(payload) if isinstance(item, Mapping)]
    if requested_job_ids or requested_stage_ids:
        stages = [
            stage
            for stage in stages
            if (stage_job_ids(stage) & requested_job_ids) or stage_id(stage) in requested_stage_ids
        ]
    else:
        stages = []
    truncated = len(stages) > max_stages
    stages = stages[:max_stages]
    fact_state = "supported" if stages and not truncated else "unknown"
    if fact_state != "supported":
        return {
            "summary": _unknown_stage_summary(),
            "stage_records": (),
        }

    shuffle_read = sum(
        _number_or_zero(_first_present(stage, ("shuffleReadBytes",))) for stage in stages
    )
    shuffle_write = sum(
        _number_or_zero(_first_present(stage, ("shuffleWriteBytes",))) for stage in stages
    )
    input_bytes_state, input_bytes = summarize_stage_bytes(
        stages,
        direct_keys=("inputBytes", "input_bytes"),
        nested_sources=("inputMetrics", "input"),
        nested_keys=("bytesRead", "inputBytes", "bytes"),
    )
    input_rows_state, input_rows = summarize_stage_counts(
        stages,
        direct_keys=("inputRows", "input_records", "inputRecords", "recordsRead"),
        nested_sources=("inputMetrics", "input"),
        nested_keys=("recordsRead", "inputRows", "inputRecords", "records"),
    )
    output_bytes_state, output_bytes = summarize_stage_bytes(
        stages,
        direct_keys=("outputBytes", "output_bytes"),
        nested_sources=("outputMetrics", "output"),
        nested_keys=("bytesWritten", "outputBytes", "bytes"),
    )
    output_rows_state, output_rows = summarize_stage_counts(
        stages,
        direct_keys=("outputRows", "output_records", "outputRecords", "recordsWritten"),
        nested_sources=("outputMetrics", "output"),
        nested_keys=("recordsWritten", "outputRows", "outputRecords", "records"),
    )
    spill_bytes = sum(
        _number_or_zero(_first_present(stage, ("memoryBytesSpilled", "memoryBytesSpilledBytes")))
        + _number_or_zero(_first_present(stage, ("diskBytesSpilled", "diskBytesSpilledBytes")))
        for stage in stages
    )
    task_count = sum(
        _int_or_zero(_first_present(stage, ("numTasks", "taskCount"))) for stage in stages
    )
    failed_count = sum(
        _int_or_zero(_first_present(stage, ("numFailedTasks", "failedTaskCount")))
        for stage in stages
    )
    scheduler_delay_state, scheduler_delay_ms = summarize_scheduler_delay(stages)
    skew = summarize_stage_skew(stages, max_tasks_sampled=max_tasks_sampled)
    return {
        "summary": {
            "factState": "supported",
            "stageCount": len(stages),
            "failedStageCount": failed_stage_count(stages),
            "schedulerDelayState": scheduler_delay_state,
            "schedulerDelayMillis": scheduler_delay_ms,
            "inputBytesState": input_bytes_state,
            "inputBytes": input_bytes,
            "inputRowsState": input_rows_state,
            "inputRows": input_rows,
            "outputBytesState": output_bytes_state,
            "outputBytes": output_bytes,
            "outputRowsState": output_rows_state,
            "outputRows": output_rows,
            "shuffleReadBytes": shuffle_read,
            "shuffleWriteBytes": shuffle_write,
            "spillBytes": spill_bytes,
            "skewSummary": skew,
        },
        "stage_records": tuple(stages),
        "taskCount": task_count,
        "failedTaskCount": failed_count,
    }


def summarize_tasks(stages_summary: Mapping[str, Any], *, max_tasks_sampled: int) -> dict[str, Any]:
    stage_records = tuple(stages_summary.get("stage_records") or ())
    if not stage_records:
        return _unknown_task_summary()
    task_count = _int_or_zero(stages_summary.get("taskCount"))
    failed = _int_or_zero(stages_summary.get("failedTaskCount"))
    retried = summarized_retry_count(stage_records, task_count=task_count)
    duration_buckets = summarized_duration_buckets(
        stage_records,
        task_count=task_count,
        max_tasks_sampled=max_tasks_sampled,
    )
    if task_count <= 0:
        return _unknown_task_summary()
    return {
        "factState": "supported",
        "taskCountState": "supported",
        "taskCount": task_count,
        "durationBucketState": duration_buckets[0],
        "sampledTaskCount": duration_buckets[1],
        "failedTaskState": "supported",
        "failedTaskCount": failed,
        "retriedTaskState": "supported" if retried is not None else "unknown",
        "retriedTaskCount": retried or 0,
        "durationBuckets": duration_buckets[2],
    }


def summarized_retry_count(
    stages: tuple[Any, ...],
    *,
    task_count: int,
) -> int | None:
    total = 0
    for stage in stages:
        if not isinstance(stage, Mapping):
            return None
        value = _first_present(
            stage,
            (
                "retriedTaskCount",
                "numRetriedTasks",
                "retryTaskCount",
                "taskRetryCount",
            ),
        )
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            return None
        total += value
    if total > task_count:
        return None
    return total


def summarize_scheduler_delay(stages: list[Mapping[str, Any]]) -> tuple[str, int]:
    values: list[int] = []
    for stage in stages:
        value = _first_present(
            stage,
            (
                "schedulerDelayMillis",
                "schedulerDelayMs",
                "schedulerDelay",
                "schedulerDelayTime",
            ),
        )
        parsed = _parse_duration_ms(value)
        if parsed is None:
            return "unknown", 0
        values.append(parsed)

    total = sum(values)
    if total > 0:
        return "supported", total
    return "not_observed", 0


def summarized_duration_buckets(
    stages: tuple[Any, ...],
    *,
    task_count: int,
    max_tasks_sampled: int,
) -> tuple[str, int, dict[str, int]]:
    totals = _zero_duration_buckets()
    sampled = 0
    for stage in stages:
        if not isinstance(stage, Mapping):
            return "unknown", 0, _zero_duration_buckets()
        parsed = _duration_bucket_counts(
            _first_present(
                stage,
                (
                    "durationBuckets",
                    "taskDurationBuckets",
                    "taskDurationBucketCounts",
                ),
            )
        )
        if parsed is None:
            return "unknown", 0, _zero_duration_buckets()
        stage_sampled = sum(parsed.values())
        stage_task_count = _int_or_zero(_first_present(stage, ("numTasks", "taskCount")))
        if stage_sampled <= 0 or stage_sampled > stage_task_count:
            return "unknown", 0, _zero_duration_buckets()
        sampled += stage_sampled
        for bucket in SPARK_TASK_DURATION_BUCKET_KEYS:
            totals[bucket] += parsed[bucket]

    if sampled <= 0 or sampled > task_count or sampled > max_tasks_sampled:
        return "unknown", 0, _zero_duration_buckets()
    return "supported", sampled, totals


def summarize_stage_bytes(
    stages: list[Mapping[str, Any]],
    *,
    direct_keys: tuple[str, ...],
    nested_sources: tuple[str, ...],
    nested_keys: tuple[str, ...],
) -> tuple[str, float]:
    values: list[float] = []
    for stage in stages:
        value = stage_bytes_value(
            stage,
            direct_keys=direct_keys,
            nested_sources=nested_sources,
            nested_keys=nested_keys,
        )
        if value is None:
            return "unknown", 0
        values.append(value)
    total = sum(values)
    if total > 0:
        return "supported", total
    return "not_observed", 0


def stage_bytes_value(
    stage: Mapping[str, Any],
    *,
    direct_keys: tuple[str, ...],
    nested_sources: tuple[str, ...],
    nested_keys: tuple[str, ...],
) -> float | None:
    value = _non_negative_number_or_none(_first_present(stage, direct_keys))
    if value is not None:
        return value
    for source_key in nested_sources:
        nested = stage.get(source_key)
        if not isinstance(nested, Mapping):
            continue
        value = _non_negative_number_or_none(_first_present(nested, nested_keys))
        if value is not None:
            return value
    return None


def summarize_stage_counts(
    stages: list[Mapping[str, Any]],
    *,
    direct_keys: tuple[str, ...],
    nested_sources: tuple[str, ...],
    nested_keys: tuple[str, ...],
) -> tuple[str, int]:
    values: list[int] = []
    for stage in stages:
        value = stage_count_value(
            stage,
            direct_keys=direct_keys,
            nested_sources=nested_sources,
            nested_keys=nested_keys,
        )
        if value is None:
            return "unknown", 0
        values.append(value)
    total = sum(values)
    if total > 0:
        return "supported", total
    return "not_observed", 0


def stage_count_value(
    stage: Mapping[str, Any],
    *,
    direct_keys: tuple[str, ...],
    nested_sources: tuple[str, ...],
    nested_keys: tuple[str, ...],
) -> int | None:
    value = _non_negative_int_or_none(_first_present(stage, direct_keys))
    if value is not None:
        return value
    for source_key in nested_sources:
        nested = stage.get(source_key)
        if not isinstance(nested, Mapping):
            continue
        value = _non_negative_int_or_none(_first_present(nested, nested_keys))
        if value is not None:
            return value
    return None


def summarize_executors(payload: Any) -> dict[str, Any]:
    executors = [item for item in _as_list(payload) if isinstance(item, Mapping)]
    if not executors:
        return {
            "factState": "unknown",
            "executorLossState": "unknown",
            "executorLossCount": 0,
            "executorMemoryUsedState": "unknown",
            "executorMemoryUsedBytes": 0,
            "executorMemoryCapacityState": "unknown",
            "executorMemoryCapacityBytes": 0,
            "executorChurnState": "unknown",
            "executorChurnObserved": False,
            "dynamicAllocationState": "unknown",
            "dynamicAllocationObserved": False,
        }
    loss_count = sum(1 for executor in executors if executor_inactive(executor))
    memory_used = summarize_executor_memory(
        executors,
        keys=("memoryUsed", "memoryUsedBytes", "usedMemory", "usedMemoryBytes"),
    )
    memory_capacity = summarize_executor_memory(
        executors,
        keys=("maxMemory", "maxMemoryBytes", "memoryCapacity", "memoryCapacityBytes"),
    )
    if (
        memory_used[0] == "supported"
        and memory_capacity[0] == "supported"
        and memory_used[1] > memory_capacity[1]
    ):
        memory_used = ("unknown", 0)
        memory_capacity = ("unknown", 0)
    dynamic_allocation = dynamic_allocation_observed(payload, executors)
    return {
        "factState": "unknown",
        "executorLossState": "supported" if loss_count > 0 else "not_observed",
        "executorLossCount": loss_count,
        "executorMemoryUsedState": memory_used[0],
        "executorMemoryUsedBytes": memory_used[1],
        "executorMemoryCapacityState": memory_capacity[0],
        "executorMemoryCapacityBytes": memory_capacity[1],
        "executorChurnState": "supported",
        "executorChurnObserved": loss_count > 0,
        "dynamicAllocationState": dynamic_allocation[0],
        "dynamicAllocationObserved": dynamic_allocation[1],
    }


def summarize_executor_memory(
    executors: list[Mapping[str, Any]],
    *,
    keys: tuple[str, ...],
) -> tuple[str, float]:
    values: list[float] = []
    for executor in executors:
        value = _non_negative_number_or_none(_first_present(executor, keys))
        if value is None:
            return "unknown", 0
        values.append(value)
    total = sum(values)
    if total > 0:
        return "supported", total
    return "not_observed", 0


def _unknown_application_summary() -> dict[str, Any]:
    return {
        "factState": "unknown",
        "lifecycle": "unknown",
        "attemptState": "unknown",
        "attemptCount": 1,
    }


def spark_history_source_coverage(
    warnings: list[str],
    attempted_endpoints: int,
    successful_endpoints: int,
) -> dict[str, Any]:
    return {
        "factState": "unknown" if warnings else "supported",
        "attemptedEndpointCount": attempted_endpoints,
        "successfulEndpointCount": successful_endpoints,
        "warningIds": sorted(set(warnings)),
    }


def spark_history_server_limitations(
    executors: Mapping[str, Any],
    warnings: list[str],
) -> list[dict[str, str]]:
    return [
        {"id": "live_history_server_collection", "state": "supported"},
        {"id": "no_raw_event_log", "state": "unsupported"},
        {"id": "no_spark_job_execution", "state": "unsupported"},
        {"id": "no_browser_report_surface", "state": "unsupported"},
        {"id": "no_product_support", "state": "unsupported"},
        {"id": "structured_streaming_not_modeled", "state": "unsupported"},
        {"id": "cluster_manager_context", "state": "unknown"},
        {"id": "executor_loss", "state": str(executors.get("executorLossState") or "unknown")},
        {"id": "spark_history_source_coverage", "state": "unknown" if warnings else "supported"},
    ]


def linked_job_ids(sql_execution: Mapping[str, Any]) -> frozenset[str]:
    ids: set[str] = set()
    for key in (
        "jobIds",
        "job_ids",
        "jobs",
        "runningJobIds",
        "successJobIds",
        "failedJobIds",
        "activeJobIds",
    ):
        value = sql_execution.get(key)
        if isinstance(value, list):
            ids.update(str(item) for item in value if isinstance(item, (int, str)))
        elif isinstance(value, (int, str)):
            ids.add(str(value))
    return frozenset(ids)


def stage_job_ids(stage: Mapping[str, Any]) -> frozenset[str]:
    value = _first_present(stage, ("jobIds", "job_ids"))
    if not isinstance(value, list):
        return frozenset()
    return frozenset(str(item) for item in value if isinstance(item, (int, str)))


def job_stage_ids(job: Mapping[str, Any]) -> frozenset[str]:
    value = _first_present(job, ("stageIds", "stage_ids", "stages"))
    if not isinstance(value, list):
        return frozenset()
    ids: set[str] = set()
    for item in value:
        if not isinstance(item, (int, str)):
            continue
        text = str(item)
        if text:
            ids.add(text)
    return frozenset(ids)


def stage_id(stage: Mapping[str, Any]) -> str:
    value = _first_present(stage, ("stageId", "stage_id", "id"))
    if not isinstance(value, (int, str)):
        return ""
    return str(value)


def stage_attempt_selector(stage: Mapping[str, Any]) -> tuple[str, str] | None:
    stage_id_value = _first_present(stage, ("stageId", "stage_id", "id"))
    attempt_id_value = _first_present(
        stage,
        (
            "attemptId",
            "attempt_id",
            "stageAttemptId",
            "stage_attempt_id",
            "attemptNumber",
        ),
    )
    if not isinstance(stage_id_value, (int, str)) or not isinstance(attempt_id_value, (int, str)):
        return None
    stage_id_text = str(stage_id_value).strip()
    attempt_id_text = str(attempt_id_value).strip()
    if not stage_id_text or not attempt_id_text:
        return None
    return stage_id_text, attempt_id_text


def summarize_stage_skew(
    stages: list[Mapping[str, Any]],
    *,
    max_tasks_sampled: int,
) -> dict[str, Any]:
    ratios: list[float] = []
    sampled = 0
    missing_quantile_count = 0
    for stage in stages:
        quantiles = task_runtime_quantiles(stage)
        if quantiles is None:
            missing_quantile_count += 1
            continue
        median, maximum = quantiles
        if median > 0:
            ratios.append(maximum / median)
        sampled += _int_or_zero(_first_present(stage, ("numTasks", "taskCount")))
    if not ratios:
        return {
            "state": "unknown",
            "checked": False,
            "candidate": False,
            "maxToMedianTaskDurationRatio": 0,
            "sampledTaskCount": 0,
        }
    ratio = max(ratios)
    candidate = ratio >= SPARK_HISTORY_SKEW_RATIO_THRESHOLD
    if missing_quantile_count and not candidate:
        return {
            "state": "unknown",
            "checked": False,
            "candidate": False,
            "maxToMedianTaskDurationRatio": round(ratio, 3),
            "sampledTaskCount": min(sampled, max_tasks_sampled),
        }
    return {
        "state": "supported" if candidate else "not_observed",
        "checked": True,
        "candidate": candidate,
        "maxToMedianTaskDurationRatio": round(ratio, 3),
        "sampledTaskCount": min(sampled, max_tasks_sampled),
    }


def task_runtime_quantiles(stage: Mapping[str, Any]) -> tuple[float, float] | None:
    distributions = _first_present(
        stage,
        ("taskMetricsDistributions", "executorSummary", "taskMetrics"),
    )
    parsed = _runtime_metric_quantiles(distributions)
    if len(parsed) >= 3:
        return parsed[len(parsed) // 2], parsed[-1]
    for value in _iter_nested_values(distributions):
        if not isinstance(value, Mapping):
            continue
        label = str(_first_present(value, ("name", "metric", "metricName")) or "").lower()
        if label and "runtime" not in label and "duration" not in label:
            continue
        quantiles = _first_present(value, ("quantiles", "values"))
        parsed = _numeric_list(quantiles)
        if len(parsed) >= 3:
            return parsed[len(parsed) // 2], parsed[-1]
    parsed = _numeric_list(_first_present(stage, ("executorRunTime", "durationQuantiles")))
    if len(parsed) >= 3:
        return parsed[len(parsed) // 2], parsed[-1]
    return None


def _runtime_metric_quantiles(value: Any) -> list[float]:
    if not isinstance(value, Mapping):
        return []
    for key, raw_quantiles in value.items():
        label = str(key).lower()
        if (
            "runtime" not in label
            and "duration" not in label
            and "tasktime" not in label
            and "task_time" not in label
        ):
            continue
        if isinstance(raw_quantiles, Mapping):
            parsed = _numeric_list(_first_present(raw_quantiles, ("quantiles", "values")))
        else:
            parsed = _numeric_list(raw_quantiles)
        if len(parsed) >= 3:
            return parsed
    return []


def failed_stage_count(stages: list[Mapping[str, Any]]) -> int:
    count = 0
    for stage in stages:
        status = str(_first_present(stage, ("status", "state")) or "").lower()
        if "fail" in status:
            count += 1
    return count


def executor_inactive(executor: Mapping[str, Any]) -> bool:
    active = _first_present(executor, ("isActive", "active"))
    if active is False:
        return True
    if _first_present(executor, ("removeTime", "removedTime", "endTime")) is not None:
        return True
    return False


def dynamic_allocation_observed(
    payload: Any,
    executors: list[Mapping[str, Any]],
) -> tuple[str, bool]:
    markers = tuple(
        _dynamic_allocation_marker(item) for item in _dynamic_allocation_sources(payload)
    )
    markers += tuple(_dynamic_allocation_marker(executor) for executor in executors)
    observed = tuple(marker for marker in markers if marker is not None)
    if not observed:
        return "unknown", False
    return "supported", any(observed)


def _dynamic_allocation_sources(payload: Any) -> tuple[Mapping[str, Any], ...]:
    if isinstance(payload, Mapping):
        return (payload,)
    return ()


def _dynamic_allocation_marker(payload: Mapping[str, Any]) -> bool | None:
    marker = _first_present(
        payload,
        (
            "dynamicAllocationObserved",
            "dynamicAllocationEnabled",
            "dynamicAllocation",
        ),
    )
    if isinstance(marker, bool):
        return marker
    return None


def spark_version_family(payload: Any) -> str:
    version = None
    if isinstance(payload, str):
        version = payload
    elif isinstance(payload, Mapping):
        version = _first_present(payload, ("spark", "sparkVersion", "version"))
    if not isinstance(version, str):
        return "unknown"
    match = re.search(r"(\d+)\.(\d+)", version)
    if not match:
        return "unknown"
    return f"spark_{match.group(1)}_{match.group(2)}"


def spark_lifecycle(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"complete", "completed", "success", "succeeded", "finished"}:
        return "finished"
    if text in {"failed", "error", "killed"}:
        return "failed"
    if text in {"running", "active"}:
        return "running"
    if text in {"skipped"}:
        return "skipped"
    return "unknown"


def spark_job_state(value: Any) -> str:
    lifecycle = spark_lifecycle(value)
    return "finished" if lifecycle == "finished" else lifecycle


def _duration_ms(raw: Mapping[str, Any]) -> int | None:
    for key in ("duration", "durationMillis", "duration_ms", "elapsedTime", "elapsedTimeMillis"):
        value = raw.get(key)
        parsed = _parse_duration_ms(value)
        if parsed is not None:
            return parsed
    return None


def _parse_duration_ms(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)) and value >= 0:
        return int(value)
    text = str(value).strip().lower()
    match = re.fullmatch(
        r"([0-9]+(?:\.[0-9]+)?)\s*(ms|millis|milliseconds|s|sec|secs|seconds)?",
        text,
    )
    if not match:
        return None
    number = float(match.group(1))
    unit = match.group(2) or "ms"
    if unit.startswith("s"):
        number *= 1000
    return max(0, int(number))


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, Mapping):
        for key in ("applications", "jobs", "stages", "sql", "executions"):
            nested = value.get(key)
            if isinstance(nested, list):
                return nested
    return []


def _first_present(raw: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in raw:
            return raw[key]
    return None


def _number_or_zero(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return 0
    return value


def _non_negative_number_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return value


def _non_negative_int_or_none(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _int_or_zero(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


def _duration_bucket_counts(value: Any) -> dict[str, int] | None:
    if not isinstance(value, Mapping) or set(value) != set(SPARK_TASK_DURATION_BUCKET_KEYS):
        return None
    parsed: dict[str, int] = {}
    for bucket in SPARK_TASK_DURATION_BUCKET_KEYS:
        count = value.get(bucket)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            return None
        parsed[bucket] = count
    return parsed


def _numeric_list(value: Any) -> list[float]:
    if not isinstance(value, list):
        return []
    parsed: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)) or item < 0:
            return []
        parsed.append(float(item))
    return parsed


def _iter_nested_values(value: Any) -> Iterable[Any]:
    if isinstance(value, Mapping):
        yield value
        for nested in value.values():
            yield from _iter_nested_values(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _iter_nested_values(nested)


def _zero_job_counts() -> dict[str, int]:
    return {"failed": 0, "finished": 0, "running": 0, "skipped": 0, "unknown": 0}


def _zero_duration_buckets() -> dict[str, int]:
    return {bucket: 0 for bucket in SPARK_TASK_DURATION_BUCKET_KEYS}


def _unknown_stage_summary() -> dict[str, Any]:
    return {
        "factState": "unknown",
        "stageCount": 0,
        "failedStageCount": 0,
        "schedulerDelayState": "unknown",
        "schedulerDelayMillis": 0,
        "inputBytesState": "unknown",
        "inputBytes": 0,
        "inputRowsState": "unknown",
        "inputRows": 0,
        "outputBytesState": "unknown",
        "outputBytes": 0,
        "outputRowsState": "unknown",
        "outputRows": 0,
        "shuffleReadBytes": 0,
        "shuffleWriteBytes": 0,
        "spillBytes": 0,
        "skewSummary": {
            "state": "unknown",
            "checked": False,
            "candidate": False,
            "maxToMedianTaskDurationRatio": 0,
            "sampledTaskCount": 0,
        },
    }


def _unknown_task_summary() -> dict[str, Any]:
    return {
        "factState": "unknown",
        "taskCountState": "unknown",
        "taskCount": 0,
        "durationBucketState": "unknown",
        "sampledTaskCount": 0,
        "failedTaskState": "unknown",
        "failedTaskCount": 0,
        "retriedTaskState": "unknown",
        "retriedTaskCount": 0,
        "durationBuckets": _zero_duration_buckets(),
    }
