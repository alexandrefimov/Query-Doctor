"""Check local Markdown links used by public documentation."""

from __future__ import annotations

import html
import re
import sys
import unicodedata
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
DOC_GLOBS = (
    "*.md",
    "docs/**/*.md",
    "deploy/**/*.md",
    ".github/ISSUE_TEMPLATE/*.md",
)

REFERENCE_LINK_RE = re.compile(r"^\s*\[[^\]]+]:\s+(.+?)\s*$")
ATX_HEADING_RE = re.compile(r"^ {0,3}#{1,6}(?:[ \t]+|$)(.*)$")
SETEXT_HEADING_RE = re.compile(r"^ {0,3}(?:=+|-+)[ \t]*$")
REFERENCE_HEADING_LINK_RE = re.compile(r"!?\[([^\]]*)]\s*\[[^\]]*]")
HTML_TAG_RE = re.compile(r"</?[A-Za-z][^>]*>")
UNDERSCORE_EMPHASIS_RE = re.compile(r"(?<!\w)(_{1,3})(?=\S)(.+?)(?<=\S)\1(?!\w)")
FENCE_OPEN_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
FENCE_CLOSE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*$")
MARKDOWN_ESCAPE_RE = re.compile(r"\\([!\"#$%&'()*+,\-./:;<=>?@\[\\\]^_`{|}~])")


class _ExplicitAnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._record_id(tag, attrs)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._record_id(tag, attrs)

    def _record_id(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if value and (name == "id" or (tag == "a" and name == "name")):
                self.ids.add(value)


def markdown_files(root: Path = ROOT) -> list[Path]:
    files: set[Path] = set()
    for pattern in DOC_GLOBS:
        files.update(root.glob(pattern))
    return sorted(path for path in files if path.is_file())


def fence_opener(line: str) -> tuple[str, int] | None:
    match = FENCE_OPEN_RE.match(line)
    if not match:
        return None
    marker = match.group(1)
    if marker[0] == "`" and "`" in match.group(2):
        return None
    return marker[0], len(marker)


def is_fence_closer(line: str, marker: str, minimum_length: int) -> bool:
    match = FENCE_CLOSE_RE.match(line)
    return bool(match and match.group(1)[0] == marker and len(match.group(1)) >= minimum_length)


def _is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


def mask_inline_code_spans(text: str) -> str:
    """Mask complete CommonMark-style backtick spans while preserving offsets."""
    masked = list(text)
    cursor = 0
    while cursor < len(text):
        if text[cursor] != "`" or _is_escaped(text, cursor):
            cursor += 1
            continue

        opener_start = cursor
        while cursor < len(text) and text[cursor] == "`":
            cursor += 1
        opener_length = cursor - opener_start
        search = cursor
        closer_end: int | None = None
        while search < len(text):
            if text[search] != "`":
                search += 1
                continue
            closer_start = search
            while search < len(text) and text[search] == "`":
                search += 1
            if search - closer_start == opener_length:
                closer_end = search
                break
        if closer_end is None:
            continue
        for index in range(opener_start, closer_end):
            if masked[index] not in "\r\n":
                masked[index] = " "
        cursor = closer_end
    return "".join(masked)


def is_indented_code_line(line: str) -> bool:
    columns = 0
    for character in line:
        if character == " ":
            columns += 1
        elif character == "\t":
            columns += 4 - (columns % 4)
        else:
            break
        if columns >= 4:
            return True
    return False


def _find_label_end(masked: str, start: int) -> int | None:
    depth = 1
    cursor = start + 1
    while cursor < len(masked):
        if masked[cursor] == "\\" and cursor + 1 < len(masked):
            cursor += 2
            continue
        if masked[cursor] == "[":
            depth += 1
        elif masked[cursor] == "]":
            depth -= 1
            if depth == 0:
                return cursor
        cursor += 1
    return None


def _find_link_close(text: str, cursor: int) -> int | None:
    while cursor < len(text) and text[cursor] in " \t":
        cursor += 1
    if cursor >= len(text):
        return None
    if text[cursor] == ")":
        return cursor

    delimiter = text[cursor]
    if delimiter in {'"', "'"}:
        cursor += 1
        while cursor < len(text):
            if text[cursor] == "\\" and cursor + 1 < len(text):
                cursor += 2
                continue
            if text[cursor] == delimiter:
                cursor += 1
                break
            cursor += 1
        else:
            return None
    elif delimiter == "(":
        depth = 1
        cursor += 1
        while cursor < len(text) and depth:
            if text[cursor] == "\\" and cursor + 1 < len(text):
                cursor += 2
                continue
            if text[cursor] == "(":
                depth += 1
            elif text[cursor] == ")":
                depth -= 1
            cursor += 1
        if depth:
            return None
    else:
        return None

    while cursor < len(text) and text[cursor] in " \t":
        cursor += 1
    return cursor if cursor < len(text) and text[cursor] == ")" else None


def _parse_inline_destination(text: str, open_paren: int) -> tuple[str, int] | None:
    cursor = open_paren + 1
    while cursor < len(text) and text[cursor] in " \t":
        cursor += 1

    if cursor < len(text) and text[cursor] == "<":
        destination_start = cursor + 1
        cursor += 1
        while cursor < len(text):
            if text[cursor] == "\\" and cursor + 1 < len(text):
                cursor += 2
                continue
            if text[cursor] == ">":
                destination = text[destination_start:cursor]
                close = _find_link_close(text, cursor + 1)
                if close is None:
                    return None
                return destination, close
            cursor += 1
        return None

    destination_start = cursor
    depth = 0
    while cursor < len(text):
        character = text[cursor]
        if character == "\\" and cursor + 1 < len(text):
            cursor += 2
            continue
        if character == "(":
            depth += 1
        elif character == ")":
            if depth == 0:
                return text[destination_start:cursor], cursor
            depth -= 1
        elif character in " \t":
            destination = text[destination_start:cursor]
            close = _find_link_close(text, cursor)
            if close is None:
                return None
            return destination, close
        cursor += 1
    return None


def iter_inline_links(text: str):
    """Yield parsed inline link spans as (start, end, label, destination)."""
    masked = mask_inline_code_spans(text)
    cursor = 0
    while cursor < len(masked):
        if masked[cursor] != "[" or _is_escaped(masked, cursor):
            cursor += 1
            continue
        label_end = _find_label_end(masked, cursor)
        if label_end is None or label_end + 1 >= len(masked) or masked[label_end + 1] != "(":
            cursor += 1
            continue
        parsed = _parse_inline_destination(text, label_end + 1)
        if parsed is None:
            cursor += 1
            continue
        destination, close = parsed
        span_start = cursor
        if cursor > 0 and masked[cursor - 1] == "!" and not _is_escaped(masked, cursor - 1):
            span_start -= 1
        yield span_start, close + 1, text[cursor + 1 : label_end], destination
        cursor = close + 1


def _unescape_markdown_destination(target: str) -> str:
    return MARKDOWN_ESCAPE_RE.sub(r"\1", target)


def extract_target(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<"):
        end = target.find(">")
        if end != -1:
            return _unescape_markdown_destination(target[1:end])
    return _unescape_markdown_destination(target.split(maxsplit=1)[0])


def should_skip(target: str) -> bool:
    if not target:
        return True
    parsed = urlsplit(target)
    # Any URI with a scheme is not a repository-local filesystem target.
    return bool(parsed.scheme) or bool(parsed.netloc)


def resolve_target(source: Path, target: str, *, root: Path = ROOT) -> Path | None:
    if should_skip(target):
        return None

    parsed = urlsplit(target)
    path_text = unquote(parsed.path)
    if not path_text:
        return source.resolve() if parsed.fragment else None
    if path_text.startswith("/"):
        return (root / path_text.lstrip("/")).resolve()
    return (source.parent / path_text).resolve()


def iter_unfenced_lines(path: Path):
    active_fence: tuple[str, int] | None = None
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if active_fence is not None:
            if is_fence_closer(line, *active_fence):
                active_fence = None
            continue

        opener = fence_opener(line)
        if opener is not None:
            active_fence = opener
            continue
        yield lineno, line


def iter_link_source_lines(path: Path):
    """Yield link-bearing Markdown with code masked and line numbers preserved."""
    raw_lines = path.read_text(encoding="utf-8").splitlines()
    unfenced = dict(iter_unfenced_lines(path))
    visible_lines = [
        ""
        if lineno not in unfenced or is_indented_code_line(unfenced[lineno])
        else unfenced[lineno]
        for lineno in range(1, len(raw_lines) + 1)
    ]
    masked_lines = mask_inline_code_spans("\n".join(visible_lines)).split("\n")
    yield from enumerate(masked_lines, start=1)


def iter_targets(path: Path):
    for lineno, line in iter_link_source_lines(path):
        for _start, _end, _label, destination in iter_inline_links(line):
            yield lineno, _unescape_markdown_destination(destination)

        reference_match = REFERENCE_LINK_RE.match(line)
        if reference_match:
            yield lineno, extract_target(reference_match.group(1))


def github_heading_slug(heading: str) -> str:
    """Return the GitHub-style base anchor for one rendered heading."""
    visible = heading
    for start, end, label, _destination in reversed(list(iter_inline_links(heading))):
        visible = f"{visible[:start]}{label}{visible[end:]}"
    visible = REFERENCE_HEADING_LINK_RE.sub(r"\1", visible)
    visible = HTML_TAG_RE.sub("", visible)
    visible = UNDERSCORE_EMPHASIS_RE.sub(r"\2", visible)
    visible = html.unescape(visible).strip().lower()

    slug: list[str] = []
    for character in visible:
        if character == " ":
            slug.append("-")
            continue
        category = unicodedata.category(character)
        if character in {"-", "_"} or category[0] in {"L", "M", "N"}:
            slug.append(character)
    return "".join(slug)


def markdown_anchors(path: Path) -> set[str]:
    """Collect generated heading anchors and explicit HTML ids outside fences."""
    lines = list(iter_unfenced_lines(path))
    heading_anchors: set[str] = set()
    duplicate_counts: dict[str, int] = {}

    def add_heading(heading: str) -> None:
        base = github_heading_slug(heading)
        candidate = base
        while candidate in heading_anchors:
            duplicate_counts[base] = duplicate_counts.get(base, 0) + 1
            candidate = f"{base}-{duplicate_counts[base]}"
        heading_anchors.add(candidate)
        duplicate_counts.setdefault(base, 0)

    previous: tuple[int, str] | None = None
    for lineno, line in lines:
        heading_match = ATX_HEADING_RE.match(line)
        if heading_match:
            heading = re.sub(r"[ \t]+#+[ \t]*$", "", heading_match.group(1))
            add_heading(heading)
        elif (
            previous is not None
            and previous[0] + 1 == lineno
            and previous[1].strip()
            and not is_indented_code_line(previous[1])
            and not ATX_HEADING_RE.match(previous[1])
            and SETEXT_HEADING_RE.match(line)
        ):
            add_heading(previous[1].strip())
        previous = (lineno, line)

    anchor_parser = _ExplicitAnchorParser()
    html_lines = []
    for _lineno, line in lines:
        html_lines.append("" if is_indented_code_line(line) else line)
    anchor_parser.feed(mask_inline_code_spans("\n".join(html_lines)))
    anchor_parser.close()
    return heading_anchors | anchor_parser.ids


def check_markdown_links(root: Path = ROOT) -> list[str]:
    root = root.resolve()
    failures: list[str] = []
    anchors_by_path: dict[Path, set[str]] = {}
    for markdown_path in markdown_files(root):
        for lineno, target in iter_targets(markdown_path):
            resolved = resolve_target(markdown_path, target, root=root)
            if resolved is not None:
                try:
                    resolved.relative_to(root)
                except ValueError:
                    rel_source = markdown_path.relative_to(root)
                    failures.append(
                        f"{rel_source}:{lineno}: local link target resolves outside "
                        f"repository: {target}"
                    )
                    continue
            if resolved is not None and not resolved.exists():
                rel_source = markdown_path.relative_to(root)
                failures.append(f"{rel_source}:{lineno}: missing local link target: {target}")
                continue

            parsed = urlsplit(target)
            if (
                resolved is None
                or not parsed.fragment
                or resolved.suffix.lower() != ".md"
                or not resolved.is_file()
            ):
                continue

            anchors = anchors_by_path.get(resolved)
            if anchors is None:
                anchors = markdown_anchors(resolved)
                anchors_by_path[resolved] = anchors
            fragment = unquote(parsed.fragment)
            if fragment not in anchors:
                rel_source = markdown_path.relative_to(root)
                failures.append(
                    f"{rel_source}:{lineno}: missing local Markdown anchor "
                    f"'#{fragment}' in target: {target}"
                )

    return failures


def main() -> int:
    failures = check_markdown_links()

    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
