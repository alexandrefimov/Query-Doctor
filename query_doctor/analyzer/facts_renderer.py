"""Markdown rendering for deterministic analyzer facts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from query_doctor.analyzer.cm_metrics import build_cm_metrics_facts
from query_doctor.analyzer.scalars import fmt_bytes, fmt_duration, fmt_rows, numeric_context_value


def md_escape(value: str) -> str:
    return value.replace("|", "\\|")


def render_operator_table(title: str, rows: list[dict[str, Any]], max_rows: int | None = None) -> list[str]:
    out = [f"## {title}", ""]
    if not rows:
        out += ["No parsed operators in this category.", ""]
        return out
    visible_rows = rows[:max_rows] if max_rows is not None else rows
    out.append(
        "| operator | time | actual rows | estimated rows | rows ratio | peak mem | est. peak mem | mem ratio |"
    )
    out.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for op in visible_rows:
        out.append(
            "| "
            + " | ".join(
                [
                    md_escape(op["label"]),
                    op["time"],
                    op["actual_rows_human"],
                    op["estimated_rows_human"],
                    op["rows_ratio_human"],
                    op["peak_mem_human"],
                    op["estimated_peak_mem_human"],
                    op["mem_ratio_human"],
                ]
            )
            + " |"
        )
    if len(visible_rows) < len(rows):
        out.append(f"| ... {len(rows) - len(visible_rows)} more in verbose output |  |  |  |  |  |  |  |")
    out.append("")
    return out


def render_summary(analysis: dict[str, Any]) -> list[str]:
    return [
        "## Summary",
        "",
        f"- Parsed operators: {len(analysis['operators'])}",
        f"- Cardinality anomalies: {len(analysis['cardinality_anomalies'])}",
        f"- Memory anomalies: {len(analysis['memory_anomalies'])}",
        f"- Zero/unknown row estimate gaps: {len(analysis['zero_row_estimate_gaps'])}",
        f"- Zero/unknown memory estimate gaps: {len(analysis['zero_memory_estimate_gaps'])}",
        "",
    ]


def render_action_cards(analysis: dict[str, Any]) -> list[str]:
    lines = ["## Action Cards", ""]
    cards = analysis.get("action_cards") or []
    if not cards:
        lines.append("No deterministic action cards were triggered from the parsed evidence.")
        lines.append("")
        return lines

    for i, card in enumerate(cards, start=1):
        lines.append(f"### Card {i}: {card['title']}")
        lines.append("")
        lines.append("Finding:")
        lines.append(f"- {card['finding']}")
        lines.append("")
        lines.append("Evidence:")
        for item in card["evidence"]:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("Admin actions:")
        for item in card["admin_actions"]:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("User actions:")
        for item in card["user_actions"]:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("How to verify:")
        for item in card["how_to_verify"]:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("Missing evidence:")
        for item in card["missing_evidence"]:
            lines.append(f"- {item}")
        lines.append("")
    return lines


def render_findings(analysis: dict[str, Any], verbose: bool) -> list[str]:
    lines = ["## Findings", ""]
    if not analysis["findings"]:
        lines.append("No deterministic findings were produced from the digest.")
        lines.append("")
        return lines

    for finding in analysis["findings"]:
        heading = finding.get("title") or finding["id"]
        lines.append(f"### {heading} [{finding['severity']}]")
        lines.append("")
        lines.append(f"- {finding['summary']}")
        if finding.get("operators"):
            operators = finding["operators"] if verbose else finding["operators"][:5]
            lines.append("- Operators:")
            for op in operators:
                lines.append(
                    f"  - {op['label']}: time={op['time']}, "
                    f"rows={op['actual_rows_human']} vs est {op['estimated_rows_human']} "
                    f"({op['rows_ratio_human']}), mem={op['peak_mem_human']} vs est "
                    f"{op['estimated_peak_mem_human']} ({op['mem_ratio_human']})"
                )
            if not verbose and len(finding["operators"]) > len(operators):
                lines.append(f"  - ... {len(finding['operators']) - len(operators)} more in verbose output")
        if finding.get("evidence_lines") and (verbose or finding.get("id") == "host_execution_tail_suspected"):
            lines.append("- Evidence lines:")
            for ev in finding["evidence_lines"]:
                lines.append(f"  - `{ev}`")
        if finding.get("admin_actions"):
            lines.append("- Admin checks:")
            for action in finding["admin_actions"]:
                lines.append(f"  - {action}")
        if finding.get("missing_evidence"):
            lines.append("- Missing evidence:")
            for item in finding["missing_evidence"]:
                lines.append(f"  - {item}")
        lines.append("")
    return lines


def render_backend_tail_evidence(analysis: dict[str, Any]) -> list[str]:
    backend = analysis.get("backend_tail") or {}
    if not backend.get("rows_parsed"):
        return []

    lines = ["## Backend / Host Tail Evidence", "", "### Summary", ""]
    lines.extend(
        [
            f"- backend rows parsed: {backend['rows_parsed']}",
            f"- host tail candidates: {backend['tail_candidate_count']}",
            f"- execution tail candidates: {backend['execution_tail_candidate_count']}",
            f"- read-rate tail candidates: {backend['read_rate_tail_candidate_count']}",
            f"- write-path tail candidates: {backend['write_path_tail_candidate_count']}",
            f"- data skew: {backend['data_skew']} ({backend['data_skew_reason']})",
            f"- execution skew: {backend['execution_skew']}",
            f"- write-path anomaly: {backend['write_path_anomaly']}",
            "",
        ]
    )
    candidates = backend.get("candidates") or []
    if not candidates:
        lines.extend(["### Normalized tail candidates", "", "- none", ""])
        lines.extend(["### Host tail candidates", ""])
        lines.append("- none")
        lines.append("")
        return lines

    lines.extend(["### Normalized tail candidates", ""])
    lines.append("| host | fragment | family | metric_key | worst | peer | gap | ratio |")
    lines.append("|---|---|---|---|---:|---:|---:|---:|")
    for candidate in candidates:
        lines.append(
            "| "
            + " | ".join(
                [
                    md_escape(str(candidate.get("host") or "unknown")),
                    md_escape(str(candidate.get("fragment_group") or "unknown")),
                    md_escape(str(candidate.get("metric_family") or "unknown")),
                    md_escape(str(candidate.get("metric_key") or "unknown")),
                    md_escape(str(candidate.get("worst_human") or "n/a")),
                    md_escape(str(candidate.get("peer_human") or "n/a")),
                    md_escape(str(candidate.get("gap_human") or "n/a")),
                    md_escape(str(candidate.get("ratio_human") or "n/a")),
                ]
            )
            + " |"
        )
    lines.append("")

    lines.extend(["### Host tail candidates", ""])
    lines.append("| host | evidence | ratio/metric |")
    lines.append("|---|---|---:|")
    for candidate in candidates:
        host = candidate.get("host") or "unknown"
        evidence = candidate.get("evidence") or "n/a"
        ratio = candidate.get("ratio_human") or "n/a"
        lines.append(f"| {md_escape(host)} | {md_escape(evidence)} | {ratio} |")
    lines.append("")
    lines.extend(["### Interpretation guardrails", ""])
    if backend.get("execution_tail_candidates"):
        lines.append("- Execution skew is suspected from parsed backend execution-time counters.")
    else:
        lines.append("- Execution skew is not confirmed by backend execution-time tail candidates.")
    if backend.get("write_path_candidates"):
        lines.append("- Host-specific HDFS/RPC/write path issue is suspected, not proven.")
    else:
        lines.append("- Host-specific HDFS/RPC/write path issue is not confirmed by backend write-path counters.")
    lines.append("")
    return lines


def render_verbose_evidence(analysis: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    if analysis.get("stats_evidence_lines"):
        lines.append("## Stats/cardinality-related lines from digest")
        lines.append("")
        for line in analysis["stats_evidence_lines"]:
            lines.append(f"- `{line}`")
        lines.append("")

    if analysis.get("spill_evidence_lines"):
        lines.append("## Spill/scratch-related lines from digest")
        lines.append("")
        for line in analysis["spill_evidence_lines"]:
            lines.append(f"- `{line}`")
        lines.append("")

    if analysis.get("codegen_evidence_lines"):
        lines.append("## Codegen/LLVM mention lines from digest")
        lines.append("")
        for line in analysis["codegen_evidence_lines"]:
            lines.append(f"- `{line}`")
        lines.append("")

    lines.append("## Parsed operator evidence")
    lines.append("")
    for op in analysis["operators"]:
        lines.append(
            f"- {op['label']}: rows={op['actual_rows_human']} vs est {op['estimated_rows_human']} "
            f"({op['rows_ratio_human']}), mem={op['peak_mem_human']} vs est "
            f"{op['estimated_peak_mem_human']} ({op['mem_ratio_human']})"
        )
        for ev in op.get("evidence_lines", []):
            lines.append(f"  - `{ev}`")
    lines.append("")
    return lines


def availability_label(item: dict[str, Any]) -> str:
    return "available" if item.get("available") else "missing"


def render_referenced_tables(analysis: dict[str, Any]) -> list[str]:
    lines = ["## Referenced Tables", ""]
    tables = analysis.get("referenced_tables") or []
    if tables:
        lines.extend(f"- `{table}`" for table in tables)
    else:
        lines.append(
            "- not_observed: no referenced table names were parsed from SQL inputs or profile digest."
        )
    lines.append("")
    return lines


def render_sql_context(analysis: dict[str, Any]) -> list[str]:
    lines = ["## SQL Context", ""]
    default_database = analysis.get("default_database")
    if default_database:
        lines.append(f"- default_database: `{default_database}`")
    else:
        lines.append("- default_database: not_observed")
    lines.append("")
    return lines


def render_table_metadata_context(analysis: dict[str, Any]) -> list[str]:
    context = analysis.get("table_metadata_context") or {}
    lines = ["## Table Metadata Context", ""]
    context_file = context.get("context_file", "not_observed")
    lines.append(f"- context file: {context_file}")
    if context.get("context_path"):
        lines.append(f"- context path: `{context['context_path']}`")
    lines.append(f"- table metadata facts: {context.get('table_metadata_facts', 'unknown')}")
    lines.append(f"- tables requested: {context.get('tables_requested', 0)}")
    read_only = context.get("read_only_statements_only")
    if read_only is not None:
        lines.append(f"- read-only statements only: {'yes' if read_only else 'no'}")
    if context.get("error"):
        lines.append(f"- error: {context['error']}")
    lines.append("")

    for table in context.get("tables") or []:
        lines.extend([f"### Table: {table['table']}", ""])
        lines.append(f"- object type: {table.get('object_type', 'unknown')}")
        for statement in ("SHOW CREATE TABLE", "SHOW TABLE STATS", "SHOW COLUMN STATS"):
            lines.append(f"- {statement} status: {table.get('statements', {}).get(statement, 'unknown')}")
        lines.append(f"- table stats rows: {table.get('table_rows', 'unknown')}")
        lines.append(
            "- table stats row-count completeness: "
            f"{table.get('table_stats_row_count_completeness', 'unknown')}"
        )
        lines.append(f"- table stats size: {table.get('table_size', 'unknown')}")
        lines.append(
            f"- column stats columns observed: {table.get('column_stats_columns_observed', 'unknown')}"
        )
        lines.append(
            f"- column stats missing/unknown markers: {table.get('column_stats_missing_markers', 'unknown')}"
        )
        lines.append(
            f"- column stats completeness: {table.get('column_stats_completeness', 'unknown')}"
        )
        columns = table.get("column_stats_columns") or []
        if columns:
            lines.append("- column stats columns: " + ", ".join(f"`{column}`" for column in columns))
        lines.append(f"- file format: {table.get('file_format', 'unknown')}")
        partitions = table.get("partition_columns") or []
        if partitions:
            lines.append("- partition columns: " + ", ".join(f"`{column}`" for column in partitions))
        else:
            lines.append("- partition columns: unknown")
        lines.append("")
    return lines


def render_cm_query_context(analysis: dict[str, Any]) -> list[str]:
    context = analysis.get("cm_query_context")
    if not context:
        return []

    lines = ["## CM Query Context", ""]
    if not context.get("available"):
        lines.append("- available: no")
        if context.get("error"):
            lines.append(f"- error: {context['error']}")
        lines.append("")
        return lines

    lines.append("- available: yes")
    for field in ("query_id", "status", "query_state", "query_type", "pool", "start_time", "end_time"):
        value = context.get(field)
        if value is not None:
            lines.append(f"- {field}: {value}")
    duration_ms = numeric_context_value(context, "duration_ms")
    if duration_ms is not None:
        lines.append(f"- duration: {fmt_duration(duration_ms)}")
    if context.get("admission_result") is not None:
        lines.append(f"- admission_result: {context['admission_result']}")
    admission_wait_ms = numeric_context_value(context, "admission_wait_ms")
    if admission_wait_ms is not None:
        lines.append(f"- admission_wait: {fmt_duration(admission_wait_ms)}")
    rows_produced = numeric_context_value(context, "rows_produced")
    if rows_produced is not None:
        lines.append(f"- rows_produced: {fmt_rows(rows_produced)}")
    for field, label in (
        ("bytes_read", "bytes_read"),
        ("bytes_sent", "bytes_sent"),
        ("memory_aggregate_peak", "memory_aggregate_peak"),
        ("memory_per_node_peak", "memory_per_node_peak"),
    ):
        value = numeric_context_value(context, field)
        if value is not None:
            lines.append(f"- {label}: {fmt_bytes(value)}")
    lines.append("")
    return lines


def render_query_wall_clock(analysis: dict[str, Any]) -> list[str]:
    clock = analysis.get("query_wall_clock") or {}
    lines = ["## Query Wall Clock", ""]
    lines.append(f"- duration: {clock.get('duration_human') or 'unknown'}")
    lines.append(f"- source: {clock.get('source') or 'unknown'}")
    lines.append(f"- confidence: {clock.get('confidence') or 'unknown'}")
    lines.append("")
    return lines


def render_runtime_counter_context(analysis: dict[str, Any]) -> list[str]:
    context = analysis.get("runtime_counter_context") or {}
    families = context.get("families") or {}
    if not families:
        return []

    labels = {
        "codegen": "codegen",
        "cpu": "CPU",
        "network": "network",
        "thread_wall_clock": "thread wall-clock",
        "wait": "wait",
    }
    lines = ["## Runtime Counter Context", ""]
    lines.append(
        f"- guardrail: {context.get('guardrail') or 'runtime counters are context only'}"
    )
    for family, item in families.items():
        label = labels.get(family, family.replace("_", " "))
        lines.append(
            f"- {label}: counters={item.get('count', 0)}, "
            f"max={item.get('max_human') or 'unknown'}, "
            f"max_counter={md_escape(str(item.get('max_counter') or 'unknown'))}"
        )
    lines.append("")
    return lines


def render_evidence_quality(analysis: dict[str, Any]) -> list[str]:
    quality = analysis.get("evidence_quality") or {}
    if not quality:
        return []

    lines = ["## Evidence Quality", ""]
    lines.append(f"- score: {quality.get('score', 0)}/100")
    lines.append(f"- level: {quality.get('level', 'unknown')}")
    lines.append("")

    strengths = quality.get("strengths") or []
    lines.extend(["### Strengths", ""])
    if strengths:
        lines.extend(f"- {item}" for item in strengths)
    else:
        lines.append("- none")
    lines.append("")

    limitations = quality.get("limitations") or []
    lines.extend(["### Limitations", ""])
    if limitations:
        lines.extend(f"- {item}" for item in limitations)
    else:
        lines.append("- none")
    lines.append("")
    return lines


def render_cm_timeseries_context(analysis: dict[str, Any]) -> list[str]:
    context = analysis.get("cm_timeseries_context")
    if not context:
        return []

    lines = ["## CM Time-Series Context", ""]
    lines.append(f"- available: {'yes' if context.get('available') else 'no'}")
    if context.get("metrics_profile"):
        lines.append(f"- metrics_profile: {context.get('metrics_profile')}")
    window = context.get("window") or {}
    if window.get("from") and window.get("to"):
        lines.append(f"- window: {window['from']} to {window['to']}")
    if window.get("padding_sec") is not None:
        lines.append(f"- window padding seconds: {window['padding_sec']}")
    limits = context.get("limits") if isinstance(context.get("limits"), dict) else {}
    if limits.get("max_response_bytes") is not None:
        lines.append(f"- max_response_bytes: {limits['max_response_bytes']}")
    if limits.get("max_points_per_query") is not None:
        lines.append(f"- max_points_per_query: {limits['max_points_per_query']}")
    lines.append("")

    for query in context.get("queries") or []:
        label = query.get("label") or query.get("id") or "unknown"
        lines.append(f"### {label}")
        lines.append("")
        lines.append(f"- status: {query.get('status', 'unknown')}")
        lines.append(f"- point_count: {query.get('point_count', 0)}")
        if query.get("reason"):
            lines.append(f"- reason: {query.get('reason')}")
        if query.get("truncated"):
            lines.append("- truncated: yes")
        if query.get("series_count") is not None:
            lines.append(f"- series_count: {query.get('series_count')}")
        for field in ("min", "max", "avg", "latest"):
            value = numeric_context_value(query, field)
            if value is not None:
                lines.append(f"- {field}: {value:.2f}")
        top_series = [item for item in query.get("top_series") or [] if isinstance(item, dict)]
        if top_series:
            lines.append("- top_series_by_max:")
            for series in top_series[:3]:
                series_name = series.get("series") or "series"
                point_count = series.get("point_count", 0)
                max_value = numeric_context_value(series, "max")
                avg_value = numeric_context_value(series, "avg")
                if max_value is None or avg_value is None:
                    continue
                lines.append(
                    f"  - {series_name}: points={point_count}, max={max_value:.2f}, avg={avg_value:.2f}"
                )
        lines.append("")

    warnings = context.get("warnings") or []
    if warnings:
        lines.extend(["### Collection warnings", ""])
        for warning in warnings:
            lines.append(f"- {warning}")
        lines.append("")
    return lines


def render_cm_metrics_facts(analysis: dict[str, Any]) -> list[str]:
    context = analysis.get("cm_timeseries_context")
    if not context:
        return []

    facts = build_cm_metrics_facts(context)
    lines = ["## CM Metrics Facts", ""]
    lines.append(f"- status: {facts['status']}")
    if context.get("metrics_profile"):
        lines.append(f"- metrics_profile: {context.get('metrics_profile')}")
    lines.append(
        f"- coverage: {facts['ok_metrics']}/{facts['total_metrics']} metrics ok, "
        f"{facts['total_points']} points"
    )
    lines.append(
        f"- availability: {facts['ok_metrics']} ok, {facts['no_data_metrics']} no_data, "
        f"{facts['unavailable_metrics_count']} unavailable"
    )
    unavailable_metrics = facts.get("unavailable_metrics") or []
    lines.append(
        "- unavailable_metrics: "
        + (", ".join(unavailable_metrics) if unavailable_metrics else "none")
    )
    no_data_metric_ids = facts.get("no_data_metric_ids") or []
    lines.append(
        "- no_data_metrics: "
        + (", ".join(no_data_metric_ids) if no_data_metric_ids else "none")
    )
    for key in (
        "admission_pool_pressure",
        "host_cpu_pressure",
        "daemon_memory_growth",
        "daemon_memory_pressure",
        "host_disk_io_pressure",
        "hdfs_datanode_io_pressure",
        "network_io_spike",
    ):
        signal = facts[key]
        lines.append(f"- {key}: {signal['status']}")
        lines.append(f"- {key}_basis: {signal['basis']}")
    lines.append("")

    limitations = facts.get("limitations") or []
    if limitations:
        lines.extend(["### CM metrics limitations", ""])
        for limitation in limitations:
            lines.append(f"- {limitation}")
        lines.append("")
    return lines


def render_cm_metrics_correlation(analysis: dict[str, Any]) -> list[str]:
    correlation = analysis.get("cm_metrics_correlation")
    if not correlation:
        return []

    lines = ["## CM Metrics Correlation", ""]
    lines.append(f"- status: {correlation.get('status', 'unknown')}")
    if correlation.get("coverage"):
        lines.append(f"- coverage: {correlation['coverage']}")
    lines.append(f"- correlated_signals: {correlation.get('correlated_signals', 0)}")
    lines.append(f"- context_only_signals: {correlation.get('context_only_signals', 0)}")
    lines.append(f"- guardrail: {correlation.get('guardrail', 'CM metrics are context only.')}")
    lines.append("")

    signals = correlation.get("signals") or []
    if not signals:
        lines.append("- No CM metric signals were available for correlation.")
        lines.append("")
        return lines

    for signal in signals:
        lines.append(
            f"- {signal['key']}: {signal['correlation_status']} "
            f"(metric={signal['metric_status']}, strength={signal['strength']})"
        )
        lines.append(f"  - basis: {signal['basis']}")
        lines.append(f"  - interpretation: {signal['interpretation']}")
    lines.append("")
    return lines


def render_runtime_diagnosis(analysis: dict[str, Any]) -> list[str]:
    diagnosis = analysis.get("runtime_diagnosis") or {}
    if not diagnosis:
        return []

    lines = ["## Runtime Diagnosis", ""]
    lines.append(f"- status: {diagnosis.get('status') or 'unknown'}")
    lines.append(f"- summary: {diagnosis.get('summary') or 'unknown'}")
    lines.append(
        f"- guardrail: {diagnosis.get('guardrail') or 'Runtime diagnosis is deterministic context only.'}"
    )
    lines.append("")

    signals = [signal for signal in diagnosis.get("signals") or [] if isinstance(signal, dict)]
    if not signals:
        lines.append("- No runtime diagnosis signals were available.")
        lines.append("")
        return lines

    for signal in signals:
        lines.append(f"### {signal.get('title') or signal.get('key') or 'Runtime signal'}")
        lines.append("")
        lines.append(f"- status: {signal.get('status') or 'unknown'}")
        lines.append(f"- interpretation: {signal.get('interpretation') or 'unknown'}")
        evidence = [item for item in signal.get("evidence") or [] if item]
        if evidence:
            lines.append("- evidence:")
            for item in evidence[:5]:
                lines.append(f"  - {md_escape(str(item))}")
        else:
            lines.append("- evidence: none")
        lines.append("")
    return lines


def render_impala_context(analysis: dict[str, Any]) -> list[str]:
    context = analysis.get("impala_context")
    if not context:
        return []

    lines = ["## Impala Context", ""]
    original_sql = context["original_sql"]
    lines.extend(
        [
            "### Original SQL",
            "",
            f"- present: {'yes' if original_sql['available'] else 'no'}",
            f"- path: `{original_sql['path']}`",
            "",
            "### Referenced Tables",
            "",
        ]
    )

    tables = context.get("referenced_tables") or []
    if tables:
        lines.extend(f"- `{table}`" for table in tables)
    else:
        lines.append("- none parsed")
    lines.append("")

    lines.extend(["### Collected Metadata", ""])
    explain = context["explain"]
    lines.append(f"- EXPLAIN: {availability_label(explain)} (`{explain['path']}`)")
    for table in tables:
        lines.append(f"- `{table}`:")
        for command, status in context["table_metadata"].get(table, {}).items():
            lines.append(f"  - {command}: {availability_label(status)} (`{status['path']}`)")
    lines.append("")

    lines.extend(["### Collector Warnings / Failures", ""])
    warnings = context.get("warnings") or []
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- none found in collector summary")
    lines.append("")
    return lines


def render_md(analysis: dict[str, Any], source_path: Path, verbose: bool = False) -> str:
    totals = analysis["totals"]
    lines: list[str] = []
    lines.append("# Query Doctor deterministic analysis facts")
    lines.append("")
    lines.append("> This file is generated by deterministic parsing/rules. The LLM report writer must not add facts that are absent here.")
    lines.append("")

    lines.append("## Totals")
    lines.append("")
    for key in ["TotalTime", "TotalBytesRead", "TotalBytesSent"]:
        item = totals.get(key)
        if not item:
            lines.append(f"- {key}: not parsed")
            continue
        if key == "TotalTime":
            lines.append(f"- {key}: {item.get('raw')} ({fmt_duration(item.get('ms'))})")
        else:
            lines.append(f"- {key}: {item.get('raw')} ({fmt_bytes(item.get('bytes'))})")
    lines.append("")

    lines += render_summary(analysis)
    lines += render_query_wall_clock(analysis)
    lines += render_runtime_counter_context(analysis)
    lines += render_evidence_quality(analysis)
    report_top_n = int(analysis.get("thresholds", {}).get("report_top_n", 10))
    max_table_rows = None if verbose else report_top_n
    lines += render_operator_table("Top operators by time", analysis["top_operators_by_time"])
    lines += render_operator_table("Actual rows vs estimated rows anomalies", analysis["cardinality_anomalies"], max_table_rows)
    lines += render_operator_table("Peak memory vs estimated memory anomalies", analysis["memory_anomalies"], max_table_rows)
    lines += render_operator_table("Zero/unknown row estimate gaps", analysis["zero_row_estimate_gaps"], max_table_rows)
    lines += render_operator_table("Zero/unknown memory estimate gaps", analysis["zero_memory_estimate_gaps"], max_table_rows)

    lines += render_sql_context(analysis)
    lines += render_referenced_tables(analysis)
    lines += render_cm_query_context(analysis)
    lines += render_cm_timeseries_context(analysis)
    lines += render_cm_metrics_facts(analysis)
    lines += render_cm_metrics_correlation(analysis)
    lines += render_runtime_diagnosis(analysis)
    lines += render_table_metadata_context(analysis)
    lines += render_impala_context(analysis)
    lines += render_backend_tail_evidence(analysis)
    lines += render_action_cards(analysis)

    lines += render_findings(analysis, verbose)

    lines.append("## What is NOT supported by the parsed evidence")
    lines.append("")
    for cause in analysis["not_supported_causes"]:
        lines.append(f"- {cause}")
    lines.append("")

    if verbose:
        lines += render_operator_table("Top operators by peak memory", analysis["top_operators_by_peak_memory"])
        lines += render_verbose_evidence(analysis)
    return "\n".join(lines)
