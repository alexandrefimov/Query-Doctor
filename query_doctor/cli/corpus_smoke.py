#!/usr/bin/env python3
"""Run analyzer smoke checks across local Query Doctor corpus cases."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

from query_doctor.cli.commands import command_prefix


REPO_DIR = Path(__file__).resolve().parents[2]
FACTS_FILENAME = "analysis_facts.md"
BANNED_PHRASES = (
    "reduce skew",
    "optimize joins",
    "improve query",
    "skew is proven",
    "stats are stale",
    "hot keys exist",
)


class SmokeError(ValueError):
    """Raised for unsafe or invalid smoke-run inputs."""


class AnalyzerResult:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class CaseResult:
    def __init__(
        self,
        *,
        case_path: Path,
        parsed_operators: int | None,
        cardinality_anomalies: int | None,
        memory_anomalies: int | None,
        action_cards_present: bool,
        severe_action_cards_present: bool,
        findings_present: bool,
        analyzer_exit_status: int,
        facts_present: bool,
        banned_phrase_matches: list[dict[str, int | str]],
    ) -> None:
        self.case_path = case_path
        self.parsed_operators = parsed_operators
        self.cardinality_anomalies = cardinality_anomalies
        self.memory_anomalies = memory_anomalies
        self.action_cards_present = action_cards_present
        self.severe_action_cards_present = severe_action_cards_present
        self.findings_present = findings_present
        self.analyzer_exit_status = analyzer_exit_status
        self.facts_present = facts_present
        self.banned_phrase_matches = banned_phrase_matches

    @property
    def analyzer_passed(self) -> bool:
        return self.analyzer_exit_status == 0 and self.facts_present

    @property
    def banned_phrase_hit_count(self) -> int:
        return sum(int(item["count"]) for item in self.banned_phrase_matches)

    @property
    def status(self) -> str:
        if self.analyzer_exit_status != 0:
            return "analyzer_error"
        if not self.facts_present:
            return "facts_missing"
        if self.banned_phrase_matches:
            return "banned_phrases"
        return "ok"

    @property
    def classification(self) -> str:
        if not self.analyzer_passed:
            return "FAIL"
        if (
            (self.cardinality_anomalies or 0) > 0
            or (self.memory_anomalies or 0) > 0
            or self.severe_action_cards_present
        ):
            return "PROBLEM"
        if self.action_cards_present or self.findings_present:
            return "WARN"
        return "OK"

    def to_json(self) -> dict[str, object]:
        return {
            "action_cards_present": self.action_cards_present,
            "analyzer_exit_status": self.analyzer_exit_status,
            "banned_phrase_matches": self.banned_phrase_matches,
            "cardinality_anomalies": self.cardinality_anomalies,
            "case_path": display_path(self.case_path),
            "classification": self.classification,
            "facts_present": self.facts_present,
            "findings_present": self.findings_present,
            "memory_anomalies": self.memory_anomalies,
            "parsed_operators": self.parsed_operators,
            "severe_action_cards_present": self.severe_action_cards_present,
            "status": self.status,
        }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run analyzer-only smoke checks across immediate local Query Doctor corpus case directories. "
            "Does not call Cloudera Manager, collect profiles, or generate LLM reports."
        )
    )
    parser.add_argument("root", help="Local corpus root, for example cases/cm-corpus.")
    parser.add_argument(
        "--keep-generated",
        action="store_true",
        help=f"Keep generated {FACTS_FILENAME} files instead of removing them after each case.",
    )
    parser.add_argument(
        "--json-out",
        help="Optional path for a deterministic JSON summary. No JSON file is written by default.",
    )
    parser.add_argument(
        "--fail-on-analyzer-error",
        action="store_true",
        help="Exit non-zero if any case fails analyzer execution or does not produce analysis facts.",
    )
    parser.add_argument(
        "--fail-on-banned-phrases",
        action="store_true",
        help="Exit non-zero if generated analysis facts contain unsupported/banned phrases.",
    )
    return parser.parse_args(argv)


def validate_root(value: str) -> Path:
    if not value.strip():
        raise SmokeError("Corpus root path is empty.")
    root = Path(value).expanduser()
    absolute = root if root.is_absolute() else Path.cwd() / root
    if absolute.is_symlink():
        raise SmokeError(f"Refusing symlink corpus root: {root}")
    if not absolute.exists():
        raise SmokeError(f"Corpus root does not exist: {root}")
    if not absolute.is_dir():
        raise SmokeError(f"Corpus root is not a directory: {root}")
    return absolute


def iter_case_dirs(root: Path) -> list[Path]:
    cases: list[Path] = []
    for child in root.iterdir():
        if child.is_symlink() or not child.is_dir():
            continue
        if (child / "profile_digest.md").is_file():
            cases.append(child)
    return sorted(cases, key=lambda item: item.name)


def run_analyzer(case_dir: Path) -> AnalyzerResult:
    result = subprocess.run(
        analyzer_command(case_dir),
        cwd=REPO_DIR,
        text=True,
        capture_output=True,
        check=False,
    )
    return AnalyzerResult(result.returncode, result.stdout, result.stderr)


def analyzer_command(case_dir: Path) -> list[str]:
    return command_prefix(REPO_DIR, "analyze") + [str(case_dir)]


def parse_count(facts_text: str, key: str) -> int | None:
    match = re.search(rf"^\s*[-*]?\s*{re.escape(key)}\s*:\s*(?P<value>\d+)\s*$", facts_text, re.MULTILINE)
    if not match:
        return None
    return int(match.group("value"))


def markdown_section(text: str, heading: str) -> str:
    match = re.search(rf"^##\s+{re.escape(heading)}\s*$", text, re.MULTILINE)
    if not match:
        return ""
    start = match.end()
    next_match = re.search(r"^##\s+", text[start:], re.MULTILINE)
    end = start + next_match.start() if next_match else len(text)
    return text[start:end].strip()


def section_has_real_content(text: str, heading: str, empty_marker: str) -> bool:
    section = markdown_section(text, heading)
    if not section:
        return False
    return empty_marker.lower() not in section.lower()


def section_has_severe_signal(text: str, heading: str) -> bool:
    section = markdown_section(text, heading)
    return bool(section and re.search(r"\bsevere\b", section, re.IGNORECASE))


def scan_banned_phrases(facts_text: str) -> list[dict[str, int | str]]:
    lower_text = facts_text.lower()
    matches: list[dict[str, int | str]] = []
    for phrase in BANNED_PHRASES:
        count = lower_text.count(phrase)
        if count:
            matches.append({"phrase": phrase, "count": count})
    return matches


def smoke_case(
    case_dir: Path,
    *,
    keep_generated: bool,
    analyzer_runner: Callable[[Path], AnalyzerResult],
) -> CaseResult:
    facts_path = case_dir / FACTS_FILENAME
    result = analyzer_runner(case_dir)
    facts_present = facts_path.is_file()
    facts_text = facts_path.read_text(encoding="utf-8", errors="replace") if facts_present else ""
    action_cards_present = section_has_real_content(
        facts_text,
        "Action Cards",
        "No deterministic action cards were triggered from the parsed evidence.",
    )

    case_result = CaseResult(
        case_path=case_dir,
        parsed_operators=parse_count(facts_text, "Parsed operators") if facts_present else None,
        cardinality_anomalies=parse_count(facts_text, "Cardinality anomalies") if facts_present else None,
        memory_anomalies=parse_count(facts_text, "Memory anomalies") if facts_present else None,
        action_cards_present=action_cards_present,
        severe_action_cards_present=action_cards_present and section_has_severe_signal(facts_text, "Action Cards"),
        findings_present=section_has_real_content(
            facts_text,
            "Findings",
            "No deterministic findings were produced from the digest.",
        ),
        analyzer_exit_status=result.returncode,
        facts_present=facts_present,
        banned_phrase_matches=scan_banned_phrases(facts_text) if facts_present else [],
    )

    if result.returncode == 0 and facts_present and not keep_generated:
        facts_path.unlink()

    return case_result


def build_totals(results: list[CaseResult]) -> dict[str, int]:
    return {
        "analyzer_failed": sum(1 for item in results if not item.analyzer_passed),
        "analyzer_passed": sum(1 for item in results if item.analyzer_passed),
        "banned_phrase_hits": sum(item.banned_phrase_hit_count for item in results),
        "cases_scanned": len(results),
        "cases_with_action_cards": sum(1 for item in results if item.action_cards_present),
        "fail_cases": sum(1 for item in results if item.classification == "FAIL"),
        "ok_cases": sum(1 for item in results if item.classification == "OK"),
        "problem_cases": sum(1 for item in results if item.classification == "PROBLEM"),
        "warn_cases": sum(1 for item in results if item.classification == "WARN"),
    }


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def format_value(value: int | None) -> str:
    return "n/a" if value is None else str(value)


def print_table(results: list[CaseResult], totals: dict[str, int]) -> None:
    headers = ["case", "class", "operators", "cardinality", "memory", "action_cards", "status"]
    rows = [
        [
            display_path(result.case_path),
            result.classification,
            format_value(result.parsed_operators),
            format_value(result.cardinality_anomalies),
            format_value(result.memory_anomalies),
            "yes" if result.action_cards_present else "no",
            result.status,
        ]
        for result in results
    ]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows)) if rows else len(headers[index])
        for index in range(len(headers))
    ]

    print(" | ".join(headers[index].ljust(widths[index]) for index in range(len(headers))))
    print(" | ".join("-" * widths[index] for index in range(len(headers))))
    for row in rows:
        print(" | ".join(row[index].ljust(widths[index]) for index in range(len(headers))))

    print()
    print(f"Cases scanned: {totals['cases_scanned']}")
    print(f"Analyzer passed: {totals['analyzer_passed']}")
    print(f"Analyzer failed: {totals['analyzer_failed']}")
    print(f"Cases with action cards: {totals['cases_with_action_cards']}")
    print(f"Banned phrase hits: {totals['banned_phrase_hits']}")
    print(f"OK cases: {totals['ok_cases']}")
    print(f"WARN cases: {totals['warn_cases']}")
    print(f"PROBLEM cases: {totals['problem_cases']}")
    print(f"FAIL cases: {totals['fail_cases']}")


def write_json_summary(path: str, root: Path, results: list[CaseResult], totals: dict[str, int]) -> None:
    output_path = Path(path).expanduser()
    payload = {
        "cases": [result.to_json() for result in results],
        "root": display_path(root),
        "totals": totals,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_smoke(
    root: Path,
    *,
    keep_generated: bool,
    analyzer_runner: Callable[[Path], AnalyzerResult] = run_analyzer,
) -> tuple[list[CaseResult], dict[str, int]]:
    results = [
        smoke_case(case_dir, keep_generated=keep_generated, analyzer_runner=analyzer_runner)
        for case_dir in iter_case_dirs(root)
    ]
    return results, build_totals(results)


def main(
    argv: list[str] | None = None,
    *,
    analyzer_runner: Callable[[Path], AnalyzerResult] = run_analyzer,
) -> int:
    args = parse_args(argv)
    try:
        root = validate_root(args.root)
    except SmokeError as exc:
        print(f"[corpus-smoke] ERROR: {exc}", file=sys.stderr)
        return 2

    results, totals = run_smoke(root, keep_generated=args.keep_generated, analyzer_runner=analyzer_runner)
    print_table(results, totals)
    if args.json_out:
        write_json_summary(args.json_out, root, results, totals)

    should_fail = False
    if args.fail_on_analyzer_error and totals["analyzer_failed"]:
        should_fail = True
    if args.fail_on_banned_phrases and totals["banned_phrase_hits"]:
        should_fail = True
    return 1 if should_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
