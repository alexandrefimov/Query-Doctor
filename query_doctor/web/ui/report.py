"""Report rendering helpers for the local Query Doctor UI."""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

from query_doctor.safety.browser_display import redact_browser_display_text
from query_doctor.web.ui.markdown import render_report_markdown_html


ARTIFACT_CANDIDATES = (
    ("Profile digest", "profile_digest.md"),
    ("Profile text", "profile.txt"),
    ("Profile JSON", "profile.json"),
    ("SQL", "sql.sql"),
    ("SQL", "query.sql"),
    ("SQL", "original_query.sql"),
    ("EXPLAIN", "explain.txt"),
    ("Analyzer facts", "analysis_facts.md"),
    ("Diagnosis", "diagnosis.md"),
    ("Impala metadata", "impala_context.md"),
    ("Impala metadata JSON", "impala_context.json"),
    ("CM query details", "cm_query_details.json"),
    ("CM metadata", "cm_metadata.json"),
    ("Collection warnings", "collection_warnings.txt"),
)


def render_result(result: Any) -> list[str]:
    headings = extract_markdown_headings(result.report_text)
    artifacts = existing_artifacts(result.case_dir)
    has_facts = has_analyzer_facts_section(result.report_text)
    return [
        render_report_header(result),
        "<section class=\"report-shell\">",
        "<div class=\"content-main\">",
        "<details class=\"panel report-card\" open>",
        "<summary>Validated diagnosis markdown</summary>",
        "<div class=\"report-body\">",
        render_appendix_notice() if has_facts else "",
        render_report_markdown_html(result.report_text, with_heading_ids=True),
        "</div>",
        "</details>",
        "</div>",
        render_report_sidebar(result, headings=headings, artifacts=artifacts, has_facts=has_facts),
        "</section>",
    ]


def render_report_header(result: Any) -> str:
    overview_items = (
        ("validation", '<span class="badge green">PASS</span>'),
        ("mode", f'<span class="badge gray">{escape_report_value(result.report_mode)}</span>'),
        ("parsed operators", escape_report_value(result.parsed_operators)),
        ("cardinality anomalies", escape_report_value(result.cardinality_anomalies)),
        ("memory anomalies", escape_report_value(result.memory_anomalies)),
        ("case source", escape_report_value(result.case_source)),
    )
    overview = "".join(
        "<div class=\"case-overview-card\">"
        f"<span>{html.escape(label)}</span><strong>{value}</strong>"
        "</div>"
        for label, value in overview_items
    )
    retry_note = (
        "<div class=\"batch-note\">Report generation was retried after validator feedback; only the final validated report is rendered.</div>"
        if result.report_retry
        else ""
    )
    return (
        "<section class=\"panel report-header\" aria-label=\"Report header\">"
        "<div class=\"breadcrumb\"><a href=\"/query\">Specific Query</a><span>/</span><span>validated diagnosis</span></div>"
        "<div class=\"report-title-row\"><div>"
        "<h1>Specific Query diagnosis</h1>"
        "<div class=\"report-subtitle\">Validated report for one explicit Impala Query ID.</div>"
        "<div class=\"query-line\">"
        f"<span>Query ID:</span><code>{escape_report_value(result.query_id)}</code>"
        "<span>Report:</span><code>validated</code>"
        "</div></div></div>"
        "<div class=\"case-overview\" aria-label=\"Specific Query result overview\">"
        f"<div class=\"case-overview-grid\">{overview}</div>"
        "</div>"
        "<div class=\"status-strip\" aria-label=\"Report status\">"
        "<span class=\"status-item\"><span class=\"dot\"></span>Validation: <span class=\"badge green\">PASS</span></span>"
        "<span class=\"status-item\"><span class=\"dot\"></span>Validated before render</span>"
        "<span class=\"status-item\"><span class=\"dot gray\"></span>Raw SQL, profiles, metadata and local paths are hidden</span>"
        "<span class=\"status-item\"><span class=\"dot\"></span>Report ready</span>"
        "</div>"
        f"{retry_note}"
        "</section>"
    )


def render_appendix_notice() -> str:
    return (
        "<div class=\"appendix-notice\">"
        "<span><strong>Факты анализатора</strong> are marked as deterministic appendix when present. "
        "This section is not LLM-written narrative.</span>"
        "<span class=\"badge gray\">deterministic appendix</span>"
        "</div>"
    )


def render_report_sidebar(
    result: Any,
    *,
    headings: list[tuple[str, str]],
    artifacts: list[tuple[str, str]],
    has_facts: bool,
) -> str:
    return (
        "<aside class=\"side-panel\" aria-label=\"Report side panel\">"
        + render_toc_card(headings)
        + render_report_metadata_card(result, has_facts)
        + render_evidence_card(result.case_dir)
        + render_artifacts_card(artifacts)
        + render_pipeline_card(result, artifacts)
        + "</aside>"
    )


def render_toc_card(headings: list[tuple[str, str]]) -> str:
    if not headings:
        return ""
    links = "".join(f"<a href=\"#{anchor}\">{html.escape(text)}</a>" for text, anchor in headings)
    return f"<section class=\"panel side-card\"><h2>Sections</h2><nav class=\"toc-list\">{links}</nav></section>"


def render_report_metadata_card(result: Any, has_facts: bool) -> str:
    facts_state = "available" if has_facts else "not_observed"
    retry_row = (
        "<div class=\"meta-row\"><span>Report generation</span><strong>regenerated after validator retry</strong></div>"
        if result.report_retry
        else ""
    )
    return (
        "<section class=\"panel side-card\"><h2>Report metadata</h2><div class=\"meta-list\">"
        f"<div class=\"meta-row\"><span>Mode</span><strong>{escape_report_value(result.report_mode)}</strong></div>"
        "<div class=\"meta-row\"><span>Validation</span><strong>PASS</strong></div>"
        "<div class=\"meta-row\"><span>Report</span><strong>ready</strong></div>"
        f"<div class=\"meta-row\"><span>Analyzer facts</span><strong>{facts_state}</strong></div>"
        f"<div class=\"meta-row\"><span>Parsed operators</span><strong>{escape_report_value(result.parsed_operators)}</strong></div>"
        f"<div class=\"meta-row\"><span>Cardinality anomalies</span><strong>{escape_report_value(result.cardinality_anomalies)}</strong></div>"
        f"<div class=\"meta-row\"><span>Memory anomalies</span><strong>{escape_report_value(result.memory_anomalies)}</strong></div>"
        f"<div class=\"meta-row\"><span>Case source</span><strong>{escape_report_value(result.case_source)}</strong></div>"
        f"{retry_row}"
        "</div></section>"
    )


def render_evidence_card(case_dir: Path) -> str:
    states = [
        ("Profile", file_state(case_dir, ("profile_digest.md", "profile.txt", "profile.json"))),
        ("SQL", file_state(case_dir, ("sql.sql", "query.sql", "original_query.sql"))),
        ("EXPLAIN", file_state(case_dir, ("explain.txt",))),
        ("Metadata", file_state(case_dir, ("impala_context.md", "impala_context.json"))),
        ("Host metrics", "not collected"),
    ]
    rows = "".join(
        f"<div class=\"meta-row\"><span>{html.escape(label)}</span>{render_state_badge(state)}</div>"
        for label, state in states
    )
    return f"<section class=\"panel side-card\"><h2>Evidence completeness</h2><div class=\"meta-list\">{rows}</div></section>"


def render_artifacts_card(artifacts: list[tuple[str, str]]) -> str:
    if not artifacts:
        return (
            "<section class=\"panel side-card\"><h2>Evidence categories</h2>"
            "<p class=\"helper\">No recognized safe evidence categories are available.</p></section>"
        )
    items = "".join(
        "<div class=\"artifact-item\"><span>"
        f"{html.escape(label)}</span>"
        "<span class=\"badge green\">available</span></div>"
        for label, _filename in artifacts
    )
    return f"<section class=\"panel side-card\"><h2>Evidence categories</h2><div class=\"artifact-list\">{items}</div></section>"


def render_pipeline_card(result: Any, artifacts: list[tuple[str, str]]) -> str:
    profile_state = "available" if any(name.startswith("profile") for _, name in artifacts) else "not observed"
    facts_state = "available" if any(name == "analysis_facts.md" for _, name in artifacts) else "not observed"
    return (
        "<section class=\"panel side-card\"><h2>Pipeline</h2><div class=\"timeline\">"
        f"{render_timeline_item('Case source', result.case_source)}"
        f"{render_timeline_item('Profile evidence', profile_state)}"
        f"{render_timeline_item('Analyzer facts', facts_state)}"
        f"{render_timeline_item('Report validation', 'PASS')}"
        "</div></section>"
    )


def render_timeline_item(label: str, value: str) -> str:
    return (
        "<div class=\"timeline-item\"><span class=\"timeline-dot\"></span><div>"
        f"<strong>{html.escape(label)}</strong><span>{escape_report_value(value)}</span>"
        "</div></div>"
    )


def file_state(case_dir: Path, names: tuple[str, ...]) -> str:
    return "available" if any((case_dir / name).is_file() for name in names) else "not collected"


def render_state_badge(state: str) -> str:
    if state == "available":
        return "<span class=\"badge green\">available</span>"
    return f"<span class=\"badge gray\">{html.escape(state)}</span>"


def existing_artifacts(case_dir: Path) -> list[tuple[str, str]]:
    return [(label, filename) for label, filename in ARTIFACT_CANDIDATES if (case_dir / filename).is_file()]


def escape_report_value(value: Any) -> str:
    return html.escape(
        redact_browser_display_text(
            value,
            redact_field_names=True,
            redact_artifact_markers=True,
            redact_model_names=True,
        )
    )


def extract_markdown_headings(markdown_text: str) -> list[tuple[str, str]]:
    headings: list[tuple[str, str]] = []
    counter = 0
    in_fence = False
    fence = ""
    for line in markdown_text.splitlines():
        fence_match = re.match(r"^\s*(```|~~~)", line)
        if fence_match:
            marker = fence_match.group(1)
            if not in_fence:
                in_fence = True
                fence = marker
            elif line.strip().startswith(fence):
                in_fence = False
            continue
        if in_fence:
            continue
        heading_match = re.match(r"^(#{1,4})\s+(.+?)\s*$", line)
        if heading_match:
            counter += 1
            headings.append((strip_inline_markdown(heading_match.group(2)), f"section-{counter}"))
    return headings


def strip_inline_markdown(text: str) -> str:
    return re.sub(r"`([^`]+)`", r"\1", text).strip()


def has_analyzer_facts_section(markdown_text: str) -> bool:
    return bool(re.search(r"^##\s+Факты анализатора\s*$", markdown_text, re.MULTILINE))
