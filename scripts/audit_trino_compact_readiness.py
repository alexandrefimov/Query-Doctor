#!/usr/bin/env python3
"""Audit Trino compact boundary readiness without making a support claim."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.analyzer.engine_fact_consumer import (  # noqa: E402
    FACT_GROUPS,
    engine_fact_consumer_probe_from_boundary,
)
from query_doctor.analyzer.engine_facts import (  # noqa: E402
    ENGINE_FACT_BOUNDARY_SCHEMA_VERSION,
    EngineFactContractError,
    engine_fact_namespace_definitions,
)
from query_doctor.report.safety_validation import (  # noqa: E402
    contains_raw_sql_like_text,
    validate_report_internal_fingerprints,
)
from query_doctor.safety import redaction  # noqa: E402
from query_doctor.trino.diagnosis import (  # noqa: E402
    TRINO_COMPACT_DIAGNOSIS_SUPPORT_STATUS,
    build_trino_compact_diagnosis_from_boundary,
)


EXPECTED_DIAGNOSIS_BOUNDARY = {
    "root_cause": "not_claimed",
    "details_trusted_report_surface": "not_wired",
    "optimizer_behavior": "not_wired",
    "trino_sql_execution": "not_performed",
    "live_recent_scan": "not_wired",
}
TRINO_SMOKE_SUMMARY_KIND = "trino_kerberos_smoke_summary_v1"
TRINO_SMOKE_BAD_STATUSES = frozenset(
    {
        "request_failed",
        "invalid_response",
        "too_large",
        "too_many_pages",
        "trino_error",
    }
)
REQUIRED_TRINO_LIMITATION_IDS = frozenset(
    {
        "no_live_trino_support",
        "no_browser_report_surface",
        "no_trino_sql_execution",
        "no_root_cause_claim",
    }
)
QUERY_LIST_FACT_PREFIX = "query_list_"
SOURCE_GRANULARITY_AGGREGATE_QUERY_LIST = "aggregate_query_list"
SOURCE_GRANULARITY_ONE_QUERY_BOUNDARY = "one_query_boundary"
LOCAL_PATH_RE = re.compile(
    r"(?<![\w/])(?:/private)?/(?:Users|home|tmp|var|etc)/[^\s<>'\"]+"
    r"|(?<![\w/])[A-Za-z]:\\[^\s<>'\"]+"
)
URL_RE = re.compile(r"\bhttps?://\S+", re.IGNORECASE)


class TrinoCompactReadinessInputError(RuntimeError):
    """Raised when boundary JSON cannot be loaded safely."""


@dataclass(frozen=True)
class TrinoCompactReadinessIssue:
    category: str
    message: str


@dataclass
class TrinoCompactReadinessResult:
    source_schema_version: str = "unknown"
    support_status: str = "unknown"
    parser_coverage: str = "unknown"
    lifecycle: str = "unknown"
    source_granularity: str = "unknown"
    diagnosis_artifact_checked: bool = False
    smoke_summary_checked: bool = False
    smoke_mode: str = "not_provided"
    fact_count: int = 0
    attention_area_count: int = 0
    supported_attention_area_count: int = 0
    fact_group_counts: Counter[str] = field(default_factory=Counter)
    fact_scope_counts: Counter[str] = field(default_factory=Counter)
    fact_state_counts: Counter[str] = field(default_factory=Counter)
    attention_state_counts: Counter[str] = field(default_factory=Counter)
    limitation_state_counts: Counter[str] = field(default_factory=Counter)
    smoke_status_counts: Counter[str] = field(default_factory=Counter)
    issue_counts: Counter[str] = field(default_factory=Counter)
    issues: list[TrinoCompactReadinessIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


@dataclass
class TrinoCompactReadinessBatchResult:
    input_count: int = 0
    ok_count: int = 0
    failed_count: int = 0
    fact_count: int = 0
    attention_area_count: int = 0
    supported_attention_area_count: int = 0
    source_schema_counts: Counter[str] = field(default_factory=Counter)
    support_status_counts: Counter[str] = field(default_factory=Counter)
    parser_coverage_counts: Counter[str] = field(default_factory=Counter)
    lifecycle_counts: Counter[str] = field(default_factory=Counter)
    source_granularity_counts: Counter[str] = field(default_factory=Counter)
    fact_group_counts: Counter[str] = field(default_factory=Counter)
    fact_scope_counts: Counter[str] = field(default_factory=Counter)
    fact_state_counts: Counter[str] = field(default_factory=Counter)
    attention_state_counts: Counter[str] = field(default_factory=Counter)
    limitation_state_counts: Counter[str] = field(default_factory=Counter)
    issue_counts: Counter[str] = field(default_factory=Counter)
    issues: list[tuple[int, TrinoCompactReadinessIssue]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.failed_count == 0


def load_json_object(path: Path, *, input_label: str = "boundary JSON input") -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise TrinoCompactReadinessInputError(f"{input_label} could not be read") from exc
    except json.JSONDecodeError as exc:
        raise TrinoCompactReadinessInputError(f"{input_label} is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise TrinoCompactReadinessInputError(f"{input_label} must be an object")
    return payload


def audit_boundary_json(
    boundary_json: Path,
    *,
    diagnosis_json: Path | None = None,
    smoke_summary_json: Path | None = None,
    require_executed_smoke: bool = False,
    require_supported_attention: bool = False,
    fail_on_unknown_parser_coverage: bool = False,
    require_one_query_boundary: bool = False,
) -> TrinoCompactReadinessResult:
    diagnosis_payload = (
        None
        if diagnosis_json is None
        else load_json_object(diagnosis_json, input_label="diagnosis JSON input")
    )
    smoke_summary_payload = (
        None
        if smoke_summary_json is None
        else load_json_object(smoke_summary_json, input_label="smoke summary JSON input")
    )
    return audit_boundary_payload(
        load_json_object(boundary_json),
        diagnosis_payload=diagnosis_payload,
        smoke_summary_payload=smoke_summary_payload,
        require_executed_smoke=require_executed_smoke,
        require_supported_attention=require_supported_attention,
        fail_on_unknown_parser_coverage=fail_on_unknown_parser_coverage,
        require_one_query_boundary=require_one_query_boundary,
    )


def audit_boundary_json_suite(
    boundary_jsons: Iterable[Path],
    *,
    require_supported_attention: bool = False,
    fail_on_unknown_parser_coverage: bool = False,
    require_one_query_boundary: bool = False,
) -> TrinoCompactReadinessBatchResult:
    batch = TrinoCompactReadinessBatchResult()
    for index, boundary_json in enumerate(boundary_jsons, start=1):
        batch.input_count += 1
        try:
            result = audit_boundary_json(
                boundary_json,
                require_supported_attention=require_supported_attention,
                fail_on_unknown_parser_coverage=fail_on_unknown_parser_coverage,
                require_one_query_boundary=require_one_query_boundary,
            )
        except TrinoCompactReadinessInputError:
            issue = TrinoCompactReadinessIssue(
                "boundary_input_unreadable",
                "One Trino boundary JSON input could not be read or parsed safely.",
            )
            batch.failed_count += 1
            batch.issue_counts[issue.category] += 1
            batch.issues.append((index, issue))
            continue
        add_suite_result(batch, index, result)
    return batch


def audit_boundary_payload(
    payload: Mapping[str, Any],
    *,
    diagnosis_payload: Mapping[str, Any] | None = None,
    smoke_summary_payload: Mapping[str, Any] | None = None,
    require_executed_smoke: bool = False,
    require_supported_attention: bool = False,
    fail_on_unknown_parser_coverage: bool = False,
    require_one_query_boundary: bool = False,
) -> TrinoCompactReadinessResult:
    result = TrinoCompactReadinessResult(
        source_schema_version=safe_label(payload.get("schema_version")),
    )
    audit_boundary_raw_free(result, payload)

    try:
        probe = engine_fact_consumer_probe_from_boundary(payload)
    except EngineFactContractError:
        add_issue(
            result,
            "boundary_contract_invalid",
            "Trino boundary JSON failed normalized fact-boundary validation.",
        )
        return result

    audit_probe_boundary(
        result,
        payload,
        probe,
        require_one_query_boundary=require_one_query_boundary,
    )

    try:
        diagnosis = build_trino_compact_diagnosis_from_boundary(payload)
    except EngineFactContractError:
        add_issue(
            result,
            "compact_diagnosis_invalid",
            "Trino compact diagnosis could not be built from accepted boundary facts.",
        )
        return result

    audit_diagnosis_boundary(result, diagnosis)
    audit_diagnosis_raw_free(result, diagnosis)
    if diagnosis_payload is not None:
        audit_diagnosis_artifact(result, diagnosis_payload, expected_diagnosis=diagnosis)
    if smoke_summary_payload is not None:
        audit_smoke_summary(
            result,
            smoke_summary_payload,
            require_executed_smoke=require_executed_smoke,
        )
    if require_supported_attention and result.supported_attention_area_count <= 0:
        add_issue(
            result,
            "missing_supported_attention_area",
            "Strict readiness requires at least one supported Trino attention area.",
        )
    if fail_on_unknown_parser_coverage and result.parser_coverage == "unknown":
        add_issue(
            result,
            "trino_parser_coverage_unknown",
            "Strict readiness requires supported Trino parser coverage.",
        )
    return result


def audit_diagnosis_artifact(
    result: TrinoCompactReadinessResult,
    diagnosis_payload: Mapping[str, Any],
    *,
    expected_diagnosis: Mapping[str, Any],
) -> None:
    result.diagnosis_artifact_checked = True
    audit_diagnosis_raw_free(result, diagnosis_payload)
    if json_compatible(diagnosis_payload) != json_compatible(expected_diagnosis):
        add_issue(
            result,
            "diagnosis_artifact_mismatch",
            "Trino compact diagnosis artifact must match the deterministic diagnosis built from the boundary.",
        )


def audit_smoke_summary(
    result: TrinoCompactReadinessResult,
    smoke_summary_payload: Mapping[str, Any],
    *,
    require_executed_smoke: bool,
) -> None:
    result.smoke_summary_checked = True
    text = json.dumps(smoke_summary_payload, ensure_ascii=True, sort_keys=True)
    for category in raw_text_issue_categories(text):
        add_issue(
            result,
            "smoke_summary_raw_boundary",
            f"Trino smoke summary contains raw-like {category} content.",
        )
    if smoke_summary_payload.get("summary_kind") != TRINO_SMOKE_SUMMARY_KIND:
        add_issue(
            result,
            "smoke_summary_contract_invalid",
            "Trino smoke summary must use the expected summary kind.",
        )
    result.smoke_mode = safe_label(smoke_summary_payload.get("mode"))
    if result.smoke_mode not in {"dry_run", "execute"}:
        add_issue(
            result,
            "smoke_summary_contract_invalid",
            "Trino smoke summary mode must be dry_run or execute.",
        )
    if require_executed_smoke and result.smoke_mode != "execute":
        add_issue(
            result,
            "smoke_summary_not_executed",
            "Strict Trino readiness requires an executed Kerberos/SPNEGO smoke summary.",
        )
    checks = list_of_mappings(smoke_summary_payload.get("checks"))
    if not checks:
        add_issue(
            result,
            "smoke_summary_contract_invalid",
            "Trino smoke summary must contain at least one smoke check.",
        )
    for check in checks:
        status = safe_label(check.get("status"))
        result.smoke_status_counts[status] += 1
        if status in TRINO_SMOKE_BAD_STATUSES:
            add_issue(
                result,
                "smoke_summary_failed_check",
                "Trino smoke summary must not contain failed smoke checks.",
            )


def audit_probe_boundary(
    result: TrinoCompactReadinessResult,
    payload: Mapping[str, Any],
    probe: Mapping[str, Any],
    *,
    require_one_query_boundary: bool = False,
) -> None:
    if probe.get("engine") != "trino":
        add_issue(
            result,
            "boundary_engine_mismatch",
            "Trino readiness accepts only engine=trino boundaries.",
        )
        return
    result.source_schema_version = safe_label(probe.get("source_schema_version"))
    result.parser_coverage = safe_label(probe.get("parser_coverage"))
    result.lifecycle = safe_label(probe.get("lifecycle"))
    result.fact_state_counts.update(safe_counter(probe.get("state_counts")))

    fact_groups = mapping(payload.get("fact_groups"))
    definitions = {
        definition.fact_id: definition for definition in engine_fact_namespace_definitions()
    }
    query_list_fact_seen = False
    for group in FACT_GROUPS:
        facts = list_of_mappings(fact_groups.get(group))
        result.fact_group_counts[group] += len(facts)
        result.fact_count += len(facts)
        for fact in facts:
            fact_id = fact.get("id")
            if not isinstance(fact_id, str):
                continue
            if fact_id.startswith(QUERY_LIST_FACT_PREFIX):
                query_list_fact_seen = True
            definition = definitions.get(fact_id)
            if definition is None:
                result.fact_scope_counts["unregistered"] += 1
                add_issue(
                    result,
                    "trino_fact_unregistered",
                    "Trino boundary facts must use registered fact identifiers.",
                )
                continue
            result.fact_scope_counts[definition.scope] += 1
            if definition.scope == "shared":
                add_issue(
                    result,
                    "trino_fact_promoted_to_shared_scope",
                    "Trino facts must not move into shared scope without a promotion gate.",
                )
            if definition.scope == "engine_specific" and fact_id.startswith(("impala_", "spark_")):
                add_issue(
                    result,
                    "trino_engine_fact_foreign_prefix",
                    "Trino engine-specific facts must not borrow another engine prefix.",
                )
    result.source_granularity = (
        SOURCE_GRANULARITY_AGGREGATE_QUERY_LIST
        if query_list_fact_seen
        else SOURCE_GRANULARITY_ONE_QUERY_BOUNDARY
    )
    if require_one_query_boundary and query_list_fact_seen:
        add_issue(
            result,
            "trino_query_list_aggregate_not_one_query",
            "Strict one-query readiness must not use aggregate query-list boundary facts.",
        )


def audit_diagnosis_boundary(
    result: TrinoCompactReadinessResult,
    diagnosis: Mapping[str, Any],
) -> None:
    if diagnosis.get("engine") != "trino":
        add_issue(
            result,
            "diagnosis_engine_mismatch",
            "Trino compact diagnosis must stay on engine=trino.",
        )
    result.support_status = safe_label(diagnosis.get("support_status"))
    if result.support_status != TRINO_COMPACT_DIAGNOSIS_SUPPORT_STATUS:
        add_issue(
            result,
            "trino_support_claim_boundary",
            "Trino compact diagnosis must stay below live product support.",
        )

    boundary = diagnosis.get("diagnosis_boundary")
    if not isinstance(boundary, Mapping):
        add_issue(
            result,
            "missing_diagnosis_boundary",
            "Trino compact diagnosis must publish an explicit no-claim boundary.",
        )
    else:
        for key, expected in EXPECTED_DIAGNOSIS_BOUNDARY.items():
            if boundary.get(key) != expected:
                add_issue(
                    result,
                    "trino_diagnosis_boundary_drift",
                    "Trino compact diagnosis boundary no longer matches the no-claim contract.",
                )

    attention_areas = list_of_mappings(diagnosis.get("attention_areas"))
    result.attention_area_count = len(attention_areas)
    for area in attention_areas:
        state = safe_label(area.get("state"))
        result.attention_state_counts[state] += 1
        if state == "supported":
            result.supported_attention_area_count += 1

    limitations = list_of_mappings(diagnosis.get("limitations"))
    limitation_ids: set[str] = set()
    for limitation in limitations:
        limitation_id = limitation.get("id")
        if isinstance(limitation_id, str):
            limitation_ids.add(limitation_id)
        result.limitation_state_counts[safe_label(limitation.get("state"))] += 1
    missing_limitations = REQUIRED_TRINO_LIMITATION_IDS - limitation_ids
    if missing_limitations:
        add_issue(
            result,
            "trino_limitation_boundary_missing",
            "Trino compact diagnosis must keep explicit support and no-claim limitations.",
        )


def audit_boundary_raw_free(
    result: TrinoCompactReadinessResult,
    payload: Mapping[str, Any],
) -> None:
    text = json.dumps(payload, ensure_ascii=True, sort_keys=True)
    for category in raw_text_issue_categories(text):
        add_issue(
            result,
            "boundary_raw_boundary",
            f"Trino boundary JSON contains raw-like {category} content.",
        )


def audit_diagnosis_raw_free(
    result: TrinoCompactReadinessResult,
    diagnosis: Mapping[str, Any],
) -> None:
    text = json.dumps(diagnosis, ensure_ascii=True, sort_keys=True)
    for category in raw_text_issue_categories(text):
        add_issue(
            result,
            "diagnosis_raw_boundary",
            f"Trino compact diagnosis contains raw-like {category} content.",
        )


def raw_text_issue_categories(text: str) -> tuple[str, ...]:
    categories: list[str] = []
    if contains_raw_sql_like_text(text):
        categories.append("sql")
    if validate_report_internal_fingerprints(text):
        categories.append("internal_fingerprint")
    if redaction.EMAIL_RE.search(text):
        categories.append("email")
    if redaction.IPV4_RE.search(text):
        categories.append("ipv4")
    if redaction.HOSTLIKE_FQDN_RE.search(text):
        categories.append("hostname")
    if URL_RE.search(text):
        categories.append("url")
    if LOCAL_PATH_RE.search(text):
        categories.append("local_path")
    if redaction.SECRET_VALUE_RE.search(text):
        categories.append("secret")
    return tuple(sorted(set(categories)))


def add_issue(
    result: TrinoCompactReadinessResult,
    category: str,
    message: str,
) -> None:
    result.issue_counts[category] += 1
    result.issues.append(TrinoCompactReadinessIssue(category, message))


def add_suite_result(
    batch: TrinoCompactReadinessBatchResult,
    index: int,
    result: TrinoCompactReadinessResult,
) -> None:
    if result.ok:
        batch.ok_count += 1
    else:
        batch.failed_count += 1
    batch.fact_count += result.fact_count
    batch.attention_area_count += result.attention_area_count
    batch.supported_attention_area_count += result.supported_attention_area_count
    batch.source_schema_counts[result.source_schema_version] += 1
    batch.support_status_counts[result.support_status] += 1
    batch.parser_coverage_counts[result.parser_coverage] += 1
    batch.lifecycle_counts[result.lifecycle] += 1
    batch.source_granularity_counts[result.source_granularity] += 1
    batch.fact_group_counts.update(result.fact_group_counts)
    batch.fact_scope_counts.update(result.fact_scope_counts)
    batch.fact_state_counts.update(result.fact_state_counts)
    batch.attention_state_counts.update(result.attention_state_counts)
    batch.limitation_state_counts.update(result.limitation_state_counts)
    batch.issue_counts.update(result.issue_counts)
    for issue in result.issues:
        batch.issues.append((index, issue))


def print_counter(title: str, counter: Counter[str], *, out: TextIO, limit: int) -> None:
    print(f"{title}:", file=out)
    if not counter:
        print("  <none>", file=out)
        return
    for key, count in counter.most_common(limit):
        print(f"  {key}: {count}", file=out)


def print_result(
    result: TrinoCompactReadinessResult,
    *,
    out: TextIO | None = None,
    limit: int = 12,
) -> None:
    if out is None:
        out = sys.stdout
    status = "ok" if result.ok else "failed"
    print(f"Trino compact readiness: {status}", file=out)
    print("Input: boundary_json", file=out)
    print(
        "Boundary: "
        f"support_status={result.support_status}, "
        "root_cause=not_claimed, "
        "trino_sql_execution=not_performed, "
        "live_recent_scan=not_wired",
        file=out,
    )
    print(
        "Source: "
        f"schema={result.source_schema_version}, "
        f"parser_coverage={result.parser_coverage}, "
        f"lifecycle={result.lifecycle}, "
        f"granularity={result.source_granularity}",
        file=out,
    )
    print(
        f"Diagnosis artifact: {'checked' if result.diagnosis_artifact_checked else 'not_provided'}",
        file=out,
    )
    print(
        "Smoke summary: "
        f"{'checked' if result.smoke_summary_checked else 'not_provided'}, "
        f"mode={result.smoke_mode}",
        file=out,
    )
    print(
        "Facts: "
        f"total={result.fact_count}, "
        f"attention_areas={result.attention_area_count}, "
        f"supported_attention_areas={result.supported_attention_area_count}",
        file=out,
    )
    print_counter("Fact groups", result.fact_group_counts, out=out, limit=limit)
    print_counter("Fact scopes", result.fact_scope_counts, out=out, limit=limit)
    print_counter("Fact states", result.fact_state_counts, out=out, limit=limit)
    print_counter("Attention states", result.attention_state_counts, out=out, limit=limit)
    print_counter("Limitation states", result.limitation_state_counts, out=out, limit=limit)
    print_counter("Smoke statuses", result.smoke_status_counts, out=out, limit=limit)
    if result.issues:
        print_counter("Issues", result.issue_counts, out=out, limit=limit)
        print("Issue examples:", file=out)
        for issue in result.issues[:limit]:
            print(f"  {issue.category}: {issue.message}", file=out)
    else:
        print("Issues: none", file=out)


def print_suite_result(
    batch: TrinoCompactReadinessBatchResult,
    *,
    out: TextIO | None = None,
    limit: int = 12,
) -> None:
    if out is None:
        out = sys.stdout
    status = "ok" if batch.ok else "failed"
    print(f"Trino compact readiness suite: {status}", file=out)
    print(
        "Inputs: "
        f"boundary_json_count={batch.input_count}, "
        f"ok={batch.ok_count}, "
        f"failed={batch.failed_count}",
        file=out,
    )
    print(
        "Totals: "
        f"facts={batch.fact_count}, "
        f"attention_areas={batch.attention_area_count}, "
        f"supported_attention_areas={batch.supported_attention_area_count}",
        file=out,
    )
    print_counter("Source schemas", batch.source_schema_counts, out=out, limit=limit)
    print_counter("Support statuses", batch.support_status_counts, out=out, limit=limit)
    print_counter("Parser coverage", batch.parser_coverage_counts, out=out, limit=limit)
    print_counter("Lifecycles", batch.lifecycle_counts, out=out, limit=limit)
    print_counter("Source granularity", batch.source_granularity_counts, out=out, limit=limit)
    print_counter("Fact groups", batch.fact_group_counts, out=out, limit=limit)
    print_counter("Fact scopes", batch.fact_scope_counts, out=out, limit=limit)
    print_counter("Fact states", batch.fact_state_counts, out=out, limit=limit)
    print_counter("Attention states", batch.attention_state_counts, out=out, limit=limit)
    print_counter("Limitation states", batch.limitation_state_counts, out=out, limit=limit)
    if batch.issues:
        print_counter("Issues", batch.issue_counts, out=out, limit=limit)
        print("Issue examples:", file=out)
        for index, issue in batch.issues[:limit]:
            print(f"  input-{index:03d}: {issue.category}: {issue.message}", file=out)
    else:
        print("Issues: none", file=out)


def list_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def safe_counter(value: Any) -> Counter[str]:
    counter: Counter[str] = Counter()
    if not isinstance(value, Mapping):
        return counter
    for key, count in value.items():
        if isinstance(key, str) and isinstance(count, int) and not isinstance(count, bool):
            counter[key] += count
    return counter


def safe_label(value: Any) -> str:
    return value if isinstance(value, str) and value else "unknown"


def json_compatible(value: Mapping[str, Any]) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=True, sort_keys=True))


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "boundary_json",
        type=Path,
        nargs="+",
        help="Accepted Trino engine_fact_boundary_v1 JSON. Pass multiple paths for suite mode.",
    )
    parser.add_argument("--limit", type=int, default=12, help="Rows to print per section.")
    parser.add_argument(
        "--require-supported-attention",
        action="store_true",
        help="Return non-zero unless the diagnosis contains a supported Trino attention area.",
    )
    parser.add_argument(
        "--fail-on-unknown-parser-coverage",
        action="store_true",
        help="Return non-zero when parser coverage remains unknown.",
    )
    parser.add_argument(
        "--require-one-query-boundary",
        action="store_true",
        help=(
            "Return non-zero for aggregate query-list boundaries; use this for one-query "
            "Trino diagnosis readiness gates."
        ),
    )
    parser.add_argument(
        "--diagnosis-json",
        type=Path,
        default=None,
        help=(
            "Optional compact diagnosis JSON artifact written from the same boundary. "
            "Only valid with one boundary JSON input; the path is never printed."
        ),
    )
    parser.add_argument(
        "--smoke-summary",
        type=Path,
        default=None,
        help=(
            "Optional trino_smoke_summary.json artifact from the dev-only Kerberos/SPNEGO "
            "smoke. Only valid with one boundary JSON input; the path is never printed."
        ),
    )
    parser.add_argument(
        "--require-executed-smoke",
        action="store_true",
        help="Return non-zero unless --smoke-summary records mode=execute.",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    if args.diagnosis_json is not None and len(args.boundary_json) > 1:
        print(
            "[trino-compact-readiness] rejected: diagnosis artifact checking accepts one boundary input",
            file=sys.stderr,
        )
        return 2
    if args.smoke_summary is not None and len(args.boundary_json) > 1:
        print(
            "[trino-compact-readiness] rejected: smoke summary checking accepts one boundary input",
            file=sys.stderr,
        )
        return 2
    if args.require_executed_smoke and args.smoke_summary is None:
        print(
            "[trino-compact-readiness] rejected: --require-executed-smoke requires --smoke-summary",
            file=sys.stderr,
        )
        return 2
    if len(args.boundary_json) > 1:
        batch = audit_boundary_json_suite(
            args.boundary_json,
            require_supported_attention=args.require_supported_attention,
            fail_on_unknown_parser_coverage=args.fail_on_unknown_parser_coverage,
            require_one_query_boundary=args.require_one_query_boundary,
        )
        print_suite_result(batch, limit=args.limit)
        return 0 if batch.ok else 1
    try:
        result = audit_boundary_json(
            args.boundary_json[0],
            diagnosis_json=args.diagnosis_json,
            smoke_summary_json=args.smoke_summary,
            require_executed_smoke=args.require_executed_smoke,
            require_supported_attention=args.require_supported_attention,
            fail_on_unknown_parser_coverage=args.fail_on_unknown_parser_coverage,
            require_one_query_boundary=args.require_one_query_boundary,
        )
    except TrinoCompactReadinessInputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print_result(result, limit=args.limit)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
