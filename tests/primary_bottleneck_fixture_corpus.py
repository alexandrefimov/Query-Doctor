import json
import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


PRIMARY_BOTTLENECK_FIXTURE_DIR = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "primary_bottleneck_fixtures"
)
PRIMARY_BOTTLENECK_FIXTURE_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*\.json$")
PRIMARY_BOTTLENECK_FIXTURE_KEYS = frozenset({"analysis", "expected"})
PRIMARY_BOTTLENECK_EXPECTED_KEYS = frozenset({"label", "confidence", "reasons"})

# Keep the compact fixture corpus representative as classifier taxonomy grows.
PRIMARY_BOTTLENECK_FIXTURE_LABELS = frozenset(
    {
        "client_fetch_tail",
        "mixed",
        "runtime_admission",
        "runtime_data_movement",
        "runtime_memory",
        "runtime_skew",
        "runtime_storage",
        "sql_shape",
        "stats",
        "unknown",
    }
)
PRIMARY_BOTTLENECK_FIXTURE_CONFIDENCES = frozenset({"low", "medium", "high"})
UNKNOWN_PRIMARY_REASON_COVERAGE = frozenset(
    {
        "codegen_finding_not_primary_supported",
        "data_movement_context_only",
        "memory_estimate_context_only",
        "no_primary_branch_supported",
        "profile_dialect_not_supported_for_primary",
        "scan_skew_medium_supporting_only",
        "storage_context_view_only",
        "very_short_query_or_unknown_wall_clock",
        "wall_clock_not_explained_by_mapped_operators",
    }
)
PRIMARY_BOTTLENECK_REASON_FAMILIES = {
    "client_fetch_tail": (
        "client_fetch_wait_top_finding",
        "client_fetch_wait_share_*",
    ),
    "mixed": (
        "competing_client_fetch_tail",
        "competing_runtime_data_movement",
        "competing_runtime_memory",
        "competing_runtime_skew",
        "competing_runtime_storage",
        "competing_sql_shape",
        "competing_stats",
    ),
    "runtime_admission": (
        "admission_timed_out",
        "admission_wait_explicit",
        "admission_wait_share_*",
        "admission_wait_source_profile_resource_facts",
        "admission_wait_source_profile_timing_facts",
        "admission_wait_source_query_context",
    ),
    "runtime_data_movement": ("large_intermediate_or_exchange_top_finding",),
    "runtime_memory": (
        "memory_pressure_spill_scratch_supported",
        "spill_scratch_counters_*",
    ),
    "runtime_skew": (
        "execution_tail_top_finding",
        "scan_skew_bytes_read",
        "scan_skew_rows_produced",
        "tail_candidates_*",
    ),
    "runtime_storage": (
        "storage_or_hdfs_runtime_diagnosis",
        "storage_or_hdfs_top_finding",
    ),
    "sql_shape": (
        "aggregate_memory_estimate_top_finding",
        "analytic_top_finding",
        "join_top_finding",
        "sort_top_finding",
        "stats_not_primary",
    ),
    "stats": (
        "cardinality_anomalies_*",
        "stats_candidate_supported",
    ),
}
PRIMARY_BOTTLENECK_EXACT_REASON_IDS = (
    frozenset(
        reason
        for reasons in PRIMARY_BOTTLENECK_REASON_FAMILIES.values()
        for reason in reasons
        if not reason.endswith("*")
    )
    | UNKNOWN_PRIMARY_REASON_COVERAGE
)
PRIMARY_BOTTLENECK_REASON_PATTERNS = (
    re.compile(r"^admission_wait_share_[0-9]+pct$"),
    re.compile(r"^cardinality_anomalies_[0-9]+$"),
    re.compile(r"^client_fetch_wait_share_[0-9]+pct$"),
    re.compile(r"^spill_scratch_counters_[0-9]+$"),
    re.compile(r"^tail_candidates_[0-9]+$"),
)


@dataclass(frozen=True)
class PrimaryBottleneckFixtureCoverage:
    covered_labels: frozenset[str]
    covered_confidences: frozenset[str]
    unknown_reasons: frozenset[str]
    reasons_by_label: dict[str, frozenset[str]]
    missing_reason_families: dict[str, tuple[str, ...]]


def primary_bottleneck_fixture_names() -> list[str]:
    return sorted(path.name for path in PRIMARY_BOTTLENECK_FIXTURE_DIR.glob("*.json"))


def primary_bottleneck_fixture_payloads() -> dict[str, dict]:
    return {
        fixture_name: json.loads(
            (PRIMARY_BOTTLENECK_FIXTURE_DIR / fixture_name).read_text(encoding="utf-8")
        )
        for fixture_name in primary_bottleneck_fixture_names()
    }


def primary_bottleneck_fixture_expected_results() -> tuple[dict, ...]:
    return tuple(payload["expected"] for payload in primary_bottleneck_fixture_payloads().values())


def primary_bottleneck_fixture_coverage(
    expected_results: Optional[Sequence[dict]] = None,
) -> PrimaryBottleneckFixtureCoverage:
    if expected_results is None:
        expected_results = primary_bottleneck_fixture_expected_results()

    covered_labels = frozenset(str(expected["label"]) for expected in expected_results)
    covered_confidences = frozenset(str(expected["confidence"]) for expected in expected_results)
    reasons_by_label = {
        label: frozenset(
            str(reason)
            for expected in expected_results
            if expected["label"] == label
            for reason in expected.get("reasons", [])
        )
        for label in PRIMARY_BOTTLENECK_FIXTURE_LABELS
    }
    missing_reason_families = {
        label: tuple(
            expected_reason
            for expected_reason in required_reasons
            if not reason_family_is_covered(
                reasons_by_label.get(label, frozenset()), expected_reason
            )
        )
        for label, required_reasons in PRIMARY_BOTTLENECK_REASON_FAMILIES.items()
    }
    missing_reason_families = {
        label: missing for label, missing in missing_reason_families.items() if missing
    }

    return PrimaryBottleneckFixtureCoverage(
        covered_labels=covered_labels,
        covered_confidences=covered_confidences,
        unknown_reasons=reasons_by_label["unknown"],
        reasons_by_label=reasons_by_label,
        missing_reason_families=missing_reason_families,
    )


def reason_family_is_covered(reasons: Collection[str], expected: str) -> bool:
    if expected.endswith("*"):
        return any(reason.startswith(expected[:-1]) for reason in reasons)
    return expected in reasons


def reason_id_is_known(reason: str) -> bool:
    return reason in PRIMARY_BOTTLENECK_EXACT_REASON_IDS or any(
        pattern.fullmatch(reason) for pattern in PRIMARY_BOTTLENECK_REASON_PATTERNS
    )
