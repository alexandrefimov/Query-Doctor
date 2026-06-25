#!/usr/bin/env python3
"""Check active docs for stale guidance that slows agents down."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]

ACTIVE_DOCS = (
    "README.md",
    "AGENTS.md",
    "docs/README.md",
    "docs/agent-quickstart.md",
    "docs/codex-handoff.md",
    "docs/public-documentation-boundary.md",
    "docs/code-audit.md",
    "docs/code-map.md",
    "docs/agent-playbook.md",
    "docs/test-matrix.md",
    "docs/validation-log.md",
    "docs/safety-contract.md",
    "docs/owner-raw-d3-deployment.md",
    "docs/engine-redaction-note-v1.md",
    "docs/brand-voice.md",
    "docs/architecture.md",
    "docs/upstream-impala-ai-analyzer.md",
    "docs/impala-profile-counter-caveats.md",
    "docs/engine-expansion-plan.md",
    "docs/engine-support-gap-matrix.md",
    "docs/trino-beta-ui-readiness.md",
    "docs/trino-shared-deployment-hardening.md",
    "docs/query-optimizer-contract.md",
    "docs/roadmap.md",
    "docs/customer-readiness-priorities.md",
    "docs/repository-simplification-audit.md",
    "docs/development-practices.md",
    "docs/analyzer-audit.md",
    "docs/changelog.md",
)

IGNORED_SCHEMES = {"http", "https", "mailto", "tel", "app"}
INLINE_LINK_RE = re.compile(r"!?\[[^\]]*]\(([^)\n]+)\)")
REFERENCE_LINK_RE = re.compile(r"^\s*\[[^\]]+]:\s+(.+?)\s*$")
REVIEWED_RE = re.compile(r"^Last (?:reviewed|updated):\s+(\d{4}-\d{2}-\d{2})\s*$", re.IGNORECASE)
STATUS_ROW_RE = re.compile(
    r"^\|\s*\[[^\]]+]\(([^)]+)\)\s*\|\s*(active|reference|archived)\s*\|", re.IGNORECASE
)
MAX_ACTIVE_DOC_AGE_DAYS = 90


@dataclass(frozen=True)
class StalePattern:
    pattern: re.Pattern[str]
    message: str


STALE_PATTERNS = (
    StalePattern(re.compile(r"Russian Help page", re.IGNORECASE), "old Help language guidance"),
    StalePattern(re.compile(r"\bquery_doctor(?:_v2)?\.py\b"), "removed root prototype command"),
    StalePattern(re.compile(r"\bcm_impala_case\.py\b"), "removed root prototype command"),
    StalePattern(
        re.compile(r"python3?\s+query_doctor(?:_v2)?\.py\b"), "removed root command invocation"
    ),
    StalePattern(re.compile(r"<<<<<<<|=======|>>>>>>>"), "merge conflict marker"),
    StalePattern(
        re.compile(r"\bTODO\b|\bTBD\b|outdated|obsolete", re.IGNORECASE),
        "stale marker in active docs",
    ),
)


def active_doc_paths(root: Path = ROOT) -> list[Path]:
    return [root / rel for rel in ACTIVE_DOCS]


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


def resolve_target(source: Path, target: str, root: Path = ROOT) -> Path | None:
    if should_skip(target):
        return None
    parsed = urlsplit(target)
    path_text = unquote(parsed.path)
    if not path_text:
        return None
    if path_text.startswith("/"):
        return root / path_text.lstrip("/")
    return (source.parent / path_text).resolve()


def iter_doc_lines(path: Path):
    in_fence = False
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if is_fence(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            yield lineno, line


def reviewed_date(path: Path) -> date | None:
    for line in path.read_text(encoding="utf-8").splitlines()[:8]:
        match = REVIEWED_RE.match(line)
        if match:
            return date.fromisoformat(match.group(1))
    return None


def status_index_docs(root: Path = ROOT) -> dict[str, str]:
    index = root / "docs" / "README.md"
    if not index.is_file():
        return {}
    docs: dict[str, str] = {}
    for _, line in iter_doc_lines(index):
        match = STATUS_ROW_RE.match(line)
        if not match:
            continue
        status = match.group(2).lower()
        target = extract_target(match.group(1))
        resolved = resolve_target(index, target, root)
        if resolved is not None:
            docs[str(resolved.relative_to(root))] = status
    return docs


def status_index_active_docs(root: Path = ROOT) -> set[str]:
    return {rel for rel, status in status_index_docs(root).items() if status == "active"}


def current_doc_paths(root: Path = ROOT) -> set[str]:
    docs_root = root / "docs"
    if not docs_root.is_dir():
        return set()
    current: set[str] = set()
    for path in docs_root.glob("**/*.md"):
        rel = path.relative_to(root)
        parts = rel.parts
        if len(parts) > 1 and parts[1] in {"archive", "i18n"}:
            continue
        current.add(str(rel))
    return current


def localized_source_path(localized: Path, root: Path = ROOT) -> Path:
    rel = localized.relative_to(root)
    parts = rel.parts
    marker = ("i18n", "ru")
    for index in range(len(parts) - 1):
        if tuple(parts[index : index + 2]) == marker:
            base_parts = parts[:index]
            return root.joinpath(*base_parts, parts[-1])
    return root / rel.name


def find_i18n_failures(root: Path = ROOT) -> list[str]:
    failures: list[str] = []
    for localized in sorted((root / "docs").glob("**/i18n/ru/*.md")):
        source = localized_source_path(localized, root)
        if not source.is_file():
            failures.append(
                f"{localized.relative_to(root)}: English source is missing: {source.relative_to(root)}"
            )
    return failures


def find_failures(paths: list[Path], root: Path = ROOT) -> list[str]:
    failures: list[str] = []
    today = date.today()
    active_rels = {str(Path(rel)) for rel in ACTIVE_DOCS}
    status_rels = status_index_docs(root)
    status_active_rels = status_index_active_docs(root)
    if status_active_rels and status_active_rels != active_rels:
        missing_from_index = sorted(active_rels - status_active_rels)
        missing_from_config = sorted(status_active_rels - active_rels)
        if missing_from_index:
            failures.append(
                "docs/README.md: active docs missing from status index: "
                f"{', '.join(missing_from_index)}"
            )
        if missing_from_config:
            failures.append(
                "scripts/check_active_docs.py: ACTIVE_DOCS missing status-index active docs: "
                f"{', '.join(missing_from_config)}"
            )
    if status_rels:
        missing_from_index = sorted(current_doc_paths(root) - set(status_rels))
        if missing_from_index:
            failures.append(
                "docs/README.md: current docs missing from status index: "
                f"{', '.join(missing_from_index)}"
            )
    for path in paths:
        rel_path = path.relative_to(root)
        if not path.is_file():
            failures.append(f"{rel_path}: active doc is missing")
            continue
        if str(rel_path) in active_rels:
            last_reviewed = reviewed_date(path)
            if last_reviewed is None:
                failures.append(f"{rel_path}: active doc missing Last reviewed/Last updated header")
            elif (today - last_reviewed).days > MAX_ACTIVE_DOC_AGE_DAYS:
                failures.append(
                    f"{rel_path}: active doc review is older than {MAX_ACTIVE_DOC_AGE_DAYS} days"
                )
        for lineno, line in iter_doc_lines(path):
            for stale in STALE_PATTERNS:
                if stale.pattern.search(line):
                    failures.append(f"{rel_path}:{lineno}: {stale.message}")

            for match in INLINE_LINK_RE.finditer(line):
                target = extract_target(match.group(1))
                resolved = resolve_target(path, target, root)
                if resolved is not None and not resolved.exists():
                    failures.append(f"{rel_path}:{lineno}: missing local link target: {target}")

            reference_match = REFERENCE_LINK_RE.match(line)
            if reference_match:
                target = extract_target(reference_match.group(1))
                resolved = resolve_target(path, target, root)
                if resolved is not None and not resolved.exists():
                    failures.append(f"{rel_path}:{lineno}: missing local link target: {target}")
    if paths == active_doc_paths(root):
        failures.extend(find_i18n_failures(root))
    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        type=Path,
        default=ROOT,
        help="Repository root. Defaults to the repository containing this script.",
    )
    parser.add_argument(
        "--paths",
        nargs="*",
        help="Specific markdown files to check. Defaults to active docs.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.repo.resolve()
    paths = [root / path for path in args.paths] if args.paths else active_doc_paths(root)
    failures = find_failures(paths, root)
    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    print(f"Checked {len(paths)} docs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
