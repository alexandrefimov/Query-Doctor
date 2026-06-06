"""Typed normalized engine facts for contract-shaping work.

This module is intentionally narrower than a full analyzer abstraction. It
defines the raw-free fact object that future parser outputs can target before
Recent ranking, reports, or browser presenters consume them.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal, Union

from query_doctor.safety import redaction


DiagnosticState = Literal["supported", "not_observed", "unknown"]
MetricValue = Union[bool, float, int, str, None]
NormalizedFactScope = Literal[
    "shared",
    "distributed_sql_family",
    "engine_specific",
    "source_boundary",
    "support_boundary",
]
AttentionValueGate = Literal["state_supported", "positive_number"]

VALID_DIAGNOSTIC_STATES = frozenset({"supported", "not_observed", "unknown"})
ENGINE_FACT_BOUNDARY_SCHEMA_VERSION = "engine_fact_boundary_v1"
REGISTERED_ENGINE_FACT_ENGINES = frozenset({"impala", "spark", "trino"})
TRINO_ENGINE_SPECIFIC_ALLOWED_PREFIXES = ("no_", "query_detail_", "query_list_", "trino_")
SPARK_ENGINE_SPECIFIC_ALLOWED_PREFIXES = ("spark_",)
ENGINE_PREFIXES = ("impala_", "spark_", "trino_")


class EngineFactContractError(ValueError):
    """Raised when a normalized engine fact violates the local contract."""


@dataclass(frozen=True)
class EngineFactDefinition:
    fact_id: str
    scope: NormalizedFactScope
    allowed_engines: frozenset[str]
    attention_signal_id: str | None = None
    attention_value_gate: AttentionValueGate = "state_supported"


@dataclass(frozen=True)
class MetricFact:
    fact_id: str
    state: DiagnosticState
    value: MetricValue = None
    unit: str | None = None
    summary: str | None = None

    def __post_init__(self) -> None:
        _validate_identifier(self.fact_id, "fact_id")
        _validate_state(self.state)
        if self.unit is not None:
            _validate_identifier(self.unit, "unit")
        if self.state == "unknown" and self.value is not None:
            raise EngineFactContractError("unknown metric facts must not carry values")

    def to_public_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.fact_id,
            "state": self.state,
        }
        if self.value is not None:
            payload["value"] = self.value
        if self.unit:
            payload["unit"] = self.unit
        if self.summary:
            payload["summary"] = self.summary
        return payload


@dataclass(frozen=True)
class LimitationFact:
    fact_id: str
    state: DiagnosticState
    summary: str

    def __post_init__(self) -> None:
        _validate_identifier(self.fact_id, "fact_id")
        _validate_state(self.state)
        if not self.summary.strip():
            raise EngineFactContractError("limitation facts need a summary")

    def to_public_dict(self) -> dict[str, str]:
        return {
            "id": self.fact_id,
            "state": self.state,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class EngineIdentityFacts:
    engine: str
    source: str
    parser_coverage: DiagnosticState
    source_version: str | None = None

    def __post_init__(self) -> None:
        _validate_identifier(self.engine, "engine")
        _validate_identifier(self.source, "source")
        _validate_state(self.parser_coverage)
        if self.source_version is not None:
            _validate_safe_label(self.source_version, "source_version")

    def to_public_dict(self) -> dict[str, str]:
        payload = {
            "engine": self.engine,
            "source": self.source,
            "parser_coverage": self.parser_coverage,
        }
        if self.source_version:
            payload["source_version"] = self.source_version
        return payload


@dataclass(frozen=True)
class QueryLifecycleFacts:
    state: DiagnosticState
    lifecycle: str
    blocked: DiagnosticState = "unknown"
    failure: DiagnosticState = "unknown"
    failure_category_state: DiagnosticState = "unknown"
    failure_category: str | None = None

    def __post_init__(self) -> None:
        _validate_state(self.state)
        _validate_safe_label(self.lifecycle, "lifecycle")
        _validate_state(self.blocked)
        _validate_state(self.failure)
        _validate_state(self.failure_category_state)
        if self.failure_category_state == "supported":
            if self.failure_category is None:
                raise EngineFactContractError("supported failure category facts need a category")
            _validate_identifier(self.failure_category, "failure_category")
        elif self.failure_category is not None:
            raise EngineFactContractError(
                "unsupported failure category facts must not carry a category"
            )

    def to_public_dict(self) -> dict[str, Any]:
        failure_category: dict[str, str] = {
            "state": self.failure_category_state,
        }
        if self.failure_category is not None:
            failure_category["value"] = self.failure_category
        return {
            "state": self.state,
            "lifecycle": self.lifecycle,
            "blocked": self.blocked,
            "failure": self.failure,
            "failure_category": failure_category,
        }


@dataclass(frozen=True)
class EngineFactBundle:
    identity: EngineIdentityFacts
    lifecycle: QueryLifecycleFacts
    timing: tuple[MetricFact, ...] = ()
    resources: tuple[MetricFact, ...] = ()
    stages: tuple[MetricFact, ...] = ()
    limitations: tuple[LimitationFact, ...] = ()

    def facts_by_id(self) -> dict[str, MetricFact | LimitationFact]:
        facts: dict[str, MetricFact | LimitationFact] = {}
        for fact in self.timing + self.resources + self.stages + self.limitations:
            if fact.fact_id in facts:
                raise EngineFactContractError(f"duplicate engine fact id: {fact.fact_id}")
            facts[fact.fact_id] = fact
        validate_engine_fact_namespaces(self.identity.engine, facts.values())
        return facts

    def to_public_dict(self) -> dict[str, Any]:
        self.facts_by_id()
        return {
            "identity": self.identity.to_public_dict(),
            "lifecycle": self.lifecycle.to_public_dict(),
            "timing": [fact.to_public_dict() for fact in self.timing],
            "resources": [fact.to_public_dict() for fact in self.resources],
            "stages": [fact.to_public_dict() for fact in self.stages],
            "limitations": [fact.to_public_dict() for fact in self.limitations],
        }


LOCAL_PATH_RE = re.compile(
    r"(?<![\w/])(?:/private)?/(?:Users|home|tmp|var|etc)/[^\s<>'\"]+"
    r"|(?<![\w/])[A-Za-z]:\\[^\s<>'\"]+"
)
URL_RE = re.compile(r"\bhttps?://\S+", re.IGNORECASE)
SQL_SNIPPET_RE = re.compile(
    r"\b(?:SELECT|WITH|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER)\b"
    r"(?=[\s\S]{0,160}\b(?:FROM|JOIN|TABLE|INTO)\b)",
    re.IGNORECASE,
)


def public_engine_facts_text(bundle: EngineFactBundle) -> str:
    return json.dumps(bundle.to_public_dict(), ensure_ascii=True, sort_keys=True)


def engine_fact_boundary_payload(bundle: EngineFactBundle) -> dict[str, Any]:
    violations = validate_engine_fact_bundle_raw_free(bundle)
    if violations:
        joined = ", ".join(violations)
        raise EngineFactContractError(
            f"engine fact bundle is not safe for report/browser boundary: {joined}"
        )

    public = bundle.to_public_dict()
    identity = public["identity"]
    boundary_identity = {
        "engine": identity["engine"],
        "parser_coverage": identity["parser_coverage"],
    }
    if "source_version" in identity:
        boundary_identity["source_version"] = identity["source_version"]

    return {
        "schema_version": ENGINE_FACT_BOUNDARY_SCHEMA_VERSION,
        "identity": boundary_identity,
        "lifecycle": public["lifecycle"],
        "fact_groups": {
            "timing": public["timing"],
            "resources": public["resources"],
            "stages": public["stages"],
            "limitations": public["limitations"],
        },
    }


def engine_fact_boundary_text(bundle: EngineFactBundle) -> str:
    return json.dumps(engine_fact_boundary_payload(bundle), ensure_ascii=True, sort_keys=True)


def engine_fact_namespace_definitions() -> tuple[EngineFactDefinition, ...]:
    return tuple(_ENGINE_FACT_DEFINITIONS[fact_id] for fact_id in sorted(_ENGINE_FACT_DEFINITIONS))


def validate_engine_fact_namespaces(
    engine: str,
    facts: Iterable[MetricFact | LimitationFact],
) -> None:
    for fact in facts:
        validate_engine_fact_namespace(engine, fact.fact_id)


def validate_engine_fact_namespace(engine: str, fact_id: str) -> None:
    _validate_identifier(engine, "engine")
    _validate_identifier(fact_id, "fact_id")
    if engine not in REGISTERED_ENGINE_FACT_ENGINES:
        raise EngineFactContractError(
            f"engine fact namespace is not registered for engine: {engine}"
        )
    definition = _ENGINE_FACT_DEFINITIONS.get(fact_id)
    if definition is None:
        raise EngineFactContractError(f"unregistered normalized engine fact id: {fact_id}")
    if engine not in definition.allowed_engines:
        allowed = ", ".join(sorted(definition.allowed_engines))
        raise EngineFactContractError(
            f"normalized engine fact id {fact_id} is not allowed for engine {engine}; "
            f"allowed engines: {allowed}"
        )


def engine_fact_attention_signal_id(
    *,
    engine: str,
    fact_id: str,
    state: str,
    value: Any = None,
) -> str | None:
    definition = _ENGINE_FACT_DEFINITIONS.get(fact_id)
    if definition is None or engine not in definition.allowed_engines:
        return None
    signal_id = definition.attention_signal_id
    if signal_id is None or state != "supported":
        return None
    if definition.attention_value_gate == "positive_number" and not _is_positive_number(value):
        return None
    return signal_id


def validate_engine_fact_bundle_raw_free(
    bundle: EngineFactBundle,
    *,
    forbidden_tokens: tuple[str, ...] = (),
) -> list[str]:
    text = public_engine_facts_text(bundle)
    lower_text = text.lower()
    violations: list[str] = []

    if redaction.EMAIL_RE.search(text):
        violations.append("email")
    if redaction.IPV4_RE.search(text):
        violations.append("ipv4")
    if redaction.HOSTLIKE_FQDN_RE.search(text):
        violations.append("hostname")
    if URL_RE.search(text):
        violations.append("url")
    if LOCAL_PATH_RE.search(text):
        violations.append("local_path")
    if redaction.SECRET_VALUE_RE.search(text):
        violations.append("secret")
    if SQL_SNIPPET_RE.search(text):
        violations.append("sql")

    for token in forbidden_tokens:
        if token and token.lower() in lower_text:
            violations.append(f"forbidden_token:{token}")

    return sorted(set(violations))


def _validate_state(state: str) -> None:
    if state not in VALID_DIAGNOSTIC_STATES:
        raise EngineFactContractError(f"unsupported diagnostic state: {state}")


def _validate_identifier(value: str, field_name: str) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", value):
        raise EngineFactContractError(f"{field_name} must be a lower-case snake_case identifier")


def _validate_safe_label(value: str, field_name: str) -> None:
    if not value.strip():
        raise EngineFactContractError(f"{field_name} must not be empty")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise EngineFactContractError(f"{field_name} must not contain control characters")


def _is_positive_number(value: Any) -> bool:
    return isinstance(value, (float, int)) and not isinstance(value, bool) and value > 0


def _build_engine_fact_definitions() -> dict[str, EngineFactDefinition]:
    definitions: dict[str, EngineFactDefinition] = {}

    def add(
        fact_ids: Iterable[str],
        *,
        scope: NormalizedFactScope,
        allowed_engines: Iterable[str],
        attention_signal_id: str | None = None,
        attention_value_gate: AttentionValueGate = "state_supported",
    ) -> None:
        engines = frozenset(allowed_engines)
        if not engines or not engines <= REGISTERED_ENGINE_FACT_ENGINES:
            raise EngineFactContractError("engine fact definition has unsupported engines")
        for fact_id in fact_ids:
            _validate_identifier(fact_id, "fact_id")
            _validate_engine_fact_definition_naming(
                fact_id=fact_id,
                scope=scope,
                allowed_engines=engines,
            )
            if fact_id in definitions:
                raise EngineFactContractError(f"duplicate engine fact definition: {fact_id}")
            definitions[fact_id] = EngineFactDefinition(
                fact_id=fact_id,
                scope=scope,
                allowed_engines=engines,
                attention_signal_id=attention_signal_id,
                attention_value_gate=attention_value_gate,
            )

    add(
        ("planning_time_ms",),
        scope="distributed_sql_family",
        allowed_engines=("impala", "trino"),
    )
    add(
        ("source_contract",),
        scope="source_boundary",
        allowed_engines=("spark", "trino"),
    )
    add(
        ("cluster_events",),
        scope="support_boundary",
        allowed_engines=("impala", "trino"),
    )

    add(
        (
            "admission_result",
            "admission_time_ms",
            "admission_wait_ms",
            "backend_start_time_ms",
            "backend_startup_latency_max_ms",
            "client_fetch_evidence_tier",
            "client_fetch_wait_ms",
            "exec_node_row_count_conclusions",
            "exec_node_unsafe_operator_count",
            "fetch_time_ms",
            "fragment_instance_count",
            "fragment_instances_per_host_max",
            "fragment_lifecycle_instance_count",
            "fragment_section_count",
            "impala_profile_json",
            "incomplete_or_cancelled_exec_nodes",
            "metadata_context",
            "per_node_bytes_read_max_bytes",
            "per_node_peak_memory_max_bytes",
            "profile_analysis_support",
            "profile_compatibility",
            "profile_dialect",
            "profile_primary_bottleneck_policy",
            "profile_total_time_ms",
            "query_timeline_duration_ms",
            "query_wall_clock_ms",
            "rows_available_time_ms",
            "runtime_metrics",
            "runtime_node_count",
            "total_bytes_read",
            "total_bytes_sent",
            "zero_rows_not_meaningful_for_incomplete_nodes",
        ),
        scope="engine_specific",
        allowed_engines=("impala",),
    )
    add(
        ("backend_execution_tail_candidates",),
        scope="engine_specific",
        allowed_engines=("impala",),
        attention_signal_id="execution_tail_candidate",
    )
    add(
        ("spill_or_scratch_evidence",),
        scope="engine_specific",
        allowed_engines=("impala",),
        attention_signal_id="spill_or_scratch_evidence",
    )

    add(
        (
            "no_admission_model",
            "no_fragment_lifecycle",
            "no_live_metadata_collection",
            "no_metadata_identifier_output",
            "no_profile_counters",
            "query_detail_fetch",
            "query_detail_import",
            "query_list_blocked_reason_count",
            "query_list_cpu_duration_present_count",
            "query_list_elapsed_1s_to_10s_count",
            "query_list_elapsed_duration_present_count",
            "query_list_elapsed_over_10m_count",
            "query_list_elapsed_under_1s_count",
            "query_list_execution_duration_present_count",
            "query_list_external_error_count",
            "query_list_failed_count",
            "query_list_finished_count",
            "query_list_fully_blocked_present_count",
            "query_list_output_size_present_count",
            "query_list_peak_total_memory_present_count",
            "query_list_peak_user_memory_over_100gb_count",
            "query_list_peak_user_memory_present_count",
            "query_list_peak_user_memory_under_1mb_count",
            "query_list_physical_input_size_present_count",
            "query_list_planning_duration_present_count",
            "query_list_processed_input_rows_present_count",
            "query_list_processed_input_unknown_count",
            "query_list_queued_duration_present_count",
            "query_list_queued_over_1m_count",
            "query_list_queued_under_1s_count",
            "query_list_records_seen",
            "query_list_records_summarized",
            "query_list_source_granularity",
            "query_list_spilled_data_size_present_count",
            "query_list_split_queue_blocked_count",
            "query_list_stats_present_count",
            "query_list_user_error_count",
            "query_list_waiting_for_memory_blocked_count",
            "trino_blocked_signal",
            "trino_completed_split_count",
            "trino_cpu_time_ms",
            "trino_elapsed_time_ms",
            "trino_execution_time_ms",
            "trino_input_bytes",
            "trino_input_rows",
            "trino_metadata_column_stats_missing_count",
            "trino_metadata_column_stats_present_count",
            "trino_metadata_columns_checked",
            "trino_metadata_relations_checked",
            "trino_metadata_stats_completeness",
            "trino_metadata_summary_import",
            "trino_output_bytes",
            "trino_output_rows",
            "trino_peak_memory_bytes",
            "trino_queued_time_ms",
            "trino_stage_count",
            "trino_statement_execution",
            "trino_task_count",
            "trino_version_family",
            "trino_wall_time_ms",
        ),
        scope="engine_specific",
        allowed_engines=("trino",),
    )
    add(
        ("trino_connector_metric_signal",),
        scope="engine_specific",
        allowed_engines=("trino",),
        attention_signal_id="connector_metric_signal",
    )
    add(
        ("trino_failed_task_count",),
        scope="engine_specific",
        allowed_engines=("trino",),
        attention_signal_id="task_failures_observed",
        attention_value_gate="positive_number",
    )
    add(
        ("trino_resource_group_queue_time_ms",),
        scope="engine_specific",
        allowed_engines=("trino",),
        attention_signal_id="blocked_or_admission_wait",
        attention_value_gate="positive_number",
    )
    add(
        ("trino_retried_task_count",),
        scope="engine_specific",
        allowed_engines=("trino",),
        attention_signal_id="task_retries_observed",
        attention_value_gate="positive_number",
    )
    add(
        ("trino_spilled_bytes",),
        scope="engine_specific",
        allowed_engines=("trino",),
        attention_signal_id="spill_or_scratch_evidence",
    )
    add(
        ("trino_stage_skew_candidate",),
        scope="engine_specific",
        allowed_engines=("trino",),
        attention_signal_id="stage_skew_candidate",
    )

    add(
        (
            "cluster_manager_context",
            "executor_loss",
            "live_history_server_collection",
            "no_browser_report_surface",
            "no_live_history_server_collection",
            "no_product_support",
            "no_raw_event_log",
            "no_spark_job_execution",
            "spark_fixture_import",
            "spark_history_source_coverage",
            "sql_execution_endpoint",
            "task_summary_endpoint",
            "structured_streaming_not_modeled",
        ),
        scope="support_boundary",
        allowed_engines=("spark",),
    )
    add(
        (
            "spark_adaptive_execution_enabled",
            "spark_application_attempt_count",
            "spark_application_attempt_state",
            "spark_application_lifecycle",
            "spark_dynamic_allocation_observed",
            "spark_executor_loss_count",
            "spark_executor_memory_capacity_bytes",
            "spark_executor_memory_used_bytes",
            "spark_finished_job_count",
            "spark_input_bytes",
            "spark_input_rows",
            "spark_linked_job_count",
            "spark_output_bytes",
            "spark_output_rows",
            "spark_plan_shape_coverage",
            "spark_query_linkage",
            "spark_running_job_count",
            "spark_sampled_task_count",
            "spark_shuffle_read_bytes",
            "spark_shuffle_write_bytes",
            "spark_skipped_job_count",
            "spark_sql_elapsed_time_ms",
            "spark_stage_count",
            "spark_task_count",
            "spark_task_duration_10s_to_1m_count",
            "spark_task_duration_1s_to_10s_count",
            "spark_task_duration_under_1s_count",
            "spark_unknown_job_count",
            "spark_version_family",
        ),
        scope="engine_specific",
        allowed_engines=("spark",),
    )
    add(
        ("spark_adaptive_plan_changed",),
        scope="engine_specific",
        allowed_engines=("spark",),
        attention_signal_id="adaptive_plan_change_observed",
    )
    add(
        ("spark_executor_churn_observed",),
        scope="engine_specific",
        allowed_engines=("spark",),
        attention_signal_id="executor_churn_observed",
    )
    add(
        ("spark_failed_job_count",),
        scope="engine_specific",
        allowed_engines=("spark",),
        attention_signal_id="job_failures_observed",
        attention_value_gate="positive_number",
    )
    add(
        ("spark_failed_stage_count",),
        scope="engine_specific",
        allowed_engines=("spark",),
        attention_signal_id="stage_failures_observed",
        attention_value_gate="positive_number",
    )
    add(
        ("spark_failed_task_count",),
        scope="engine_specific",
        allowed_engines=("spark",),
        attention_signal_id="task_failures_observed",
        attention_value_gate="positive_number",
    )
    add(
        ("spark_retried_task_count",),
        scope="engine_specific",
        allowed_engines=("spark",),
        attention_signal_id="task_retries_observed",
        attention_value_gate="positive_number",
    )
    add(
        ("spark_task_duration_over_1m_count",),
        scope="engine_specific",
        allowed_engines=("spark",),
        attention_signal_id="execution_tail_candidate",
        attention_value_gate="positive_number",
    )
    add(
        ("spark_scheduler_delay_ms",),
        scope="engine_specific",
        allowed_engines=("spark",),
        attention_signal_id="spark_scheduler_delay_observed",
        attention_value_gate="positive_number",
    )
    add(
        ("spark_spilled_bytes",),
        scope="engine_specific",
        allowed_engines=("spark",),
        attention_signal_id="spill_or_scratch_evidence",
    )
    add(
        ("spark_stage_skew_candidate",),
        scope="engine_specific",
        allowed_engines=("spark",),
        attention_signal_id="stage_skew_candidate",
    )

    return definitions


def _validate_engine_fact_definition_naming(
    *,
    fact_id: str,
    scope: NormalizedFactScope,
    allowed_engines: frozenset[str],
) -> None:
    if scope in {"shared", "distributed_sql_family"}:
        if len(allowed_engines) < 2:
            raise EngineFactContractError(
                "shared engine fact definitions must allow more than one engine"
            )
        if fact_id.startswith(ENGINE_PREFIXES):
            raise EngineFactContractError(
                "shared engine fact ids must not use engine-specific prefixes"
            )
        return
    if scope != "engine_specific":
        return
    if allowed_engines == frozenset({"trino"}):
        if fact_id.startswith(TRINO_ENGINE_SPECIFIC_ALLOWED_PREFIXES):
            return
        raise EngineFactContractError(
            "new Trino engine-specific fact ids must use a trino_, query_detail_, "
            "query_list_, or no_ prefix"
        )
    if allowed_engines == frozenset({"spark"}):
        if fact_id.startswith(SPARK_ENGINE_SPECIFIC_ALLOWED_PREFIXES):
            return
        raise EngineFactContractError("new Spark engine-specific fact ids must use a spark_ prefix")
    if allowed_engines == frozenset({"impala"}):
        return
    raise EngineFactContractError(
        "engine-specific fact definitions must belong to exactly one engine"
    )


_ENGINE_FACT_DEFINITIONS = _build_engine_fact_definitions()
