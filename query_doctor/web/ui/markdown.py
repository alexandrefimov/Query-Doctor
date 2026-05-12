"""Safe markdown subset rendering helpers for Query Doctor reports."""

from __future__ import annotations

import html
import re

from query_doctor.report.language_contract import EN_REPORT_CONTRACT, RU_REPORT_CONTRACT


def render_details_inline_report_html(report_text: str) -> str:
    sections = split_report_markdown_h2_sections(report_text)
    if not sections:
        return render_report_markdown_html(report_text, with_heading_ids=True)
    visible_titles = {
        heading.removeprefix("## ").strip()
        for heading in (
            EN_REPORT_CONTRACT.short_summary_heading,
            EN_REPORT_CONTRACT.recommendations_heading,
            RU_REPORT_CONTRACT.short_summary_heading,
            RU_REPORT_CONTRACT.recommendations_heading,
        )
    }
    visible_html: list[str] = []
    appendix_html: list[str] = []
    for title, section_text in sections:
        rendered = render_report_markdown_html(section_text, with_heading_ids=False)
        if title in visible_titles:
            visible_html.append(rendered)
        else:
            appendix_html.append(rendered)
    result = "\n".join(visible_html)
    if appendix_html:
        result += (
            '\n<details class="analysis-subdetails report-appendix" aria-label="LLM report details">'
            "<summary>Detailed report and follow-up checks</summary>"
            '<div class="report-body">' + "\n".join(appendix_html) + "</div></details>"
        )
    return result


def split_report_markdown_h2_sections(report_text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, list[str]]] = []
    current_title = ""
    current_lines: list[str] = []
    for line in report_text.splitlines():
        match = re.match(r"^##\s+(.+?)\s*$", line)
        if match:
            if current_title or current_lines:
                sections.append((current_title, current_lines))
            current_title = match.group(1).strip()
            current_lines = [line]
            continue
        current_lines.append(line)
    if current_title or current_lines:
        sections.append((current_title, current_lines))
    if not any(title for title, _lines in sections):
        return []
    return [
        (title, "\n".join(lines).strip()) for title, lines in sections if "\n".join(lines).strip()
    ]


def render_report_markdown_html(markdown_text: str, *, with_heading_ids: bool = False) -> str:
    lines = markdown_text.splitlines()
    blocks: list[str] = []
    paragraph: list[str] = []
    list_type: str | None = None
    list_items: list[str] = []
    index = 0
    heading_counter = 0

    def flush_paragraph() -> None:
        if paragraph:
            blocks.append(
                f"<p>{render_inline_markdown(' '.join(part.strip() for part in paragraph))}</p>"
            )
            paragraph.clear()

    def flush_list() -> None:
        nonlocal list_type
        if list_type is not None:
            tag = "ol" if list_type == "ol" else "ul"
            blocks.append(
                f"<{tag}>" + "".join(f"<li>{item}</li>" for item in list_items) + f"</{tag}>"
            )
            list_items.clear()
            list_type = None

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            flush_list()
            index += 1
            continue

        if stripped in {"<details>", "</details>"}:
            flush_paragraph()
            flush_list()
            blocks.append(stripped)
            index += 1
            continue

        summary_match = re.fullmatch(r"<summary>(.*?)</summary>", stripped)
        if summary_match:
            flush_paragraph()
            flush_list()
            blocks.append(f"<summary>{html.escape(summary_match.group(1))}</summary>")
            index += 1
            continue

        fence_match = re.match(r"^\s*(```|~~~)", line)
        if fence_match:
            flush_paragraph()
            flush_list()
            fence = fence_match.group(1)
            index += 1
            code_lines: list[str] = []
            while index < len(lines) and not lines[index].strip().startswith(fence):
                code_lines.append(lines[index])
                index += 1
            if index < len(lines):
                index += 1
            code_text = html.escape("\n".join(code_lines))
            blocks.append(f"<pre><code>{code_text}</code></pre>")
            continue

        if is_table_start(lines, index):
            flush_paragraph()
            flush_list()
            table_lines = [lines[index], lines[index + 1]]
            index += 2
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                table_lines.append(lines[index])
                index += 1
            blocks.append(render_markdown_table(table_lines))
            continue

        heading_match = re.match(r"^(#{1,4})\s+(.+?)\s*$", line)
        if heading_match:
            flush_paragraph()
            flush_list()
            level = len(heading_match.group(1))
            heading_counter += 1
            heading_id = f' id="section-{heading_counter}"' if with_heading_ids else ""
            blocks.append(
                f"<h{level}{heading_id}>{render_inline_markdown(heading_match.group(2))}</h{level}>"
            )
            index += 1
            continue

        quote_match = re.match(r"^\s*>\s?(.*)$", line)
        if quote_match:
            flush_paragraph()
            flush_list()
            quote_lines = [quote_match.group(1)]
            index += 1
            while index < len(lines):
                next_quote = re.match(r"^\s*>\s?(.*)$", lines[index])
                if not next_quote:
                    break
                quote_lines.append(next_quote.group(1))
                index += 1
            quote_text = "<br>".join(render_inline_markdown(part) for part in quote_lines)
            blocks.append(f"<blockquote>{quote_text}</blockquote>")
            continue

        unordered = re.match(r"^\s*[-*+]\s+(.+)$", line)
        ordered = re.match(r"^\s*\d+[.)]\s+(.+)$", line)
        if unordered or ordered:
            flush_paragraph()
            current_type = "ol" if ordered else "ul"
            if list_type != current_type:
                flush_list()
                list_type = current_type
            item_text = ordered.group(1) if ordered else unordered.group(1)
            list_items.append(render_inline_markdown(item_text))
            index += 1
            continue

        flush_list()
        paragraph.append(line)
        index += 1

    flush_paragraph()
    flush_list()
    return "\n".join(blocks)


def render_inline_markdown(text: str) -> str:
    parts = re.split(r"(`[^`]+`)", text)
    rendered: list[str] = []
    for part in parts:
        if len(part) >= 2 and part.startswith("`") and part.endswith("`"):
            rendered.append(f"<code>{html.escape(part[1:-1])}</code>")
        else:
            rendered.append(html.escape(part))
    return "".join(rendered)


def is_table_start(lines: list[str], index: int) -> bool:
    if index + 1 >= len(lines):
        return False
    return "|" in lines[index] and is_table_separator(lines[index + 1])


def is_table_separator(line: str) -> bool:
    cells = split_table_row(line)
    if not cells:
        return False
    return all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def split_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|") if cell.strip()]


def render_markdown_table(table_lines: list[str]) -> str:
    header = split_table_row(table_lines[0])
    rows = [split_table_row(line) for line in table_lines[2:]]
    header_html = "".join(f"<th>{render_inline_markdown(cell)}</th>" for cell in header)
    body_rows: list[str] = []
    for row in rows:
        cells = row[: len(header)] + [""] * max(0, len(header) - len(row))
        body_rows.append(
            "<tr>" + "".join(f"<td>{render_inline_markdown(cell)}</td>" for cell in cells) + "</tr>"
        )
    return (
        "<table><thead><tr>"
        + header_html
        + "</tr></thead><tbody>"
        + "".join(body_rows)
        + "</tbody></table>"
    )
