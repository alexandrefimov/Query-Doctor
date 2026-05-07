"""Check local Markdown links used by public documentation."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
DOC_GLOBS = (
    "*.md",
    "docs/**/*.md",
    ".github/ISSUE_TEMPLATE/*.md",
)

INLINE_LINK_RE = re.compile(r"!?\[[^\]]*]\(([^)\n]+)\)")
REFERENCE_LINK_RE = re.compile(r"^\s*\[[^\]]+]:\s+(.+?)\s*$")
IGNORED_SCHEMES = {"http", "https", "mailto", "tel", "app"}


def markdown_files() -> list[Path]:
    files: set[Path] = set()
    for pattern in DOC_GLOBS:
        files.update(ROOT.glob(pattern))
    return sorted(path for path in files if path.is_file())


def is_fence(line: str) -> bool:
    stripped = line.lstrip()
    return stripped.startswith("```") or stripped.startswith("~~~")


def extract_target(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<"):
        end = target.find(">")
        if end != -1:
            return target[1:end]
    return target.split(maxsplit=1)[0]


def should_skip(target: str) -> bool:
    if not target or target.startswith("#"):
        return True
    parsed = urlsplit(target)
    return parsed.scheme.lower() in IGNORED_SCHEMES


def resolve_target(source: Path, target: str) -> Path | None:
    if should_skip(target):
        return None

    parsed = urlsplit(target)
    path_text = unquote(parsed.path)
    if not path_text:
        return None
    if path_text.startswith("/"):
        return ROOT / path_text.lstrip("/")
    return (source.parent / path_text).resolve()


def iter_targets(path: Path):
    in_fence = False
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if is_fence(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        for match in INLINE_LINK_RE.finditer(line):
            yield lineno, extract_target(match.group(1))

        reference_match = REFERENCE_LINK_RE.match(line)
        if reference_match:
            yield lineno, extract_target(reference_match.group(1))


def main() -> int:
    failures: list[str] = []
    for markdown_path in markdown_files():
        for lineno, target in iter_targets(markdown_path):
            resolved = resolve_target(markdown_path, target)
            if resolved is not None and not resolved.exists():
                rel_source = markdown_path.relative_to(ROOT)
                failures.append(f"{rel_source}:{lineno}: missing local link target: {target}")

    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
