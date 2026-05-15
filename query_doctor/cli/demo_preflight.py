#!/usr/bin/env python3
"""Deterministic local preflight for Query Doctor demo/release readiness."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from typing import Callable


REPO_DIR = Path(__file__).resolve().parents[2]

READY = "READY"
READY_WITH_WARNINGS = "READY_WITH_WARNINGS"
NOT_READY = "NOT_READY"

TEXT_SUFFIXES = {".css", ".html", ".json", ".md", ".py", ".txt"}
PUBLIC_RELEASE_TEXT_SUFFIXES = TEXT_SUFFIXES | {".cfg", ".ini", ".sh", ".toml", ".yaml", ".yml"}
RESERVED_EXAMPLE_DOMAINS = ("example.com", "example.net", "example.org")
GIT_GREP_CHUNK_SIZE = 40

BROWSER_UI_PREFIXES = (
    "query_doctor/web/ui/",
    "query_doctor/web/presenters/",
)
BROWSER_UI_FILES: tuple[str, ...] = ()

REPORT_VALIDATION_PATHS = (
    "query_doctor/cli/report.py",
    "query_doctor/report/",
    "tests/test_report_sanitizer.py",
)
OPTIMIZER_VALIDATION_PREFIXES = (
    "query_doctor/optimizer/",
    "query_doctor/web/optimizer",
)
OPTIMIZER_VALIDATION_FILES = ("query_doctor/cli/optimize_query.py",)
METADATA_COLLECTOR_PREFIXES = (
    "query_doctor/impala/",
    "query_doctor/cm/",
)
METADATA_COLLECTOR_FILES = (
    "query_doctor/cli/collect_cm_profiles.py",
    "query_doctor/cli/collect_impala_context.py",
)
CONFIG_PATHS = (
    "query_doctor/config/",
    "query-doctor-config.example.json",
)

RAW_ARTIFACT_TOKENS = (
    "profile_digest.md",
    "query_metadata.json",
    "cm_metadata.json",
    "collection_warnings.txt",
    "analysis_facts.md",
    "diagnosis.md",
    "diagnosis.partial.md",
    "optimized_query.sql",
    "optimized_query.validated.json",
    "optimized_query.partial.txt",
    "optimized_query_recommendations.md",
    "impala_context.md",
    "impala_context.json",
    "original_query.sql",
    "referenced_tables.txt",
    "explain.txt",
)

UNSAFE_PATTERNS = (
    (
        "local path",
        re.compile(
            r"(?<![\w/])(?:/private)?/tmp/[^\s<>'\"]+|(?<![\w/])/Users/[^\s<>'\"]+|(?<![\w/])/var/folders/[^\s<>'\"]+|(?<![\w/])[A-Za-z]:\\[^\s<>'\"]+"
        ),
    ),
    ("raw profile marker", re.compile(r"\bBEGIN PROFILE\b|\bQuery Timeline\b", re.IGNORECASE)),
    (
        "raw subprocess output",
        re.compile(r"\braw\s+(?:stdout|stderr)\b|\bsubprocess\s+output\b", re.IGNORECASE),
    ),
    ("model/runtime internals", re.compile(r"\bqwen[\w:.-]*\b|\bollama\b", re.IGNORECASE)),
    (
        "secret-like token",
        re.compile(
            r"\b(?:CM_PASSWORD|CM_TOKEN|Authorization:\s*Bearer|api[_-]?key|password\s*=|token\s*=)\b",
            re.IGNORECASE,
        ),
    ),
)
PUBLIC_RELEASE_PATTERNS = (
    (
        "private local user path",
        re.compile(
            r"(?<![\w/])(?:/Users|/home)/(?!demo\b|example\b|runner\b)[A-Za-z0-9._-]+(?:/[^\s<>'\"]*)?"
        ),
    ),
    (
        "private-looking hostname/domain",
        re.compile(
            r"\b(?:[A-Za-z0-9-]+\.)+(?:corp|internal|lan|local|private|prod|pw)\b", re.IGNORECASE
        ),
    ),
    (
        "production-looking hostname/domain",
        re.compile(
            r"\b(?:[A-Za-z0-9-]+\.)*[A-Za-z0-9-]*prod[A-Za-z0-9-]*(?:\.[A-Za-z0-9-]+)+\b",
            re.IGNORECASE,
        ),
    ),
    (
        "embedded URL credentials",
        re.compile(r"https?://[^/\s:@]+:[^@\s/]+@[^/\s<>'\"]+", re.IGNORECASE),
    ),
    ("private key material", re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----")),
    (
        "high-confidence cloud token",
        re.compile(
            r"\b(?:AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9_]{30,}|github_pat_[A-Za-z0-9_]{40,}|sk-[A-Za-z0-9]{20,})\b"
        ),
    ),
    (
        "authorization token",
        re.compile(
            r"\bAuthorization:\s*Bearer\s+(?!<redacted>|[.]{3}|secret-token\b)[A-Za-z0-9._=-]{12,}",
            re.IGNORECASE,
        ),
    ),
)
PUBLIC_RELEASE_GREP_PATTERNS = (
    r"/Users/[A-Za-z0-9._-]+",
    r"/home/[A-Za-z0-9._-]+",
    r"([A-Za-z0-9-]+\.)+(corp|internal|lan|local|private|prod|pw)",
    r"([A-Za-z0-9-]+\.)*[A-Za-z0-9-]*prod[A-Za-z0-9-]*(\.[A-Za-z0-9-]+)+",
    r"https?://[^/[:space:]@]+:[^@[:space:]/]+@[^/[:space:]]+",
    r"-----BEGIN (RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----",
    r"(AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9_]{30,}|github_pat_[A-Za-z0-9_]{40,}|sk-[A-Za-z0-9]{20,})",
    r"Authorization:[[:space:]]*Bearer[[:space:]]+[A-Za-z0-9._=-]{12,}",
)
SQL_LIKE_PATTERN = re.compile(
    r"\b(?:SELECT\s+.{1,120}\s+FROM|WITH\s+[A-Za-z_][\w$]*\s+AS|SHOW\s+(?:CREATE\s+TABLE|TABLE\s+STATS|COLUMN\s+STATS)|"
    r"INSERT\s+.{1,80}\s+INTO|CREATE\s+TABLE|DROP\s+TABLE|ALTER\s+TABLE|COMPUTE\s+STATS|INVALIDATE\s+METADATA|REFRESH\s+[A-Za-z_])",
    re.IGNORECASE | re.DOTALL,
)

TEST_COMMANDS_BY_CATEGORY = {
    "browser display safety": (
        "python3 -m pytest -q tests/test_web_server.py tests/test_web_optimizer.py tests/test_web_ui_home.py tests/test_web_ui_help.py tests/test_web_display_safety.py tests/test_web_trusted_artifacts.py",
    ),
    "report validation": ("python3 -m pytest -q tests/test_report_sanitizer.py",),
    "optimizer validation": (
        "python3 -m pytest -q tests/test_optimizer_sql.py tests/test_query_optimizer.py tests/test_web_optimizer.py",
    ),
    "metadata collection": (
        "python3 -m pytest -q tests/test_impala_context_collector_cli.py tests/test_impala_metadata_workflow.py tests/test_cm_profile_collector_cli.py",
    ),
    "config loading": ("python3 -m pytest -q tests/test_config_contract.py",),
}


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class Finding:
    severity: str
    message: str
    path: str = ""


@dataclass(frozen=True)
class PreflightReport:
    dirty_paths: tuple[str, ...]
    changed_files: tuple[str, ...]
    findings: tuple[Finding, ...]
    suggested_tests: tuple[str, ...]

    @property
    def status(self) -> str:
        return classify_status(self.findings)


Runner = Callable[..., CommandResult]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run deterministic local Query Doctor demo/release preflight checks."
    )
    parser.add_argument(
        "--repo",
        default=None,
        help="Repository root to inspect. Defaults to the current working directory.",
    )
    parser.add_argument(
        "--public-release",
        action="store_true",
        help="Also scan the tracked tree and git history for private-data markers before making the repository public.",
    )
    parser.add_argument(
        "--skip-history",
        action="store_true",
        help="With --public-release, skip git history scanning and inspect only the current tracked tree.",
    )
    return parser.parse_args(argv)


def run_command(args: list[str], *, cwd: Path) -> CommandResult:
    completed = subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=False)
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def git_output(args: list[str], *, repo_dir: Path, runner: Runner = run_command) -> CommandResult:
    return runner(["git", *args], cwd=repo_dir)


def status_lines_to_paths(status_text: str) -> tuple[str, ...]:
    paths: list[str] = []
    for line in status_text.splitlines():
        if not line.strip():
            continue
        raw_path = line[3:] if len(line) > 3 else line.strip()
        if " -> " in raw_path:
            raw_path = raw_path.rsplit(" -> ", 1)[1]
        path = raw_path.strip()
        if path:
            paths.append(path)
    return tuple(sorted(dict.fromkeys(paths)))


def changed_files_from_git(repo_dir: Path, *, runner: Runner = run_command) -> tuple[str, ...]:
    names: list[str] = []
    for args in (["diff", "--name-only"], ["diff", "--cached", "--name-only"]):
        result = git_output(args, repo_dir=repo_dir, runner=runner)
        if result.returncode == 0:
            names.extend(line.strip() for line in result.stdout.splitlines() if line.strip())
    status = git_output(["status", "--porcelain"], repo_dir=repo_dir, runner=runner)
    if status.returncode == 0:
        names.extend(status_lines_to_paths(status.stdout))
    return tuple(sorted(dict.fromkeys(names)))


def safety_categories_for_path(path: str) -> tuple[str, ...]:
    categories: list[str] = []
    if (
        path in BROWSER_UI_FILES
        or path.startswith(BROWSER_UI_PREFIXES)
        or "browser_display" in path
        or "trusted_artifacts" in path
    ):
        categories.append("browser display safety")
    if path in REPORT_VALIDATION_PATHS or "report_sanitizer" in path:
        categories.append("report validation")
    if path in OPTIMIZER_VALIDATION_FILES or path.startswith(OPTIMIZER_VALIDATION_PREFIXES):
        categories.append("optimizer validation")
    if path in METADATA_COLLECTOR_FILES or path.startswith(METADATA_COLLECTOR_PREFIXES):
        categories.append("metadata collection")
    if path in CONFIG_PATHS or any(
        path.startswith(prefix) for prefix in CONFIG_PATHS if prefix.endswith("/")
    ):
        categories.append("config loading")
    return tuple(categories)


def changed_sensitive_categories(changed_files: tuple[str, ...]) -> tuple[str, ...]:
    categories: list[str] = []
    for path in changed_files:
        categories.extend(safety_categories_for_path(path))
    return tuple(sorted(dict.fromkeys(categories)))


def is_relevant_text_file(path: str) -> bool:
    if path.startswith("tests/"):
        return False
    suffix = Path(path).suffix
    if suffix not in TEXT_SUFFIXES:
        return False
    if path.startswith(
        ("docs/", "query_doctor/web/", "query_doctor/report/", "query_doctor/safety/")
    ):
        return True
    if path.startswith("query_doctor_") and suffix == ".py":
        return True
    return False


def scan_text_for_unsafe_output(text: str, *, path: str) -> tuple[Finding, ...]:
    # Docs get warnings, code/UI trust surfaces get blockers; patterns are intentionally conservative.
    findings: list[Finding] = []
    is_doc = path.startswith("docs/")
    unsafe_severity = "warning" if is_doc else "blocker"
    for token in RAW_ARTIFACT_TOKENS:
        if token in text:
            findings.append(
                Finding(
                    unsafe_severity,
                    f"browser/trusted-output text contains raw artifact filename: {token}",
                    path,
                )
            )
    for label, pattern in UNSAFE_PATTERNS:
        if pattern.search(text):
            findings.append(
                Finding(unsafe_severity, f"browser/trusted-output text contains {label}", path)
            )
    if SQL_LIKE_PATTERN.search(text):
        severity = "warning" if is_doc else "blocker"
        findings.append(
            Finding(severity, "browser/trusted-output text contains SQL-like snippet", path)
        )
    return tuple(findings)


def is_public_release_text_file(path: str) -> bool:
    return Path(path).suffix in PUBLIC_RELEASE_TEXT_SUFFIXES


def public_release_match_is_allowed(label: str, value: str) -> bool:
    lowered = value.lower()
    if label == "private local user path":
        return lowered.startswith(("/users/demo", "/users/example", "/home/demo", "/home/example"))
    if label == "embedded URL credentials":
        parsed = urlsplit(lowered)
        host = parsed.hostname or ""
        if (
            parsed.username == "user"
            and parsed.password == "pass"
            and host
            in {
                "localhost",
                "127.0.0.1",
            }
        ):
            return True
        return any(
            host == domain or host.endswith(f".{domain}") for domain in RESERVED_EXAMPLE_DOMAINS
        )
    if label == "authorization token":
        return "secret" in lowered or "<redacted>" in lowered
    if label == "production-looking hostname/domain":
        return any(
            lowered == domain or lowered.endswith(f".{domain}")
            for domain in RESERVED_EXAMPLE_DOMAINS
        )
    if label == "private-looking hostname/domain":
        return lowered == "query-doctor-cm.local"
    return False


def scan_public_release_text(text: str, *, path: str) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    for label, pattern in PUBLIC_RELEASE_PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(0)
            if public_release_match_is_allowed(label, value):
                continue
            severity = (
                "warning"
                if path.startswith("tests/")
                and label
                not in {
                    "private key material",
                    "high-confidence cloud token",
                }
                else "blocker"
            )
            findings.append(Finding(severity, f"public release scan found {label}", path))
            break
    return tuple(findings)


def tracked_files(repo_dir: Path, *, runner: Runner = run_command) -> tuple[str, ...]:
    result = git_output(["ls-files"], repo_dir=repo_dir, runner=runner)
    if result.returncode != 0:
        return ()
    return tuple(line.strip() for line in result.stdout.splitlines() if line.strip())


def scan_tracked_tree_for_public_release(
    repo_dir: Path,
    *,
    runner: Runner = run_command,
) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    for path in tracked_files(repo_dir, runner=runner):
        if not is_public_release_text_file(path):
            continue
        full_path = repo_dir / path
        if not full_path.is_file():
            continue
        try:
            text = full_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            findings.append(
                Finding("warning", "could not read tracked file for public release scan", path)
            )
            continue
        findings.extend(scan_public_release_text(text, path=path))
    return tuple(findings)


def chunked(values: tuple[str, ...], size: int) -> tuple[tuple[str, ...], ...]:
    return tuple(tuple(values[index : index + size]) for index in range(0, len(values), size))


def parse_git_grep_line(line: str) -> tuple[str, str, str] | None:
    parts = line.split(":", 3)
    if len(parts) != 4:
        return None
    revision, path, _line_number, text = parts
    if not revision or not path:
        return None
    return revision, path, text


def scan_git_history_for_public_release(
    repo_dir: Path,
    *,
    runner: Runner = run_command,
) -> tuple[Finding, ...]:
    revisions_result = git_output(["rev-list", "--all"], repo_dir=repo_dir, runner=runner)
    if revisions_result.returncode != 0:
        return (Finding("warning", "could not read git history for public release scan"),)
    revisions = tuple(line.strip() for line in revisions_result.stdout.splitlines() if line.strip())
    if not revisions:
        return ()

    findings: list[Finding] = []
    seen: set[tuple[str, str, str]] = set()
    for pattern in PUBLIC_RELEASE_GREP_PATTERNS:
        for revision_chunk in chunked(revisions, GIT_GREP_CHUNK_SIZE):
            result = git_output(
                ["grep", "-n", "-I", "-E", "-e", pattern, *revision_chunk, "--", "."],
                repo_dir=repo_dir,
                runner=runner,
            )
            if result.returncode not in (0, 1):
                findings.append(
                    Finding("warning", "git history grep failed during public release scan")
                )
                continue
            if result.returncode == 1:
                continue
            for line in result.stdout.splitlines():
                parsed = parse_git_grep_line(line)
                if parsed is None:
                    continue
                revision, path, text = parsed
                text_findings = scan_public_release_text(text, path=path)
                for finding in text_findings:
                    key = (revision[:12], finding.path, finding.message)
                    if key in seen:
                        continue
                    seen.add(key)
                    findings.append(
                        Finding(
                            finding.severity,
                            f"git history contains {finding.message.removeprefix('public release scan found ')} in {revision[:12]}",
                            finding.path,
                        )
                    )
                    if len(findings) >= 20:
                        return tuple(findings)
    return tuple(findings)


def added_lines_from_unified_diff(diff_text: str) -> str:
    lines: list[str] = []
    for line in diff_text.splitlines():
        if line.startswith(("+++", "---", "@@")):
            continue
        if line.startswith("+"):
            lines.append(line[1:])
    return "\n".join(lines)


def path_is_tracked(repo_dir: Path, path: str, *, runner: Runner = run_command) -> bool:
    result = git_output(
        ["ls-files", "--error-unmatch", "--", path], repo_dir=repo_dir, runner=runner
    )
    return result.returncode == 0


def changed_text_for_path(repo_dir: Path, path: str, *, runner: Runner = run_command) -> str:
    changed_chunks: list[str] = []
    for args in (
        ["diff", "--unified=0", "--", path],
        ["diff", "--cached", "--unified=0", "--", path],
    ):
        result = git_output(args, repo_dir=repo_dir, runner=runner)
        if result.returncode == 0:
            changed_text = added_lines_from_unified_diff(result.stdout)
            if changed_text:
                changed_chunks.append(changed_text)
    if changed_chunks:
        return "\n".join(changed_chunks)
    if not path_is_tracked(repo_dir, path, runner=runner):
        full_path = repo_dir / path
        if full_path.is_file():
            return full_path.read_text(encoding="utf-8", errors="replace")
    return ""


def scan_changed_files(
    repo_dir: Path,
    changed_files: tuple[str, ...],
    *,
    runner: Runner = run_command,
) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    for path in changed_files:
        if not is_relevant_text_file(path):
            continue
        try:
            text = changed_text_for_path(repo_dir, path, runner=runner)
        except OSError:
            findings.append(Finding("warning", "could not read changed file for safety scan", path))
            continue
        if not text:
            continue
        findings.extend(scan_text_for_unsafe_output(text, path=path))
    return tuple(findings)


def suggested_tests_for_categories(
    categories: tuple[str, ...], *, repo_dir: Path
) -> tuple[str, ...]:
    commands: list[str] = []
    for category in categories:
        for command in TEST_COMMANDS_BY_CATEGORY.get(category, ()):
            existing_parts = [part for part in command.split() if part.startswith("tests/")]
            if existing_parts and not all((repo_dir / part).exists() for part in existing_parts):
                continue
            commands.append(command)
    return tuple(dict.fromkeys(commands))


def classify_status(findings: tuple[Finding, ...]) -> str:
    if any(finding.severity == "blocker" for finding in findings):
        return NOT_READY
    if any(finding.severity == "warning" for finding in findings):
        return READY_WITH_WARNINGS
    return READY


def build_report(
    repo_dir: Path,
    *,
    runner: Runner = run_command,
    public_release: bool = False,
    skip_history: bool = False,
) -> PreflightReport:
    status = git_output(["status", "--porcelain"], repo_dir=repo_dir, runner=runner)
    dirty_paths = status_lines_to_paths(status.stdout) if status.returncode == 0 else ()
    changed_files = changed_files_from_git(repo_dir, runner=runner)

    findings: list[Finding] = []
    if status.returncode != 0:
        findings.append(Finding("warning", "could not read git status"))
    elif dirty_paths:
        findings.append(
            Finding("warning", f"working tree has {len(dirty_paths)} uncommitted path(s)")
        )

    diff_check = git_output(["diff", "--check"], repo_dir=repo_dir, runner=runner)
    if diff_check.returncode != 0:
        detail = (diff_check.stdout or diff_check.stderr).strip()
        findings.append(Finding("blocker", f"git diff --check failed: {detail}"))

    categories = changed_sensitive_categories(changed_files)
    for category in categories:
        findings.append(Finding("warning", f"safety-sensitive files changed: {category}"))

    if categories and not any(path.startswith("docs/") for path in changed_files):
        findings.append(
            Finding("warning", "safety-sensitive changes have no docs update in the current diff")
        )

    findings.extend(scan_changed_files(repo_dir, changed_files, runner=runner))
    if public_release:
        findings.extend(scan_tracked_tree_for_public_release(repo_dir, runner=runner))
        if not skip_history:
            findings.extend(scan_git_history_for_public_release(repo_dir, runner=runner))
    return PreflightReport(
        dirty_paths=dirty_paths,
        changed_files=changed_files,
        findings=tuple(findings),
        suggested_tests=suggested_tests_for_categories(categories, repo_dir=repo_dir),
    )


def render_report(report: PreflightReport) -> str:
    lines: list[str] = []
    lines.append("Query Doctor demo preflight")
    lines.append("")
    lines.append(f"Changed files: {len(report.changed_files)}")
    if report.changed_files:
        for path in report.changed_files[:20]:
            lines.append(f"  - {path}")
        if len(report.changed_files) > 20:
            lines.append(f"  ... {len(report.changed_files) - 20} more")
    lines.append("")
    if report.findings:
        lines.append("Findings:")
        for finding in report.findings:
            location = f" [{finding.path}]" if finding.path else ""
            lines.append(f"  {finding.severity.upper()}: {finding.message}{location}")
    else:
        lines.append("Findings: none")
    if report.suggested_tests:
        lines.append("")
        lines.append("Suggested focused tests:")
        for command in report.suggested_tests:
            lines.append(f"  - {command}")
    lines.append("")
    lines.append(f"Final status: {report.status}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_dir = Path(args.repo or ".").resolve()
    report = build_report(
        repo_dir, public_release=args.public_release, skip_history=args.skip_history
    )
    print(render_report(report))
    return 1 if report.status == NOT_READY else 0


if __name__ == "__main__":
    raise SystemExit(main())
