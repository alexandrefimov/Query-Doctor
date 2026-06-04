#!/usr/bin/env python3
"""Audit Spark compact diagnosis readiness without making a support claim."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.analyzer.engine_facts import (  # noqa: E402
    EngineFactBundle,
    EngineFactContractError,
    MetricFact,
    engine_fact_namespace_definitions,
    validate_engine_fact_bundle_raw_free,
)
from query_doctor.report.safety_validation import (  # noqa: E402
    contains_raw_sql_like_text,
    validate_report_internal_fingerprints,
)
from query_doctor.safety import redaction  # noqa: E402
from query_doctor.spark.diagnosis import (  # noqa: E402
    build_spark_compact_diagnosis,
    spark_bundle_for_compact_payload,
)


EXPECTED_SUPPORT_STATUS = "experimental_compact_intake"
EXPECTED_DIAGNOSIS_BOUNDARY = {
    "root_cause": "not_claimed",
    "details_trusted_report_surface": "not_wired",
    "optimizer_behavior": "not_wired",
    "spark_job_execution": "not_performed",
}
ACCEPTED_SPARK_SOURCE_CONTRACTS = frozenset(
    {
        "spark_history_eventlog_compact_v1",
        "spark_history_server_compact_v1",
    }
)
REQUIRED_SPARK_LIMITATION_IDS = frozenset(
    {
        "no_product_support",
        "no_browser_report_surface",
        "no_spark_job_execution",
        "no_raw_event_log",
        "structured_streaming_not_modeled",
        "cluster_manager_context",
    }
)
ALLOWED_SPARK_SUPPORT_BOUNDARY_IDS = frozenset(
    {
        "cluster_manager_context",
        "executor_loss",
        "live_history_server_collection",
        "no_browser_report_surface",
        "no_live_history_server_collection",
        "no_product_support",
        "no_raw_event_log",
        "no_spark_job_execution",
        "spark_fixture_import",
        "spark_history_source_coverage",
        "structured_streaming_not_modeled",
    }
)


class SparkCompactReadinessInputError(RuntimeError):
    """Raised when compact JSON cannot be loaded safely."""


@dataclass(frozen=True)
class SparkCompactReadinessIssue:
    category: str
    message: str


@dataclass
class SparkCompactReadinessResult:
    source_contract: str = "unknown"
    support_status: str = "unknown"
    parser_coverage: str = "unknown"
    lifecycle: str = "unknown"
    fact_count: int = 0
    attention_area_count: int = 0
    supported_attention_area_count: int = 0
    source_warning_count: int = 0
    fact_scope_counts: Counter[str] = field(default_factory=Counter)
    fact_state_counts: Counter[str] = field(default_factory=Counter)
    attention_state_counts: Counter[str] = field(default_factory=Counter)
    limitation_state_counts: Counter[str] = field(default_factory=Counter)
    issue_counts: Counter[str] = field(default_factory=Counter)
    issues: list[SparkCompactReadinessIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


@dataclass
class SparkCompactReadinessBatchResult:
    input_count: int = 0
    ok_count: int = 0
    failed_count: int = 0
    fact_count: int = 0
    attention_area_count: int = 0
    supported_attention_area_count: int = 0
    source_warning_count: int = 0
    source_contract_counts: Counter[str] = field(default_factory=Counter)
    support_status_counts: Counter[str] = field(default_factory=Counter)
    parser_coverage_counts: Counter[str] = field(default_factory=Counter)
    lifecycle_counts: Counter[str] = field(default_factory=Counter)
    fact_scope_counts: Counter[str] = field(default_factory=Counter)
    fact_state_counts: Counter[str] = field(default_factory=Counter)
    attention_state_counts: Counter[str] = field(default_factory=Counter)
    limitation_state_counts: Counter[str] = field(default_factory=Counter)
    issue_counts: Counter[str] = field(default_factory=Counter)
    issues: list[tuple[int | None, SparkCompactReadinessIssue]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SparkCompactReadinessInputError("compact JSON input could not be read") from exc
    except json.JSONDecodeError as exc:
        raise SparkCompactReadinessInputError("compact JSON input is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise SparkCompactReadinessInputError("compact JSON input must be an object")
    return payload


def audit_compact_json(
    compact_json: Path,
    *,
    require_supported_attention: bool = False,
    fail_on_source_warnings: bool = False,
) -> SparkCompactReadinessResult:
    return audit_compact_payload(
        load_json_object(compact_json),
        require_supported_attention=require_supported_attention,
        fail_on_source_warnings=fail_on_source_warnings,
    )


def audit_compact_json_suite(
    compact_jsons: Iterable[Path],
    *,
    require_supported_attention: bool = False,
    fail_on_source_warnings: bool = False,
    require_min_inputs: int = 1,
    required_source_contracts: Iterable[str] = (),
) -> SparkCompactReadinessBatchResult:
    batch = SparkCompactReadinessBatchResult()
    for index, compact_json in enumerate(compact_jsons, start=1):
        batch.input_count += 1
        try:
            result = audit_compact_json(
                compact_json,
                require_supported_attention=require_supported_attention,
                fail_on_source_warnings=fail_on_source_warnings,
            )
        except SparkCompactReadinessInputError:
            issue = SparkCompactReadinessIssue(
                "compact_input_unreadable",
                "One compact JSON input could not be read or parsed safely.",
            )
            batch.failed_count += 1
            batch.issue_counts[issue.category] += 1
            batch.issues.append((index, issue))
            continue
        add_suite_result(batch, index, result)
    audit_suite_breadth(
        batch,
        require_min_inputs=require_min_inputs,
        required_source_contracts=required_source_contracts,
    )
    return batch


def audit_compact_payload(
    payload: dict[str, Any],
    *,
    require_supported_attention: bool = False,
    fail_on_source_warnings: bool = False,
) -> SparkCompactReadinessResult:
    result = SparkCompactReadinessResult(source_contract=safe_source_contract(payload))
    try:
        bundle = spark_bundle_for_compact_payload(payload)
    except EngineFactContractError:
        add_issue(
            result,
            "compact_contract_invalid",
            "Compact Spark payload failed schema or fact validation.",
        )
        return result

    audit_engine_fact_boundary(result, bundle)

    try:
        diagnosis = build_spark_compact_diagnosis(payload)
    except EngineFactContractError:
        add_issue(
            result,
            "compact_diagnosis_invalid",
            "Compact Spark diagnosis could not be built from accepted facts.",
        )
        return result

    audit_diagnosis_boundary(result, diagnosis)
    audit_diagnosis_raw_free(result, diagnosis)
    if require_supported_attention and result.supported_attention_area_count <= 0:
        add_issue(
            result,
            "missing_supported_attention_area",
            "Strict readiness requires at least one supported Spark attention area.",
        )
    if fail_on_source_warnings and result.source_warning_count:
        add_issue(
            result,
            "spark_source_warning_present",
            "Strict readiness requires Spark compact source warnings to be cleared.",
        )
    return result


def audit_engine_fact_boundary(
    result: SparkCompactReadinessResult,
    bundle: EngineFactBundle,
) -> None:
    try:
        facts = bundle.facts_by_id()
    except EngineFactContractError:
        add_issue(
            result,
            "engine_fact_contract_invalid",
            "Spark engine fact bundle failed namespace validation.",
        )
        return

    result.parser_coverage = bundle.identity.parser_coverage
    result.lifecycle = bundle.lifecycle.lifecycle
    result.fact_count = len(facts)
    definitions = {
        definition.fact_id: definition for definition in engine_fact_namespace_definitions()
    }

    for fact_id, fact in facts.items():
        definition = definitions.get(fact_id)
        if definition is None:
            result.fact_scope_counts["unregistered"] += 1
            add_issue(
                result,
                "spark_fact_unregistered",
                "Spark compact facts must use registered fact identifiers.",
            )
            continue
        result.fact_scope_counts[definition.scope] += 1
        result.fact_state_counts[fact.state] += 1
        if definition.scope in {"shared", "distributed_sql_family"}:
            add_issue(
                result,
                "spark_fact_promoted_to_shared_scope",
                "Spark compact facts must remain Spark-specific until a separate promotion gate.",
            )
        if definition.scope == "engine_specific" and not fact_id.startswith("spark_"):
            add_issue(
                result,
                "spark_engine_fact_without_prefix",
                "Spark engine-specific facts must keep the spark_ prefix.",
            )
        if (
            definition.scope == "support_boundary"
            and fact_id not in ALLOWED_SPARK_SUPPORT_BOUNDARY_IDS
        ):
            add_issue(
                result,
                "spark_support_boundary_id_unapproved",
                "Spark support-boundary facts must use the approved compact limitation vocabulary.",
            )

    raw_violations = validate_engine_fact_bundle_raw_free(bundle)
    for violation in raw_violations:
        add_issue(
            result,
            "engine_fact_raw_boundary",
            f"Spark engine fact boundary contains raw-like {violation} content.",
        )


def audit_diagnosis_boundary(
    result: SparkCompactReadinessResult,
    diagnosis: dict[str, Any],
) -> None:
    if diagnosis.get("engine") != "spark":
        add_issue(
            result,
            "diagnosis_engine_mismatch",
            "Spark compact diagnosis must stay on engine=spark.",
        )
    result.support_status = str(diagnosis.get("support_status") or "unknown")
    if result.support_status != EXPECTED_SUPPORT_STATUS:
        add_issue(
            result,
            "spark_support_claim_boundary",
            "Spark compact diagnosis must stay experimental and below product support.",
        )

    boundary = diagnosis.get("diagnosis_boundary")
    if not isinstance(boundary, dict):
        add_issue(
            result,
            "missing_diagnosis_boundary",
            "Spark compact diagnosis must publish an explicit no-claim boundary.",
        )
    else:
        for key, expected in EXPECTED_DIAGNOSIS_BOUNDARY.items():
            if boundary.get(key) != expected:
                add_issue(
                    result,
                    "spark_diagnosis_boundary_drift",
                    "Spark compact diagnosis boundary no longer matches the no-claim contract.",
                )

    attention_areas = list_of_mappings(diagnosis.get("attention_areas"))
    result.attention_area_count = len(attention_areas)
    for area in attention_areas:
        state = str(area.get("state") or "unknown")
        result.attention_state_counts[state] += 1
        if state == "supported":
            result.supported_attention_area_count += 1

    limitations = list_of_mappings(diagnosis.get("limitations"))
    limitation_ids: set[str] = set()
    for limitation in limitations:
        limitation_id = str(limitation.get("id") or "")
        if limitation_id:
            limitation_ids.add(limitation_id)
        result.limitation_state_counts[str(limitation.get("state") or "unknown")] += 1
    missing_limitations = REQUIRED_SPARK_LIMITATION_IDS - limitation_ids
    if missing_limitations:
        add_issue(
            result,
            "spark_limitation_boundary_missing",
            "Spark compact diagnosis must keep explicit support and source limitations.",
        )

    source_warnings = diagnosis.get("source_warnings")
    if isinstance(source_warnings, (list, tuple)):
        result.source_warning_count = len(source_warnings)


def audit_diagnosis_raw_free(
    result: SparkCompactReadinessResult,
    diagnosis: dict[str, Any],
) -> None:
    text = json.dumps(diagnosis, ensure_ascii=True, sort_keys=True)
    if contains_raw_sql_like_text(text):
        add_issue(
            result,
            "diagnosis_raw_boundary",
            "Spark compact diagnosis contains raw SQL-like text.",
        )
    for _violation in validate_report_internal_fingerprints(text):
        add_issue(
            result,
            "diagnosis_raw_boundary",
            "Spark compact diagnosis contains internal artifact or runtime fingerprints.",
        )
    for label, observed in raw_text_violations(text).items():
        if observed:
            add_issue(
                result,
                "diagnosis_raw_boundary",
                f"Spark compact diagnosis contains raw-like {label} content.",
            )


def raw_text_violations(text: str) -> dict[str, bool]:
    return {
        "email": bool(redaction.EMAIL_RE.search(text)),
        "ipv4": bool(redaction.IPV4_RE.search(text)),
        "hostname": bool(redaction.HOSTLIKE_FQDN_RE.search(text)),
        "secret": bool(redaction.SECRET_VALUE_RE.search(text)),
    }


def safe_source_contract(payload: dict[str, Any]) -> str:
    value = payload.get("sourceContract")
    if value in ACCEPTED_SPARK_SOURCE_CONTRACTS:
        return str(value)
    return "unknown"


def list_of_mappings(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def add_issue(result: SparkCompactReadinessResult, category: str, message: str) -> None:
    result.issue_counts[category] += 1
    result.issues.append(SparkCompactReadinessIssue(category, message))


def add_suite_result(
    batch: SparkCompactReadinessBatchResult,
    index: int,
    result: SparkCompactReadinessResult,
) -> None:
    if result.ok:
        batch.ok_count += 1
    else:
        batch.failed_count += 1
    batch.fact_count += result.fact_count
    batch.attention_area_count += result.attention_area_count
    batch.supported_attention_area_count += result.supported_attention_area_count
    batch.source_warning_count += result.source_warning_count
    batch.source_contract_counts[result.source_contract] += 1
    batch.support_status_counts[result.support_status] += 1
    batch.parser_coverage_counts[result.parser_coverage] += 1
    batch.lifecycle_counts[result.lifecycle] += 1
    batch.fact_scope_counts.update(result.fact_scope_counts)
    batch.fact_state_counts.update(result.fact_state_counts)
    batch.attention_state_counts.update(result.attention_state_counts)
    batch.limitation_state_counts.update(result.limitation_state_counts)
    batch.issue_counts.update(result.issue_counts)
    for issue in result.issues:
        batch.issues.append((index, issue))


def audit_suite_breadth(
    batch: SparkCompactReadinessBatchResult,
    *,
    require_min_inputs: int,
    required_source_contracts: Iterable[str],
) -> None:
    if batch.input_count < require_min_inputs:
        add_suite_issue(
            batch,
            "spark_suite_input_count_gap",
            "Strict suite readiness requires more compact inputs.",
        )
    for source_contract in required_source_contracts:
        if batch.source_contract_counts[source_contract] <= 0:
            add_suite_issue(
                batch,
                "spark_suite_source_contract_gap",
                "Strict suite readiness requires each selected source contract to appear.",
            )


def add_suite_issue(
    batch: SparkCompactReadinessBatchResult,
    category: str,
    message: str,
) -> None:
    issue = SparkCompactReadinessIssue(category, message)
    batch.issue_counts[category] += 1
    batch.issues.append((None, issue))


def print_counter(title: str, counter: Counter[str], *, out: TextIO, limit: int) -> None:
    print(f"{title}:", file=out)
    if not counter:
        print("  <none>", file=out)
        return
    for key, count in counter.most_common(limit):
        print(f"  {key}: {count}", file=out)


def print_result(
    result: SparkCompactReadinessResult,
    *,
    out: TextIO | None = None,
    limit: int = 12,
) -> None:
    if out is None:
        out = sys.stdout
    status = "ok" if result.ok else "failed"
    print(f"Spark compact readiness: {status}", file=out)
    print("Input: compact_json", file=out)
    print(
        "Boundary: "
        f"support_status={result.support_status}, "
        "root_cause=not_claimed, "
        "job_execution=not_performed",
        file=out,
    )
    print(
        "Source: "
        f"contract={result.source_contract}, "
        f"parser_coverage={result.parser_coverage}, "
        f"lifecycle={result.lifecycle}, "
        f"source_warnings={result.source_warning_count}",
        file=out,
    )
    print(
        "Facts: "
        f"total={result.fact_count}, "
        f"attention_areas={result.attention_area_count}, "
        f"supported_attention_areas={result.supported_attention_area_count}",
        file=out,
    )
    print_counter("Fact scopes", result.fact_scope_counts, out=out, limit=limit)
    print_counter("Fact states", result.fact_state_counts, out=out, limit=limit)
    print_counter("Attention states", result.attention_state_counts, out=out, limit=limit)
    print_counter("Limitation states", result.limitation_state_counts, out=out, limit=limit)
    if result.issues:
        print_counter("Issues", result.issue_counts, out=out, limit=limit)
        print("Issue examples:", file=out)
        for issue in result.issues[:limit]:
            print(f"  {issue.category}: {issue.message}", file=out)
    else:
        print("Issues: none", file=out)


def print_suite_result(
    batch: SparkCompactReadinessBatchResult,
    *,
    out: TextIO | None = None,
    limit: int = 12,
) -> None:
    if out is None:
        out = sys.stdout
    status = "ok" if batch.ok else "failed"
    print(f"Spark compact readiness suite: {status}", file=out)
    print(
        "Inputs: "
        f"compact_json_count={batch.input_count}, "
        f"ok={batch.ok_count}, "
        f"failed={batch.failed_count}",
        file=out,
    )
    print(
        "Totals: "
        f"facts={batch.fact_count}, "
        f"attention_areas={batch.attention_area_count}, "
        f"supported_attention_areas={batch.supported_attention_area_count}, "
        f"source_warnings={batch.source_warning_count}",
        file=out,
    )
    print_counter("Source contracts", batch.source_contract_counts, out=out, limit=limit)
    print_counter("Support statuses", batch.support_status_counts, out=out, limit=limit)
    print_counter("Parser coverage", batch.parser_coverage_counts, out=out, limit=limit)
    print_counter("Lifecycles", batch.lifecycle_counts, out=out, limit=limit)
    print_counter("Fact scopes", batch.fact_scope_counts, out=out, limit=limit)
    print_counter("Fact states", batch.fact_state_counts, out=out, limit=limit)
    print_counter("Attention states", batch.attention_state_counts, out=out, limit=limit)
    print_counter("Limitation states", batch.limitation_state_counts, out=out, limit=limit)
    if batch.issues:
        print_counter("Issues", batch.issue_counts, out=out, limit=limit)
        print("Issue examples:", file=out)
        for index, issue in batch.issues[:limit]:
            label = "suite" if index is None else f"input-{index:03d}"
            print(f"  {label}: {issue.category}: {issue.message}", file=out)
    else:
        print("Issues: none", file=out)


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "compact_json",
        type=Path,
        nargs="+",
        help="Accepted Spark compact JSON input. Pass multiple paths for suite mode.",
    )
    parser.add_argument("--limit", type=int, default=12, help="Rows to print per section.")
    parser.add_argument(
        "--require-supported-attention",
        action="store_true",
        help="Return non-zero unless the diagnosis contains a supported Spark attention area.",
    )
    parser.add_argument(
        "--fail-on-source-warnings",
        action="store_true",
        help="Return non-zero when compact source warning IDs are present.",
    )
    parser.add_argument(
        "--require-min-inputs",
        type=positive_int,
        default=1,
        help="Require at least this many compact inputs in suite mode.",
    )
    parser.add_argument(
        "--require-source-contract",
        action="append",
        choices=sorted(ACCEPTED_SPARK_SOURCE_CONTRACTS),
        default=None,
        help=(
            "Require the suite to include at least one compact input with this source contract. "
            "May be repeated."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    required_source_contracts = args.require_source_contract or ()
    if len(args.compact_json) > 1 or args.require_min_inputs > 1 or required_source_contracts:
        batch = audit_compact_json_suite(
            args.compact_json,
            require_supported_attention=args.require_supported_attention,
            fail_on_source_warnings=args.fail_on_source_warnings,
            require_min_inputs=args.require_min_inputs,
            required_source_contracts=required_source_contracts,
        )
        print_suite_result(batch, limit=args.limit)
        return 0 if batch.ok else 1
    try:
        result = audit_compact_json(
            args.compact_json[0],
            require_supported_attention=args.require_supported_attention,
            fail_on_source_warnings=args.fail_on_source_warnings,
        )
    except SparkCompactReadinessInputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print_result(result, limit=args.limit)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
