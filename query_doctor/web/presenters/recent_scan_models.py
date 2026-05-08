"""Recent scan view model dataclasses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RecentScanCaseRowView:
    rank: int
    case_id: str | None
    query_id: Any
    user: Any
    score: Any
    status_summary: str
    signal_summary: str
    duration_sec: Any
    cardinality_anomaly_count: Any
    memory_anomaly_count: Any
    backend_data_skew: Any
    host_tail_candidate_count: Any
    collection_status: Any
    analysis_status: Any
    metadata_status: Any
    table_stats_status: Any
    report_status: str
    reason_text: str
    optimization_tier: str
    optimization_score: int
    optimization_impact: str
    optimization_confidence: str
    optimization_artifact_status: str
    optimizer_rewrite_support: str
    optimizer_rewrite_support_label: str
    optimizer_rewrite_support_reason: str
    optimization_summary: str
    optimization_review_areas: str
    stats_tier: str
    stats_score: int
    stats_impact: str
    stats_confidence: str
    stats_need_type: str
    stats_speed_benefit: str
    stats_summary: str
    stats_review_areas: str
    stats_required_confirmation: str
    score_value: float
    score_severity: str
    has_failure: bool
    has_spill: bool


@dataclass(frozen=True)
class RecentScanSummaryView:
    header_items: tuple[tuple[str, Any], ...]
    rows: tuple[RecentScanCaseRowView, ...]
    scope_parts: tuple[str, ...]
    empty_message: str | None
    warning_messages: tuple[str, ...]


@dataclass(frozen=True)
class ReportActionView:
    status: str
    running: bool
    trusted: bool
    partial_untrusted: bool
    error: Any
    job_id: str
    stage_label: str
    progress: int
    note: str
    button_label: str
    button_disabled: bool
    show_open_link: bool
    job_kind: str


@dataclass(frozen=True)
class RecentScanMetadataTableView:
    table: Any
    object_type: Any
    statements: dict[str, Any]
    row_count_stats: Any
    column_stats: Any
    observed_columns: Any
    missing_markers: Any
    partition_columns: Any
    file_format: Any
    limitations: str


@dataclass(frozen=True)
class RecentScanMetadataView:
    unavailable: bool
    fallback_note: str
    summary_items: tuple[tuple[str, Any], ...]
    tables: tuple[RecentScanMetadataTableView, ...]


@dataclass(frozen=True)
class RecentScanCmMetricSignalView:
    label: str
    status: Any
    basis: Any


@dataclass(frozen=True)
class RecentScanCmMetricCorrelationView:
    label: str
    status: Any
    metric_status: Any
    strength: Any
    interpretation: Any


@dataclass(frozen=True)
class RecentScanCmMetricsView:
    unavailable: bool
    summary_items: tuple[tuple[str, Any], ...]
    signals: tuple[RecentScanCmMetricSignalView, ...]
    correlations: tuple[RecentScanCmMetricCorrelationView, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class RecentScanRuntimeDiagnosisSignalView:
    title: str
    status: Any
    interpretation: Any
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class RecentScanRuntimeDiagnosisView:
    unavailable: bool
    status: Any
    summary: Any
    guardrail: Any
    signals: tuple[RecentScanRuntimeDiagnosisSignalView, ...]


@dataclass(frozen=True)
class RecentScanClusterRuntimeContextView:
    unavailable: bool
    summary_items: tuple[tuple[str, Any], ...]
    signal_rollup_items: tuple[tuple[str, Any], ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class RecentScanRuntimeVerdictView:
    title: str
    badge_class: str
    summary: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class RecentScanEvidenceQualityView:
    unavailable: bool
    score: Any
    level: str
    strengths: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class RecentScanStatsQualityView:
    unavailable: bool
    status: str
    table_stats: str
    column_stats: str
    interpretation: str
    guardrail: str


@dataclass(frozen=True)
class RecentScanCaseDetailView:
    case_id: str
    query_id: Any
    user: Any
    report_status: str
    trust_note: str
    status_summary: str
    signal_summary: str
    has_spill: bool
    table_stats_status: Any
    score: Any
    duration_sec: Any
    overall_rank: Any
    optimization_rank: Any
    stats_rank: Any
    status_fields: tuple[tuple[str, Any], ...]
    runtime_fields: tuple[tuple[str, Any], ...]
    technical_fields: tuple[tuple[str, Any], ...]
    score_reasons: tuple[str, ...]
    optimization_candidate: dict[str, Any]
    stats_candidate: dict[str, Any]
    metadata: RecentScanMetadataView
    cm_metrics: RecentScanCmMetricsView
    runtime_diagnosis: RecentScanRuntimeDiagnosisView
    cluster_runtime_context: RecentScanClusterRuntimeContextView
    runtime_verdict: RecentScanRuntimeVerdictView
    evidence_quality: RecentScanEvidenceQualityView
    stats_quality: RecentScanStatsQualityView
    report_action: ReportActionView
    score_severity: str
