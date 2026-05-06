"""Markdown section helpers used by report sanitization and validation."""

from __future__ import annotations


def extract_markdown_section(text: str, heading: str) -> list[str]:
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == heading)
    except StopIteration:
        return []

    section_lines: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        section_lines.append(line)
    return section_lines


def extract_markdown_subsection(lines: list[str], heading: str) -> list[str]:
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == heading)
    except StopIteration:
        return []

    subsection_lines: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("### "):
            break
        subsection_lines.append(line)
    return subsection_lines


def strip_markdown_section(text: str, heading: str) -> str:
    lines = text.splitlines()
    stripped_lines: list[str] = []
    skipping = False
    for line in lines:
        if line.strip() == heading:
            skipping = True
            continue
        if skipping and line.startswith("## "):
            skipping = False
        if not skipping:
            stripped_lines.append(line)
    return "\n".join(stripped_lines).strip() + "\n"
