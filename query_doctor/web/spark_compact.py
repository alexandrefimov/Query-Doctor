"""Safe web handler for local Spark compact diagnosis."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.analyzer.spark_fixture_schema import SPARK_HISTORY_COMPACT_FIXTURE_MAX_JSON_BYTES
from query_doctor.cm.models import CMClientError
from query_doctor.spark.diagnosis import build_spark_compact_diagnosis
from query_doctor.spark.history_server import (
    DEFAULT_MAX_SPARK_HISTORY_RESPONSE_BYTES,
    DEFAULT_SPARK_HISTORY_MAX_JOBS,
    DEFAULT_SPARK_HISTORY_MAX_APPLICATION_ATTEMPTS,
    DEFAULT_SPARK_HISTORY_MAX_SQL_EXECUTIONS,
    DEFAULT_SPARK_HISTORY_MAX_STAGES,
    DEFAULT_SPARK_HISTORY_MAX_TASK_SUMMARIES,
    DEFAULT_SPARK_HISTORY_MAX_TASKS_SAMPLED,
    DEFAULT_SPARK_HISTORY_TIMEOUT_SEC,
    SPARK_HISTORY_SERVER_MAX_RESPONSE_BYTES,
    collect_spark_history_server_compact_summary,
)
from query_doctor.web.form_helpers import (
    first_form_value,
    form_flag_enabled,
    parse_positive_form_int,
)
from query_doctor.web.models import WebError, WebSettings
from query_doctor.web.ui.spark import render_spark_compact_page


SPARK_COMPACT_ACTION_FIELD = "spark_compact_action"
SPARK_COMPACT_ACTION_JSON = "compact_json"
SPARK_COMPACT_ACTION_HISTORY_SERVER = "history_server"
SPARK_WEB_HISTORY_TIMEOUT_MAX = 60
SPARK_WEB_HISTORY_MAX_RESPONSE_BYTES_MAX = SPARK_HISTORY_SERVER_MAX_RESPONSE_BYTES
SPARK_WEB_HISTORY_MAX_APPLICATION_ATTEMPTS_MAX = 50
SPARK_WEB_HISTORY_MAX_SQL_EXECUTIONS_MAX = 50
SPARK_WEB_HISTORY_MAX_JOBS_MAX = 500
SPARK_WEB_HISTORY_MAX_STAGES_MAX = 1000
SPARK_WEB_HISTORY_MAX_TASK_SUMMARIES_MAX = 100
SPARK_WEB_HISTORY_MAX_TASKS_SAMPLED_MAX = 1000
SPARK_HISTORY_COLLECTION_FAILED_SAFE_ERROR = (
    "Spark History Server compact collection failed safely."
)
SAFE_SPARK_HISTORY_WEB_ERROR_MESSAGES = frozenset(
    {
        "Spark History Server endpoint request failed safely.",
        "Spark History Server endpoint response exceeded the configured byte limit.",
        "Spark History Server endpoint did not return JSON.",
        "Spark History Server URL must be an http or https base URL.",
        "Spark History Server URL must not contain credentials.",
        "Spark History Server URL must not contain query or fragment parts.",
        "Spark History Server URL port must be valid.",
        "Spark History Server URL must include a host.",
        "Spark History Server URL host must not contain controls.",
        "Spark History Server URL target is not allowed.",
        "Spark History Server URL target could not be resolved safely.",
        "Spark History Server local or private targets require explicit opt-in.",
        "Spark History Server path segment is required.",
        "Spark History Server path segment must not contain controls.",
        "Spark History Server path segment must not traverse paths.",
        "Spark application id is required.",
        "Spark application id must not traverse paths.",
        "Spark History Server collection bounds must be positive.",
        "Spark History Server response byte bound exceeds the compact cap.",
        "Spark History Server compact collection did not find a readable JSON endpoint.",
    }
)


def handle_spark_compact_request(
    form: dict[str, list[str]],
    settings: WebSettings,
) -> tuple[int, str]:
    try:
        action = first_form_value(form, SPARK_COMPACT_ACTION_FIELD) or SPARK_COMPACT_ACTION_JSON
        if action == SPARK_COMPACT_ACTION_HISTORY_SERVER:
            try:
                diagnosis, collection_status = collect_spark_history_diagnosis(form)
            except (CMClientError, EngineFactContractError) as exc:
                raise WebError(safe_spark_history_web_error_message(exc)) from exc
            return 200, render_spark_compact_page(
                settings,
                result=diagnosis,
                collection_status=collection_status,
            )
        if action != SPARK_COMPACT_ACTION_JSON:
            raise WebError("Spark compact action is not supported.")
        diagnosis = build_spark_compact_diagnosis(parse_spark_compact_form_payload(form))
    except (CMClientError, EngineFactContractError, ValueError, WebError) as exc:
        return 400, render_spark_compact_page(settings, error=exc)
    return 200, render_spark_compact_page(settings, result=diagnosis)


def collect_spark_history_diagnosis(
    form: dict[str, list[str]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    history_server_url = first_form_value(form, "history_server_url")
    application_id = first_form_value(form, "application_id")
    sql_execution_id = first_form_value(form, "sql_execution_id") or None
    if not history_server_url:
        raise WebError("Spark History Server URL is required.")
    if not application_id:
        raise WebError("Spark application id is required.")
    result = collect_spark_history_server_compact_summary(
        history_server_url=history_server_url,
        application_id=application_id,
        sql_execution_id=sql_execution_id,
        timeout_sec=parse_positive_form_int(
            form,
            "timeout_sec",
            default=DEFAULT_SPARK_HISTORY_TIMEOUT_SEC,
            maximum=SPARK_WEB_HISTORY_TIMEOUT_MAX,
        ),
        max_response_bytes=parse_positive_form_int(
            form,
            "max_response_bytes",
            default=DEFAULT_MAX_SPARK_HISTORY_RESPONSE_BYTES,
            maximum=SPARK_WEB_HISTORY_MAX_RESPONSE_BYTES_MAX,
        ),
        max_application_attempts=parse_positive_form_int(
            form,
            "max_application_attempts",
            default=DEFAULT_SPARK_HISTORY_MAX_APPLICATION_ATTEMPTS,
            maximum=SPARK_WEB_HISTORY_MAX_APPLICATION_ATTEMPTS_MAX,
        ),
        max_sql_executions=parse_positive_form_int(
            form,
            "max_sql_executions",
            default=DEFAULT_SPARK_HISTORY_MAX_SQL_EXECUTIONS,
            maximum=SPARK_WEB_HISTORY_MAX_SQL_EXECUTIONS_MAX,
        ),
        max_jobs=parse_positive_form_int(
            form,
            "max_jobs",
            default=DEFAULT_SPARK_HISTORY_MAX_JOBS,
            maximum=SPARK_WEB_HISTORY_MAX_JOBS_MAX,
        ),
        max_stages=parse_positive_form_int(
            form,
            "max_stages",
            default=DEFAULT_SPARK_HISTORY_MAX_STAGES,
            maximum=SPARK_WEB_HISTORY_MAX_STAGES_MAX,
        ),
        max_task_summaries=parse_positive_form_int(
            form,
            "max_task_summaries",
            default=DEFAULT_SPARK_HISTORY_MAX_TASK_SUMMARIES,
            maximum=SPARK_WEB_HISTORY_MAX_TASK_SUMMARIES_MAX,
        ),
        max_tasks_sampled=parse_positive_form_int(
            form,
            "max_tasks_sampled",
            default=DEFAULT_SPARK_HISTORY_MAX_TASKS_SAMPLED,
            maximum=SPARK_WEB_HISTORY_MAX_TASKS_SAMPLED_MAX,
        ),
        allow_local_targets=form_flag_enabled(form, "allow_local_history_server_target"),
    )
    collection_status = {
        "attempted_endpoints": result.attempted_endpoints,
        "successful_endpoints": result.successful_endpoints,
        "warnings": result.warnings,
    }
    return build_spark_compact_diagnosis(result.payload), collection_status


def safe_spark_history_web_error_message(error: object) -> str:
    message = str(error)
    if message in SAFE_SPARK_HISTORY_WEB_ERROR_MESSAGES:
        return message
    return SPARK_HISTORY_COLLECTION_FAILED_SAFE_ERROR


def parse_spark_compact_form_payload(form: dict[str, list[str]]) -> Mapping[str, Any]:
    text = first_form_value(form, "compact_json")
    if not text:
        raise WebError("Spark compact JSON is required.")
    if len(text.encode("utf-8")) > SPARK_HISTORY_COMPACT_FIXTURE_MAX_JSON_BYTES:
        raise WebError("Spark compact JSON exceeds the accepted compact payload limit.")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise WebError("Spark compact JSON is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise WebError("Spark compact JSON must be an object.")
    return payload
