"""Deterministic analyzer service orchestration."""

from __future__ import annotations

import argparse
import re
from typing import Any

from query_doctor.analyzer.backend_tail import (
    backend_tail_finding_severity,
    build_backend_tail_analysis,
    parse_backend_host_facts,
)
from query_doctor.analyzer.context_collection import build_query_wall_clock
from query_doctor.analyzer.operators import (
    op_label,
    op_to_json,
    operator_with_best_memory_ratio,
    operator_with_best_rows_ratio,
    operator_with_zero_memory_estimate_gap,
    operator_with_zero_row_estimate_gap,
    parse_operators,
)
from query_doctor.analyzer.profile_signals import (
    CODEGEN_RE,
    CODEGEN_TIMING_RE,
    SCAN_STORAGE_RE,
    SPILL_RE,
    STATS_PATTERNS,
    find_codegen_bottleneck_lines,
    find_matching_lines,
    find_nonzero_spill_metric_lines,
)
from query_doctor.analyzer.profile_format import build_profile_format_facts
from query_doctor.analyzer.profile_text import normalize_profile_text
from query_doctor.analyzer.runtime_counters import (
    build_runtime_counter_context,
    extract_query_timeline_duration_ms,
    extract_total_counter,
)
from query_doctor.analyzer.scalars import fmt_bytes, fmt_duration, fmt_ratio, fmt_rows
from query_doctor.analyzer.thresholds import MEDIUM_DATA_MOVEMENT_BYTES


def make_finding(
    finding_id: str,
    severity: str,
    title: str,
    summary: str,
    operators: list[dict[str, Any]] | None = None,
    evidence_lines: list[str] | None = None,
    admin_actions: list[str] | None = None,
    missing_evidence: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": finding_id,
        "severity": severity,
        "title": title,
        "summary": summary,
        "operators": operators or [],
        "evidence_lines": evidence_lines or [],
        "admin_actions": admin_actions or [],
        "missing_evidence": missing_evidence or [],
    }

def analyze(
    text: str,
    args: argparse.Namespace,
    cm_query_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    text = normalize_profile_text(text)
    operators = parse_operators(text)
    profile_format = build_profile_format_facts(text, cm_query_context)
    backend_tail = build_backend_tail_analysis(parse_backend_host_facts(text))
    runtime_counter_context = build_runtime_counter_context(text)
    totals = {
        name: extract_total_counter(text, name)
        for name in ["TotalBytesRead", "TotalBytesSent", "TotalTime"]
    }
    query_wall_clock = build_query_wall_clock(totals, cm_query_context, extract_query_timeline_duration_ms(text))

    top_by_time = sorted(
        [op for op in operators if op.time_ms is not None],
        key=lambda x: x.time_ms or 0,
        reverse=True,
    )[: args.top_n]
    top_by_memory = sorted(
        [op for op in operators if op.peak_mem_bytes is not None],
        key=lambda x: x.peak_mem_bytes or 0,
        reverse=True,
    )[: args.top_n]

    cardinality_anomalies = sorted(
        [
            anomaly
            for op in operators
            if (anomaly := operator_with_best_rows_ratio(op, args.rows_ratio_threshold)) is not None
        ],
        key=lambda x: x.rows_ratio or 0,
        reverse=True,
    )
    memory_anomalies = sorted(
        [
            anomaly
            for op in operators
            if (anomaly := operator_with_best_memory_ratio(op, args.mem_ratio_threshold)) is not None
        ],
        key=lambda x: x.mem_ratio or 0,
        reverse=True,
    )
    zero_row_estimate_gaps = sorted(
        [
            gap
            for op in operators
            if (gap := operator_with_zero_row_estimate_gap(op)) is not None
        ],
        key=lambda x: x.actual_rows or 0,
        reverse=True,
    )
    zero_memory_estimate_gaps = sorted(
        [
            gap
            for op in operators
            if (gap := operator_with_zero_memory_estimate_gap(op)) is not None
        ],
        key=lambda x: x.peak_mem_bytes or 0,
        reverse=True,
    )

    join_bottlenecks = [
        op
        for op in operators
        if op.is_join
        and (
            (op.time_ms is not None and op.time_ms >= args.slow_operator_ms)
            or (op.actual_rows is not None and op.actual_rows >= args.large_rows_threshold)
            or op.is_partitioned
            or (op.rows_ratio is not None and op.rows_ratio >= args.rows_ratio_threshold)
        )
    ]
    sort_bottlenecks = [
        op
        for op in operators
        if op.is_sort
        and (
            (op.time_ms is not None and op.time_ms >= args.slow_operator_ms)
            or (op.actual_rows is not None and op.actual_rows >= args.large_rows_threshold)
            or (op.mem_ratio is not None and op.mem_ratio >= args.mem_ratio_threshold)
        )
    ]
    analytic_bottlenecks = [
        op
        for op in operators
        if op.is_analytic
        and (
            (op.time_ms is not None and op.time_ms >= args.slow_operator_ms)
            or (op.actual_rows is not None and op.actual_rows >= args.large_rows_threshold)
        )
    ]

    spill_lines = find_matching_lines(text, SPILL_RE)
    spill_nonzero_lines = find_nonzero_spill_metric_lines(text)
    stats_lines = find_matching_lines(text, re.compile("|".join(p.pattern for p in STATS_PATTERNS), re.IGNORECASE))
    storage_lines = find_matching_lines(text, SCAN_STORAGE_RE)
    codegen_lines = find_matching_lines(text, CODEGEN_RE)

    scan_top_ops = [op for op in top_by_time[:3] if op.is_scan]
    query_wall_clock_ms = query_wall_clock.get("duration_ms")
    codegen_bottleneck_lines = find_codegen_bottleneck_lines(text, query_wall_clock_ms)
    storage_bottleneck_evidence: list[str] = []
    for op in scan_top_ops:
        if op.time_ms is not None and op.time_ms >= args.slow_operator_ms:
            if isinstance(query_wall_clock_ms, (int, float)) and query_wall_clock_ms > 0:
                share = op.time_ms / query_wall_clock_ms
                if share < 0.10:
                    continue
                storage_bottleneck_evidence.append(
                    f"{op_label(op)} is among top time operators: {fmt_duration(op.time_ms)}"
                )

    findings: list[dict[str, Any]] = []
    not_supported_causes: list[str] = []

    network_exchange_evidence: list[str] = []
    total_sent = totals.get("TotalBytesSent")
    network_exchange_severity = "medium"
    if (
        total_sent
        and total_sent.get("bytes") is not None
        and total_sent["bytes"] >= MEDIUM_DATA_MOVEMENT_BYTES
    ):
        if total_sent["bytes"] >= args.large_bytes_threshold:
            network_exchange_severity = "high"
        network_exchange_evidence.append(
            f"TotalBytesSent is large: {total_sent['raw']} ({fmt_bytes(total_sent['bytes'])})"
        )
    elif total_sent and total_sent.get("bytes") is not None and total_sent["bytes"] < MEDIUM_DATA_MOVEMENT_BYTES:
        not_supported_causes.append(
            "TotalBytesSent was parsed below the large data-movement threshold: "
            f"{total_sent['raw']} ({fmt_bytes(total_sent['bytes'])}); do not treat it as large exchange traffic."
        )

    if network_exchange_evidence:
        for op in top_by_time[: args.top_n]:
            if "EXCHANGE" in op.operator_name.upper() and op.time_ms is not None:
                network_exchange_evidence.append(
                    f"{op_label(op)} has notable time: {fmt_duration(op.time_ms)}"
                )

    total_read = totals.get("TotalBytesRead")
    if total_read and total_read.get("bytes") is not None and total_read["bytes"] < MEDIUM_DATA_MOVEMENT_BYTES:
        not_supported_causes.append(
            "TotalBytesRead was parsed below the large I/O footprint threshold: "
            f"{total_read['raw']} ({fmt_bytes(total_read['bytes'])}); do not treat it as large scan I/O."
        )

    if total_sent and total_sent.get("bytes") is not None and total_sent["bytes"] >= args.large_bytes_threshold:
        network_exchange_evidence.append(
            "TotalBytesSent meets the high data-movement threshold "
            f"({fmt_bytes(args.large_bytes_threshold)})."
        )

    if cardinality_anomalies:
        worst = cardinality_anomalies[0]
        findings.append(
            make_finding(
                "cardinality_estimate_errors",
                "high" if (worst.rows_ratio or 0) >= 100 else "medium",
                "Cardinality estimate errors",
                (
                    f"Detected actual-vs-estimated row count mismatches. Worst parsed ratio: "
                    f"{op_label(worst)} = {fmt_ratio(worst.rows_ratio)} "
                    f"({fmt_rows(worst.actual_rows)} actual vs {fmt_rows(worst.estimated_rows)} estimated)."
                ),
                operators=[op_to_json(op) for op in cardinality_anomalies],
            )
        )
    elif not zero_row_estimate_gaps:
        not_supported_causes.append(
            "No parsed actual-vs-estimated row count anomaly above threshold; do not claim cardinality estimate errors unless another evidence line supports it."
        )

    if zero_row_estimate_gaps:
        worst = zero_row_estimate_gaps[0]
        findings.append(
            make_finding(
                "zero_row_estimate_gaps",
                "medium",
                "Zero/unknown row estimate gaps",
                (
                    "Detected positive actual rows with an explicit zero/non-positive row estimate. "
                    f"Worst parsed gap: {op_label(worst)} = {fmt_rows(worst.actual_rows)} "
                    f"actual rows vs {fmt_rows(worst.estimated_rows)} estimated rows."
                ),
                operators=[op_to_json(op) for op in zero_row_estimate_gaps],
            )
        )

    if memory_anomalies:
        worst = memory_anomalies[0]
        findings.append(
            make_finding(
                "memory_estimate_errors",
                "high" if (worst.mem_ratio or 0) >= 10 else "medium",
                "Memory estimate errors",
                (
                    f"Detected peak memory above estimated peak memory. Worst parsed ratio: "
                    f"{op_label(worst)} = {fmt_ratio(worst.mem_ratio)} "
                    f"({fmt_bytes(worst.peak_mem_bytes)} peak vs {fmt_bytes(worst.estimated_peak_mem_bytes)} estimated)."
                ),
                operators=[op_to_json(op) for op in memory_anomalies],
            )
        )

    if zero_memory_estimate_gaps:
        worst = zero_memory_estimate_gaps[0]
        findings.append(
            make_finding(
                "zero_memory_estimate_gaps",
                "medium",
                "Zero/unknown memory estimate gaps",
                (
                    "Detected positive peak memory with an explicit zero/non-positive estimated peak memory. "
                    f"Worst parsed gap: {op_label(worst)} = {fmt_bytes(worst.peak_mem_bytes)} "
                    f"peak memory vs {fmt_bytes(worst.estimated_peak_mem_bytes)} estimated peak memory."
                ),
                operators=[op_to_json(op) for op in zero_memory_estimate_gaps],
            )
        )

    if join_bottlenecks:
        findings.append(
            make_finding(
                "join_bottleneck",
                "high",
                "Join bottleneck",
                "Detected heavy join operators by time, row volume, partitioned join mode, or bad estimates.",
                operators=[op_to_json(op) for op in sorted(join_bottlenecks, key=lambda x: x.time_ms or 0, reverse=True)],
            )
        )

    if sort_bottlenecks:
        findings.append(
            make_finding(
                "sort_bottleneck",
                "medium",
                "Sort bottleneck",
                "Detected expensive SORT/TOP-N operators by time, row volume, or memory estimate mismatch.",
                operators=[op_to_json(op) for op in sorted(sort_bottlenecks, key=lambda x: x.time_ms or 0, reverse=True)],
            )
        )

    if analytic_bottlenecks:
        findings.append(
            make_finding(
                "analytic_bottleneck",
                "medium",
                "Analytic bottleneck",
                "Detected ANALYTIC operators with notable time or row volume.",
                operators=[op_to_json(op) for op in sorted(analytic_bottlenecks, key=lambda x: x.time_ms or 0, reverse=True)],
            )
        )
    elif re.search(r"\bANALYTIC\b", text, re.IGNORECASE):
        findings.append(
            make_finding(
                "analytic_present",
                "info",
                "Analytic present",
                "ANALYTIC operators are mentioned in the digest, but this parser did not extract enough per-operator metrics to rank them.",
            )
        )

    if spill_nonzero_lines:
        findings.append(
            make_finding(
                "spill_or_scratch_io",
                "medium",
                "Spill or scratch I/O",
                "Detected non-zero spill/scratch metric evidence in digest lines.",
                evidence_lines=spill_nonzero_lines,
            )
        )
    else:
        not_supported_causes.append(
            "No non-zero spill/scratch I/O evidence was parsed."
        )

    if storage_bottleneck_evidence:
        findings.append(
            make_finding(
                "hdfs_or_storage_bottleneck",
                "medium",
                "Storage/HDFS candidate signal",
                "Detected scan/storage operator evidence among top time operators. Treat this as a candidate signal, not a root-cause claim.",
                evidence_lines=storage_bottleneck_evidence,
            )
        )
    else:
        if scan_top_ops and not isinstance(query_wall_clock_ms, (int, float)):
            not_supported_causes.append(
                "Storage/HDFS share was not evaluated because Query Wall Clock duration is unknown."
            )
        not_supported_causes.append(
            "No direct HDFS/storage candidate signal was parsed. Large TotalBytesRead is an I/O footprint, not proof that HDFS/block size/replication is the root cause."
        )

    if network_exchange_evidence:
        findings.append(
            make_finding(
                "large_intermediate_or_exchange_traffic",
                network_exchange_severity,
                "Large intermediate or exchange traffic",
                "Detected large bytes sent / exchange footprint. Treat as intermediate data movement evidence, not automatically as a network fault.",
                evidence_lines=network_exchange_evidence,
            )
        )
    else:
        not_supported_causes.append(
            "No large exchange/network traffic evidence was parsed from TotalBytesSent or EXCHANGE operators."
        )

    if codegen_bottleneck_lines:
        findings.append(
            make_finding(
                "codegen_bottleneck",
                "medium",
                "Codegen candidate signal",
                "Detected notable codegen/LLVM timing evidence. Treat this as a candidate signal, not a root-cause claim.",
                evidence_lines=codegen_bottleneck_lines[: args.max_evidence_lines],
            )
        )
    else:
        if CODEGEN_TIMING_RE.search(text) and not isinstance(query_wall_clock_ms, (int, float)):
            not_supported_causes.append(
                "Codegen/LLVM share was not evaluated because Query Wall Clock duration is unknown."
            )
        not_supported_causes.append(
            "No codegen/LLVM candidate signal was parsed."
        )

    if backend_tail["execution_tail_candidates"]:
        findings.append(
            make_finding(
                "host_execution_tail_suspected",
                backend_tail_finding_severity(backend_tail["execution_tail_candidates"]),
                "Host-specific execution tail suspected",
                (
                    "Execution skew is suspected from parsed backend execution-time counters. "
                    "Host-specific HDFS/RPC/write path issue is suspected, not proven."
                ),
                evidence_lines=[
                    f"{candidate['host']}: {candidate['evidence']} ({candidate['ratio_human']})"
                    for candidate in backend_tail["execution_tail_candidates"][: args.max_evidence_lines]
                ],
                admin_actions=[
                    "Compare per-host RowsProduced / BytesRead / BytesWritten rates.",
                    "Check HDFS write latency and DataNode pipeline details for the tail host.",
                    "Check NIC errors, retransmits, drops, MTU, LACP/bond, and switch output discards.",
                    "Check whether the tail persists after scanner thread cap changes if that evidence is available.",
                ],
                missing_evidence=[
                    "NIC counters.",
                    "Switch drops.",
                    "DataNode pipeline details.",
                    "Per-host OS/network metrics.",
                ],
            )
        )

    if backend_tail["write_path_candidates"]:
        findings.append(
            make_finding(
                "backend_write_path_anomaly",
                backend_tail_finding_severity(backend_tail["write_path_candidates"]),
                "Backend write-path anomaly",
                (
                    "Backend write-rate or HDFS-write counters show a host-specific write-path tail. "
                    "Treat this as write-path evidence, not execution skew and not scan-storage proof."
                ),
                evidence_lines=[
                    f"{candidate['host']}: {candidate['evidence']} ({candidate['ratio_human']})"
                    for candidate in backend_tail["write_path_candidates"][: args.max_evidence_lines]
                ],
                admin_actions=[
                    "Check HDFS write latency and DataNode pipeline details for the write-path tail host.",
                    "Compare per-host BytesWritten, write rate and HDFS write time.",
                    "Check impalad/DataNode RPC latency, NIC errors and disk write latency around the query window.",
                ],
                missing_evidence=[
                    "DataNode pipeline details.",
                    "Per-host disk write latency.",
                    "Per-host network/RPC metrics.",
                ],
            )
        )

    not_supported_causes.append(
        "No evidence in the profile digest supports HDFS block-size or replication-factor changes as a query-level fix unless scan/storage counters prove it."
    )
    not_supported_causes.append(
        "No evidence in the profile digest supports blaming external network instability; large TotalBytesSent only shows data movement volume."
    )

    return {
        "thresholds": {
            "rows_ratio_threshold": args.rows_ratio_threshold,
            "mem_ratio_threshold": args.mem_ratio_threshold,
            "slow_operator_ms": args.slow_operator_ms,
            "large_rows_threshold": args.large_rows_threshold,
            "large_bytes_threshold": args.large_bytes_threshold,
            "medium_data_movement_bytes": MEDIUM_DATA_MOVEMENT_BYTES,
            "report_top_n": args.top_n,
        },
        "totals": totals,
        "query_wall_clock": query_wall_clock,
        "profile_format": profile_format,
        "backend_tail": backend_tail,
        "runtime_counter_context": runtime_counter_context,
        "operators": [op_to_json(op) for op in operators],
        "top_operators_by_time": [op_to_json(op) for op in top_by_time],
        "top_operators_by_peak_memory": [op_to_json(op) for op in top_by_memory],
        "cardinality_anomalies": [op_to_json(op) for op in cardinality_anomalies],
        "memory_anomalies": [op_to_json(op) for op in memory_anomalies],
        "zero_row_estimate_gaps": [op_to_json(op) for op in zero_row_estimate_gaps],
        "zero_memory_estimate_gaps": [op_to_json(op) for op in zero_memory_estimate_gaps],
        "stats_evidence_lines": stats_lines[: args.max_evidence_lines],
        "spill_evidence_lines": spill_lines[: args.max_evidence_lines],
        "spill_nonzero_evidence_lines": spill_nonzero_lines[: args.max_evidence_lines],
        "storage_evidence_lines": storage_lines[: args.max_evidence_lines],
        "codegen_evidence_lines": codegen_lines[: args.max_evidence_lines],
        "findings": findings,
        "not_supported_causes": not_supported_causes,
    }
