"""Python-owned report contract digest derived from deterministic facts."""

from __future__ import annotations

import json
import re
from typing import Any

from query_doctor.report.facts_extractors import (
    backend_data_skew_is_supported,
    backend_has_proven_tail,
    backend_summary_value,
    cluster_event_context_points,
    cluster_event_context_summary,
    cluster_runtime_context_points,
    cluster_runtime_context_summary,
    cm_metrics_correlation_points,
    cm_metrics_correlation_summary,
    cm_metrics_facts_summary,
    cm_metrics_observed_points,
    facts_cardinality_anomaly_count,
    facts_has_backend_tail_evidence,
    facts_have_action_cards,
    facts_have_large_intermediate_or_exchange,
    facts_have_metadata_stats_gap,
    facts_have_spill_scratch_evidence,
    facts_memory_anomaly_count,
    first_bullet_value,
    parse_backend_tail_summary,
)
from query_doctor.report.markdown import extract_markdown_section, extract_markdown_subsection
from query_doctor.report.recommendation_candidates import recommendation_candidate_lines


FACT_APPENDIX_MAX_ITEMS = 8


def _localized(language: str, ru_text: str, en_text: str) -> str:
    return ru_text if language == "ru" else en_text


def markdown_bullet_lines(lines: list[str], *, limit: int = FACT_APPENDIX_MAX_ITEMS) -> list[str]:
    bullets = [line.strip() for line in lines if line.lstrip().startswith("- ")]
    return bullets[:limit]


def markdown_subheading_titles(lines: list[str], *, prefix: str = "### ", limit: int = FACT_APPENDIX_MAX_ITEMS) -> list[str]:
    titles = [line[len(prefix) :].strip() for line in lines if line.startswith(prefix)]
    return titles[:limit]


def supported_summary_points(facts_text: str, *, language: str = "ru") -> list[str]:
    points: list[str] = []
    cardinality_count = facts_cardinality_anomaly_count(facts_text)
    memory_count = facts_memory_anomaly_count(facts_text)
    if cardinality_count and cardinality_count > 0:
        points.append(
            _localized(
                language,
                "В parsed facts есть подтверждённые cardinality estimate anomalies; "
                "описание должно сохранять направление estimate mismatch.",
                "Parsed facts contain confirmed cardinality estimate anomalies; wording must preserve the estimate mismatch direction.",
            )
        )
    if memory_count and memory_count > 0:
        points.append(
            _localized(
                language,
                "В parsed facts есть memory estimate anomalies; это отдельный сигнал от cardinality mismatch.",
                "Parsed facts contain memory estimate anomalies; this is separate from cardinality mismatch.",
            )
        )
    if facts_have_large_intermediate_or_exchange(facts_text):
        points.append(
            _localized(
                language,
                "В parsed facts есть large intermediate/exchange traffic; описывать как data movement volume, "
                "не как external network instability.",
                "Parsed facts contain large intermediate/exchange traffic; describe it as data movement volume, not external network instability.",
            )
        )
    if facts_has_backend_tail_evidence(facts_text):
        summary = parse_backend_tail_summary(facts_text)
        if backend_data_skew_is_supported(summary):
            points.append(
                _localized(
                    language,
                    "Backend facts support data skew по RowsProduced; это не доказывает cardinality underestimation.",
                    "Backend facts support data skew by RowsProduced; this does not prove cardinality underestimation.",
                )
            )
        if backend_has_proven_tail(summary):
            points.append("Backend facts support execution skew / host-tail evidence.")
        else:
            points.append("Backend facts do not prove a single slow tail host unless execution skew is yes.")
    if facts_have_spill_scratch_evidence(facts_text):
        points.append(
            "Parsed findings contain non-zero spill/scratch metric evidence; keep causal wording separate."
        )
    if facts_have_metadata_stats_gap(facts_text):
        points.append(
            "Metadata digest shows table/column stats gaps; frame stats work as approved maintenance, not proven root cause."
        )
    for point in cm_metrics_observed_points(facts_text):
        points.append(
            f"Runtime Metrics Facts contain an observed context signal: {point}. "
            "Use it as bounded runtime context, not as standalone root cause."
        )
    cm_correlation = cm_metrics_correlation_summary(facts_text)
    correlated_signals = cm_correlation.get("correlated_signals")
    context_only_signals = cm_correlation.get("context_only_signals")
    if correlated_signals and correlated_signals != "0":
        points.append(
            f"Runtime Metrics Correlation contains {correlated_signals} correlated runtime context signal(s); "
            "these may strengthen profile-supported evidence, not standalone root-cause claims."
        )
    elif context_only_signals and context_only_signals != "0":
        points.append(
            f"Runtime Metrics Correlation contains {context_only_signals} context-only signal(s); "
            "keep them out of root-cause wording and SQL optimizer actions."
        )
    cluster_context = cluster_runtime_context_summary(facts_text)
    cluster_correlated = cluster_context.get("correlated_signals")
    cluster_context_only = cluster_context.get("context_only_signals")
    cluster_scoring = cluster_context.get("scoring_contribution")
    if cluster_context.get("status") in {"available", "partial"}:
        parts = []
        if cluster_correlated and cluster_correlated != "none":
            parts.append(f"correlated={cluster_correlated}")
        if cluster_context_only and cluster_context_only != "none":
            parts.append(f"context-only={cluster_context_only}")
        if cluster_scoring:
            parts.append(f"scoring={cluster_scoring}")
        suffix = "; ".join(parts) if parts else "no runtime signal rollup"
        points.append(
            "Cluster Runtime Context is a Python-owned runtime summary "
            f"({suffix}); use it for evidence framing, not root-cause proof."
        )
    cluster_events = cluster_event_context_summary(facts_text)
    cluster_event_status = cluster_events.get("status")
    cluster_event_counts = cluster_events.get("signal_counts")
    if cluster_events.get("available") == "yes":
        suffix = f"status={cluster_event_status or 'unknown'}"
        if cluster_event_counts and cluster_event_counts != "none":
            suffix += f"; signals={cluster_event_counts}"
        points.append(
            "Cluster Event Context contains bounded event summary "
            f"({suffix}); use it for follow-up checks, not root-cause proof."
        )
    if not points:
        points.append("Parsed facts do not select a confirmed optimization target; use this report as a baseline.")
    return points[:FACT_APPENDIX_MAX_ITEMS]


def action_card_differentiators(action_card_lines: list[str], *, limit: int = 3) -> list[str]:
    differentiators: list[str] = []
    current_title: str | None = None
    current_values: dict[str, str] = {}

    def flush() -> None:
        if len(differentiators) >= limit or not current_title:
            return
        operator = current_values.get("operator")
        if not operator:
            return
        details = [f"Action Card operator: {operator}", current_title]
        for label in (
            "actual rows",
            "estimated rows",
            "actual/estimated ratio",
            "peak memory",
            "estimated peak memory",
            "peak/estimated memory ratio",
        ):
            value = current_values.get(label)
            if value:
                details.append(f"{label}: {value}")
        differentiators.append("; ".join(details))

    for line in action_card_lines:
        stripped = line.strip()
        if stripped.startswith("### Card "):
            flush()
            current_title = stripped[4:].strip()
            current_values = {}
            continue
        match = re.match(r"^-\s*(?P<label>[A-Za-z/ ]+):\s*(?P<value>.+?)\s*$", stripped)
        if match and current_title:
            current_values[match.group("label").strip()] = match.group("value").strip()
    flush()
    return differentiators


def case_summary_differentiators(facts_text: str) -> list[str]:
    """Return safe case-specific facts that help the LLM avoid generic summaries."""
    summary_lines = extract_markdown_section(facts_text, "## Summary")
    query_wall_clock_lines = extract_markdown_section(facts_text, "## Query Wall Clock")
    evidence_quality_lines = extract_markdown_section(facts_text, "## Evidence Quality")
    totals_lines = extract_markdown_section(facts_text, "## Totals")
    action_card_lines = extract_markdown_section(facts_text, "## Action Cards")
    findings_lines = extract_markdown_section(facts_text, "## Findings")
    backend_summary = parse_backend_tail_summary(facts_text)
    backend_lines = extract_markdown_section(facts_text, "## Backend / Host Tail Evidence")
    backend_normalized_lines = extract_markdown_subsection(backend_lines, "### Normalized tail candidates")
    cm_metrics = cm_metrics_facts_summary(facts_text)

    differentiators: list[str] = []
    for label in (
        "Parsed operators",
        "Cardinality anomalies",
        "Memory anomalies",
        "Zero/unknown row estimate gaps",
        "Zero/unknown memory estimate gaps",
    ):
        value = first_bullet_value(summary_lines, label)
        if value:
            differentiators.append(f"{label}: {value}")
    wall_clock = first_bullet_value(query_wall_clock_lines, "duration")
    wall_clock_source = first_bullet_value(query_wall_clock_lines, "source")
    wall_clock_confidence = first_bullet_value(query_wall_clock_lines, "confidence")
    if wall_clock:
        detail_parts = [wall_clock]
        if wall_clock_source:
            detail_parts.append(f"source={wall_clock_source}")
        if wall_clock_confidence:
            detail_parts.append(f"confidence={wall_clock_confidence}")
        differentiators.append(f"Query wall-clock: {', '.join(detail_parts)}")
    evidence_quality_score = first_bullet_value(evidence_quality_lines, "score")
    evidence_quality_level = first_bullet_value(evidence_quality_lines, "level")
    if evidence_quality_score or evidence_quality_level:
        parts = []
        if evidence_quality_score:
            parts.append(f"score={evidence_quality_score}")
        if evidence_quality_level:
            parts.append(f"level={evidence_quality_level}")
        differentiators.append(f"Evidence quality: {', '.join(parts)}")
    for label in ("TotalTime", "TotalBytesRead", "TotalBytesSent"):
        value = first_bullet_value(totals_lines, label)
        if value:
            differentiators.append(f"{label}: {value}")

    differentiators.extend(action_card_differentiators(action_card_lines))
    for title in markdown_subheading_titles(action_card_lines, limit=3):
        if len(differentiators) >= FACT_APPENDIX_MAX_ITEMS:
            break
        differentiators.append(f"Action Card: {title}")
    for title in markdown_subheading_titles(findings_lines, limit=3):
        differentiators.append(f"Finding: {title}")

    for label in (
        "host tail candidates",
        "execution tail candidates",
        "read-rate tail candidates",
        "write-path tail candidates",
        "data skew",
        "execution skew",
        "write-path anomaly",
    ):
        value = backend_summary_value(backend_summary, label)
        if value != "unknown":
            differentiators.append(f"Backend {label}: {value}")
    for line in backend_normalized_lines:
        stripped = line.strip()
        if not stripped.startswith("|") or stripped.startswith("|---") or "metric_key" in stripped:
            continue
        differentiators.append(f"Backend normalized tail candidate: {stripped}")
        break

    if cm_metrics.get("coverage"):
        differentiators.append(f"Runtime metrics coverage: {cm_metrics['coverage']}")
    for point in cm_metrics_observed_points(facts_text):
        differentiators.append(f"Runtime metric signal: {point}")
    cm_correlation = cm_metrics_correlation_summary(facts_text)
    if cm_correlation.get("correlated_signals"):
        differentiators.append(f"Runtime metrics correlated signals: {cm_correlation['correlated_signals']}")
    for point in cm_metrics_correlation_points(facts_text):
        differentiators.append(f"Runtime metric correlation: {point}")
    cluster_context = cluster_runtime_context_summary(facts_text)
    if cluster_context.get("scoring_contribution"):
        differentiators.append(f"Cluster runtime scoring: {cluster_context['scoring_contribution']}")
    cluster_events = cluster_event_context_summary(facts_text)
    if cluster_events.get("status"):
        differentiators.append(f"Cluster event context status: {cluster_events['status']}")
    if cluster_events.get("signal_counts"):
        differentiators.append(f"Cluster event signals: {cluster_events['signal_counts']}")

    return differentiators[:FACT_APPENDIX_MAX_ITEMS]


def evidence_groups(facts_text: str) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    action_card_lines = extract_markdown_section(facts_text, "## Action Cards")
    findings_lines = extract_markdown_section(facts_text, "## Findings")
    limitation_lines = extract_markdown_section(
        facts_text,
        "## What is NOT supported by the parsed evidence",
    )
    action_cards = markdown_subheading_titles(action_card_lines)
    findings = markdown_subheading_titles(findings_lines)
    unsupported = markdown_bullet_lines(limitation_lines)
    cm_metric_points = cm_metrics_observed_points(facts_text)
    cm_metric_correlation_points = cm_metrics_correlation_points(facts_text)
    cluster_context_points = cluster_runtime_context_points(facts_text)
    cluster_event_points = cluster_event_context_points(facts_text)
    if action_cards:
        groups["action_cards"] = action_cards
    if findings:
        groups["findings"] = findings
    if cm_metric_points:
        groups["cm_metrics"] = cm_metric_points
    if cm_metric_correlation_points:
        groups["cm_metrics_correlation"] = cm_metric_correlation_points
    if cluster_context_points:
        groups["cluster_runtime_context"] = cluster_context_points
    if cluster_event_points:
        groups["cluster_event_context"] = cluster_event_points
    if unsupported:
        groups["unsupported"] = unsupported
    return groups


def build_report_contract_digest(facts_text: str, *, language: str = "ru") -> dict[str, Any]:
    """Return a compact Python-owned contract for LLM report slots."""
    summary_lines = extract_markdown_section(facts_text, "## Summary")
    totals_lines = extract_markdown_section(facts_text, "## Totals")
    evidence_quality_lines = extract_markdown_section(facts_text, "## Evidence Quality")
    action_card_lines = extract_markdown_section(facts_text, "## Action Cards")
    findings_lines = extract_markdown_section(facts_text, "## Findings")
    limitation_lines = extract_markdown_section(
        facts_text,
        "## What is NOT supported by the parsed evidence",
    )
    backend_summary = parse_backend_tail_summary(facts_text)
    cm_metrics = cm_metrics_facts_summary(facts_text)
    cm_metrics_correlation = cm_metrics_correlation_summary(facts_text)
    cluster_runtime_context = cluster_runtime_context_summary(facts_text)
    cluster_event_context = cluster_event_context_summary(facts_text)
    return {
        "summary": {
            label: first_bullet_value(summary_lines, label)
            for label in (
                "Parsed operators",
                "Cardinality anomalies",
                "Memory anomalies",
                "Zero/unknown row estimate gaps",
                "Zero/unknown memory estimate gaps",
            )
            if first_bullet_value(summary_lines, label) is not None
        },
        "totals": {
            label: first_bullet_value(totals_lines, label)
            for label in ("TotalTime", "TotalBytesRead", "TotalBytesSent")
            if first_bullet_value(totals_lines, label) is not None
        },
        "evidence_flags": {
            "has_action_cards": facts_have_action_cards(facts_text),
            "has_backend_tail_evidence": facts_has_backend_tail_evidence(facts_text),
            "has_spill_scratch_evidence": facts_have_spill_scratch_evidence(facts_text),
            "has_metadata_stats_gap": facts_have_metadata_stats_gap(facts_text),
            "has_large_intermediate_or_exchange": facts_have_large_intermediate_or_exchange(facts_text),
        },
        "backend_summary": backend_summary,
        "cm_metrics": cm_metrics,
        "cm_metrics_correlation": cm_metrics_correlation,
        "cluster_runtime_context": cluster_runtime_context,
        "cluster_event_context": cluster_event_context,
        "evidence_quality": {
            label: first_bullet_value(evidence_quality_lines, label)
            for label in ("score", "level")
            if first_bullet_value(evidence_quality_lines, label) is not None
        },
        "supported_summary_points": supported_summary_points(facts_text, language=language),
        "case_differentiators": case_summary_differentiators(facts_text),
        "evidence_groups": evidence_groups(facts_text),
        "recommendation_candidates": [
            {"id": candidate_id, "text": text}
            for candidate_id, text in recommendation_candidate_lines(facts_text, language=language)
        ],
        "action_card_titles": markdown_subheading_titles(action_card_lines),
        "finding_titles": markdown_subheading_titles(findings_lines),
        "unsupported_conclusions": markdown_bullet_lines(limitation_lines),
    }


def format_report_contract_digest(facts_text: str, *, language: str = "ru") -> str:
    return json.dumps(
        build_report_contract_digest(facts_text, language=language),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
