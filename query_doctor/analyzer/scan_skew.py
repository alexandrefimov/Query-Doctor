"""Scan-skew evidence tiers from selected-query backend facts."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from query_doctor.analyzer.backend_tail_analysis import (
    BACKEND_DATA_SKEW_RATIO,
    BACKEND_MIN_HOSTS_FOR_SKEW,
)
from query_doctor.analyzer.scalars import fmt_duration, fmt_ratio


SCAN_SKEW_METRICS = (
    ("scan_bytes_assigned", "assigned scan bytes"),
    ("bytes_read", "bytes read"),
    ("rows_produced", "rows produced"),
)
DIRECT_SCAN_SKEW_PRIMARY_METRICS = {"scan_bytes_assigned", "bytes_read"}
SCAN_SKEW_LONG_PHASE_MIN_MS = 10_000.0
SCAN_SKEW_RUNTIME_IMBALANCE_RATIO = 1.5


@dataclass(frozen=True)
class ScanSkewMetricSpread:
    metric_key: str
    metric_label: str
    ratio: float


@dataclass(frozen=True)
class ScanSkewEvidence:
    source: str
    fragment_group: str
    metric_key: str
    metric_label: str
    ratio: float
    group_host_count: int
    corroborating_metric_count: int
    group_max_execution_time_ms: float | None
    group_avg_execution_time_ms: float | None
    group_max_avg_execution_ratio: float | None
    runtime_status: str


@dataclass(frozen=True)
class ScanSkewFacts:
    status: str
    evidence_tier: str
    finding_supported: bool
    primary_supported: bool
    evidence_source: str
    fragment_group: str
    skew_metric: str
    skew_metric_label: str
    skew_ratio: float | None
    skew_ratio_human: str
    skew_group_host_count: int
    corroborating_metric_count: int
    group_max_execution_time_ms: float | None
    group_max_execution_time_human: str
    group_avg_execution_time_ms: float | None
    group_avg_execution_time_human: str
    group_max_avg_execution_ratio: float | None
    group_max_avg_execution_ratio_human: str
    runtime_status: str
    backend_rows_parsed: int
    skew_group_count: int
    comparable_group_count: int
    aggregate_summary_observed: bool
    guardrail: str
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_scan_skew_facts(analysis: dict[str, Any]) -> dict[str, Any]:
    """Build raw-free scan-skew evidence facts for the selected query."""

    return scan_skew_facts(analysis).to_dict()


def scan_skew_facts(analysis: dict[str, Any]) -> ScanSkewFacts:
    backend = analysis.get("backend_tail")
    backend = backend if isinstance(backend, dict) else {}
    evidence = best_scan_skew_evidence(backend)
    backend_rows_parsed = int_value(backend.get("rows_parsed"))
    groups = backend.get("groups")
    groups = groups if isinstance(groups, list) else []
    skew_group_count = sum(
        1
        for group in groups
        if isinstance(group, dict) and str(group.get("data_skew") or "").strip().lower() == "yes"
    )
    comparable_group_count = sum(
        1 for group in groups if isinstance(group, dict) and bool(group.get("comparable_work"))
    )
    aggregate_summary_observed = str(
        backend.get("data_skew") or ""
    ).strip().lower() == "yes" or bool(skew_group_count)

    if evidence is not None:
        status = "supported"
        evidence_tier = evidence_tier_for_scan_skew(evidence)
        finding_supported = True
    elif aggregate_summary_observed:
        status = "context_only"
        evidence_tier = "context_only"
        finding_supported = False
    elif backend_rows_parsed or groups:
        status = "not_observed"
        evidence_tier = "unsupported"
        finding_supported = False
    else:
        status = "not_observed"
        evidence_tier = "unsupported"
        finding_supported = False

    return ScanSkewFacts(
        status=status,
        evidence_tier=evidence_tier,
        finding_supported=finding_supported,
        primary_supported=finding_supported and evidence_tier == "strong",
        evidence_source=evidence.source if evidence is not None else "",
        fragment_group=evidence.fragment_group if evidence is not None else "",
        skew_metric=evidence.metric_key if evidence is not None else "",
        skew_metric_label=evidence.metric_label if evidence is not None else "",
        skew_ratio=evidence.ratio if evidence is not None else None,
        skew_ratio_human=fmt_ratio(evidence.ratio) if evidence is not None else "n/a",
        skew_group_host_count=evidence.group_host_count if evidence is not None else 0,
        corroborating_metric_count=(
            evidence.corroborating_metric_count if evidence is not None else 0
        ),
        group_max_execution_time_ms=(
            evidence.group_max_execution_time_ms if evidence is not None else None
        ),
        group_max_execution_time_human=(
            fmt_duration(evidence.group_max_execution_time_ms)
            if evidence is not None and evidence.group_max_execution_time_ms is not None
            else "n/a"
        ),
        group_avg_execution_time_ms=(
            evidence.group_avg_execution_time_ms if evidence is not None else None
        ),
        group_avg_execution_time_human=(
            fmt_duration(evidence.group_avg_execution_time_ms)
            if evidence is not None and evidence.group_avg_execution_time_ms is not None
            else "n/a"
        ),
        group_max_avg_execution_ratio=(
            evidence.group_max_avg_execution_ratio if evidence is not None else None
        ),
        group_max_avg_execution_ratio_human=(
            fmt_ratio(evidence.group_max_avg_execution_ratio)
            if evidence is not None and evidence.group_max_avg_execution_ratio is not None
            else "n/a"
        ),
        runtime_status=evidence.runtime_status if evidence is not None else "not_observed",
        backend_rows_parsed=backend_rows_parsed,
        skew_group_count=skew_group_count,
        comparable_group_count=comparable_group_count,
        aggregate_summary_observed=aggregate_summary_observed,
        guardrail=(
            "Scan skew can become supported only from per-instance scan bytes, "
            "bytes read, rows, or a mapped equivalent aggregate spread for the selected query. "
            "Primary runtime-skew routing also requires a long-running phase with material "
            "Max Time vs Avg Time imbalance and either direct scan/bytes spread or multiple "
            "corroborating spread metrics. Operator-level totals, runtime duration, network "
            "metrics, and aggregate-only timers remain "
            "context-only by themselves."
        ),
        limitations=tuple(
            scan_skew_limitations(evidence, aggregate_summary_observed, evidence_tier)
        ),
    )


def scan_skew_facts_from_analysis(analysis: dict[str, Any]) -> ScanSkewFacts:
    existing = analysis.get("scan_skew")
    if isinstance(existing, dict):
        return scan_skew_facts_from_mapping(existing)
    return scan_skew_facts(analysis)


def scan_skew_facts_from_mapping(payload: dict[str, Any]) -> ScanSkewFacts:
    return ScanSkewFacts(
        status=safe_token(payload.get("status"), default="not_observed"),
        evidence_tier=safe_token(payload.get("evidence_tier"), default="unsupported"),
        finding_supported=bool_value(payload.get("finding_supported")),
        primary_supported=bool_value(payload.get("primary_supported")),
        evidence_source=str(payload.get("evidence_source") or ""),
        fragment_group=str(payload.get("fragment_group") or ""),
        skew_metric=str(payload.get("skew_metric") or ""),
        skew_metric_label=str(payload.get("skew_metric_label") or ""),
        skew_ratio=numeric_value(payload.get("skew_ratio")),
        skew_ratio_human=str(payload.get("skew_ratio_human") or "n/a"),
        skew_group_host_count=int_value(payload.get("skew_group_host_count")),
        corroborating_metric_count=int_value(payload.get("corroborating_metric_count")),
        group_max_execution_time_ms=numeric_value(payload.get("group_max_execution_time_ms")),
        group_max_execution_time_human=str(payload.get("group_max_execution_time_human") or "n/a"),
        group_avg_execution_time_ms=numeric_value(payload.get("group_avg_execution_time_ms")),
        group_avg_execution_time_human=str(payload.get("group_avg_execution_time_human") or "n/a"),
        group_max_avg_execution_ratio=numeric_value(payload.get("group_max_avg_execution_ratio")),
        group_max_avg_execution_ratio_human=str(
            payload.get("group_max_avg_execution_ratio_human") or "n/a"
        ),
        runtime_status=safe_token(payload.get("runtime_status"), default="unknown"),
        backend_rows_parsed=int_value(payload.get("backend_rows_parsed")),
        skew_group_count=int_value(payload.get("skew_group_count")),
        comparable_group_count=int_value(payload.get("comparable_group_count")),
        aggregate_summary_observed=bool_value(payload.get("aggregate_summary_observed")),
        guardrail=str(payload.get("guardrail") or ""),
        limitations=tuple(str(item) for item in payload.get("limitations") or [] if item),
    )


def best_scan_skew_evidence(backend: dict[str, Any]) -> ScanSkewEvidence | None:
    host_evidence = best_scan_skew_evidence_from_hosts(backend)
    group_evidence = best_scan_skew_evidence_from_groups(backend)
    if scan_skew_evidence_sort_key(group_evidence) > scan_skew_evidence_sort_key(host_evidence):
        return group_evidence
    return host_evidence


def best_scan_skew_evidence_from_hosts(backend: dict[str, Any]) -> ScanSkewEvidence | None:
    hosts = backend.get("hosts")
    hosts = hosts if isinstance(hosts, list) else []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for host in hosts:
        if not isinstance(host, dict):
            continue
        group = str(host.get("fragment_group") or "unknown")
        grouped.setdefault(group, []).append(host)

    best: ScanSkewEvidence | None = None
    for group, group_hosts in grouped.items():
        evidence = scan_skew_evidence_from_group(
            group,
            group_hosts,
            source="per_instance_backend_metrics",
        )
        if evidence is not None and scan_skew_evidence_sort_key(
            evidence
        ) > scan_skew_evidence_sort_key(best):
            best = evidence
    return best


def best_scan_skew_evidence_from_groups(backend: dict[str, Any]) -> ScanSkewEvidence | None:
    groups = backend.get("groups")
    groups = groups if isinstance(groups, list) else []
    best: ScanSkewEvidence | None = None
    for group in groups:
        if not isinstance(group, dict):
            continue
        if str(group.get("data_skew") or "").strip().lower() != "yes":
            continue
        if int_value(group.get("host_count")) < BACKEND_MIN_HOSTS_FOR_SKEW:
            continue
        reason = str(group.get("data_skew_reason") or "")
        metric_key, metric_label = metric_from_reason(reason)
        if not metric_key:
            continue
        ratio = ratio_from_text(reason)
        if ratio is None or ratio < BACKEND_DATA_SKEW_RATIO:
            continue
        group_max_execution_time_ms = numeric_value(
            group.get("group_max_execution_time_ms")
            or group.get("max_execution_time_ms")
            or group.get("execution_time_max_ms")
        )
        group_avg_execution_time_ms = numeric_value(
            group.get("group_avg_execution_time_ms")
            or group.get("avg_execution_time_ms")
            or group.get("execution_time_avg_ms")
        )
        group_max_avg_execution_ratio = max_avg_ratio(
            group_max_execution_time_ms,
            group_avg_execution_time_ms,
        )
        evidence = ScanSkewEvidence(
            source="mapped_backend_group_summary",
            fragment_group=str(group.get("fragment_group") or "unknown"),
            metric_key=metric_key,
            metric_label=metric_label,
            ratio=ratio,
            group_host_count=int_value(group.get("host_count")),
            corroborating_metric_count=1,
            group_max_execution_time_ms=group_max_execution_time_ms,
            group_avg_execution_time_ms=group_avg_execution_time_ms,
            group_max_avg_execution_ratio=group_max_avg_execution_ratio,
            runtime_status=runtime_status(
                group_max_execution_time_ms,
                group_max_avg_execution_ratio,
            ),
        )
        if scan_skew_evidence_sort_key(evidence) > scan_skew_evidence_sort_key(best):
            best = evidence
    return best


def scan_skew_evidence_from_group(
    fragment_group: str,
    hosts: list[dict[str, Any]],
    *,
    source: str,
) -> ScanSkewEvidence | None:
    spreads = scan_skew_metric_spreads(hosts)
    if not spreads:
        return None
    primary_spread = max(spreads, key=lambda spread: spread.ratio)
    max_execution_ms, avg_execution_ms, max_avg_execution_ratio = group_execution_stats(hosts)
    return ScanSkewEvidence(
        source=source,
        fragment_group=fragment_group,
        metric_key=primary_spread.metric_key,
        metric_label=primary_spread.metric_label,
        ratio=primary_spread.ratio,
        group_host_count=len(hosts),
        corroborating_metric_count=len(spreads),
        group_max_execution_time_ms=max_execution_ms,
        group_avg_execution_time_ms=avg_execution_ms,
        group_max_avg_execution_ratio=max_avg_execution_ratio,
        runtime_status=runtime_status(max_execution_ms, max_avg_execution_ratio),
    )


def scan_skew_metric_spreads(hosts: list[dict[str, Any]]) -> list[ScanSkewMetricSpread]:
    spreads: list[ScanSkewMetricSpread] = []
    for metric_key, metric_label in SCAN_SKEW_METRICS:
        ratio = scan_skew_ratio(hosts, metric_key)
        if ratio is None or ratio < BACKEND_DATA_SKEW_RATIO:
            continue
        spreads.append(
            ScanSkewMetricSpread(
                metric_key=metric_key,
                metric_label=metric_label,
                ratio=ratio,
            )
        )
    return spreads


def scan_skew_ratio(hosts: list[dict[str, Any]], metric_key: str) -> float | None:
    values = []
    for host in hosts:
        value = numeric_value(host.get(metric_key))
        if value is not None and value > 0:
            values.append(value)
    if len(values) < BACKEND_MIN_HOSTS_FOR_SKEW:
        return None
    min_value = min(values)
    if min_value <= 0:
        return None
    return max(values) / min_value


def group_execution_stats(
    hosts: list[dict[str, Any]],
) -> tuple[float | None, float | None, float | None]:
    values = [
        value
        for host in hosts
        if (value := numeric_value(host.get("execution_time_ms"))) is not None and value > 0
    ]
    if len(values) < BACKEND_MIN_HOSTS_FOR_SKEW:
        return None, None, None
    max_value = max(values)
    avg_value = sum(values) / len(values)
    return max_value, avg_value, max_avg_ratio(max_value, avg_value)


def max_avg_ratio(max_value: float | None, avg_value: float | None) -> float | None:
    if max_value is None or avg_value is None or avg_value <= 0:
        return None
    return max_value / avg_value


def runtime_status(
    max_execution_time_ms: float | None,
    max_avg_execution_ratio: float | None,
) -> str:
    if max_execution_time_ms is None:
        return "timing_unknown"
    if max_execution_time_ms < SCAN_SKEW_LONG_PHASE_MIN_MS:
        return "short_running"
    if (
        max_avg_execution_ratio is not None
        and max_avg_execution_ratio >= SCAN_SKEW_RUNTIME_IMBALANCE_RATIO
    ):
        return "long_running_imbalanced"
    return "long_running_balanced"


def evidence_tier_for_scan_skew(evidence: ScanSkewEvidence) -> str:
    if evidence.runtime_status == "long_running_imbalanced" and (
        evidence.metric_key in DIRECT_SCAN_SKEW_PRIMARY_METRICS
        or evidence.corroborating_metric_count >= 2
    ):
        return "strong"
    return "medium"


def scan_skew_evidence_sort_key(evidence: ScanSkewEvidence | None) -> tuple[int, int, int, float]:
    if evidence is None:
        return (-1, 0, 0, 0.0)
    runtime_rank = {
        "long_running_imbalanced": 3,
        "timing_unknown": 2,
        "long_running_balanced": 1,
        "short_running": 0,
    }.get(evidence.runtime_status, -1)
    return (
        runtime_rank,
        evidence.corroborating_metric_count,
        evidence.group_host_count,
        evidence.ratio,
    )


def metric_from_reason(reason: str) -> tuple[str, str]:
    normalized = reason.lower()
    for metric_key, metric_label in SCAN_SKEW_METRICS:
        if metric_label in normalized:
            return metric_key, metric_label
    return "", ""


def ratio_from_text(text: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)x", text, re.IGNORECASE)
    if not match:
        return None
    return numeric_value(match.group(1))


def scan_skew_limitations(
    evidence: ScanSkewEvidence | None,
    aggregate_summary_observed: bool,
    evidence_tier: str,
) -> list[str]:
    limitations = [
        "Operator-level scan totals, query duration, exchange/network timers, and runtime metrics are context-only without per-instance or mapped equivalent scan-spread evidence."
    ]
    if evidence is not None and evidence_tier == "strong":
        limitations.append(
            "Scan skew evidence supports a runtime-skew follow-up, but it does not prove table layout, HDFS placement, runtime filters, or statistics as the root cause by itself."
        )
    elif evidence is not None:
        limitations.append(
            "Scan spread evidence was observed, but primary runtime-skew routing requires a long-running phase with material Max Time vs Avg Time imbalance."
        )
        if evidence.runtime_status == "timing_unknown":
            limitations.append(
                "Per-backend execution timing was unavailable, so scan skew stays below primary-bottleneck promotion."
            )
        elif evidence.runtime_status == "short_running":
            limitations.append(
                "The skewed phase was short-running, so it remains supporting context."
            )
        elif evidence.runtime_status == "long_running_balanced":
            limitations.append(
                "The skewed phase was long-running, but Max Time vs Avg Time imbalance was not material."
            )
        elif evidence.runtime_status == "long_running_imbalanced":
            limitations.append(
                "The skewed phase was long-running and imbalanced, but primary routing requires direct scan/bytes spread or multiple corroborating spread metrics."
            )
    elif aggregate_summary_observed:
        limitations.append(
            "A backend data-skew summary was observed, but mapped per-instance or equivalent scan-spread fields were not available for primary promotion."
        )
    return limitations


def numeric_value(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def int_value(value: Any) -> int:
    parsed = numeric_value(value)
    if parsed is None or parsed <= 0:
        return 0
    return int(parsed)


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y"}


def safe_token(value: object, *, default: str) -> str:
    text = str(value or "").strip().lower()
    return text if text else default
