"""Safe Recent query scan view models for the web UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from query_doctor_web_display_safety import redact_browser_display_text

STATEMENT_LABELS = {
    "SHOW CREATE TABLE": "create metadata",
    "SHOW TABLE STATS": "table stats",
    "SHOW COLUMN STATS": "column stats",
}

CANDIDATE_REASON_LABELS = {
    "selected: SELECT-like user query": "SELECT/WITH query",
    "selected: INSERT query": "INSERT query",
    "selected: DELETE query": "DELETE query",
    "selected: UPSERT query": "UPSERT query",
    "selected: CREATE TABLE AS SELECT query": "CREATE TABLE AS SELECT query",
    "selected: query type indicates user query; SQL verb unknown": "QUERY with unknown SQL verb",
    "eligible but not selected because recent-select limit was reached": "analysis cap reached",
    "excluded: user filter mismatch": "user filter mismatch",
    "excluded: pool filter mismatch": "pool filter mismatch",
    "excluded: query type filter mismatch": "query type mismatch",
    "excluded: running query": "running query",
    "excluded: failed query": "failed query",
    "excluded: cancelled query": "cancelled query",
    "excluded: Query Doctor collector smoke statement": "Query Doctor smoke statement",
    "excluded: admin or metadata statement": "admin or metadata statement",
    "excluded: not SELECT-like query text": "not SELECT/WITH query text",
    "excluded: not analyzable query text": "not analyzable query text",
    "excluded: query type is not user QUERY/SELECT": "not user QUERY/SELECT type",
    "excluded: unknown statement type": "unknown statement type",
    "excluded: duration unknown": "duration unknown",
    "excluded: duration below recent-min-duration-sec": "below minimum duration",
    "excluded: duration above recent-max-duration-sec": "above maximum duration",
}


@dataclass(frozen=True)
class RecentScanCaseRowView:
    rank: int
    case_id: str | None
    query_id: Any
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
class RecentScanCaseDetailView:
    case_id: str
    query_id: Any
    report_status: str
    trust_note: str
    status_summary: str
    signal_summary: str
    has_spill: bool
    table_stats_status: Any
    score: Any
    duration_sec: Any
    status_fields: tuple[tuple[str, Any], ...]
    runtime_fields: tuple[tuple[str, Any], ...]
    technical_fields: tuple[tuple[str, Any], ...]
    score_reasons: tuple[str, ...]
    metadata: RecentScanMetadataView
    cm_metrics: RecentScanCmMetricsView
    report_action: ReportActionView
    score_severity: str


def present_recent_scan_summary(summary: dict[str, Any]) -> RecentScanSummaryView:
    cases = summary.get("cases")
    raw_cases = [case for case in cases if isinstance(case, dict)] if isinstance(cases, list) else []
    rows = tuple(present_recent_scan_case_row(rank, case) for rank, case in enumerate(raw_cases, start=1))
    bad_count = sum(1 for row in rows if row.score_severity in {"failed", "high"})
    suspicious_count = sum(1 for row in rows if row.score_severity == "suspicious")
    good_count = sum(1 for row in rows if row.score_severity == "clean")
    metadata_count = sum(1 for row in rows if str(row.metadata_status).lower() in {"ok", "available", "done", "collected"})
    header_items = (
        ("total", len(rows)),
        ("bad", bad_count),
        ("suspicious", suspicious_count),
        ("good", good_count),
        ("analyzed", safe_display_value(summary.get("selected_count"))),
        ("CM inspected", safe_display_value(summary.get("summaries_inspected"))),
        ("metadata", metadata_count),
    )
    return RecentScanSummaryView(
        header_items=header_items,
        rows=rows,
        scope_parts=recent_scan_scope_parts(summary),
        empty_message=recent_scan_empty_message(summary, case_count=len(rows)),
        warning_messages=recent_scan_warning_messages(summary),
    )


def present_recent_scan_case_row(rank: int, case: dict[str, Any]) -> RecentScanCaseRowView:
    reasons = case.get("score_reasons")
    reason_text = "; ".join(safe_display_text(item) for item in reasons) if isinstance(reasons, list) else ""
    collection_status = safe_display_value(case.get("collection_status"))
    analysis_status = safe_display_value(case.get("analysis_status"))
    metadata_status = safe_display_value(case.get("metadata_status"))
    report_status = batch_report_status(case)
    return RecentScanCaseRowView(
        rank=rank,
        case_id=batch_case_id(case),
        query_id=safe_display_value(case.get("query_id")),
        score=safe_display_value(case.get("score")),
        status_summary=recent_scan_status_summary(
            collection_status,
            analysis_status,
            metadata_status,
            report_status,
        ),
        signal_summary=recent_scan_signal_summary(case),
        duration_sec=safe_display_value(case.get("duration_sec")),
        cardinality_anomaly_count=safe_display_value(case.get("cardinality_anomaly_count")),
        memory_anomaly_count=safe_display_value(case.get("memory_anomaly_count")),
        backend_data_skew=safe_display_value(case.get("backend_data_skew")),
        host_tail_candidate_count=safe_display_value(case.get("host_tail_candidate_count")),
        collection_status=collection_status,
        analysis_status=analysis_status,
        metadata_status=metadata_status,
        table_stats_status=safe_display_value(case.get("table_stats_status")),
        report_status=report_status,
        reason_text=reason_text,
        score_value=numeric_value(case.get("score")),
        score_severity=case_score_severity(case),
        has_failure=case_has_failure(case),
        has_spill=case_has_spill(case),
    )


def present_recent_scan_case_detail(
    case_id: str,
    case: dict[str, Any],
    metadata_facts: dict[str, Any] | None = None,
    cm_metrics_facts: dict[str, Any] | None = None,
    *,
    report_state: dict[str, Any] | None = None,
) -> RecentScanCaseDetailView:
    report_status = batch_case_display_report_status(case, report_state)
    collection_status = safe_display_value(case.get("collection_status"))
    analysis_status = safe_display_value(case.get("analysis_status"))
    metadata_status = safe_display_value(case.get("metadata_status"))
    trust_note = (
        "LLM report is available for this case."
        if report_status == "validated report"
        else "LLM report has not been generated for this case."
    )
    return RecentScanCaseDetailView(
        case_id=safe_display_text(case_id),
        query_id=safe_display_value(case.get("query_id")),
        report_status=report_status,
        trust_note=trust_note,
        status_summary=recent_scan_status_summary(
            collection_status,
            analysis_status,
            metadata_status,
            report_status,
        ),
        signal_summary=recent_scan_signal_summary(case),
        has_spill=case_has_spill(case),
        table_stats_status=safe_display_value(case.get("table_stats_status")),
        score=safe_display_value(case.get("score")),
        duration_sec=safe_display_value(case.get("duration_sec")),
        status_fields=(
            ("case", safe_display_value(case_id)),
            ("query id", safe_display_value(case.get("query_id"))),
            ("score", safe_display_value(case.get("score"))),
            ("duration sec", safe_display_value(case.get("duration_sec"))),
            ("collection", collection_status),
            ("analysis", analysis_status),
            ("metadata", metadata_status),
            ("report", report_status),
        ),
        runtime_fields=(
            ("cardinality anomalies", safe_display_value(case.get("cardinality_anomaly_count"))),
            ("memory anomalies", safe_display_value(case.get("memory_anomaly_count"))),
            ("zero row estimate gaps", safe_display_value(case.get("zero_row_estimate_gap_count"))),
            ("zero memory estimate gaps", safe_display_value(case.get("zero_memory_estimate_gap_count"))),
            ("backend data skew", safe_display_value(case.get("backend_data_skew"))),
            ("host-tail candidates", safe_display_value(case.get("host_tail_candidate_count"))),
        ),
        technical_fields=(
            ("referenced tables", safe_display_value(case.get("referenced_table_count"))),
            ("collected metadata tables", safe_display_value(case.get("collected_metadata_table_count"))),
            ("too large metadata", safe_display_value(case.get("too_large_count"))),
            ("failure category", safe_display_value(case.get("failure_category"))),
            ("cm collect seconds", safe_display_value(case.get("cm_collect_seconds"))),
            ("analysis seconds", safe_display_value(case.get("analysis_seconds"))),
            ("report seconds", safe_display_value(case.get("report_seconds"))),
            ("total seconds", safe_display_value(case.get("total_seconds"))),
            ("report generated", safe_display_value(case.get("report_generated"))),
        ),
        score_reasons=tuple(safe_display_text(reason) for reason in case.get("score_reasons") or [] if reason is not None),
        metadata=present_recent_scan_metadata(case, metadata_facts),
        cm_metrics=present_recent_scan_cm_metrics(cm_metrics_facts),
        report_action=present_report_action(report_state),
        score_severity=case_score_severity(case),
    )


def present_report_action(report_state: dict[str, Any] | None) -> ReportActionView:
    state = report_state if isinstance(report_state, dict) else {}
    status = safe_display_text(state.get("status") or "not_run")
    running = bool(state.get("running"))
    trusted = bool(state.get("trusted"))
    partial_untrusted = bool(state.get("partial") and not trusted)
    return ReportActionView(
        status=status,
        running=running,
        trusted=trusted,
        partial_untrusted=partial_untrusted,
        error=safe_display_value(state.get("error")),
        job_id=safe_display_text(state.get("job_id") or ""),
        stage_label=safe_display_text(state.get("stage_label") or ""),
        progress=clamped_progress(state.get("progress")),
        note=(
            "LLM report generation is running for this selected case."
            if running
            else "Runs one LLM report for this selected case only. No batch-wide report generation is started."
        ),
        button_label="Generating LLM report" if running else "Generate LLM report",
        button_disabled=running,
        show_open_link=trusted,
    )


def clamped_progress(value: Any) -> int:
    try:
        progress = int(float(value))
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, progress))


def present_recent_scan_metadata(case: dict[str, Any], metadata_facts: dict[str, Any] | None) -> RecentScanMetadataView:
    if not metadata_facts:
        fallback_note = (
            "Table-level metadata facts are unavailable. Safe aggregate metadata facts "
            "from batch_summary.json are shown instead."
            if has_metadata_aggregate_facts(case)
            else ""
        )
        return RecentScanMetadataView(
            unavailable=not bool(fallback_note),
            fallback_note=fallback_note,
            summary_items=metadata_summary_items(case, {}),
            tables=(),
        )
    statement_counts = metadata_facts.get("statement_counts")
    if not isinstance(statement_counts, dict):
        statement_counts = {}
    tables = metadata_facts.get("tables")
    raw_tables = [table for table in tables if isinstance(table, dict)] if isinstance(tables, list) else []
    return RecentScanMetadataView(
        unavailable=False,
        fallback_note="",
        summary_items=metadata_summary_items(case, statement_counts),
        tables=tuple(present_metadata_table(table) for table in raw_tables),
    )


def present_metadata_table(table: dict[str, Any]) -> RecentScanMetadataTableView:
    statements = table.get("statements")
    safe_statements = safe_statement_statuses(statements if isinstance(statements, dict) else {})
    return RecentScanMetadataTableView(
        table=safe_display_value(table.get("table")),
        object_type=safe_display_value(table.get("object type")),
        statements=safe_statements,
        row_count_stats=safe_display_value(table.get("table stats row-count completeness")),
        column_stats=safe_display_value(table.get("column stats completeness")),
        observed_columns=safe_display_value(table.get("column stats columns observed")),
        missing_markers=safe_display_value(table.get("column stats missing/unknown markers")),
        partition_columns=safe_display_value(table.get("partition columns")),
        file_format=safe_display_value(table.get("file format")),
        limitations=metadata_fact_limitations(table, safe_statements),
    )


def present_recent_scan_cm_metrics(cm_metrics_facts: dict[str, Any] | None) -> RecentScanCmMetricsView:
    if not cm_metrics_facts:
        return RecentScanCmMetricsView(
            unavailable=True,
            summary_items=(),
            signals=(),
            correlations=(),
            limitations=(),
        )
    summary = cm_metrics_facts.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    raw_signals = cm_metrics_facts.get("signals")
    signals = [signal for signal in raw_signals if isinstance(signal, dict)] if isinstance(raw_signals, list) else []
    correlation_summary = cm_metrics_facts.get("correlation_summary")
    if not isinstance(correlation_summary, dict):
        correlation_summary = {}
    raw_correlations = cm_metrics_facts.get("correlations")
    correlations = (
        [correlation for correlation in raw_correlations if isinstance(correlation, dict)]
        if isinstance(raw_correlations, list)
        else []
    )
    raw_limitations = cm_metrics_facts.get("limitations")
    limitations = raw_limitations if isinstance(raw_limitations, list) else []
    summary_pairs: list[tuple[str, Any]] = [
        ("status", safe_display_value(summary.get("status"))),
        ("coverage", safe_display_value(summary.get("coverage"))),
    ]
    for key in ("correlated_signals", "context_only_signals"):
        if key in correlation_summary:
            summary_pairs.append((key, safe_display_value(correlation_summary.get(key))))
    summary_items = tuple(summary_pairs)
    signal_views = tuple(
        RecentScanCmMetricSignalView(
            label=safe_display_text(signal.get("label")),
            status=safe_display_value(signal.get("status")),
            basis=safe_display_value(signal.get("basis")),
        )
        for signal in signals
    )
    correlation_views = tuple(
        RecentScanCmMetricCorrelationView(
            label=safe_display_text(correlation.get("label")),
            status=safe_display_value(correlation.get("status")),
            metric_status=safe_display_value(correlation.get("metric_status")),
            strength=safe_display_value(correlation.get("strength")),
            interpretation=safe_display_value(correlation.get("interpretation")),
        )
        for correlation in correlations
    )
    limitation_views = tuple(safe_display_text(item) for item in limitations if item is not None)
    unavailable = (
        not signal_views
        and not correlation_views
        and all(value in {None, "", "unknown"} for _, value in summary_items)
    )
    return RecentScanCmMetricsView(
        unavailable=unavailable,
        summary_items=summary_items,
        signals=signal_views,
        correlations=correlation_views,
        limitations=limitation_views,
    )


def metadata_summary_items(case: dict[str, Any], statement_counts: dict[Any, Any]) -> tuple[tuple[str, Any], ...]:
    counts_known = bool(statement_counts)
    items: list[tuple[str, Any]] = [
        ("metadata status", safe_display_value(case.get("metadata_status"))),
        ("referenced tables", safe_display_value(case.get("referenced_table_count"))),
        ("collected metadata tables", safe_display_value(case.get("collected_metadata_table_count"))),
        ("too large metadata", safe_display_value(case.get("too_large_count"))),
        ("metadata statements", metadata_statement_counts_summary(statement_counts) if counts_known else None),
    ]
    metadata_reasons = metadata_score_reasons(case)
    if metadata_reasons:
        items.append(("metadata score reasons", "; ".join(metadata_reasons)))
    return tuple(items)


def recent_scan_scope_parts(summary: dict[str, Any]) -> tuple[str, ...]:
    parts: list[str] = []
    summaries = summary.get("summaries_inspected")
    if summary.get("cm_summary_safety_cap_hit"):
        cap = summary.get("cm_summary_safety_cap") or summaries
        parts.append(f"CM match limit hit: {safe_display_text(cap)}")
    elif summaries is not None:
        parts.append(f"CM summaries inspected: {safe_display_text(summaries)}")
    if summary.get("from_time") or summary.get("to_time"):
        parts.append(
            "CM time window: "
            f"{safe_display_text(summary.get('from_time') or 'unknown')} -> "
            f"{safe_display_text(summary.get('to_time') or 'unknown')}"
        )
    elif summary.get("recent_window_minutes") is not None:
        parts.append(f"Search depth: {safe_display_text(summary.get('recent_window_minutes'))} minutes")
    parts.append(f"Duration filter: {safe_display_text(summary.get('duration_filter') or 'none')}")
    duration_filter_mode = str(summary.get("duration_filter_mode") or "").strip().lower()
    if duration_filter_mode and duration_filter_mode != "none":
        parts.append(f"Duration filtering: {safe_display_text(summary.get('duration_filter_mode'))}")
    if summary.get("triage_profile_limit") is not None:
        parts.append(f"Analyzer limit: {safe_display_text(summary.get('triage_profile_limit'))}")
    if summary.get("metadata_top_limit") is not None:
        parts.append(
            f"Metadata budget: up to {safe_display_text(summary.get('metadata_top_limit'))} bad/suspicious cases"
        )
    if summary.get("query_type_filter") is not None:
        parts.append(f"Query type: {query_type_filter_label(summary.get('query_type_filter'))}")
    if summary.get("only_running"):
        parts.append("Status: running only")
    if summary.get("user_filter_present"):
        parts.append("User filter: set")
    else:
        parts.append("User filter: all users")
    if summary.get("pool_filter_present"):
        parts.append("Pool filter: set")
    else:
        parts.append("Pool filter: all pools")
    if summary.get("cm_jobs") is not None or summary.get("jobs") is not None:
        parts.append(
            "Parallelism: "
            f"CM {safe_display_text(summary.get('cm_jobs') or 'n/a')}, "
            f"analyzer {safe_display_text(summary.get('jobs') or 'n/a')}, "
            f"metadata {safe_display_text(summary.get('metadata_jobs') or 'n/a')}"
        )
    parts.extend(candidate_selection_scope_parts(summary))
    return tuple(parts)


def candidate_selection_scope_parts(summary: dict[str, Any]) -> list[str]:
    parts: list[str] = []
    if "selected_count" in summary:
        selected = numeric_count(summary.get("selected_count"))
        parts.append(f"Analyzed queries: {safe_display_text(selected)}")
    if "candidate_exclusion_count" in summary:
        excluded = numeric_count(summary.get("candidate_exclusion_count"))
        parts.append(f"Excluded before analysis: {safe_display_text(excluded)}")

    reason_counts = summary.get("candidate_reason_counts")
    if not isinstance(reason_counts, dict):
        return parts
    exclusion_reasons: list[tuple[str, int, str]] = []
    for reason, count in reason_counts.items():
        reason_text = str(reason)
        if reason_text.startswith("selected:"):
            continue
        parsed_count = numeric_count(count)
        if parsed_count is None or parsed_count <= 0:
            continue
        exclusion_reasons.append((reason_text, parsed_count, candidate_reason_label(reason_text)))
    if exclusion_reasons:
        top = "; ".join(
            f"{label}: {count}{candidate_reason_sql_verb_detail(summary, reason)}"
            for reason, count, label in exclusion_reasons[:3]
        )
        parts.append(f"Top exclusions: {safe_display_text(top)}")
    return parts


def candidate_reason_sql_verb_detail(summary: dict[str, Any], reason: str) -> str:
    breakdowns = summary.get("candidate_reason_sql_verb_counts")
    if not isinstance(breakdowns, dict):
        return ""
    counts = breakdowns.get(reason)
    if not isinstance(counts, dict):
        return ""
    items: list[tuple[str, int]] = []
    for verb, count in counts.items():
        parsed = numeric_count(count)
        if parsed is None or parsed <= 0:
            continue
        label = "unknown/no SQL verb" if str(verb).lower() == "unknown" else str(verb)
        items.append((label, parsed))
    items.sort(key=lambda item: (-item[1], item[0]))
    if not items:
        return ""
    visible = items[:3]
    hidden_total = sum(count for _label, count in items[3:])
    parts = [f"{label} {count}" for label, count in visible]
    if hidden_total:
        parts.append(f"other {hidden_total}")
    top = ", ".join(parts)
    return f" ({top})"


def query_type_filter_label(value: Any) -> str:
    text = safe_display_text(value).strip()
    if not text or text.lower() == "all":
        return "all supported"
    return text


def candidate_reason_label(reason: str) -> str:
    return CANDIDATE_REASON_LABELS.get(reason, safe_display_text(reason))


def case_has_spill(case: dict[str, Any]) -> bool:
    reasons = case.get("score_reasons")
    if not isinstance(reasons, list):
        return False
    return any("spill/scratch evidence: non-zero metrics" in str(reason).lower() for reason in reasons)


def recent_scan_empty_message(summary: dict[str, Any], *, case_count: int) -> str | None:
    if summary.get("scan_too_broad"):
        return "This hour has more matching queries than the scan limit. Narrow the filters or choose a smaller hour slice."
    if summary.get("discovery_failed"):
        return "Recent scan discovery failed before case selection. Check CM connectivity and access settings, then run again."
    selected = numeric_count(summary.get("selected_count"))
    if selected or case_count:
        return None
    summaries = summary.get("summaries_inspected")
    if summaries is not None and numeric_count(summaries) == 0:
        return "No matching queries found for this hour bucket. Try another hour or changing filters."
    if summaries is not None:
        return "No query candidates matched the current scan criteria. Try another hour or changing filters."
    return None


def recent_scan_warning_messages(summary: dict[str, Any]) -> tuple[str, ...]:
    warnings = summary.get("warnings")
    if not isinstance(warnings, list):
        return ()
    return tuple(safe_display_text(warning) for warning in warnings[:3] if warning is not None)


def recent_scan_status_summary(
    collection_status: Any,
    analysis_status: Any,
    metadata_status: Any,
    report_status: str,
) -> str:
    return (
        f"collection {safe_display_text(collection_status)}; "
        f"analysis {safe_display_text(analysis_status)}; "
        f"metadata {safe_display_text(metadata_status)}; "
        f"report {safe_display_text(report_status)}"
    )


def recent_scan_signal_summary(case: dict[str, Any]) -> str:
    signals: list[str] = []
    cardinality = numeric_count(case.get("cardinality_anomaly_count"))
    memory = numeric_count(case.get("memory_anomaly_count"))
    tail = numeric_count(case.get("host_tail_candidate_count"))
    if cardinality > 0:
        signals.append(f"cardinality {safe_display_text(cardinality)}")
    if memory > 0:
        signals.append(f"memory {safe_display_text(memory)}")
    if safe_truthy(case.get("backend_data_skew")):
        signals.append("skew observed")
    if tail > 0:
        signals.append(f"host-tail {safe_display_text(tail)}")
    if signals:
        return "; ".join(signals)
    if numeric_value(case.get("score")) <= 0:
        return "no positive analyzer signals"
    return "positive score from detailed analyzer reasons"


def case_score_severity(case: dict[str, Any]) -> str:
    explicit = str(case.get("score_severity") or "").strip().lower()
    if explicit in {"failed", "high", "suspicious", "clean"}:
        return explicit
    if case_has_failure(case):
        return "failed"
    score = numeric_value(case.get("score"))
    if score <= 0:
        return "clean"
    cardinality = numeric_count(case.get("cardinality_anomaly_count"))
    memory = numeric_count(case.get("memory_anomaly_count"))
    zero_row_gaps = numeric_count(case.get("zero_row_estimate_gap_count"))
    zero_memory_gaps = numeric_count(case.get("zero_memory_estimate_gap_count"))
    host_tail = numeric_count(case.get("host_tail_candidate_count"))
    if (
        score >= 30
        or cardinality >= 5
        or memory >= 4
        or zero_row_gaps >= 4
        or zero_memory_gaps >= 4
        or (cardinality >= 3 and memory >= 2)
        or (zero_row_gaps >= 2 and zero_memory_gaps >= 2)
        or (safe_truthy(case.get("backend_data_skew")) and host_tail >= 2)
    ):
        return "high"
    return "suspicious"


def safe_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y"}


def safe_statement_statuses(statements: dict[Any, Any]) -> dict[str, Any]:
    return {
        statement_display_label(key): safe_display_value(value)
        for key, value in statements.items()
    }


def metadata_fact_limitations(table: dict[str, Any], statements: dict[str, Any]) -> str:
    limitations: list[str] = []
    object_type = str(table.get("object type") or "unknown")
    table_stats = str(table.get("table stats row-count completeness") or "unknown")
    column_stats = str(table.get("column stats completeness") or "unknown")
    if object_type == "view":
        limitations.append("view metadata stats not applicable")
    for statement, status in statements.items():
        status_text = str(status or "unknown")
        if status_text in {"error", "too_large", "timeout", "not_applicable"}:
            limitations.append(f"{statement}: {status_text}")
    if table_stats not in {"available", "unknown"}:
        limitations.append(f"row-count stats: {safe_display_text(table_stats)}")
    if column_stats not in {"available", "unknown"}:
        limitations.append(f"column stats: {safe_display_text(column_stats)}")
    return "; ".join(limitations) if limitations else "none observed"


def statement_display_label(statement: Any) -> str:
    return STATEMENT_LABELS.get(str(statement), safe_display_text(statement))


def metadata_statement_counts_summary(statement_counts: dict[Any, Any]) -> str:
    parts = [
        ("ok", statement_counts.get("ok", 0)),
        ("error", statement_counts.get("error", 0)),
        ("not_applicable", statement_counts.get("not_applicable", 0)),
        ("too_large", statement_counts.get("too_large", 0)),
    ]
    return " / ".join(f"{int(numeric_value(value))} {label}" for label, value in parts)


def metadata_score_reasons(case: dict[str, Any]) -> list[str]:
    reasons = case.get("score_reasons")
    if not isinstance(reasons, list):
        return []
    result: list[str] = []
    for reason in reasons:
        text = safe_display_text(reason)
        lower = text.lower()
        if any(marker in lower for marker in ("metadata", "stats", "statistic", "статист")):
            result.append(text)
    return result


def has_metadata_aggregate_facts(case: dict[str, Any]) -> bool:
    metadata_status = str(case.get("metadata_status") or "").lower()
    if metadata_status in {"collected", "failed", "partial"}:
        return True
    for key in ("referenced_table_count", "collected_metadata_table_count", "too_large_count"):
        if numeric_value(case.get(key)) > 0:
            return True
    return bool(metadata_score_reasons(case))


def batch_report_status(case: dict[str, Any]) -> str:
    validation = str(case.get("report_validation_status") or "not_run")
    generated = case.get("report_generated") is True
    if validation == "failed_partial_untrusted":
        return "partial untrusted"
    if generated and validation == "passed":
        return "validated report"
    if generated:
        return f"generated/{safe_display_text(validation)}"
    return safe_display_text(validation)


def batch_case_display_report_status(case: dict[str, Any], report_state: dict[str, Any] | None = None) -> str:
    if isinstance(report_state, dict):
        status = str(report_state.get("status") or "")
        if status == "generated" or report_state.get("trusted"):
            return "validated report"
        if status == "running":
            return "running"
        if status == "failed":
            return "failed"
        if status == "partial_untrusted":
            return "partial untrusted"
    return batch_report_status(case)


def case_has_failure(case: dict[str, Any]) -> bool:
    if case.get("failure_category"):
        return True
    return any(
        case.get(name) == "failed"
        for name in ("collection_status", "analysis_status", "metadata_status", "report_validation_status")
    )


def batch_case_id(case: dict[str, Any]) -> str | None:
    value = case.get("case_index")
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return f"case-{parsed:03d}"


def numeric_count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def numeric_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def safe_display_value(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    return safe_display_text(value)


def safe_display_text(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "unknown"
    return redact_browser_display_text(
        value,
        redact_field_names=True,
        redact_artifact_markers=True,
        redact_model_names=True,
    )
