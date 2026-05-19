"""Deterministic analyzer facts appendix rendering."""

from __future__ import annotations

import re

from query_doctor.report.contract import ANALYZER_FACTS_HEADING
from query_doctor.report.language_contract import get_report_language_contract
from query_doctor.report.markdown import (
    extract_markdown_section,
    extract_markdown_subsection,
    strip_markdown_section,
)
from query_doctor.safety.browser_display import redact_browser_display_text


FACT_APPENDIX_MAX_ITEMS = 8


def escape_fact_markdown_text(text: str) -> str:
    """Escape raw HTML delimiters in fact excerpts before trusted report rendering."""
    redacted = redact_browser_display_text(
        text,
        redact_artifact_markers=True,
        redact_field_names=True,
        redact_model_names=True,
        redact_infrastructure=True,
    )
    return redacted.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def first_bullet_value(lines: list[str], label: str) -> str | None:
    pattern = re.compile(
        rf"^\s*-\s*{re.escape(label)}\s*:\s*(?P<value>.+?)\s*$",
        re.IGNORECASE,
    )
    for line in lines:
        match = pattern.match(line)
        if match:
            return match.group("value").strip()
    return None


def append_fact_bullet(output: list[str], label: str, value: str | None) -> None:
    if value:
        output.append(f"- {label}: {escape_fact_markdown_text(value)}")


def limited_nonempty_lines(
    lines: list[str],
    *,
    limit: int = FACT_APPENDIX_MAX_ITEMS,
) -> tuple[list[str], int]:
    selected = [escape_fact_markdown_text(line.rstrip()) for line in lines if line.strip()]
    return selected[:limit], max(0, len(selected) - limit)


def render_analyzer_facts_appendix(facts_text: str, *, language: str = "ru") -> str:
    contract = get_report_language_contract(language)
    summary_lines = extract_markdown_section(facts_text, "## Summary")
    query_wall_clock_lines = extract_markdown_section(facts_text, "## Query Wall Clock")
    evidence_quality_lines = extract_markdown_section(facts_text, "## Evidence Quality")
    totals_lines = extract_markdown_section(facts_text, "## Totals")
    backend_lines = extract_markdown_section(facts_text, "## Backend / Host Tail Evidence")
    backend_summary_lines = extract_markdown_subsection(backend_lines, "### Summary")
    backend_normalized_lines = extract_markdown_subsection(
        backend_lines, "### Normalized tail candidates"
    )
    backend_candidates_lines = extract_markdown_subsection(
        backend_lines, "### Host tail candidates"
    )
    cluster_event_lines = extract_markdown_section(facts_text, "## Cluster Event Context")
    cluster_event_signal_lines = extract_markdown_subsection(
        cluster_event_lines,
        "### Cluster event signal rollup",
    ) or extract_markdown_subsection(cluster_event_lines, "### CM event signal rollup")
    cluster_event_next_check_lines = extract_markdown_subsection(
        cluster_event_lines,
        "### Cluster event next checks",
    ) or extract_markdown_subsection(cluster_event_lines, "### CM event next checks")
    referenced_table_lines = extract_markdown_section(facts_text, "## Referenced Tables")
    table_metadata_lines = extract_markdown_section(facts_text, "## Table Metadata Context")
    action_card_lines = extract_markdown_section(facts_text, "## Action Cards")
    findings_lines = extract_markdown_section(facts_text, "## Findings")
    limitation_lines = extract_markdown_section(
        facts_text,
        "## What is NOT supported by the parsed evidence",
    )

    lines: list[str] = [
        "",
        contract.analyzer_facts_heading,
        "",
        contract.summary_appendix_heading,
    ]
    for label in (
        "Parsed operators",
        "Cardinality anomalies",
        "Memory anomalies",
        "Zero/unknown row estimate gaps",
        "Zero/unknown memory estimate gaps",
    ):
        append_fact_bullet(lines, label, first_bullet_value(summary_lines, label))
    for label in ("TotalTime", "TotalBytesRead", "TotalBytesSent"):
        append_fact_bullet(lines, label, first_bullet_value(totals_lines, label))
    for label in ("duration", "source", "confidence"):
        append_fact_bullet(
            lines, f"query wall-clock {label}", first_bullet_value(query_wall_clock_lines, label)
        )
    if evidence_quality_lines:
        lines.extend(["", "### Evidence Quality"])
        for label in ("score", "level"):
            append_fact_bullet(lines, label, first_bullet_value(evidence_quality_lines, label))
        strengths = extract_markdown_subsection(evidence_quality_lines, "### Strengths")
        limitations = extract_markdown_subsection(evidence_quality_lines, "### Limitations")
        strength_excerpt, remaining_strengths = limited_nonempty_lines(
            strengths, limit=FACT_APPENDIX_MAX_ITEMS
        )
        if strength_excerpt:
            lines.extend(["", "#### Strengths"])
            lines.extend(strength_excerpt)
            if remaining_strengths:
                lines.append(f"- ... {remaining_strengths} more evidence-quality strengths omitted")
        limitation_excerpt, remaining_limitations = limited_nonempty_lines(
            limitations, limit=FACT_APPENDIX_MAX_ITEMS
        )
        if limitation_excerpt:
            lines.extend(["", "#### Limitations"])
            lines.extend(limitation_excerpt)
            if remaining_limitations:
                lines.append(
                    f"- ... {remaining_limitations} more evidence-quality limitations omitted"
                )

    if backend_summary_lines:
        lines.extend(["", "### Backend / Host Tail Evidence"])
        for label in (
            "backend rows parsed",
            "host tail candidates",
            "execution tail candidates",
            "read-rate tail candidates",
            "write-path tail candidates",
            "data skew",
            "execution skew",
            "write-path anomaly",
        ):
            append_fact_bullet(lines, label, first_bullet_value(backend_summary_lines, label))

        normalized_excerpt, remaining_normalized = limited_nonempty_lines(
            backend_normalized_lines,
            limit=FACT_APPENDIX_MAX_ITEMS,
        )
        if normalized_excerpt:
            lines.extend(["", "### Normalized tail candidates"])
            lines.extend(normalized_excerpt)
            if remaining_normalized:
                lines.append(f"- ... {remaining_normalized} more normalized tail lines omitted")

        candidate_excerpt, remaining_candidates = limited_nonempty_lines(
            [line for line in backend_candidates_lines if not re.match(r"^\s*\|?\s*-{3,}", line)],
            limit=6,
        )
        if candidate_excerpt and candidate_excerpt != ["- none"]:
            lines.extend(["", "Host tail candidates excerpt:"])
            lines.extend(candidate_excerpt)
            if remaining_candidates:
                lines.append(
                    f"- ... {remaining_candidates} more candidate lines omitted from appendix."
                )

    if cluster_event_lines:
        lines.extend(["", "### Cluster Event Context"])
        for label in (
            "status",
            "available",
            "source_status",
            "window_scope",
            "signal_counts",
            "guardrail",
        ):
            append_fact_bullet(lines, label, first_bullet_value(cluster_event_lines, label))
        signal_excerpt, remaining_signals = limited_nonempty_lines(
            [line for line in cluster_event_signal_lines if line.lstrip().startswith("- ")],
            limit=FACT_APPENDIX_MAX_ITEMS,
        )
        if signal_excerpt:
            lines.extend(["", "#### Cluster event signal rollup"])
            lines.extend(signal_excerpt)
            if remaining_signals:
                lines.append(f"- ... {remaining_signals} more cluster event signal lines omitted")
        check_excerpt, remaining_checks = limited_nonempty_lines(
            [line for line in cluster_event_next_check_lines if line.lstrip().startswith("- ")],
            limit=FACT_APPENDIX_MAX_ITEMS,
        )
        if check_excerpt:
            lines.extend(["", "#### Cluster event next checks"])
            lines.extend(check_excerpt)
            if remaining_checks:
                lines.append(f"- ... {remaining_checks} more cluster event checks omitted")

    if referenced_table_lines:
        table_excerpt, remaining_tables = limited_nonempty_lines(
            [line for line in referenced_table_lines if line.lstrip().startswith("- ")],
            limit=FACT_APPENDIX_MAX_ITEMS,
        )
        if table_excerpt:
            lines.extend(["", "### Referenced Tables"])
            lines.extend(table_excerpt)
            if remaining_tables:
                lines.append(f"- ... {remaining_tables} more table lines omitted from appendix.")

    if table_metadata_lines:
        metadata_excerpt, remaining_metadata = limited_nonempty_lines(
            [
                line
                for line in table_metadata_lines
                if line.startswith("### Table:") or line.lstrip().startswith("- ")
                if not re.match(r"^\s*-\s*context path\s*:", line, flags=re.IGNORECASE)
            ],
            limit=FACT_APPENDIX_MAX_ITEMS * 2,
        )
        if metadata_excerpt:
            lines.extend(["", "### Table Metadata Context"])
            lines.extend(metadata_excerpt)
            if remaining_metadata:
                lines.append(
                    f"- ... {remaining_metadata} more metadata lines omitted from appendix."
                )

    if action_card_lines:
        lines.extend(["", "### Action cards"])
        card_titles = [
            escape_fact_markdown_text(line[4:].strip())
            for line in action_card_lines
            if line.startswith("### Card ")
        ]
        if card_titles:
            for title in card_titles[:FACT_APPENDIX_MAX_ITEMS]:
                lines.append(f"- {title}")
            if len(card_titles) > FACT_APPENDIX_MAX_ITEMS:
                lines.append(
                    f"- ... {len(card_titles) - FACT_APPENDIX_MAX_ITEMS} more action cards omitted from appendix."
                )
        else:
            excerpt, remaining = limited_nonempty_lines(
                action_card_lines,
                limit=FACT_APPENDIX_MAX_ITEMS,
            )
            lines.extend(excerpt or ["- No action-card facts present in analyzer facts."])
            if remaining:
                lines.append(f"- ... {remaining} more action-card lines omitted from appendix.")

    finding_titles = [
        escape_fact_markdown_text(line[4:].strip())
        for line in findings_lines
        if line.startswith("### ")
    ]
    if finding_titles:
        lines.extend(["", "### Findings"])
        for title in finding_titles[:FACT_APPENDIX_MAX_ITEMS]:
            lines.append(f"- {title}")
        if len(finding_titles) > FACT_APPENDIX_MAX_ITEMS:
            lines.append(
                f"- ... {len(finding_titles) - FACT_APPENDIX_MAX_ITEMS} more findings omitted from appendix."
            )

    if limitation_lines:
        lines.extend(["", contract.limitations_appendix_heading])
        limitation_excerpt, remaining_limitations = limited_nonempty_lines(
            [line for line in limitation_lines if line.lstrip().startswith("- ")],
            limit=FACT_APPENDIX_MAX_ITEMS,
        )
        lines.extend(limitation_excerpt)
        if remaining_limitations:
            lines.append(
                f"- ... {remaining_limitations} more limitation lines omitted from appendix."
            )

    lines.append("")
    return "\n".join(lines)


def append_analyzer_facts_appendix(
    report_text: str, facts_text: str, *, language: str = "ru"
) -> str:
    contract = get_report_language_contract(language)
    without_model_appendix = strip_markdown_section(report_text, contract.analyzer_facts_heading)
    if contract.analyzer_facts_heading != ANALYZER_FACTS_HEADING:
        without_model_appendix = strip_markdown_section(
            without_model_appendix, ANALYZER_FACTS_HEADING
        )
    return (
        without_model_appendix.rstrip()
        + "\n"
        + render_analyzer_facts_appendix(facts_text, language=language)
    )
