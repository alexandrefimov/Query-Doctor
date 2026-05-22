"""Scan-skew evidence tiers from selected-query backend facts."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from query_doctor.analyzer.backend_tail_analysis import (
    BACKEND_DATA_SKEW_RATIO,
    BACKEND_MIN_HOSTS_FOR_SKEW,
)
from query_doctor.analyzer.scalars import fmt_ratio


SCAN_SKEW_METRICS = (
    ("scan_bytes_assigned", "assigned scan bytes"),
    ("bytes_read", "bytes read"),
    ("rows_produced", "rows produced"),
)


@dataclass(frozen=True)
class ScanSkewEvidence:
    source: str
    fragment_group: str
    metric_key: str
    metric_label: str
    ratio: float


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
        evidence_tier = "strong"
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
        primary_supported=finding_supported,
        evidence_source=evidence.source if evidence is not None else "",
        fragment_group=evidence.fragment_group if evidence is not None else "",
        skew_metric=evidence.metric_key if evidence is not None else "",
        skew_metric_label=evidence.metric_label if evidence is not None else "",
        skew_ratio=evidence.ratio if evidence is not None else None,
        skew_ratio_human=fmt_ratio(evidence.ratio) if evidence is not None else "n/a",
        backend_rows_parsed=backend_rows_parsed,
        skew_group_count=skew_group_count,
        comparable_group_count=comparable_group_count,
        aggregate_summary_observed=aggregate_summary_observed,
        guardrail=(
            "Scan skew can become supported only from per-instance scan bytes, "
            "bytes read, rows, or a mapped equivalent aggregate spread for the selected query. "
            "Operator-level totals, runtime duration, network metrics, and aggregate-only timers "
            "remain context-only by themselves."
        ),
        limitations=tuple(scan_skew_limitations(evidence, aggregate_summary_observed)),
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
        backend_rows_parsed=int_value(payload.get("backend_rows_parsed")),
        skew_group_count=int_value(payload.get("skew_group_count")),
        comparable_group_count=int_value(payload.get("comparable_group_count")),
        aggregate_summary_observed=bool_value(payload.get("aggregate_summary_observed")),
        guardrail=str(payload.get("guardrail") or ""),
        limitations=tuple(str(item) for item in payload.get("limitations") or [] if item),
    )


def best_scan_skew_evidence(backend: dict[str, Any]) -> ScanSkewEvidence | None:
    host_evidence = best_scan_skew_evidence_from_hosts(backend)
    if host_evidence is not None:
        return host_evidence
    return best_scan_skew_evidence_from_groups(backend)


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
        for metric_key, metric_label in SCAN_SKEW_METRICS:
            ratio = scan_skew_ratio(group_hosts, metric_key)
            if ratio is None or ratio < BACKEND_DATA_SKEW_RATIO:
                continue
            evidence = ScanSkewEvidence(
                source="per_instance_backend_metrics",
                fragment_group=group,
                metric_key=metric_key,
                metric_label=metric_label,
                ratio=ratio,
            )
            if best is None or evidence.ratio > best.ratio:
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
        evidence = ScanSkewEvidence(
            source="mapped_backend_group_summary",
            fragment_group=str(group.get("fragment_group") or "unknown"),
            metric_key=metric_key,
            metric_label=metric_label,
            ratio=ratio,
        )
        if best is None or evidence.ratio > best.ratio:
            best = evidence
    return best


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
    evidence: ScanSkewEvidence | None, aggregate_summary_observed: bool
) -> list[str]:
    limitations = [
        "Operator-level scan totals, query duration, exchange/network timers, and runtime metrics are context-only without per-instance or mapped equivalent scan-spread evidence."
    ]
    if evidence is not None:
        limitations.append(
            "Scan skew evidence supports a runtime-skew follow-up, but it does not prove table layout, HDFS placement, runtime filters, or statistics as the root cause by itself."
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
