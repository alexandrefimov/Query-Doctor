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
SAFE_SPARK_HISTORY_REASON_CODES = {
    "Spark History Server endpoint request failed safely.": (
        "spark_compact.history_endpoint_request_failed"
    ),
    "Spark History Server endpoint response exceeded the configured byte limit.": (
        "spark_compact.history_response_too_large"
    ),
    "Spark History Server endpoint did not return JSON.": (
        "spark_compact.history_response_not_json"
    ),
    "Spark History Server URL must be an http or https base URL.": (
        "spark_compact.history_url_scheme_invalid"
    ),
    "Spark History Server URL must not contain credentials.": (
        "spark_compact.history_url_credentials_rejected"
    ),
    "Spark History Server URL must not contain query or fragment parts.": (
        "spark_compact.history_url_parts_rejected"
    ),
    "Spark History Server URL port must be valid.": ("spark_compact.history_url_port_invalid"),
    "Spark History Server URL must include a host.": ("spark_compact.history_url_host_required"),
    "Spark History Server URL host must not contain controls.": (
        "spark_compact.history_url_host_invalid"
    ),
    "Spark History Server URL target is not allowed.": ("spark_compact.history_target_rejected"),
    "Spark History Server URL target could not be resolved safely.": (
        "spark_compact.history_target_resolution_failed"
    ),
    "Spark History Server local or private targets require explicit opt-in.": (
        "spark_compact.history_local_target_requires_opt_in"
    ),
    "Spark History Server path segment is required.": (
        "spark_compact.history_path_segment_required"
    ),
    "Spark History Server path segment must not contain controls.": (
        "spark_compact.history_path_segment_invalid"
    ),
    "Spark History Server path segment must not traverse paths.": (
        "spark_compact.history_path_segment_rejected"
    ),
    "Spark application id is required.": "spark_compact.application_id_required",
    "Spark application attempt id is required.": "spark_compact.application_attempt_id_required",
    "Spark application id must not traverse paths.": "spark_compact.application_id_rejected",
    "Spark application id must not include an attempt path when attempt id is provided.": (
        "spark_compact.application_id_attempt_conflict"
    ),
    "Spark application attempt id must not contain controls.": (
        "spark_compact.application_attempt_id_invalid"
    ),
    "Spark application attempt id must not traverse paths.": (
        "spark_compact.application_attempt_id_rejected"
    ),
    "Spark History Server collection bounds must be positive.": (
        "spark_compact.history_bound_invalid"
    ),
    "Spark History Server response byte bound exceeds the compact cap.": (
        "spark_compact.history_response_bound_too_large"
    ),
    "Spark History Server compact collection did not find a readable JSON endpoint.": (
        "spark_compact.history_json_endpoint_unavailable"
    ),
}
SAFE_SPARK_HISTORY_WEB_ERROR_MESSAGES = frozenset(SAFE_SPARK_HISTORY_REASON_CODES)


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
                raise spark_history_collection_error(exc) from exc
            return 200, render_spark_compact_page(
                settings,
                result=diagnosis,
                collection_status=collection_status,
            )
        if action != SPARK_COMPACT_ACTION_JSON:
            raise spark_compact_input_error(
                "Spark compact action is not supported.",
                reason_code="spark_compact.action_unsupported",
                title="Spark compact action is unsupported",
                next_step="Choose compact JSON intake or bounded History Server intake, then retry.",
            )
        diagnosis = build_spark_compact_diagnosis(parse_spark_compact_form_payload(form))
    except (CMClientError, EngineFactContractError, ValueError, WebError) as exc:
        return 400, render_spark_compact_page(settings, error=exc)
    return 200, render_spark_compact_page(settings, result=diagnosis)


def collect_spark_history_diagnosis(
    form: dict[str, list[str]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    history_server_url = first_form_value(form, "history_server_url")
    application_id = first_form_value(form, "application_id")
    application_attempt_id = first_form_value(form, "application_attempt_id") or None
    sql_execution_id = first_form_value(form, "sql_execution_id") or None
    if not history_server_url:
        raise spark_compact_input_error(
            "Spark History Server URL is required.",
            reason_code="spark_compact.history_server_url_required",
            title="Spark History Server URL is missing",
            next_step="Enter an explicit Spark History Server base URL, then retry.",
        )
    if not application_id:
        raise spark_compact_input_error(
            "Spark application id is required.",
            reason_code="spark_compact.application_id_required",
            title="Spark application id is missing",
            next_step="Enter one explicit Spark application id, then retry.",
        )
    result = collect_spark_history_server_compact_summary(
        history_server_url=history_server_url,
        application_id=application_id,
        application_attempt_id=application_attempt_id,
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
        raise spark_compact_input_error(
            "Spark compact JSON is required.",
            reason_code="spark_compact.compact_json_required",
            title="Spark compact JSON is missing",
            next_step="Paste one already raw-free Spark compact JSON payload, then retry.",
        )
    if len(text.encode("utf-8")) > SPARK_HISTORY_COMPACT_FIXTURE_MAX_JSON_BYTES:
        raise spark_compact_input_error(
            "Spark compact JSON exceeds the accepted compact payload limit.",
            reason_code="spark_compact.compact_json_too_large",
            title="Spark compact JSON is too large",
            next_step="Use a compact raw-free Spark payload within the accepted byte limit.",
        )
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise spark_compact_input_error(
            "Spark compact JSON is not valid JSON.",
            reason_code="spark_compact.compact_json_invalid",
            title="Spark compact JSON is invalid",
            next_step="Fix the JSON syntax and resubmit the raw-free compact payload.",
        ) from exc
    if not isinstance(payload, dict):
        raise spark_compact_input_error(
            "Spark compact JSON must be an object.",
            reason_code="spark_compact.compact_json_object_required",
            title="Spark compact JSON object is required",
            next_step="Submit one Spark compact JSON object.",
        )
    return payload


def spark_history_collection_error(error: object) -> WebError:
    message = safe_spark_history_web_error_message(error)
    return WebError(
        message,
        title="Spark History Server collection failed",
        reason_code=SAFE_SPARK_HISTORY_REASON_CODES.get(
            message, "spark_compact.history_server_collection_failed"
        ),
        stage="Collecting Spark History Server compact summary",
        next_step="Check the History Server URL, application selector, and bounds, then retry.",
    )


def spark_compact_input_error(
    message: str,
    *,
    reason_code: str,
    title: str,
    next_step: str,
) -> WebError:
    return WebError(
        message,
        title=title,
        reason_code=reason_code,
        stage="Checking Spark compact input",
        next_step=next_step,
    )
