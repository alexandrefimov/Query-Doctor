"""Recent scan view model dataclasses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from query_doctor.web.job_progress import JobProgressView


@dataclass(frozen=True)
class RecentScanPrimaryBottleneckView:
    unavailable: bool
    label: str
    confidence: str
    summary: str
    reason_summary: str
    reason_tokens: tuple[str, ...] = ()


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
    optimizer_rewriteability_bucket: str
    optimizer_rewriteability_label: str
    optimizer_fact_summary: str
    optimizer_guardrail_summary: str
    optimizer_review_track_label: str
    optimizer_review_area: str
    optimizer_review_direction: str
    optimizer_review_workload_metric: str
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
    primary_bottleneck: RecentScanPrimaryBottleneckView
    workload_fingerprint: str
    workload_fingerprint_short: str
    workload_group_member_count: int
    workload_group_duration_sec_p95: Any
    workload_baseline_duration_sec_p95: Any
    workload_baseline_sample_count: int
    workload_regression: str
    score_value: float
    score_severity: str
    has_failure: bool
    has_spill: bool
    start_time: Any = ""
    source_locators: dict[str, tuple["RecentScanSourceLocatorView", ...]] | None = None
    action_outcome_summary: str = "none"
    pool: Any = ""


@dataclass(frozen=True)
class RecentScanWorkloadGroupView:
    fingerprint: str
    fingerprint_short: str
    member_count: int
    duration_sec_p50: Any
    duration_sec_p95: Any
    duration_sec_total: Any
    pool_top: str
    primary_bottleneck_top: str
    score_top: str
    baseline_duration_sec_p95: Any
    baseline_sample_count: int
    regression: str
    shape_summary: str
    table_summary: str
    member_case_ids: tuple[str, ...]


@dataclass(frozen=True)
class RecentScanWorkloadGroupsView:
    groups: tuple[RecentScanWorkloadGroupView, ...]


@dataclass(frozen=True)
class RecentScanWorkloadHistoryView:
    enabled: bool
    loaded_record_count: int
    appended_record_count: int
    append_status: str
    regression_counts: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class RecentScanWorkloadDigestEntryView:
    fingerprint: str
    fingerprint_short: str
    member_count: int
    duration_sec_total: Any
    duration_sec_p95: Any
    pool_top: str
    owner_top: str
    priority: str
    evidence: str
    outcome_summary: str


@dataclass(frozen=True)
class RecentScanWorkloadAdminDigestEntryView:
    scope: str
    name: str
    group_count: int
    run_count: int
    duration_sec_total: Any
    top_fingerprint: str
    top_fingerprint_short: str
    top_group_impact: Any
    group_fingerprints: tuple[str, ...]
    signal_group_fingerprints: tuple[tuple[str, tuple[str, ...]], ...]
    signal_counts: tuple[tuple[str, int], ...]
    signals: str
    evidence: str


@dataclass(frozen=True)
class RecentScanWorkloadActionQueueEntryView:
    fingerprint: str
    fingerprint_short: str
    priority: str
    signal: str
    recommendation_id: str
    group_impact: Any
    pool_top: str
    owner_top: str
    evidence: str
    next_step: str
    review_anchor: str
    verification_metric: str
    verification: str
    outcome_summary: str


@dataclass(frozen=True)
class RecentScanWorkloadDigestView:
    regressions: tuple[RecentScanWorkloadDigestEntryView, ...]
    admission_runtime: tuple[RecentScanWorkloadDigestEntryView, ...]
    stats: tuple[RecentScanWorkloadDigestEntryView, ...]
    spill: tuple[RecentScanWorkloadDigestEntryView, ...]
    status_issues: tuple[RecentScanWorkloadDigestEntryView, ...]
    low_value: tuple[RecentScanWorkloadDigestEntryView, ...]
    admin: tuple[RecentScanWorkloadAdminDigestEntryView, ...]
    action_queue: tuple[RecentScanWorkloadActionQueueEntryView, ...]


@dataclass(frozen=True)
class RecentScanWorkloadRepresentativeCaseView:
    role: str
    reason: str
    case_id: str
    query_id: Any
    user: Any
    duration_sec: Any
    score: Any
    score_severity: str
    primary_bottleneck: str


@dataclass(frozen=True)
class RecentScanWorkloadActionHintView:
    title: str
    recommendation_id: str
    priority: str
    evidence: str
    where_to_look: str
    change_direction: str
    verification_metric: str
    verification: str
    outcome_summary: str


@dataclass(frozen=True)
class RecentScanWorkloadDetailView:
    fingerprint: str
    fingerprint_short: str
    member_count: int
    duration_sec_p50: Any
    duration_sec_p95: Any
    duration_sec_total: Any
    pool_top: str
    owner_top: str
    primary_bottleneck_top: str
    score_top: str
    impact_summary: str
    frequent_short_summary: str
    bottleneck_distribution: str
    limitations: tuple[str, ...]
    baseline_duration_sec_p95: Any
    baseline_sample_count: int
    regression: str
    shape_summary: str
    table_summary: str
    outcome_summary: str
    member_case_ids: tuple[str, ...]
    action_hints: tuple[RecentScanWorkloadActionHintView, ...]
    representatives: tuple[RecentScanWorkloadRepresentativeCaseView, ...]


@dataclass(frozen=True)
class RecentScanSummaryView:
    header_items: tuple[tuple[str, Any], ...]
    rows: tuple[RecentScanCaseRowView, ...]
    workload_groups: RecentScanWorkloadGroupsView
    workload_history: RecentScanWorkloadHistoryView | None
    workload_digest: RecentScanWorkloadDigestView
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
    progress_view: JobProgressView | None = None
    unavailable_reason: str = ""
    error_info: dict[str, object] | None = None


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
class RecentScanQueryContextView:
    unavailable: bool
    summary_items: tuple[tuple[str, Any], ...]


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
class RecentScanDataMovementView:
    unavailable: bool
    summary_items: tuple[tuple[str, Any], ...]
    limitations: tuple[str, ...]


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
    row_estimate_evidence: str
    partition_coverage: str
    stats_context: str
    interpretation: str
    guardrail: str


@dataclass(frozen=True)
class RecentScanDiagnosticFactView:
    fact_id: str
    question: str
    label: str
    value: Any
    unit: str = ""
    severity: str = "neutral"
    relevance: int = 0
    interpretation: str = ""
    source_anchor: str = ""
    value_kind: str = "text"


@dataclass(frozen=True)
class RecentScanDiagnosticQuestionGroupView:
    group_id: str
    title: str
    prompt: str
    facts: tuple[RecentScanDiagnosticFactView, ...]


@dataclass(frozen=True)
class RecentScanDiagnosticQuestionsView:
    groups: tuple[RecentScanDiagnosticQuestionGroupView, ...]


@dataclass(frozen=True)
class RecentScanScoreReasonView:
    title: str
    explanation: str


@dataclass(frozen=True)
class RecentScanScoreReasonsView:
    reasons: tuple[RecentScanScoreReasonView, ...]


@dataclass(frozen=True)
class RecentScanStatusCardView:
    label: str
    value: Any
    value_kind: str


@dataclass(frozen=True)
class RecentScanStatusSummaryView:
    cards: tuple[RecentScanStatusCardView, ...]


@dataclass(frozen=True)
class RecentScanActionCandidateCardView:
    title: str
    body: str
    recommendation_id: str = ""
    source_locators: tuple["RecentScanSourceLocatorView", ...] = ()
    supporting_facts: tuple[RecentScanDiagnosticFactView, ...] = ()
    why: str = ""
    guardrails: str = ""
    change_direction: str = ""
    verification: str = ""


@dataclass(frozen=True)
class RecentScanSourceLocatorView:
    kind: str
    label: str
    coordinate: str
    detail: str
    line_span: tuple[int, int] | None = None
    line_span_source: str = ""


@dataclass(frozen=True)
class RecentScanActionCandidatesView:
    cards: tuple[RecentScanActionCandidateCardView, ...]


@dataclass(frozen=True)
class RecentScanTechnicalDetailsView:
    fields: tuple[tuple[str, Any], ...]


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
    source_locators: dict[str, tuple[RecentScanSourceLocatorView, ...]]
    metadata: RecentScanMetadataView
    cm_metrics: RecentScanCmMetricsView
    query_context: RecentScanQueryContextView
    runtime_diagnosis: RecentScanRuntimeDiagnosisView
    data_movement: RecentScanDataMovementView
    cluster_runtime_context: RecentScanClusterRuntimeContextView
    runtime_verdict: RecentScanRuntimeVerdictView
    evidence_quality: RecentScanEvidenceQualityView
    stats_quality: RecentScanStatsQualityView
    primary_bottleneck: RecentScanPrimaryBottleneckView
    workload_fingerprint: str
    workload_fingerprint_short: str
    workload_group_member_count: int
    workload_group_duration_sec_p95: Any
    workload_baseline_duration_sec_p95: Any
    workload_baseline_sample_count: int
    workload_regression: str
    report_action: ReportActionView
    score_severity: str
    diagnostic_facts: tuple[RecentScanDiagnosticFactView, ...] = ()
    source_limitations: tuple[str, ...] = ()
