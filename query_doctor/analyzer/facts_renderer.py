"""Markdown rendering for deterministic analyzer facts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from query_doctor.analyzer.cm_metrics_renderer import (
    render_cm_metrics_correlation,
    render_cm_metrics_facts,
    render_cm_timeseries_context,
)
from query_doctor.analyzer.metadata_renderer import (
    render_impala_context,
    render_stats_metadata_quality,
    render_table_metadata_context,
)
from query_doctor.analyzer.runtime_renderer import (
    render_cm_query_context,
    render_cluster_event_context,
    render_cluster_runtime_context,
    render_evidence_quality,
    render_query_wall_clock,
    render_runtime_counter_context,
    render_runtime_diagnosis,
)
from query_doctor.analyzer.scalars import fmt_bytes, fmt_duration


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


def render_primary_bottleneck(analysis: dict[str, Any]) -> list[str]:
    bottleneck = analysis.get("case_primary_bottleneck")
    if not isinstance(bottleneck, dict):
        return []
    reasons = [str(item) for item in bottleneck.get("reasons") or [] if item]
    return [
        "## Primary Bottleneck",
        "",
        f"- label: {bottleneck.get('label') or 'unknown'}",
        f"- confidence: {bottleneck.get('confidence') or 'low'}",
        f"- reasons: {', '.join(reasons) if reasons else 'none'}",
        "- guardrail: Python-derived routing label; supporting facts remain in the detailed sections below.",
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
    lines += render_primary_bottleneck(analysis)
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
    lines += render_cluster_runtime_context(analysis)
    lines += render_cluster_event_context(analysis)
    lines += render_runtime_diagnosis(analysis)
    lines += render_table_metadata_context(analysis)
    lines += render_stats_metadata_quality(analysis)
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
