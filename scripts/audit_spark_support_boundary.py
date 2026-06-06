#!/usr/bin/env python3
"""Audit the Spark bounded compact support boundary."""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from collections.abc import Iterable
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.cli.commands import COMMAND_SPECS  # noqa: E402
from query_doctor.engines.capabilities import cli_roles_for_engine  # noqa: E402
from query_doctor.engines.registry import (  # noqa: E402
    DEFAULT_ENGINE_NAME,
    list_engine_adapters,
)
from query_doctor.safety.handoff_artifacts import write_ascii_json_artifact  # noqa: E402


SPARK_SUPPORT_BOUNDARY_SUMMARY_KIND = "spark_support_boundary_audit_v1"
SPARK_SUPPORT_BOUNDARY_STATUS = "bounded_compact_only"
ALLOWED_SPARK_CLI_ROLES = cli_roles_for_engine("spark")
SPARK_PRODUCT_SURFACE_PATTERNS = (
    "query_doctor/report/**/*.py",
    "query_doctor/optimizer/**/*.py",
    "query_doctor/recent/**/*.py",
    "query_doctor/web/details_facts.py",
    "query_doctor/web/case_detail*.py",
    "query_doctor/web/report_evidence.py",
    "query_doctor/web/optimizer*.py",
    "query_doctor/web/presenters/recent_scan*.py",
    "query_doctor/web/presenters/workload_detail.py",
    "query_doctor/web/ui/recent_scan*.py",
    "query_doctor/web/ui/workload_detail.py",
    "query_doctor/web/ui/report*.py",
    "query_doctor/web/ui/optimizer.py",
)
FORBIDDEN_SPARK_PRODUCT_IMPORT_RE = re.compile(
    r"^\s*(?:"
    r"from\s+query_doctor\.spark\b|"
    r"import\s+query_doctor\.spark\b|"
    r"from\s+query_doctor\.analyzer\.spark_fixture_(?:facts|schema)\b|"
    r"import\s+query_doctor\.analyzer\.spark_fixture_(?:facts|schema)\b|"
    r"from\s+query_doctor\.analyzer\s+import\s+.*spark_fixture_(?:facts|schema)"
    r")",
    re.MULTILINE,
)
REQUIRED_README_SNIPPETS = (
    "Spark compact support surfaces",
    "no public Spark engine support",
)
REQUIRED_ARCHITECTURE_SNIPPETS = (
    "Current status: bounded_compact_research.",
    "registered bounded compact-intake adapter",
    "not a Recent scan workflow, Details/trusted report surface, optimizer path, broad live collector, raw event-log path, Spark job-execution path, or public Spark support claim",
)
REQUIRED_CHECKLIST_SNIPPETS = (
    "not a live Spark support announcement",
    "no Spark registration beyond the compact-only adapter, Recent workflow, Details route, trusted report",
)
REQUIRED_DOC_INDEX_SNIPPETS = (
    "Bounded compact Spark History Server/event-log fact-model, compact-only adapter",
    "without public engine support",
    "bounded compact research контракт для Spark History Server/event-log fact model, compact-only adapter",
)
FORBIDDEN_STALE_REGISTRATION_SNIPPETS = (
    "must not add Spark engine registration",
    "must not register Spark as an engine",
    "intentionally not engine-adapter registration",
    "still adds no Spark engine registration",
    "Не использовать evidence set для Spark engine registration",
    "не нужен Spark engine registration",
    "Research-only Spark History Server/event-log fact-model",
    "research-only контракт для Spark History Server/event-log fact model",
    "A research-only Spark architecture spike may start",
)


@dataclass(frozen=True)
class SparkSupportBoundaryIssue:
    category: str
    message: str


@dataclass
class SparkSupportBoundaryAuditResult:
    checks: dict[str, str] = field(default_factory=dict)
    issues: list[SparkSupportBoundaryIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


class SparkSupportBoundaryOutputError(RuntimeError):
    """Raised when the support-boundary audit cannot write safe output."""


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check the Spark bounded compact support boundary. This keeps Spark below "
            "Recent, Details, trusted reports, optimizer behavior, raw event-log access, "
            "Spark job execution, and production support."
        )
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="Optional raw-free machine summary path. The path is never printed.",
    )
    return parser.parse_args(argv)


def audit_spark_support_boundary(root: Path = ROOT) -> SparkSupportBoundaryAuditResult:
    result = SparkSupportBoundaryAuditResult()
    _audit_engine_registry(result)
    _audit_cli_roles(result)
    _audit_product_surface_imports(result, _spark_product_surface_paths(root))
    _audit_docs(result, root)
    return result


def _audit_engine_registry(result: SparkSupportBoundaryAuditResult) -> None:
    adapters = {adapter.engine_name: adapter for adapter in list_engine_adapters()}
    spark = adapters.get("spark")
    _record_check(
        result,
        "engine_registration",
        spark is not None
        and DEFAULT_ENGINE_NAME == "impala"
        and spark.supports_offline_evidence_import
        and spark.supports_compact_diagnosis
        and spark.supports_history_server_compact_intake
        and not spark.supports_recent_scan
        and not spark.supports_query_id_mode
        and not spark.supports_metadata_collection
        and not spark.supports_validated_reports,
        "Spark adapter must stay registered only for bounded compact support surfaces.",
    )


def _audit_cli_roles(result: SparkSupportBoundaryAuditResult) -> None:
    spark_roles = {role for role in COMMAND_SPECS if "spark" in role}
    _record_check(
        result,
        "cli_role_boundary",
        spark_roles == ALLOWED_SPARK_CLI_ROLES,
        "Spark CLI roles must stay limited to compact intake and evidence handoff.",
    )


def _audit_product_surface_imports(
    result: SparkSupportBoundaryAuditResult,
    paths: Iterable[Path],
) -> None:
    offenders = count_forbidden_product_imports(paths)
    _record_check(
        result,
        "product_surface_imports",
        offenders == 0,
        "Spark compact modules must not be imported by product Details/report/optimizer surfaces.",
    )


def count_forbidden_product_imports(paths: Iterable[Path]) -> int:
    count = 0
    for path in paths:
        if FORBIDDEN_SPARK_PRODUCT_IMPORT_RE.search(path.read_text(encoding="utf-8")):
            count += 1
    return count


def _audit_docs(result: SparkSupportBoundaryAuditResult, root: Path) -> None:
    readme = _normalized_doc(root, "README.md")
    matrix = _read_doc(root, "docs/engine-support-gap-matrix.md")
    spark_public_status = _normalized_matrix_spark_cell(matrix, "Public support status")
    spark_live_collection = _normalized_matrix_spark_cell(matrix, "Live query/profile collection")
    spark_live_design = _normalized_matrix_spark_cell(matrix, "Live collection design")
    spark_source_contract = _normalized_matrix_spark_cell(matrix, "Source/evidence contract")
    architecture = _normalized_doc(root, "docs/engines/spark-architecture-spike.md")
    checklist = _normalized_doc(root, "docs/engines/spark-test-cluster-evidence-checklist.md")
    doc_indexes = " ".join(
        (
            _normalized_doc(root, "docs/README.md"),
            _normalized_doc(root, "docs/i18n/ru/README.md"),
        )
    )
    stale_registration_docs = "\n".join(
        _read_doc(root, relative_path)
        for relative_path in (
            "docs/README.md",
            "docs/i18n/ru/README.md",
            "docs/engine-expansion-plan.md",
            "docs/engines/spark-architecture-spike.md",
            "docs/engines/i18n/ru/spark-architecture-spike.md",
            "docs/engines/i18n/ru/spark-test-cluster-evidence-checklist.md",
            "docs/changelog.md",
            "query_doctor/spark/__init__.py",
        )
    )

    _record_check(
        result,
        "readme_support_boundary",
        all(snippet in readme for snippet in REQUIRED_README_SNIPPETS),
        "README must present Spark as experimental compact intake, not public support.",
    )
    _record_check(
        result,
        "matrix_support_status",
        "bounded compact support surfaces" in _matrix_spark_cell(matrix, "Public support status")
        and "not production support" in _matrix_spark_cell(matrix, "Public support status"),
        "Engine support matrix must keep Spark support status bounded and below production.",
    )
    _record_check(
        result,
        "matrix_handoff_summary_boundary",
        "spark_one_application_handoff_summary_v1" in spark_public_status
        and "optional matching handoff summaries" in spark_live_collection
        and "without reopening Spark" in spark_live_collection
        and "optional matching spark_one_application_handoff_summary_v1 artifacts"
        in spark_live_design,
        "Engine support matrix must document retained Spark handoff summaries as optional raw-free evidence below support.",
    )
    _record_check(
        result,
        "matrix_engine_registration",
        "bounded compact intake" in _matrix_spark_cell(matrix, "Engine adapter registration")
        and "no Recent" in _matrix_spark_cell(matrix, "Engine adapter registration"),
        "Engine support matrix must keep Spark engine registration compact-only.",
    )
    _record_check(
        result,
        "matrix_application_scope_summary_gate",
        "same_application" in spark_source_contract
        and "application-level job/stage/task summaries" in spark_source_contract
        and "SQL-execution-specific timing and failure facts" in spark_source_contract
        and "task-duration context" in spark_source_contract,
        "Engine support matrix must document Spark application-scope summaries without SQL-specific overclaim.",
    )
    _record_check(
        result,
        "architecture_research_boundary",
        all(snippet in architecture for snippet in REQUIRED_ARCHITECTURE_SNIPPETS),
        "Spark architecture doc must keep the research/no-support boundary.",
    )
    _record_check(
        result,
        "evidence_checklist_no_support_boundary",
        all(snippet in checklist for snippet in REQUIRED_CHECKLIST_SNIPPETS),
        "Spark evidence checklist must keep the no-support acceptance boundary.",
    )
    _record_check(
        result,
        "docs_index_support_boundary",
        all(snippet in doc_indexes for snippet in REQUIRED_DOC_INDEX_SNIPPETS),
        "Documentation indexes must describe Spark as bounded compact work below support.",
    )
    _record_check(
        result,
        "stale_registration_wording",
        not any(
            snippet in stale_registration_docs for snippet in FORBIDDEN_STALE_REGISTRATION_SNIPPETS
        ),
        "Spark docs must say registration is compact-only, not absent.",
    )


def _read_doc(root: Path, relative_path: str) -> str:
    try:
        return (root / relative_path).read_text(encoding="utf-8")
    except OSError:
        return ""


def _normalized_doc(root: Path, relative_path: str) -> str:
    return " ".join(_read_doc(root, relative_path).replace("`", "").split())


def _matrix_spark_cell(matrix: str, row_label: str) -> str:
    for line in matrix.splitlines():
        if not line.startswith(f"| {row_label} |"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 4:
            return cells[3]
    return ""


def _normalized_matrix_spark_cell(matrix: str, row_label: str) -> str:
    return " ".join(_matrix_spark_cell(matrix, row_label).replace("`", "").split())


def _spark_product_surface_paths(root: Path) -> tuple[Path, ...]:
    paths: set[Path] = set()
    for pattern in SPARK_PRODUCT_SURFACE_PATTERNS:
        paths.update(path for path in root.glob(pattern) if path.is_file())
    return tuple(sorted(paths))


def _record_check(
    result: SparkSupportBoundaryAuditResult,
    category: str,
    passed: bool,
    message: str,
) -> None:
    result.checks[category] = "ok" if passed else "failed"
    if not passed:
        result.issues.append(SparkSupportBoundaryIssue(category, message))


def print_result(result: SparkSupportBoundaryAuditResult, *, out: TextIO | None = None) -> None:
    if out is None:
        out = sys.stdout
    status = "ok" if result.ok else "failed"
    print(f"Spark support boundary audit: {status}", file=out)
    print(
        "Boundary: "
        "production_support=not_claimed, "
        "engine_registration=bounded_compact_only, "
        "product_surfaces=not_wired, "
        "spark_job_execution=not_performed",
        file=out,
    )
    print("Checks:", file=out)
    for category, check_status in sorted(result.checks.items()):
        print(f"  {category}: {check_status}", file=out)
    if result.issues:
        print("Issues:", file=out)
        for issue in result.issues:
            print(f"  {issue.category}: {issue.message}", file=out)
    else:
        print("Issues: none", file=out)


def support_boundary_summary_payload(
    result: SparkSupportBoundaryAuditResult,
    *,
    status: str,
) -> dict[str, Any]:
    issue_counts = Counter(issue.category for issue in result.issues)
    return {
        "summary_kind": SPARK_SUPPORT_BOUNDARY_SUMMARY_KIND,
        "status": status,
        "mode": "spark_support_boundary",
        "boundary": {
            "production_support": "not_claimed",
            "engine_registration": SPARK_SUPPORT_BOUNDARY_STATUS,
            "product_surfaces": "not_wired",
            "spark_job_execution": "not_performed",
        },
        "counts": {
            "check_count": len(result.checks),
            "failed_check_count": len(result.issues),
        },
        "checks": dict(sorted(result.checks.items())),
        "issues": {
            "counts": counter_payload(issue_counts),
            "items": [
                {"category": issue.category, "message": issue.message} for issue in result.issues
            ],
        },
    }


def counter_payload(counter: Mapping[str, int]) -> dict[str, int]:
    return {key: int(counter[key]) for key in sorted(counter)}


def write_summary_or_reject(path: Path | None, payload: Mapping[str, Any]) -> bool:
    if path is None:
        return True
    try:
        write_ascii_json_artifact(path, payload)
    except OSError as exc:
        raise SparkSupportBoundaryOutputError("summary JSON output could not be written") from exc
    return True


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    result = audit_spark_support_boundary()
    status = "ok" if result.ok else "failed"
    try:
        write_summary_or_reject(
            args.summary_json,
            support_boundary_summary_payload(result, status=status),
        )
    except SparkSupportBoundaryOutputError as exc:
        print(f"[spark-support-boundary] rejected: {exc}", file=sys.stderr)
        return 2
    print_result(result)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
