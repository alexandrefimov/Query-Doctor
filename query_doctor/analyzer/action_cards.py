"""Deterministic action card generation from analyzer facts."""

from __future__ import annotations

from typing import Any

from query_doctor.analyzer.cm_metrics import correlated_cm_metric_line
from query_doctor.analyzer.operators import operator_key
from query_doctor.analyzer.scalars import fmt_bytes
from query_doctor.analyzer.thresholds import DEFAULT_LARGE_BYTES_THRESHOLD, MEDIUM_DATA_MOVEMENT_BYTES


def context_referenced_tables(analysis: dict[str, Any]) -> list[str]:
    context = analysis.get("impala_context") or {}
    return list(context.get("referenced_tables") or [])


def context_missing_metadata(analysis: dict[str, Any], command_names: set[str]) -> list[str]:
    context = analysis.get("impala_context") or {}
    missing: list[str] = []
    for table, metadata in (context.get("table_metadata") or {}).items():
        for command_name in command_names:
            status = metadata.get(command_name)
            if status and not status.get("available"):
                missing.append(f"{command_name} for `{table}`")
    return missing


def action_card_score(card: dict[str, Any]) -> float:
    op = card["operator"]
    rows_ratio = op.get("rows_actual_to_estimated_ratio") or 0
    mem_ratio = op.get("mem_actual_to_estimated_ratio") or 0
    actual_rows = op.get("actual_rows") or 0
    peak_mem = op.get("peak_mem_bytes") or 0
    return rows_ratio * 1_000_000_000 + mem_ratio * 1_000_000 + actual_rows + peak_mem / 1024


def build_action_cards(analysis: dict[str, Any], max_cards: int = 5) -> list[dict[str, Any]]:
    thresholds = analysis.get("thresholds", {})
    large_rows_threshold = float(thresholds.get("large_rows_threshold") or 1_000_000)
    large_bytes_threshold = float(thresholds.get("large_bytes_threshold") or DEFAULT_LARGE_BYTES_THRESHOLD)
    total_read = analysis.get("totals", {}).get("TotalBytesRead") or {}
    total_sent = analysis.get("totals", {}).get("TotalBytesSent") or {}
    memory_by_key = {
        operator_key(op): op
        for op in analysis.get("memory_anomalies", [])
    }

    cards: list[dict[str, Any]] = []
    used_keys: set[tuple[str, str]] = set()

    for op in analysis.get("cardinality_anomalies", []):
        if (op.get("rows_actual_to_estimated_ratio") or 0) < 100:
            continue
        if (op.get("actual_rows") or 0) < large_rows_threshold:
            continue
        key = operator_key(op)
        used_keys.add(key)
        related_memory = memory_by_key.get(key)
        cards.append(
            make_action_card(
                "Severe cardinality underestimation before high-cost operator",
                op,
                related_memory=related_memory,
                total_read=total_read,
                total_sent=total_sent,
                large_bytes_threshold=large_bytes_threshold,
                analysis=analysis,
            )
        )

    for op in analysis.get("memory_anomalies", []):
        key = operator_key(op)
        if key in used_keys:
            continue
        mem_ratio = op.get("mem_actual_to_estimated_ratio") or 0
        peak_mem = op.get("peak_mem_bytes") or 0
        if mem_ratio < 10 and peak_mem < large_bytes_threshold:
            continue
        cards.append(
            make_action_card(
                "Severe memory underestimation at high-memory operator",
                op,
                related_memory=op,
                total_read=total_read,
                total_sent=total_sent,
                large_bytes_threshold=large_bytes_threshold,
                analysis=analysis,
            )
        )

    return sorted(cards, key=action_card_score, reverse=True)[:max_cards]


def make_action_card(
    title: str,
    op: dict[str, Any],
    *,
    related_memory: dict[str, Any] | None,
    total_read: dict[str, Any],
    total_sent: dict[str, Any],
    large_bytes_threshold: float,
    analysis: dict[str, Any],
) -> dict[str, Any]:
    evidence = [
        f"operator: {op['label']}",
        f"actual rows: {op['actual_rows_human']}",
        f"estimated rows: {op['estimated_rows_human']}",
        f"actual/estimated ratio: {op['rows_ratio_human']}",
    ]
    if related_memory:
        evidence.extend(
            [
                f"peak memory: {related_memory['peak_mem_human']}",
                f"estimated peak memory: {related_memory['estimated_peak_mem_human']}",
                f"peak/estimated memory ratio: {related_memory['mem_ratio_human']}",
            ]
        )
    if total_read.get("raw") and (total_read.get("bytes") or 0) >= MEDIUM_DATA_MOVEMENT_BYTES:
        evidence.append(f"TotalBytesRead: {total_read['raw']} ({fmt_bytes(total_read.get('bytes'))})")
    if total_sent.get("raw") and (total_sent.get("bytes") or 0) >= MEDIUM_DATA_MOVEMENT_BYTES:
        evidence.append(f"TotalBytesSent: {total_sent['raw']} ({fmt_bytes(total_sent.get('bytes'))})")
    metric_evidence_keys: list[str] = []
    if related_memory:
        metric_evidence_keys.extend(["daemon_memory_growth", "daemon_memory_pressure"])
    if total_sent.get("bytes") and total_sent["bytes"] >= MEDIUM_DATA_MOVEMENT_BYTES:
        metric_evidence_keys.append("network_io_spike")
    if op.get("rows_actual_to_estimated_ratio") or op.get("time_ms"):
        metric_evidence_keys.append("host_cpu_pressure")
    for key in metric_evidence_keys:
        line = correlated_cm_metric_line(analysis, key)
        if line and line not in evidence:
            evidence.append(line)

    admin_actions = [
        "Check per-host RowsProduced for this operator.",
        "Check spill/scratch counters for this operator if available in profile.",
    ]
    if related_memory:
        admin_actions.append("Check per-host PeakMemUsage for this operator.")
        admin_actions.append("Check whether admission pool memory limits were hit.")
    if total_sent.get("bytes") and total_sent["bytes"] >= large_bytes_threshold:
        admin_actions.append("Check whether exchange volume matches TotalBytesSent.")
    if any(item.startswith("CM metrics correlation:") for item in evidence):
        admin_actions.append("Use CM metrics only as correlated runtime context, not as standalone root-cause proof.")

    tables = context_referenced_tables(analysis)
    user_actions: list[str] = []
    if tables:
        user_actions.append(
            "Run SHOW TABLE STATS for referenced tables involved in this query: "
            + ", ".join(f"`{table}`" for table in tables)
            + "."
        )
    else:
        user_actions.append("Run SHOW TABLE STATS for referenced tables involved in this query.")
    user_actions.extend(
        [
            "Run SHOW COLUMN STATS for join/filter columns once join/filter columns are identified.",
            "Check whether the query creates many-to-many JOIN amplification before SORT/ANALYTIC/AGGREGATE.",
            "If stats are missing or stale, refresh stats through the approved operational process, then re-run the query.",
        ]
    )

    missing_evidence = [
        "Exact join/filter keys unless parsed deterministically.",
        "Per-host operator distribution.",
        "Table/column stats freshness unless parsed from context.",
        "Hot key distribution.",
        "Skew is suspected but not proven.",
    ]
    for missing in context_missing_metadata(analysis, {"SHOW TABLE STATS", "SHOW COLUMN STATS"}):
        missing_evidence.append(f"Collector metadata missing: {missing}.")

    return {
        "title": title,
        "operator": op,
        "finding": f"Severe deterministic evidence was detected for {op['label']}.",
        "evidence": evidence,
        "admin_actions": admin_actions,
        "user_actions": user_actions,
        "how_to_verify": [
            "Re-run the query and compare actual vs estimated rows for the same operator.",
            "Compare PeakMemUsage and spill counters before/after.",
            "Compare runtime and bytes sent/read before/after.",
        ],
        "missing_evidence": missing_evidence,
    }
