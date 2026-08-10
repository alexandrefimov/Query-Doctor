#!/usr/bin/env python3
"""Fail when private platform runtime artifacts enter the public repository."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Sequence


ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_EXACT_PATHS = {
    ".gitlab-ci.yml",
}
EMPTY_MARKER_FINGERPRINTS: frozenset[tuple[int, str]] = frozenset()
MARKER_FINGERPRINT_SCHEMA = "query-doctor-private-marker-fingerprints-v1"
BINARY_SUFFIXES = frozenset(
    {
        ".gif",
        ".gz",
        ".ico",
        ".jpeg",
        ".jpg",
        ".otf",
        ".pdf",
        ".png",
        ".pyc",
        ".tgz",
        ".ttf",
        ".webp",
        ".whl",
        ".woff",
        ".woff2",
        ".zip",
    }
)
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class BoundaryFinding:
    path: str
    detail: str


GitRunner = Callable[[Path, Sequence[str]], subprocess.CompletedProcess[str]]
GitBytesRunner = Callable[[Path, Sequence[str]], subprocess.CompletedProcess[bytes]]


def _run_git(repo_dir: Path, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_dir,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _run_git_bytes(repo_dir: Path, args: Sequence[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def candidate_paths(repo_dir: Path) -> tuple[str, ...]:
    result = _run_git(repo_dir, ["ls-files", "-co", "--exclude-standard", "-z"])
    if result.returncode == 0:
        return tuple(path for path in result.stdout.split("\0") if path)

    ignored_parts = {".git", ".venv", "__pycache__", "build", "dist"}
    return tuple(
        path.relative_to(repo_dir).as_posix()
        for path in repo_dir.rglob("*")
        if path.is_file() and not ignored_parts.intersection(path.relative_to(repo_dir).parts)
    )


def is_distribution_text(path: str) -> bool:
    normalized = path.replace("\\", "/")
    candidate = PurePosixPath(normalized)
    return candidate.suffix.casefold() not in BINARY_SUFFIXES


def marker_fingerprint(value: str, *, case_sensitive: bool = False) -> tuple[int, str]:
    candidate = value if case_sensitive else value.casefold()
    normalized = "".join(_TOKEN_RE.findall(candidate))
    return len(normalized), hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _parse_marker_fingerprint_entries(value: object, *, field: str) -> frozenset[tuple[int, str]]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")

    fingerprints: set[tuple[int, str]] = set()
    for index, entry in enumerate(value):
        if not isinstance(entry, dict) or set(entry) != {"length", "sha256"}:
            raise ValueError(f"{field}[{index}] must contain only length and sha256")
        length = entry["length"]
        digest = entry["sha256"]
        if isinstance(length, bool) or not isinstance(length, int) or not 1 <= length <= 4096:
            raise ValueError(f"{field}[{index}].length must be an integer between 1 and 4096")
        if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
            raise ValueError(f"{field}[{index}].sha256 must be a lowercase SHA-256 digest")
        fingerprints.add((length, digest))
    return frozenset(fingerprints)


def load_marker_fingerprint_file(
    path: Path,
    *,
    repo_dir: Path,
) -> tuple[frozenset[tuple[int, str]], frozenset[tuple[int, str]]]:
    resolved_repo = repo_dir.resolve()
    resolved_path = path.expanduser().resolve()
    try:
        resolved_path.relative_to(resolved_repo)
    except ValueError:
        pass
    else:
        raise ValueError("private marker fingerprint file must stay outside the repository")

    try:
        payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("could not read private marker fingerprint file") from exc
    if not isinstance(payload, dict) or set(payload) != {
        "schema",
        "casefold",
        "caseSensitive",
    }:
        raise ValueError("private marker fingerprint file has an invalid object shape")
    if payload["schema"] != MARKER_FINGERPRINT_SCHEMA:
        raise ValueError("private marker fingerprint file has an unsupported schema")

    casefold = _parse_marker_fingerprint_entries(payload["casefold"], field="casefold")
    case_sensitive = _parse_marker_fingerprint_entries(
        payload["caseSensitive"],
        field="caseSensitive",
    )
    if not casefold and not case_sensitive:
        raise ValueError("private marker fingerprint file must contain at least one marker")
    return casefold, case_sensitive


def _matching_marker_ids(
    value: str,
    *,
    marker_fingerprints: frozenset[tuple[int, str]],
    case_sensitive: bool,
) -> set[str]:
    candidate_value = value if case_sensitive else value.casefold()
    normalized = "".join(_TOKEN_RE.findall(candidate_value))

    matches = {digest for _length, digest in marker_fingerprints if digest in value.casefold()}
    for length in {length for length, _digest in marker_fingerprints}:
        if len(normalized) < length:
            continue
        for index in range(len(normalized) - length + 1):
            digest = hashlib.sha256(normalized[index : index + length].encode("utf-8")).hexdigest()
            if (length, digest) in marker_fingerprints:
                matches.add(digest)
    return matches


def matching_marker_ids(
    value: str,
    *,
    marker_fingerprints: frozenset[tuple[int, str]] = EMPTY_MARKER_FINGERPRINTS,
    case_sensitive_marker_fingerprints: frozenset[tuple[int, str]] = EMPTY_MARKER_FINGERPRINTS,
) -> tuple[str, ...]:
    matches = _matching_marker_ids(
        value,
        marker_fingerprints=marker_fingerprints,
        case_sensitive=False,
    )
    matches.update(
        _matching_marker_ids(
            value,
            marker_fingerprints=case_sensitive_marker_fingerprints,
            case_sensitive=True,
        )
    )
    return tuple(sorted(matches))


def scan_path(
    path: str,
    *,
    marker_fingerprints: frozenset[tuple[int, str]] = EMPTY_MARKER_FINGERPRINTS,
    case_sensitive_marker_fingerprints: frozenset[tuple[int, str]] = EMPTY_MARKER_FINGERPRINTS,
) -> tuple[BoundaryFinding, ...]:
    normalized = path.replace("\\", "/")
    if normalized in FORBIDDEN_EXACT_PATHS:
        return (BoundaryFinding(normalized, "private runtime path is not public"),)
    if matching_marker_ids(
        normalized,
        marker_fingerprints=marker_fingerprints,
        case_sensitive_marker_fingerprints=case_sensitive_marker_fingerprints,
    ):
        return (BoundaryFinding(normalized, "private platform path marker"),)
    return ()


def scan_text(
    text: str,
    *,
    path: str,
    marker_fingerprints: frozenset[tuple[int, str]] = EMPTY_MARKER_FINGERPRINTS,
    case_sensitive_marker_fingerprints: frozenset[tuple[int, str]] = EMPTY_MARKER_FINGERPRINTS,
) -> tuple[BoundaryFinding, ...]:
    if not is_distribution_text(path):
        return ()

    if matching_marker_ids(
        text,
        marker_fingerprints=marker_fingerprints,
        case_sensitive_marker_fingerprints=case_sensitive_marker_fingerprints,
    ):
        return (BoundaryFinding(path, "private platform marker"),)
    return ()


def scan_repository(
    repo_dir: Path,
    *,
    marker_fingerprints: frozenset[tuple[int, str]] = EMPTY_MARKER_FINGERPRINTS,
    case_sensitive_marker_fingerprints: frozenset[tuple[int, str]] = EMPTY_MARKER_FINGERPRINTS,
) -> list[BoundaryFinding]:
    findings: list[BoundaryFinding] = []
    for path in candidate_paths(repo_dir):
        findings.extend(
            scan_path(
                path,
                marker_fingerprints=marker_fingerprints,
                case_sensitive_marker_fingerprints=case_sensitive_marker_fingerprints,
            )
        )
        if not is_distribution_text(path):
            continue
        try:
            text = (repo_dir / path).read_text(encoding="utf-8")
        except FileNotFoundError:
            continue
        except UnicodeDecodeError:
            findings.append(BoundaryFinding(path, "distribution text is not valid UTF-8"))
            continue
        except OSError:
            findings.append(BoundaryFinding(path, "could not read distribution text"))
            continue
        findings.extend(
            scan_text(
                text,
                path=path,
                marker_fingerprints=marker_fingerprints,
                case_sensitive_marker_fingerprints=case_sensitive_marker_fingerprints,
            )
        )
    return findings


def scan_history_range(
    repo_dir: Path,
    *,
    base_ref: str,
    head_ref: str,
    marker_fingerprints: frozenset[tuple[int, str]] = EMPTY_MARKER_FINGERPRINTS,
    case_sensitive_marker_fingerprints: frozenset[tuple[int, str]] = EMPTY_MARKER_FINGERPRINTS,
    runner: GitRunner = _run_git,
    bytes_runner: GitBytesRunner = _run_git_bytes,
) -> list[BoundaryFinding]:
    revision_range = f"{base_ref}..{head_ref}"
    revisions_result = runner(repo_dir, ["rev-list", "--reverse", revision_range])
    if revisions_result.returncode != 0:
        return [
            BoundaryFinding(
                "(git history)",
                f"could not scan public revision range {revision_range!r}",
            )
        ]

    findings: list[BoundaryFinding] = []
    for revision in revisions_result.stdout.splitlines():
        revision = revision.strip()
        if not revision:
            continue
        history_path = f"(git history {revision[:12]})"
        metadata_result = bytes_runner(
            repo_dir,
            ["show", "--no-patch", "--format=fuller", revision],
        )
        if metadata_result.returncode != 0:
            findings.append(
                BoundaryFinding(history_path, "could not inspect public commit metadata")
            )
            continue
        try:
            metadata = metadata_result.stdout.decode("utf-8")
        except UnicodeDecodeError:
            findings.append(BoundaryFinding(history_path, "commit metadata is not valid UTF-8"))
            continue

        changed_result = bytes_runner(
            repo_dir,
            [
                "diff-tree",
                "--root",
                "-m",
                "--no-commit-id",
                "--name-only",
                "-r",
                "-z",
                revision,
            ],
        )
        tree_result = bytes_runner(repo_dir, ["ls-tree", "-r", "-z", revision])
        if changed_result.returncode != 0 or tree_result.returncode != 0:
            findings.append(BoundaryFinding(history_path, "could not inspect public commit tree"))
            continue

        try:
            changed_paths = {
                value.decode("utf-8") for value in changed_result.stdout.split(b"\0") if value
            }
            tree_blob_paths = {
                raw_path.decode("utf-8")
                for entry in tree_result.stdout.split(b"\0")
                if entry
                for metadata_fields, separator, raw_path in (entry.partition(b"\t"),)
                if separator and metadata_fields.split()[1:2] == [b"blob"]
            }
        except UnicodeDecodeError:
            findings.append(BoundaryFinding(history_path, "public commit path is not valid UTF-8"))
            continue

        marker_detected = bool(
            matching_marker_ids(
                metadata,
                marker_fingerprints=marker_fingerprints,
                case_sensitive_marker_fingerprints=case_sensitive_marker_fingerprints,
            )
        )
        for path in sorted(changed_paths & tree_blob_paths):
            if path in FORBIDDEN_EXACT_PATHS:
                findings.append(BoundaryFinding(history_path, "private runtime path is not public"))
            marker_detected = marker_detected or bool(
                matching_marker_ids(
                    path,
                    marker_fingerprints=marker_fingerprints,
                    case_sensitive_marker_fingerprints=case_sensitive_marker_fingerprints,
                )
            )
            if not is_distribution_text(path):
                continue

            blob_result = bytes_runner(repo_dir, ["cat-file", "blob", f"{revision}:{path}"])
            if blob_result.returncode != 0:
                findings.append(
                    BoundaryFinding(history_path, "could not inspect public distribution blob")
                )
                continue
            try:
                blob_text = blob_result.stdout.decode("utf-8")
            except UnicodeDecodeError:
                findings.append(
                    BoundaryFinding(history_path, "distribution blob is not valid UTF-8")
                )
                continue
            marker_detected = marker_detected or bool(
                matching_marker_ids(
                    blob_text,
                    marker_fingerprints=marker_fingerprints,
                    case_sensitive_marker_fingerprints=case_sensitive_marker_fingerprints,
                )
            )

        if marker_detected:
            findings.append(BoundaryFinding(history_path, "private platform marker"))
    return findings


def render_findings(findings: list[BoundaryFinding]) -> str:
    if not findings:
        return "Public distribution boundary audit: OK"
    lines = ["Public distribution boundary audit: FAILED"]
    lines.extend(f"- BLOCKER: {finding.path}: {finding.detail}" for finding in findings)
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        type=Path,
        default=ROOT,
        help="Repository root. Defaults to the repository containing this script.",
    )
    parser.add_argument(
        "--history-base",
        help="Also inspect every commit after this public base ref.",
    )
    parser.add_argument(
        "--history-head",
        default="HEAD",
        help="History range head. Defaults to HEAD.",
    )
    parser.add_argument(
        "--marker-fingerprints-file",
        type=Path,
        help=(
            "Optional private fingerprint configuration outside the repository. "
            "Official public-release gates must supply it."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_dir = args.repo.resolve()
    marker_fingerprints = EMPTY_MARKER_FINGERPRINTS
    case_sensitive_marker_fingerprints = EMPTY_MARKER_FINGERPRINTS
    if args.marker_fingerprints_file is not None:
        try:
            marker_fingerprints, case_sensitive_marker_fingerprints = load_marker_fingerprint_file(
                args.marker_fingerprints_file,
                repo_dir=repo_dir,
            )
        except ValueError as exc:
            print(render_findings([BoundaryFinding("(private marker configuration)", str(exc))]))
            return 1

    findings = scan_repository(
        repo_dir,
        marker_fingerprints=marker_fingerprints,
        case_sensitive_marker_fingerprints=case_sensitive_marker_fingerprints,
    )
    if args.history_base:
        findings.extend(
            scan_history_range(
                repo_dir,
                base_ref=args.history_base,
                head_ref=args.history_head,
                marker_fingerprints=marker_fingerprints,
                case_sensitive_marker_fingerprints=case_sensitive_marker_fingerprints,
            )
        )
    print(render_findings(findings))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
