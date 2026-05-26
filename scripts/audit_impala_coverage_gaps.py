#!/usr/bin/env python3
"""Audit raw-free Impala diagnostic coverage gaps across batch summaries."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, TextIO


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.analyzer.data_movement import data_movement_facts_from_analysis  # noqa: E402
from query_doctor.analyzer.case_bottleneck import primary_bottleneck_profile_policy  # noqa: E402
from query_doctor.analyzer.profile_evidence import (  # noqa: E402
    DATA_MOVEMENT_PRIMARY_MIN_EXCHANGE_MS,
    DATA_MOVEMENT_PRIMARY_MIN_EXCHANGE_SHARE,
    medium_data_movement_threshold,
)
from query_doctor.analyzer.runtime_admission import (  # noqa: E402
    runtime_admission_facts_from_analysis,
)
from query_doctor.analyzer.scan_skew import scan_skew_facts_from_analysis  # noqa: E402
from scripts.audit_profile_evidence_gates import (  # noqa: E402
    EvidenceGateAuditInputError,
    analysis_path_for,
    bool_value,
    int_value,
    load_json_object,
    resolve_case_dir,
    summary_cases,
    text_value,
)


@dataclass(frozen=True)
class FollowUpDefinition:
    priority: str
    why: str
    next_step: str


FOLLOW_UPS: dict[str, FollowUpDefinition] = {
    "missing_analysis": FollowUpDefinition(
        "P0",
        "Some selected cases did not reach deterministic analyzer output.",
        "Retry collection or inspect bounded safe failure categories before using the batch for calibration.",
    ),
    "profile_policy_not_supported": FollowUpDefinition(
        "P0",
        "Profile-derived findings must fail closed when the profile policy is unsupported.",
        "Add dialect/source fixtures before widening profile-derived primary routing.",
    ),
    "unknown_primary_bottleneck": FollowUpDefinition(
        "P1",
        "Unknown primary labels show where deterministic evidence is still insufficient.",
        "Sample safe analyzer facts for these cases and add the narrowest missing evidence parser or limitation.",
    ),
    "missing_primary_bottleneck_label": FollowUpDefinition(
        "P1",
        "Analyzed cases should carry an explicit primary-bottleneck label, even when the label is unknown.",
        "Inspect analyzer summary assembly before treating these cases as diagnostic gaps.",
    ),
    "profile_docs_registry_not_available": FollowUpDefinition(
        "P1",
        "The bundled registry is safe, but live profile counter labels would improve version calibration.",
        "Run or improve optional `/profile_docs` collection where the source supports it; otherwise extend bundled aliases.",
    ),
    "profile_docs_missing_allowlisted_labels": FollowUpDefinition(
        "P1",
        "Missing allowlisted labels keep interpreted counters at UNKNOWN stability.",
        "Refresh the versioned registry only for counter families already interpreted by the analyzer.",
    ),
    "metadata_context_not_collected": FollowUpDefinition(
        "P1",
        "Without bounded metadata, storage family and stats context often remain unknown.",
        "Run a metadata-enabled Recent smoke for top cases or improve safe metadata collection coverage.",
    ),
    "storage_context_unknown": FollowUpDefinition(
        "P1",
        "Storage semantics affect HDFS locality, object-store, and cache diagnostics.",
        "Use safe metadata location summaries where available; keep raw paths and URIs out of facts.",
    ),
    "resource_trace_absent": FollowUpDefinition(
        "P1",
        "Resource trace can add CPU/I/O/network context when the profile source contains it.",
        "Keep absence as unknown; add selected-query isolation before allowing stronger CPU/I/O diagnosis.",
    ),
    "runtime_metrics_not_available": FollowUpDefinition(
        "P1",
        "Runtime metrics can corroborate selected-query facts but should not create causes alone.",
        "Improve configured CM or Prometheus metric availability only as supporting context.",
    ),
    "cluster_events_not_available": FollowUpDefinition(
        "P2",
        "Cluster events can explain external service pressure around selected queries.",
        "Keep events bounded and context-only until a selected-query fact supports promotion.",
    ),
    "runtime_filter_context_observed": FollowUpDefinition(
        "P1",
        "Observed runtime-filter context is useful only after producer, consumer, timing, and target scans are mapped.",
        "Add fixtures for safe producer/consumer mapping before claiming missing or late filters.",
    ),
    "runtime_filter_arrival_gap_observed": FollowUpDefinition(
        "P1",
        "Arrival gaps are a strong research signal but not enough for root-cause wording.",
        "Corroborate with target scan, producer timing, spill context, and completed-node evidence.",
    ),
    "runtime_filter_producer_consumer_mapped": FollowUpDefinition(
        "P1",
        "Producer/consumer pairing is now available as safe aggregate context for future target-scan mapping.",
        "Keep it context-only until target scans, timing, spill context, and node completion are mapped.",
    ),
    "runtime_filter_unpaired_plan_context": FollowUpDefinition(
        "P1",
        "Unpaired producer or consumer context can indicate parser coverage gaps or real plan-side asymmetry.",
        "Add fixtures for the repeated shape before turning this into diagnostic wording.",
    ),
    "runtime_filter_target_scan_mapped": FollowUpDefinition(
        "P1",
        "Runtime-filter consumers are mapped to safe aggregate scan targets for future target-scan evidence.",
        "Keep target-scan context below finding status until timing, spill context, and node completion corroborate it.",
    ),
    "runtime_filter_target_scan_incomplete": FollowUpDefinition(
        "P1",
        "Some runtime-filter consumers could not be mapped to paired scan targets.",
        "Inspect repeated safe shapes and add parser fixtures before changing diagnostic wording.",
    ),
    "runtime_filter_routing_table_observed": FollowUpDefinition(
        "P1",
        "Runtime-filter routing/final tables add bounded aggregate routing, pending, and completion context.",
        "Keep routing-table context below finding status until target scans, timing, spill context, and node completion corroborate it.",
    ),
    "scan_skew_medium_supporting": FollowUpDefinition(
        "P1",
        "Medium scan-spread signals are useful, but not enough for primary runtime-skew routing.",
        "Look for stable bytes, memory, or network corroboration before strengthening the finding.",
    ),
    "data_movement_supporting_not_primary": FollowUpDefinition(
        "P1",
        "Data movement can be a supported follow-up without enough mapped exchange time for primary routing.",
        "Calibrate exchange elapsed-time/share thresholds on comparable reruns.",
    ),
    "data_movement_exchange_context_only": FollowUpDefinition(
        "P1",
        "Mapped exchange operators without enough byte/time support identify parser or threshold gaps.",
        "Inspect safe exchange evidence tiers before adding aliases or changing thresholds.",
    ),
    "memory_pressure_supported": FollowUpDefinition(
        "P1",
        "Spill/scratch-backed memory facts are deterministic selected-query evidence.",
        "Use them to calibrate memory-pressure wording and metadata/query-shape follow-ups.",
    ),
}


@dataclass
class CoverageAuditResult:
    summary_paths: list[Path]
    total_cases: int = 0
    analyzed_cases: int = 0
    missing_analysis_count: int = 0
    analysis_error_count: int = 0
    primary_counts: Counter[str] = field(default_factory=Counter)
    profile_dialect_counts: Counter[str] = field(default_factory=Counter)
    profile_policy_counts: Counter[str] = field(default_factory=Counter)
    profile_counter_registry_counts: Counter[str] = field(default_factory=Counter)
    source_compatibility_counts: Counter[str] = field(default_factory=Counter)
    source_status_counts: Counter[str] = field(default_factory=Counter)
    evidence_quality_counts: Counter[str] = field(default_factory=Counter)
    unknown_primary_reason_counts: Counter[str] = field(default_factory=Counter)
    storage_unknown_reason_counts: Counter[str] = field(default_factory=Counter)
    scan_skew_supporting_reason_counts: Counter[str] = field(default_factory=Counter)
    data_movement_supporting_reason_counts: Counter[str] = field(default_factory=Counter)
    data_movement_calibration_signal_counts: Counter[str] = field(default_factory=Counter)
    runtime_filter_calibration_signal_counts: Counter[str] = field(default_factory=Counter)
    gap_counts: Counter[str] = field(default_factory=Counter)
    opportunity_counts: Counter[str] = field(default_factory=Counter)

    @property
    def ok(self) -> bool:
        return not self.analysis_error_count


def counter_key(*parts: object) -> str:
    return "/".join(text_value(part) for part in parts)


def primary_label_value(value: object) -> str:
    text = str(value or "").strip().lower()
    return text if text else "missing"


def reason_key(value: object) -> str:
    if isinstance(value, str):
        return value.strip() or "missing_reason"
    if isinstance(value, (list, tuple)):
        parts = [str(item).strip() for item in value if str(item).strip()]
        return "+".join(parts) if parts else "missing_reason"
    return "missing_reason"


def percent(count: int, total: int) -> str:
    if total <= 0:
        return "0.0%"
    return f"{(count / total) * 100:.1f}%"


def add_gap(result: CoverageAuditResult, key: str) -> None:
    result.gap_counts[key] += 1


def add_opportunity(result: CoverageAuditResult, key: str) -> None:
    result.opportunity_counts[key] += 1


def audit_summaries(summary_paths: Iterable[Path]) -> CoverageAuditResult:
    paths = [path.resolve(strict=True) for path in summary_paths]
    result = CoverageAuditResult(summary_paths=paths)
    for summary_path in paths:
        audit_summary_into(result, summary_path)
    return result


def audit_summary_into(result: CoverageAuditResult, summary_path: Path) -> None:
    summary = load_json_object(summary_path)
    cases = summary_cases(summary)
    result.total_cases += len(cases)

    for case in cases:
        primary = case.get("case_primary_bottleneck")
        primary = primary if isinstance(primary, dict) else {}
        primary_label = primary_label_value(primary.get("label"))
        result.primary_counts[primary_label] += 1

        case_dir = resolve_case_dir(summary_path, case)
        analysis_path = analysis_path_for(case_dir) if case_dir is not None else None
        if analysis_path is None:
            result.missing_analysis_count += 1
            add_gap(result, "missing_analysis")
            continue
        try:
            analysis = load_json_object(analysis_path)
        except EvidenceGateAuditInputError:
            result.analysis_error_count += 1
            continue
        if primary_label == "unknown":
            add_gap(result, "unknown_primary_bottleneck")
            analysis_primary = analysis.get("case_primary_bottleneck")
            analysis_primary = analysis_primary if isinstance(analysis_primary, dict) else {}
            result.unknown_primary_reason_counts[
                reason_key(analysis_primary.get("reasons") or primary.get("reasons"))
            ] += 1
        elif primary_label == "missing":
            add_gap(result, "missing_primary_bottleneck_label")
        audit_analysis(result, analysis)


def audit_analysis(result: CoverageAuditResult, analysis: dict[str, Any]) -> None:
    result.analyzed_cases += 1

    profile = analysis.get("profile_format")
    profile = profile if isinstance(profile, dict) else {}
    profile_dialect = text_value(profile.get("profile_dialect"))
    profile_policy = primary_bottleneck_profile_policy(analysis)
    result.profile_dialect_counts[profile_dialect] += 1
    result.profile_policy_counts[profile_policy] += 1
    if profile_policy != "supported":
        add_gap(result, "profile_policy_not_supported")

    registry = analysis.get("profile_counter_registry")
    registry = registry if isinstance(registry, dict) else {}
    registry_status = allowed_token(registry.get("status"), {"available", "not_observed"})
    registry_source = allowed_token(registry.get("source"), {"bundled", "profile_docs"})
    result.profile_counter_registry_counts[counter_key(registry_status, registry_source)] += 1
    if not (registry_status == "available" and registry_source == "profile_docs"):
        add_gap(result, "profile_docs_registry_not_available")
    if (
        registry_status == "available"
        and registry_source == "profile_docs"
        and int_value(registry.get("missing_counter_count")) > 0
    ):
        add_gap(result, "profile_docs_missing_allowlisted_labels")

    audit_source_compatibility(result, analysis, profile=profile, registry=registry)

    evidence_quality = analysis.get("evidence_quality")
    evidence_quality = evidence_quality if isinstance(evidence_quality, dict) else {}
    result.evidence_quality_counts[text_value(evidence_quality.get("level"))] += 1

    audit_source_provenance(result, analysis)
    audit_storage_context(result, analysis)
    audit_resource_trace(result, analysis)
    audit_runtime_filter_opportunities(result, analysis)
    audit_scan_skew_opportunities(result, analysis)
    audit_data_movement_opportunities(result, analysis)
    audit_memory_pressure_opportunities(result, analysis)


def audit_source_compatibility(
    result: CoverageAuditResult,
    analysis: dict[str, Any],
    *,
    profile: dict[str, Any],
    registry: dict[str, Any],
) -> None:
    capabilities = profile.get("source_capabilities")
    capabilities = capabilities if isinstance(capabilities, dict) else {}
    query_context = analysis.get("query_context")
    query_context = query_context if isinstance(query_context, dict) else {}
    admission_context = analysis.get("admission_context")
    admission_context = admission_context if isinstance(admission_context, dict) else {}
    resource_trace = analysis.get("resource_trace")
    resource_trace = resource_trace if isinstance(resource_trace, dict) else {}

    result.source_compatibility_counts[
        counter_key(
            "impala_distribution",
            allowed_token(
                profile.get("impala_distribution"),
                {"apache_impala", "cloudera_impala", "unknown"},
            ),
        )
    ] += 1
    result.source_compatibility_counts[
        counter_key("impala_major_version", safe_major_version(profile.get("impala_major_version")))
    ] += 1
    result.source_compatibility_counts[
        counter_key(
            "impala_build_type",
            allowed_token(profile.get("impala_build_type"), {"release", "snapshot", "debug"}),
        )
    ] += 1
    result.source_compatibility_counts[
        counter_key(
            "profile_response_format",
            allowed_token(profile.get("profile_response_format"), {"json", "text", "default"}),
        )
    ] += 1
    for key in ("json_profile_probe", "profile_docs_probe"):
        result.source_compatibility_counts[
            counter_key(key, allowed_token(capabilities.get(key), {"enabled", "not_configured"}))
        ] += 1
    for key in ("json_profile_payload", "text_profile_payload"):
        result.source_compatibility_counts[
            counter_key(
                key,
                allowed_token(
                    capabilities.get(key),
                    {
                        "observed",
                        "mapped_limited",
                        "wrapped_text_observed",
                        "not_selected",
                        "selected_but_unmapped",
                    },
                ),
            )
        ] += 1
    result.source_compatibility_counts[
        counter_key(
            "primary_profile_routing",
            allowed_token(
                capabilities.get("primary_profile_routing"),
                {"supported", "non_profile_only", "unsupported"},
            ),
        )
    ] += 1
    result.source_compatibility_counts[
        counter_key(
            "profile_fetch_attempts",
            safe_count_bucket(capabilities.get("profile_fetch_attempt_count")),
        )
    ] += 1
    result.source_compatibility_counts[
        counter_key(
            "profile_docs_fetch_attempts",
            safe_count_bucket(capabilities.get("profile_docs_fetch_attempt_count")),
        )
    ] += 1
    result.source_compatibility_counts[
        counter_key(
            "profile_counter_registry",
            allowed_token(registry.get("status"), {"available", "not_observed", "unknown"}),
            allowed_token(registry.get("source"), {"bundled", "profile_docs", "unknown"}),
        )
    ] += 1
    result.source_compatibility_counts[
        counter_key(
            "admission_context_probe",
            enabled_or_unknown(query_context.get("admission_context_probe_enabled")),
        )
    ] += 1
    result.source_compatibility_counts[
        counter_key(
            "admission_context_fetch_attempts",
            safe_count_bucket(query_context.get("admission_context_fetch_attempt_count")),
        )
    ] += 1
    result.source_compatibility_counts[
        counter_key("admission_context", admission_context_status(admission_context))
    ] += 1
    result.source_compatibility_counts[
        counter_key(
            "resource_trace",
            allowed_token(
                resource_trace.get("status"),
                {"available", "unknown", "not_observed", "unavailable"},
            ),
        )
    ] += 1


def normalized_token(value: object) -> str:
    text = str(value or "unknown").strip().lower()
    text = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in text)
    text = "_".join(part for part in text.split("_") if part)
    return text[:60] if text else "unknown"


def allowed_token(value: object, allowed: set[str]) -> str:
    text = normalized_token(value)
    return text if text in allowed else "unknown"


def safe_major_version(value: object) -> str:
    parsed = int_value(value)
    return f"major_{parsed}" if parsed > 0 else "unknown"


def safe_count_bucket(value: object) -> str:
    count = int_value(value)
    if count <= 0:
        return "none"
    if count == 1:
        return "1"
    if count <= 4:
        return "2_4"
    return "5_plus"


def enabled_or_unknown(value: object) -> str:
    if isinstance(value, bool):
        return "enabled" if value else "not_configured"
    return "unknown"


def admission_context_status(context: dict[str, Any]) -> str:
    if not context:
        return "not_collected"
    status = allowed_token(context.get("status"), {"available", "unavailable"})
    if status in {"available", "unavailable"}:
        return status
    return "unknown"


def audit_source_provenance(result: CoverageAuditResult, analysis: dict[str, Any]) -> None:
    provenance = analysis.get("source_provenance")
    items = provenance.get("items") if isinstance(provenance, dict) else None
    if not isinstance(items, list):
        result.source_status_counts["source_provenance/unknown"] += 1
        return

    for item in items:
        if not isinstance(item, dict):
            continue
        kind = text_value(item.get("kind"))
        status = text_value(item.get("status"))
        result.source_status_counts[counter_key(kind, status)] += 1
        if kind == "metadata" and status in {"none", "unavailable", "unknown"}:
            add_gap(result, "metadata_context_not_collected")
        elif kind == "metrics" and status in {"none", "unavailable", "unknown"}:
            add_gap(result, "runtime_metrics_not_available")
        elif kind == "events" and status in {"none", "unavailable", "unknown"}:
            add_gap(result, "cluster_events_not_available")


def audit_storage_context(result: CoverageAuditResult, analysis: dict[str, Any]) -> None:
    context = analysis.get("storage_context")
    context = context if isinstance(context, dict) else {}
    if text_value(context.get("storage_family")) == "unknown":
        add_gap(result, "storage_context_unknown")
        result.storage_unknown_reason_counts[storage_unknown_reason(context)] += 1


def storage_unknown_reason(context: dict[str, Any]) -> str:
    source = text_value(context.get("source"))
    if source in {
        "table_metadata_view_only",
        "table_metadata_no_location",
        "unknown",
    }:
        return source
    if int_value(context.get("metadata_table_count")) <= 0:
        return "metadata_not_available"
    if int_value(context.get("location_scheme_count")) <= 0:
        return "table_metadata_no_location"
    return source or "unknown"


def audit_resource_trace(result: CoverageAuditResult, analysis: dict[str, Any]) -> None:
    facts = analysis.get("resource_trace")
    facts = facts if isinstance(facts, dict) else {}
    if (
        text_value(facts.get("status")) != "available"
        or int_value(facts.get("observed_metric_count")) <= 0
    ):
        add_gap(result, "resource_trace_absent")


def audit_runtime_filter_opportunities(
    result: CoverageAuditResult, analysis: dict[str, Any]
) -> None:
    facts = analysis.get("runtime_filters")
    facts = facts if isinstance(facts, dict) else {}
    observed = any(
        int_value(facts.get(field)) > 0
        for field in (
            "runtime_filter_lines",
            "runtime_filter_id_count",
            "bloom_filter_counter_lines",
            "bloom_filter_counter_nonzero_lines",
        )
    )
    if observed:
        add_opportunity(result, "runtime_filter_context_observed")
    if int_value(facts.get("missing_arrival_lines")) > 0:
        add_opportunity(result, "runtime_filter_arrival_gap_observed")
    mapping_status = text_value(facts.get("producer_consumer_mapping_status"))
    if mapping_status in {"mapped", "partial"}:
        add_opportunity(result, "runtime_filter_producer_consumer_mapped")
    if mapping_status in {"partial", "unpaired"}:
        add_opportunity(result, "runtime_filter_unpaired_plan_context")
    target_scan_status = text_value(facts.get("target_scan_mapping_status"))
    if target_scan_status in {"mapped", "partial"}:
        add_opportunity(result, "runtime_filter_target_scan_mapped")
    if target_scan_status in {"partial", "unpaired", "missing_target_scan"}:
        add_opportunity(result, "runtime_filter_target_scan_incomplete")
    if text_value(facts.get("routing_table_status")) == "observed":
        add_opportunity(result, "runtime_filter_routing_table_observed")
    result.runtime_filter_calibration_signal_counts.update(
        runtime_filter_calibration_signals(facts, observed=observed)
    )


def runtime_filter_calibration_signals(facts: dict[str, Any], *, observed: bool) -> tuple[str, ...]:
    signals: list[str] = []
    if observed:
        signals.append("context_observed")
    else:
        signals.append("context_not_observed")

    evidence_tier = text_value(facts.get("evidence_tier"))
    if evidence_tier == "context_only":
        signals.append("evidence_context_only")
    elif evidence_tier == "unsupported":
        signals.append("evidence_unsupported")

    profile_dialect = text_value(facts.get("profile_dialect"))
    if profile_dialect == "classic_text_profile":
        signals.append("classic_text_profile")
    elif profile_dialect not in {"", "unknown"}:
        signals.append("unsupported_profile_dialect")

    mapping_status = text_value(facts.get("producer_consumer_mapping_status"))
    if mapping_status == "mapped":
        signals.append("producer_consumer_mapped")
    elif mapping_status == "partial":
        signals.append("producer_consumer_partial")
    elif mapping_status == "unpaired":
        signals.append("producer_consumer_unpaired")
    elif mapping_status == "not_observed" and observed:
        signals.append("producer_consumer_not_observed")

    target_scan_status = text_value(facts.get("target_scan_mapping_status"))
    if target_scan_status == "mapped":
        signals.append("target_scan_mapped")
    elif target_scan_status == "partial":
        signals.append("target_scan_partial")
    elif target_scan_status in {"unpaired", "missing_target_scan"}:
        signals.append("target_scan_incomplete")
    elif target_scan_status == "not_observed" and observed:
        signals.append("target_scan_not_observed")

    if int_value(facts.get("target_scan_consumer_lines")) > 0:
        signals.append("target_scan_consumer_observed")
    if int_value(facts.get("non_scan_consumer_lines")) > 0:
        signals.append("non_scan_consumer_observed")
    if int_value(facts.get("unknown_target_consumer_lines")) > 0:
        signals.append("unknown_target_consumer_observed")

    if text_value(facts.get("routing_table_status")) == "observed":
        signals.append("routing_table_observed")
    if int_value(facts.get("routing_filter_count")) > 0:
        signals.append("routing_rows_observed")
    if int_value(facts.get("final_filter_count")) > 0:
        signals.append("final_rows_observed")
    if int_value(facts.get("enabled_filter_count")) > 0:
        signals.append("enabled_filters_observed")
    if int_value(facts.get("partition_filter_count")) > 0:
        signals.append("partition_filters_observed")
    if int_value(facts.get("pending_nonzero_count")) > 0:
        signals.append("pending_filters_observed")
    if int_value(facts.get("arrival_observed_count")) > 0:
        signals.append("routing_arrival_observed")
    if int_value(facts.get("completed_observed_count")) > 0:
        signals.append("routing_completion_observed")

    arrival_status_value = text_value(facts.get("arrival_status"))
    if arrival_status_value == "missing_observed":
        signals.append("arrival_gap_observed")
    elif arrival_status_value == "all_arrived_observed":
        signals.append("all_arrived_observed")
    elif arrival_status_value == "mixed":
        signals.extend(("arrival_gap_observed", "all_arrived_observed", "arrival_mixed"))
    elif arrival_status_value == "not_reported" and observed:
        signals.append("arrival_status_not_reported")

    if int_value(facts.get("bloom_filter_counter_lines")) > 0:
        signals.append("bloom_counter_observed")
    if int_value(facts.get("bloom_filter_counter_nonzero_lines")) > 0:
        signals.append("bloom_counter_nonzero")

    runtime_filter_effectiveness = text_value(facts.get("exec_node_runtime_filter_effectiveness"))
    if runtime_filter_effectiveness == "supported":
        signals.append("exec_node_effectiveness_supported")
    elif runtime_filter_effectiveness == "limited":
        signals.append("exec_node_effectiveness_limited")
    elif runtime_filter_effectiveness == "unknown":
        signals.append("exec_node_effectiveness_unknown")

    return tuple(signals) or ("runtime_filter_calibration_unspecified",)


def audit_scan_skew_opportunities(result: CoverageAuditResult, analysis: dict[str, Any]) -> None:
    facts = scan_skew_facts_from_analysis(analysis)
    if facts.finding_supported and facts.evidence_tier == "medium" and not facts.primary_supported:
        add_opportunity(result, "scan_skew_medium_supporting")
        result.scan_skew_supporting_reason_counts.update(scan_skew_supporting_reasons(facts))


def scan_skew_supporting_reasons(facts: Any) -> tuple[str, ...]:
    reasons: list[str] = []
    runtime_status = text_value(getattr(facts, "runtime_status", ""))
    if runtime_status == "timing_unknown":
        reasons.append("timing_unknown")
    elif runtime_status == "short_running":
        reasons.append("phase_short_running")
    elif runtime_status == "long_running_balanced":
        reasons.append("phase_long_running_balanced")
    elif runtime_status == "long_running_imbalanced":
        if text_value(getattr(facts, "skew_metric", "")) == "rows_produced":
            reasons.append("row_spread_without_scan_bytes")
        if int_value(getattr(facts, "corroborating_metric_count", 0)) < 2:
            reasons.append("long_running_imbalanced_single_metric")
    else:
        reasons.append("runtime_status_unknown")

    if text_value(getattr(facts, "evidence_source", "")) == "mapped_backend_group_summary":
        reasons.append("mapped_group_summary")
    return tuple(reasons) or ("medium_supporting_unspecified",)


def audit_data_movement_opportunities(
    result: CoverageAuditResult, analysis: dict[str, Any]
) -> None:
    facts = data_movement_facts_from_analysis(analysis)
    result.data_movement_calibration_signal_counts.update(
        data_movement_calibration_signals(facts, analysis)
    )
    if facts.finding_supported and not facts.primary_supported:
        add_opportunity(result, "data_movement_supporting_not_primary")
        result.data_movement_supporting_reason_counts.update(
            data_movement_supporting_reasons(facts, analysis)
        )
    if (
        facts.status == "context_only"
        and facts.evidence_tier == "context_only"
        and facts.exchange_operator_count > 0
    ):
        add_opportunity(result, "data_movement_exchange_context_only")
        result.data_movement_supporting_reason_counts.update(
            data_movement_supporting_reasons(facts, analysis)
        )


def data_movement_supporting_reasons(facts: Any, analysis: dict[str, Any]) -> tuple[str, ...]:
    reasons: list[str] = []
    total_bytes = numeric_counter_value(getattr(facts, "total_bytes_sent", None))
    threshold = medium_data_movement_threshold(analysis)
    exchange_ms = numeric_counter_value(getattr(facts, "exchange_elapsed_ms", None))
    exchange_share = numeric_counter_value(getattr(facts, "exchange_elapsed_share", None))

    if bool_value(getattr(facts, "finding_supported", False)):
        reasons.append("finding_supported_not_primary")
    elif text_value(getattr(facts, "status", "")) == "context_only":
        reasons.append("exchange_context_without_supported_finding")

    if total_bytes is None:
        reasons.append("bytes_missing_or_zero")
    elif total_bytes < threshold:
        reasons.append("bytes_below_finding_threshold")
    elif not bool_value(getattr(facts, "finding_supported", False)):
        reasons.append("bytes_without_supported_finding")

    if exchange_ms is None:
        reasons.append("exchange_timing_unavailable")
    elif exchange_ms < DATA_MOVEMENT_PRIMARY_MIN_EXCHANGE_MS:
        reasons.append("exchange_elapsed_below_primary_threshold")

    if exchange_share is None:
        reasons.append("exchange_share_unknown")
    elif exchange_share < DATA_MOVEMENT_PRIMARY_MIN_EXCHANGE_SHARE:
        reasons.append("exchange_share_below_primary_threshold")

    return tuple(reasons) or ("data_movement_supporting_unspecified",)


def data_movement_calibration_signals(facts: Any, analysis: dict[str, Any]) -> tuple[str, ...]:
    signals: list[str] = []
    status = text_value(getattr(facts, "status", ""))
    evidence_tier = text_value(getattr(facts, "evidence_tier", ""))
    total_bytes = numeric_counter_value(getattr(facts, "total_bytes_sent", None))
    threshold = medium_data_movement_threshold(analysis)
    exchange_count = int_value(getattr(facts, "exchange_operator_count", 0))
    exchange_ms = numeric_counter_value(getattr(facts, "exchange_elapsed_ms", None))
    exchange_share = numeric_counter_value(getattr(facts, "exchange_elapsed_share", None))

    if status:
        signals.append(f"status_{status}")
    if evidence_tier:
        signals.append(f"evidence_{evidence_tier}")

    if bool_value(getattr(facts, "finding_supported", False)):
        signals.append("finding_supported")
    else:
        signals.append("finding_not_supported")

    if bool_value(getattr(facts, "primary_supported", False)):
        signals.append("primary_supported")
    else:
        signals.append("primary_not_supported")

    signals.append(exchange_operator_bucket(exchange_count))

    if total_bytes is None:
        signals.append("bytes_missing_or_zero")
    elif total_bytes >= threshold:
        signals.append("bytes_ge_finding_threshold")
    else:
        signals.append("bytes_below_finding_threshold")

    if exchange_ms is None:
        signals.append("exchange_timing_unavailable")
    elif exchange_ms >= DATA_MOVEMENT_PRIMARY_MIN_EXCHANGE_MS:
        signals.append("exchange_elapsed_ge_primary_threshold")
    else:
        signals.append("exchange_elapsed_below_primary_threshold")

    if exchange_share is None:
        signals.append("exchange_share_unknown")
    elif exchange_share >= DATA_MOVEMENT_PRIMARY_MIN_EXCHANGE_SHARE:
        signals.append("exchange_share_ge_primary_threshold")
    else:
        signals.append("exchange_share_below_primary_threshold")

    return tuple(signals) or ("data_movement_calibration_unspecified",)


def exchange_operator_bucket(count: int) -> str:
    if count <= 0:
        return "exchange_ops_0"
    if count >= 4:
        return "exchange_ops_4_plus"
    return f"exchange_ops_{count}"


def numeric_counter_value(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def audit_memory_pressure_opportunities(
    result: CoverageAuditResult, analysis: dict[str, Any]
) -> None:
    facts = analysis.get("memory_pressure")
    facts = facts if isinstance(facts, dict) else {}
    if bool_value(facts.get("finding_supported")):
        add_opportunity(result, "memory_pressure_supported")


def print_counter(title: str, counter: Counter[str], *, out: TextIO, limit: int) -> None:
    print(f"{title}:", file=out)
    if not counter:
        print("  <none>", file=out)
        return
    for key, count in counter.most_common(limit):
        print(f"  {key}: {count}", file=out)


def print_follow_ups(
    title: str,
    counter: Counter[str],
    *,
    out: TextIO,
    total: int,
    limit: int,
) -> None:
    print(f"{title}:", file=out)
    if not counter:
        print("  <none>", file=out)
        return
    for key, count in counter.most_common(limit):
        definition = FOLLOW_UPS.get(
            key,
            FollowUpDefinition(
                "P2", "Unclassified coverage signal.", "Inspect safe facts before acting."
            ),
        )
        print(
            f"  {definition.priority} {key}: {count} ({percent(count, total)})",
            file=out,
        )
        print(f"    why: {definition.why}", file=out)
        print(f"    next: {definition.next_step}", file=out)


def print_result(result: CoverageAuditResult, *, out: TextIO = sys.stdout, limit: int = 12) -> None:
    print(f"Summaries: {len(result.summary_paths)}", file=out)
    print(
        "Cases: "
        f"total={result.total_cases}, analyzed={result.analyzed_cases}, "
        f"missing_analysis={result.missing_analysis_count}, "
        f"analysis_errors={result.analysis_error_count}",
        file=out,
    )
    print_counter("Primary bottlenecks", result.primary_counts, out=out, limit=limit)
    print_counter("Profile dialects", result.profile_dialect_counts, out=out, limit=limit)
    print_counter("Profile policies", result.profile_policy_counts, out=out, limit=limit)
    print_counter(
        "Profile counter registry",
        result.profile_counter_registry_counts,
        out=out,
        limit=limit,
    )
    print_counter(
        "Impala source compatibility",
        result.source_compatibility_counts,
        out=out,
        limit=limit,
    )
    print_counter("Source coverage", result.source_status_counts, out=out, limit=limit)
    print_counter("Evidence quality", result.evidence_quality_counts, out=out, limit=limit)
    print_counter(
        "Unknown primary reasons",
        result.unknown_primary_reason_counts,
        out=out,
        limit=limit,
    )
    print_counter(
        "Storage unknown reasons",
        result.storage_unknown_reason_counts,
        out=out,
        limit=limit,
    )
    print_counter(
        "Scan skew supporting reasons",
        result.scan_skew_supporting_reason_counts,
        out=out,
        limit=limit,
    )
    print_counter(
        "Data movement supporting reasons",
        result.data_movement_supporting_reason_counts,
        out=out,
        limit=limit,
    )
    print_counter(
        "Data movement calibration signals",
        result.data_movement_calibration_signal_counts,
        out=out,
        limit=limit,
    )
    print_counter(
        "Runtime filter calibration signals",
        result.runtime_filter_calibration_signal_counts,
        out=out,
        limit=limit,
    )
    print_follow_ups(
        "Coverage gaps",
        result.gap_counts,
        out=out,
        total=max(result.total_cases, 1),
        limit=limit,
    )
    print_follow_ups(
        "Observed follow-up opportunities",
        result.opportunity_counts,
        out=out,
        total=max(result.analyzed_cases, 1),
        limit=limit,
    )


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summaries", nargs="+", type=Path, help="Path(s) to batch_summary.json")
    parser.add_argument("--limit", type=int, default=12, help="Rows to print per section")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = audit_summaries(args.summaries)
    except EvidenceGateAuditInputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print_result(result, limit=args.limit)
    return 1 if not result.ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
