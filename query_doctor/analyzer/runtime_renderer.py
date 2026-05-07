"""Markdown rendering for runtime context and diagnosis facts."""

from __future__ import annotations

from typing import Any

from query_doctor.analyzer.scalars import fmt_bytes, fmt_duration, fmt_rows, numeric_context_value


def md_escape(value: str) -> str:
    return value.replace("|", "\\|")


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


def render_cluster_runtime_context(analysis: dict[str, Any]) -> list[str]:
    context = analysis.get("cluster_runtime_context") or {}
    if not context:
        return []

    lines = ["## Cluster Runtime Context", ""]
    for key in (
        "status",
        "collection_status",
        "coverage",
        "metrics_profile",
        "window_scope",
        "limit_summary",
        "scoring_contribution",
        "guardrail",
    ):
        lines.append(f"- {key}: {context.get(key) or 'unknown'}")
    lines.append("")

    lines.extend(["### Signal rollup", ""])
    for key in (
        "observed_signals",
        "correlated_signals",
        "context_only_signals",
        "unknown_signals",
        "not_observed_signals",
    ):
        values = [str(item) for item in context.get(key) or [] if item]
        lines.append(f"- {key}: {', '.join(values) if values else 'none'}")
    lines.append("")

    limitations = [str(item) for item in context.get("limitations") or [] if item]
    lines.extend(["### Cluster runtime limitations", ""])
    if limitations:
        for item in limitations[:8]:
            lines.append(f"- {md_escape(item)}")
    else:
        lines.append("- none")
    lines.append("")
    return lines
