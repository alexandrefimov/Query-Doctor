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
    render_admission_context,
    render_cm_query_context,
    render_cluster_event_context,
    render_cluster_runtime_context,
    render_evidence_quality,
    render_memory_pressure_facts,
    render_query_wall_clock,
    render_runtime_admission_facts,
    render_runtime_counter_context,
    render_runtime_diagnosis,
    render_storage_context,
)
from query_doctor.analyzer.scalars import fmt_bytes, fmt_duration, fmt_rate, fmt_ratio


def md_escape(value: str) -> str:
    return value.replace("|", "\\|")


def render_operator_table(
    title: str, rows: list[dict[str, Any]], max_rows: int | None = None
) -> list[str]:
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
        out.append(
            f"| ... {len(rows) - len(visible_rows)} more in verbose output |  |  |  |  |  |  |  |"
        )
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


def render_profile_format(analysis: dict[str, Any]) -> list[str]:
    profile = analysis.get("profile_format")
    if not isinstance(profile, dict):
        return []
    features = profile.get("features") if isinstance(profile.get("features"), dict) else {}
    lines = ["## Profile Format", ""]
    lines.append(f"- family: {profile.get('profile_family') or 'unknown'}")
    lines.append(f"- dialect: {profile.get('profile_dialect') or 'unknown'}")
    lines.append(f"- dialect_confidence: {profile.get('dialect_confidence') or 'low'}")
    lines.append(
        f"- source: {profile.get('source_label') or profile.get('profile_source') or 'unknown'}"
    )
    capabilities = (
        profile.get("source_capabilities")
        if isinstance(profile.get("source_capabilities"), dict)
        else {}
    )
    if capabilities:
        lines.append(
            "- source_capabilities: "
            f"endpoint_format={capabilities.get('profile_response_format') or 'unknown'}, "
            f"json_probe={capabilities.get('json_profile_probe') or 'unknown'}, "
            f"json_payload={capabilities.get('json_profile_payload') or 'unknown'}, "
            f"text_payload={capabilities.get('text_profile_payload') or 'unknown'}, "
            f"profile_docs_probe={capabilities.get('profile_docs_probe') or 'unknown'}"
        )
    lines.append(f"- distribution: {profile.get('impala_distribution') or 'unknown'}")
    lines.append(f"- version: {profile.get('impala_version') or 'unknown'}")
    if profile.get("impala_build_type"):
        lines.append(f"- build_type: {profile['impala_build_type']}")
    if profile.get("daemon_server_mode"):
        lines.append(f"- daemon_server_mode: {profile['daemon_server_mode']}")
    if profile.get("daemon_local_catalog_mode") is not None:
        value = "yes" if profile.get("daemon_local_catalog_mode") else "no"
        lines.append(f"- daemon_local_catalog_mode: {value}")
    lines.append(f"- layout: {profile.get('layout') or 'unknown'}")
    lines.append(f"- compatibility: {profile.get('compatibility') or 'unknown'}")
    lines.append(f"- analysis_support: {profile.get('analysis_support') or 'unknown'}")
    lines.append(
        f"- primary_bottleneck_policy: {profile.get('primary_bottleneck_policy') or 'unknown'}"
    )
    lines.append(f"- per_instance_evidence: {profile.get('per_instance_evidence') or 'unknown'}")
    lines.append(
        "- sections: "
        f"summary={'yes' if features.get('summary') else 'no'}, "
        f"plan={'yes' if features.get('plan') else 'no'}, "
        f"exec_summary={'yes' if features.get('exec_summary_table') else 'no'}, "
        f"query_timeline={'yes' if features.get('query_timeline') else 'no'}"
    )
    lines.append(
        "- raw_profile_features: "
        f"runtime_nodes={features.get('runtime_node_count', 0)}, "
        f"fragments={features.get('fragment_section_count', 0)}, "
        f"instances={features.get('fragment_instance_count', 0)}, "
        f"lifecycle_headers={'yes' if features.get('fragment_instance_lifecycle') else 'no'}"
    )
    if features.get("json_mapped_counter_count"):
        lines.append(
            "- json_profile_mapping: "
            f"mapped_counter_count={features.get('json_mapped_counter_count', 0)}"
        )
    lines.append(
        "- resource_sections: "
        f"admission={'yes' if features.get('admission') else 'no'}, "
        f"backend_startup_latencies={'yes' if features.get('backend_startup_latencies') else 'no'}, "
        f"per_node_peak_memory={'yes' if features.get('per_node_peak_memory') else 'no'}, "
        f"per_node_bytes_read={'yes' if features.get('per_node_bytes_read') else 'no'}, "
        f"per_node_user_time={'yes' if features.get('per_node_user_time') else 'no'}, "
        f"per_node_system_time={'yes' if features.get('per_node_system_time') else 'no'}, "
        f"per_host_fragment_instances={'yes' if features.get('per_host_fragment_instances') else 'no'}"
    )
    limitations = [item for item in profile.get("limitations") or [] if isinstance(item, dict)]
    if limitations:
        lines.append("- limitations:")
        for item in limitations:
            lines.append(
                f"  - {item.get('id') or 'profile_limitation'}: "
                f"{item.get('summary') or 'Profile analysis is limited.'}"
            )
    lines.append("")
    return lines


def render_exec_node_completeness(analysis: dict[str, Any]) -> list[str]:
    completeness = analysis.get("exec_node_completeness")
    if not isinstance(completeness, dict):
        return []
    lines = ["## Exec Node Completeness", ""]
    lines.append(f"- profile_wide_state: {completeness.get('profile_wide_state') or 'unknown'}")
    reasons = [str(item) for item in completeness.get("profile_wide_reasons") or [] if item]
    lines.append(f"- profile_wide_reasons: {', '.join(reasons) if reasons else 'none'}")
    lines.append(
        f"- row_count_conclusions: {completeness.get('row_count_conclusions') or 'unknown'}"
    )
    lines.append(
        "- guarded_conclusions: row/cardinality, scan-selectivity, runtime-filter-effectiveness"
    )
    lines.append(f"- affected_operator_count: {completeness.get('unsafe_operator_count') or 0}")
    affected = [
        item for item in completeness.get("affected_operators") or [] if isinstance(item, dict)
    ]
    if affected:
        lines.append("- affected_operators:")
        for item in affected[:10]:
            item_reasons = [str(reason) for reason in item.get("reasons") or [] if reason]
            lines.append(
                f"  - {item.get('label') or item.get('operator_id')}: "
                f"state={item.get('state') or 'unknown'}, "
                f"reasons={', '.join(item_reasons) if item_reasons else 'none'}"
            )
        if len(affected) > 10:
            lines.append(f"  - ... {len(affected) - 10} more affected operators")
    limitations = [item for item in completeness.get("limitations") or [] if isinstance(item, dict)]
    if limitations:
        lines.append("- limitations:")
        for item in limitations:
            lines.append(
                f"  - {item.get('id') or 'exec_node_completeness_limitation'}: "
                f"{item.get('summary') or 'Exec-node completeness is limited.'}"
            )
    lines.append("")
    return lines


def render_profile_resource_facts(analysis: dict[str, Any]) -> list[str]:
    resources = analysis.get("profile_resources")
    if not isinstance(resources, dict) or not resources.get("available"):
        return []
    startup = resources.get("backend_startup_latencies")
    if not isinstance(startup, dict):
        startup = {}
    fragments = resources.get("fragment_instances_per_host")
    if not isinstance(fragments, dict):
        fragments = {}
    memory = resources.get("per_node_peak_memory")
    if not isinstance(memory, dict):
        memory = {}
    bytes_read = resources.get("per_node_bytes_read")
    if not isinstance(bytes_read, dict):
        bytes_read = {}
    user_time = resources.get("per_node_user_time")
    if not isinstance(user_time, dict):
        user_time = {}
    system_time = resources.get("per_node_system_time")
    if not isinstance(system_time, dict):
        system_time = {}

    lines = ["## Profile Resource Facts", ""]
    lines.append(
        "- guardrail: resource profile facts are deterministic context, not root-cause proof by themselves."
    )
    lines.append(f"- admission_result: {resources.get('admission_result') or 'unknown'}")
    if resources.get("admission_wait_ms") is not None:
        lines.append(f"- admission_wait: {fmt_duration(resources.get('admission_wait_ms'))}")
    if resources.get("admission_queue_reason_category") not in {None, "unknown"}:
        lines.append(
            f"- admission_queue_reason_category: {resources.get('admission_queue_reason_category')}"
        )

    if startup.get("available"):
        percentiles = (
            startup.get("percentiles") if isinstance(startup.get("percentiles"), dict) else {}
        )
        lines.append(
            "- backend_startup_latencies: "
            f"count={startup.get('count', 0)}, "
            f"sum={fmt_duration(startup.get('sum_ms'))}, "
            f"min={fmt_duration(startup.get('min_ms'))}, "
            f"max={fmt_duration(startup.get('max_ms'))}, "
            f"p50={fmt_duration(percentiles.get('p50_ms'))}, "
            f"p95={fmt_duration(percentiles.get('p95_ms'))}"
        )

    if fragments.get("available"):
        lines.append(
            "- fragment_instances_per_host: "
            f"hosts={fragments.get('count', 0)}, "
            f"total={int(fragments.get('total') or 0)}, "
            f"min={int(fragments.get('min') or 0)}, "
            f"max={int(fragments.get('max') or 0)}, "
            f"max_min_ratio={fmt_ratio(fragments.get('ratio'))}"
        )

    if memory.get("available"):
        lines.append(
            "- per_node_peak_memory: "
            f"hosts={memory.get('count', 0)}, "
            f"min={fmt_bytes(memory.get('min'))}, "
            f"max={fmt_bytes(memory.get('max'))}, "
            f"max_min_ratio={fmt_ratio(memory.get('ratio'))}"
        )

    if bytes_read.get("available"):
        lines.append(
            "- per_node_bytes_read: "
            f"hosts={bytes_read.get('count', 0)}, "
            f"min={fmt_bytes(bytes_read.get('min'))}, "
            f"max={fmt_bytes(bytes_read.get('max'))}, "
            f"max_min_ratio={fmt_ratio(bytes_read.get('ratio'))}"
        )

    if user_time.get("available"):
        lines.append(
            "- per_node_user_time: "
            f"hosts={user_time.get('count', 0)}, "
            f"min={fmt_duration(user_time.get('min'))}, "
            f"max={fmt_duration(user_time.get('max'))}, "
            f"max_min_ratio={fmt_ratio(user_time.get('ratio'))}"
        )

    if system_time.get("available"):
        lines.append(
            "- per_node_system_time: "
            f"hosts={system_time.get('count', 0)}, "
            f"min={fmt_duration(system_time.get('min'))}, "
            f"max={fmt_duration(system_time.get('max'))}, "
            f"max_min_ratio={fmt_ratio(system_time.get('ratio'))}"
        )

    lines.append("")
    return lines


def fmt_percent(value: object) -> str:
    if not isinstance(value, (int, float)):
        return "n/a"
    return f"{float(value):.2f}%"


def render_resource_trace_metric(name: str, item: dict[str, Any]) -> str:
    formatter = fmt_percent if item.get("unit") == "percent" else fmt_rate
    return (
        f"- {name}: "
        f"samples={item.get('sample_count', 0)}, "
        f"min={formatter(item.get('min'))}, "
        f"max={formatter(item.get('max'))}, "
        f"avg={formatter(item.get('avg'))}, "
        f"max_min_ratio={fmt_ratio(item.get('max_min_ratio'))}"
    )


def render_resource_trace_facts(analysis: dict[str, Any]) -> list[str]:
    facts = analysis.get("resource_trace")
    if not isinstance(facts, dict) or not facts.get("available"):
        return []
    metrics = facts.get("metrics")
    if not isinstance(metrics, dict):
        metrics = {}

    lines = ["## Resource Trace Facts", ""]
    lines.append(f"- status: {facts.get('status') or 'unknown'}")
    lines.append(f"- evidence_tier: {facts.get('evidence_tier') or 'unsupported'}")
    lines.append(f"- primary_supported: {'yes' if facts.get('primary_supported') else 'no'}")
    lines.append(f"- selected_query_mapping: {facts.get('selected_query_mapping') or 'unknown'}")
    lines.append(
        f"- guardrail: {facts.get('guardrail') or 'Resource trace facts are context only.'}"
    )
    for name in (
        "cpu_io_wait_percentage",
        "cpu_sys_percentage",
        "cpu_user_percentage",
        "disk_read_throughput",
        "disk_write_throughput",
        "network_receive_throughput",
        "network_transmit_throughput",
    ):
        item = metrics.get(name)
        if isinstance(item, dict) and item.get("available"):
            lines.append(render_resource_trace_metric(name, item))
    limitations = [str(item) for item in facts.get("limitations") or [] if item]
    if limitations:
        lines.append("- limitations:")
        for item in limitations:
            lines.append(f"  - {md_escape(item)}")
    lines.append("")
    return lines


def render_profile_timing_facts(analysis: dict[str, Any]) -> list[str]:
    timings = analysis.get("profile_timings")
    if not isinstance(timings, dict) or not timings.get("available"):
        return []

    lines = ["## Profile Timing Facts", ""]
    lines.append(
        f"- guardrail: {timings.get('guardrail') or 'profile timing facts are deterministic context only'}"
    )
    query_timeline = timings.get("query_timeline")
    if isinstance(query_timeline, dict) and query_timeline.get("available"):
        lines.append(
            "- query_timeline: "
            f"duration={fmt_duration(query_timeline.get('duration_ms'))}, "
            f"events={query_timeline.get('event_count', 0)}"
        )
        phases = query_timeline.get("phase_durations")
        if isinstance(phases, dict):
            lines.append(
                "- query_timeline_phases: "
                f"planning={fmt_duration(phases.get('planning_ms'))}, "
                f"admission={fmt_duration(phases.get('admission_ms'))}, "
                f"backend_start={fmt_duration(phases.get('backend_start_ms'))}, "
                f"rows_available={fmt_duration(phases.get('rows_available_ms'))}, "
                f"fetch={fmt_duration(phases.get('fetch_ms'))}, "
                f"unregister={fmt_duration(phases.get('unregister_ms'))}"
            )

    lifecycle = timings.get("fragment_lifecycle")
    if isinstance(lifecycle, dict) and lifecycle.get("available"):
        timeline = lifecycle.get("timeline") if isinstance(lifecycle.get("timeline"), dict) else {}
        lines.append(
            "- fragment_lifecycle: "
            f"instances={lifecycle.get('instance_count', 0)}, "
            f"timeline_max={fmt_duration(timeline.get('max_ms'))}"
        )
        events = lifecycle.get("events") if isinstance(lifecycle.get("events"), dict) else {}
        for key in (
            "prepare_finished",
            "open_finished",
            "first_batch_produced",
            "exec_internal_finished",
        ):
            item = events.get(key)
            if not isinstance(item, dict) or not item.get("available"):
                continue
            lines.append(
                f"- fragment_lifecycle_{key}: "
                f"count={item.get('count', 0)}, "
                f"min={fmt_duration(item.get('min_ms'))}, "
                f"max={fmt_duration(item.get('max_ms'))}"
            )
    lines.append("")
    return lines


def render_profile_counter_registry(analysis: dict[str, Any]) -> list[str]:
    registry = analysis.get("profile_counter_registry")
    if not isinstance(registry, dict):
        return []
    lines = ["## Profile Counter Registry", ""]
    lines.append(f"- status: {registry.get('status') or 'unknown'}")
    lines.append(f"- source: {registry.get('source') or 'unknown'}")
    if registry.get("source_counter_count") is not None:
        lines.append(f"- source_counter_count: {registry.get('source_counter_count')}")
    lines.append(f"- registry_entry_count: {registry.get('registry_entry_count') or 0}")
    lines.append(f"- missing_counter_count: {registry.get('missing_counter_count') or 0}")
    if registry.get("impala_version"):
        lines.append(f"- impala_version: {registry['impala_version']}")
    limitations = [str(item) for item in registry.get("limitations") or [] if item]
    if limitations:
        lines.append("- limitations:")
        lines.extend(f"  - {item}" for item in limitations)
    lines.append("")
    return lines


def render_client_fetch_facts(analysis: dict[str, Any]) -> list[str]:
    facts = analysis.get("client_fetch")
    if not isinstance(facts, dict):
        return []
    if facts.get("evidence_tier") == "unsupported" and not facts.get("wait_counters"):
        return []

    lines = ["## Client Fetch Tail Facts", ""]
    lines.append(f"- status: {facts.get('status') or 'not_observed'}")
    lines.append(f"- evidence_tier: {facts.get('evidence_tier') or 'unsupported'}")
    lines.append(f"- counter_status: {facts.get('counter_status') or 'not_observed'}")
    lines.append(f"- counter_stability: {facts.get('counter_stability') or 'UNKNOWN'}")
    lines.append(f"- promotion_policy: {facts.get('promotion_policy') or 'unknown'}")
    lines.append(f"- finding_supported: {'yes' if facts.get('finding_supported') else 'no'}")
    counter = facts.get("dominant_wait_counter")
    if isinstance(counter, dict):
        lines.append(
            "- client_fetch_wait: "
            f"{facts.get('client_fetch_wait_human') or 'n/a'} "
            f"(counter={counter.get('counter') or 'unknown'}, "
            f"share={facts.get('wait_share_human') or 'n/a'}, "
            f"query_duration={facts.get('query_duration_human') or 'n/a'})"
        )
    if facts.get("timeline_fetch_ms") is not None:
        lines.append(f"- query_timeline_fetch: {facts.get('timeline_fetch_human') or 'n/a'}")
    serialization = facts.get("profile_serialization_context")
    if isinstance(serialization, dict):
        lines.append(
            "- profile_serialization_context: "
            f"{serialization.get('duration_human') or 'n/a'} "
            f"(counter={serialization.get('counter') or 'unknown'})"
        )
    lines.append(
        f"- guardrail: {facts.get('guardrail') or 'Client fetch facts are deterministic context.'}"
    )
    limitations = [str(item) for item in facts.get("limitations") or [] if item]
    if limitations:
        lines.append("- limitations:")
        for item in limitations:
            lines.append(f"  - {item}")
    lines.append("")
    return lines


def render_runtime_filter_facts(analysis: dict[str, Any]) -> list[str]:
    facts = analysis.get("runtime_filters")
    if not isinstance(facts, dict):
        return []
    if facts.get("status") == "not_observed" and facts.get("evidence_tier") == "unsupported":
        return []

    lines = ["## Runtime Filter Evidence", ""]
    lines.append(f"- status: {facts.get('status') or 'unknown'}")
    lines.append(f"- evidence_tier: {facts.get('evidence_tier') or 'unsupported'}")
    lines.append(f"- finding_supported: {'yes' if facts.get('finding_supported') else 'no'}")
    lines.append(f"- primary_supported: {'yes' if facts.get('primary_supported') else 'no'}")
    lines.append(f"- profile_dialect: {facts.get('profile_dialect') or 'unknown'}")
    lines.append(f"- runtime_filter_lines: {facts.get('runtime_filter_lines') or 0}")
    lines.append(f"- plan_filter_lines: {facts.get('plan_filter_lines') or 0}")
    lines.append(f"- runtime_filter_id_count: {facts.get('runtime_filter_id_count') or 0}")
    lines.append(f"- plan_producer_lines: {facts.get('plan_producer_lines') or 0}")
    lines.append(f"- plan_consumer_lines: {facts.get('plan_consumer_lines') or 0}")
    filter_kind_counts = facts.get("filter_kind_counts")
    if isinstance(filter_kind_counts, dict) and filter_kind_counts:
        summary = ", ".join(
            f"{md_escape(str(kind))}={count}" for kind, count in sorted(filter_kind_counts.items())
        )
        lines.append(f"- filter_kind_counts: {summary}")
    lines.append(f"- arrival_status: {facts.get('arrival_status') or 'unknown'}")
    lines.append(f"- arrival_status_lines: {facts.get('arrival_status_lines') or 0}")
    lines.append(f"- missing_arrival_lines: {facts.get('missing_arrival_lines') or 0}")
    lines.append(f"- all_arrived_lines: {facts.get('all_arrived_lines') or 0}")
    lines.append(f"- max_arrival_wait: {facts.get('max_arrival_wait_human') or 'n/a'}")
    lines.append(f"- bloom_filter_counter_lines: {facts.get('bloom_filter_counter_lines') or 0}")
    lines.append(
        "- bloom_filter_counter_nonzero_lines: "
        f"{facts.get('bloom_filter_counter_nonzero_lines') or 0}"
    )
    lines.append(
        "- exec_node_runtime_filter_effectiveness: "
        f"{facts.get('exec_node_runtime_filter_effectiveness') or 'unknown'}"
    )
    lines.append(
        f"- guardrail: {facts.get('guardrail') or 'Runtime filter facts are context-only.'}"
    )
    limitations = [str(item) for item in facts.get("limitations") or [] if item]
    if limitations:
        lines.append("- limitations:")
        for item in limitations:
            lines.append(f"  - {md_escape(item)}")
    lines.append("")
    return lines


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
                lines.append(
                    f"  - ... {len(finding['operators']) - len(operators)} more in verbose output"
                )
        if finding.get("evidence_lines") and (
            verbose or finding.get("id") == "host_execution_tail_suspected"
        ):
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
        lines.append(
            "- Host-specific HDFS/RPC/write path issue is not confirmed by backend write-path counters."
        )
    lines.append("")
    return lines


def render_scan_skew_facts(analysis: dict[str, Any]) -> list[str]:
    facts = analysis.get("scan_skew")
    if not isinstance(facts, dict):
        return []
    if facts.get("status") == "not_observed" and facts.get("evidence_tier") == "unsupported":
        return []

    lines = ["## Scan Skew Evidence", ""]
    lines.append(f"- status: {facts.get('status') or 'unknown'}")
    lines.append(f"- evidence_tier: {facts.get('evidence_tier') or 'unsupported'}")
    lines.append(f"- finding_supported: {'yes' if facts.get('finding_supported') else 'no'}")
    lines.append(f"- primary_supported: {'yes' if facts.get('primary_supported') else 'no'}")
    lines.append(f"- evidence_source: {facts.get('evidence_source') or 'none'}")
    lines.append(f"- fragment_group: {facts.get('fragment_group') or 'none'}")
    lines.append(f"- skew_metric: {facts.get('skew_metric') or 'none'}")
    lines.append(f"- skew_metric_label: {facts.get('skew_metric_label') or 'none'}")
    lines.append(f"- skew_ratio: {facts.get('skew_ratio_human') or 'n/a'}")
    lines.append(f"- skew_group_host_count: {facts.get('skew_group_host_count') or 0}")
    lines.append(f"- corroborating_metric_count: {facts.get('corroborating_metric_count') or 0}")
    lines.append(
        f"- group_max_execution_time: {facts.get('group_max_execution_time_human') or 'n/a'}"
    )
    lines.append(
        f"- group_avg_execution_time: {facts.get('group_avg_execution_time_human') or 'n/a'}"
    )
    lines.append(
        "- group_max_avg_execution_ratio: "
        f"{facts.get('group_max_avg_execution_ratio_human') or 'n/a'}"
    )
    lines.append(f"- runtime_status: {facts.get('runtime_status') or 'unknown'}")
    lines.append(f"- backend_rows_parsed: {facts.get('backend_rows_parsed') or 0}")
    lines.append(f"- skew_group_count: {facts.get('skew_group_count') or 0}")
    lines.append(f"- comparable_group_count: {facts.get('comparable_group_count') or 0}")
    lines.append(
        f"- aggregate_summary_observed: {'yes' if facts.get('aggregate_summary_observed') else 'no'}"
    )
    lines.append(
        f"- guardrail: {facts.get('guardrail') or 'Scan skew facts are deterministic context.'}"
    )
    limitations = [str(item) for item in facts.get("limitations") or [] if item]
    if limitations:
        lines.append("- limitations:")
        for item in limitations:
            lines.append(f"  - {md_escape(item)}")
    lines.append("")
    return lines


def render_data_movement_facts(analysis: dict[str, Any]) -> list[str]:
    facts = analysis.get("data_movement")
    if not isinstance(facts, dict):
        return []
    if facts.get("status") == "not_observed" and facts.get("evidence_tier") == "unsupported":
        return []

    lines = ["## Data Movement Evidence", ""]
    lines.append(f"- status: {facts.get('status') or 'unknown'}")
    lines.append(f"- evidence_tier: {facts.get('evidence_tier') or 'unsupported'}")
    lines.append(f"- finding_supported: {'yes' if facts.get('finding_supported') else 'no'}")
    lines.append(f"- primary_supported: {'yes' if facts.get('primary_supported') else 'no'}")
    lines.append(f"- total_bytes_sent: {facts.get('total_bytes_sent_human') or 'n/a'}")
    lines.append(f"- exchange_operator_count: {facts.get('exchange_operator_count') or 0}")
    lines.append(f"- exchange_elapsed: {facts.get('exchange_elapsed_human') or 'n/a'}")
    lines.append(f"- exchange_elapsed_share: {facts.get('exchange_elapsed_share_human') or 'n/a'}")
    lines.append(
        f"- guardrail: {facts.get('guardrail') or 'Data movement facts are deterministic context.'}"
    )
    limitations = [str(item) for item in facts.get("limitations") or [] if item]
    if limitations:
        lines.append("- limitations:")
        for item in limitations:
            lines.append(f"  - {md_escape(item)}")
    lines.append("")
    return lines


def render_source_provenance(analysis: dict[str, Any]) -> list[str]:
    provenance = analysis.get("source_provenance")
    if not isinstance(provenance, dict):
        return []
    items = [item for item in provenance.get("items") or [] if isinstance(item, dict)]
    if not items:
        return []

    lines = ["## Source Provenance", ""]
    guardrail = provenance.get("guardrail")
    if guardrail:
        lines.append(f"- guardrail: {guardrail}")
    for item in items:
        kind = item.get("kind") or "source"
        status = item.get("status") or "unknown"
        label = item.get("label") or "unknown"
        coverage = item.get("coverage") or "unknown"
        lines.append(f"- {kind}: {status}; source={label}; coverage={coverage}")
        limitations = [str(value) for value in item.get("limitations") or [] if value]
        for limitation in limitations[:3]:
            lines.append(f"  - limitation: {limitation}")
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
    lines.append(
        "> This file is generated by deterministic parsing/rules. The LLM report writer must not add facts that are absent here."
    )
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
    lines += render_profile_format(analysis)
    lines += render_profile_counter_registry(analysis)
    lines += render_exec_node_completeness(analysis)
    lines += render_profile_resource_facts(analysis)
    lines += render_resource_trace_facts(analysis)
    lines += render_profile_timing_facts(analysis)
    lines += render_client_fetch_facts(analysis)
    lines += render_source_provenance(analysis)
    lines += render_query_wall_clock(analysis)
    lines += render_runtime_admission_facts(analysis)
    lines += render_admission_context(analysis)
    lines += render_memory_pressure_facts(analysis)
    lines += render_runtime_filter_facts(analysis)
    lines += render_storage_context(analysis)
    lines += render_data_movement_facts(analysis)
    lines += render_runtime_counter_context(analysis)
    lines += render_evidence_quality(analysis)
    report_top_n = int(analysis.get("thresholds", {}).get("report_top_n", 10))
    max_table_rows = None if verbose else report_top_n
    lines += render_operator_table("Top operators by time", analysis["top_operators_by_time"])
    lines += render_operator_table(
        "Actual rows vs estimated rows anomalies", analysis["cardinality_anomalies"], max_table_rows
    )
    lines += render_operator_table(
        "Peak memory vs estimated memory anomalies", analysis["memory_anomalies"], max_table_rows
    )
    lines += render_operator_table(
        "Zero/unknown row estimate gaps", analysis["zero_row_estimate_gaps"], max_table_rows
    )
    lines += render_operator_table(
        "Zero/unknown memory estimate gaps", analysis["zero_memory_estimate_gaps"], max_table_rows
    )

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
    lines += render_scan_skew_facts(analysis)
    lines += render_backend_tail_evidence(analysis)
    lines += render_action_cards(analysis)

    lines += render_findings(analysis, verbose)

    lines.append("## What is NOT supported by the parsed evidence")
    lines.append("")
    for cause in analysis["not_supported_causes"]:
        lines.append(f"- {cause}")
    lines.append("")

    if verbose:
        lines += render_operator_table(
            "Top operators by peak memory", analysis["top_operators_by_peak_memory"]
        )
        lines += render_verbose_evidence(analysis)
    return "\n".join(lines)
