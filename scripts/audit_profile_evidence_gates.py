#!/usr/bin/env python3
"""Audit profile-derived evidence gates for an existing batch summary."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, TextIO


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.analyzer.case_bottleneck import (  # noqa: E402
    client_fetch_primary_supported,
    per_instance_evidence_supports_profile_claims,
    primary_bottleneck_profile_policy,
    runtime_diagnosis_supports_storage,
    top_finding_id,
)
from query_doctor.analyzer.profile_evidence import (  # noqa: E402
    profile_data_movement_primary_supported,
    profile_storage_supported,
)
from query_doctor.analyzer.runtime_admission import (  # noqa: E402
    runtime_admission_facts_from_analysis,
    runtime_admission_uses_non_profile_evidence,
)
from query_doctor.analyzer.scan_skew import scan_skew_facts_from_analysis  # noqa: E402


PROFILE_PRIMARY_LABELS = {
    "client_fetch_tail",
    "runtime_admission",
    "runtime_data_movement",
    "runtime_skew",
    "runtime_storage",
}
STABLE_COUNTER_LABELS = {"STABLE_HIGH", "STABLE_LOW"}


@dataclass(frozen=True)
class EvidenceGateIssue:
    case_ref: str
    category: str
    message: str


@dataclass
class EvidenceGateAuditResult:
    summary_path: Path
    total_cases: int = 0
    analyzed_cases: int = 0
    missing_analysis_count: int = 0
    analysis_error_count: int = 0
    severity_counts: Counter[str] = field(default_factory=Counter)
    primary_counts: Counter[str] = field(default_factory=Counter)
    primary_confidence_counts: Counter[str] = field(default_factory=Counter)
    profile_dialect_counts: Counter[str] = field(default_factory=Counter)
    profile_policy_counts: Counter[str] = field(default_factory=Counter)
    profile_counter_registry_counts: Counter[str] = field(default_factory=Counter)
    evidence_quality_counts: Counter[str] = field(default_factory=Counter)
    client_fetch_counts: Counter[str] = field(default_factory=Counter)
    admission_counts: Counter[str] = field(default_factory=Counter)
    memory_pressure_counts: Counter[str] = field(default_factory=Counter)
    backend_tail_counts: Counter[str] = field(default_factory=Counter)
    scan_skew_counts: Counter[str] = field(default_factory=Counter)
    runtime_filter_counts: Counter[str] = field(default_factory=Counter)
    storage_context_counts: Counter[str] = field(default_factory=Counter)
    issue_counts: Counter[str] = field(default_factory=Counter)
    issues: list[EvidenceGateIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues and not self.analysis_error_count


class EvidenceGateAuditInputError(RuntimeError):
    """Raised when an input batch summary cannot be audited."""


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise EvidenceGateAuditInputError(f"cannot read JSON: {path}") from exc
    except json.JSONDecodeError as exc:
        raise EvidenceGateAuditInputError(f"invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise EvidenceGateAuditInputError(f"JSON root is not an object: {path}")
    return payload


def summary_cases(summary: dict[str, Any]) -> list[dict[str, Any]]:
    cases = summary.get("cases")
    if not isinstance(cases, list):
        raise EvidenceGateAuditInputError("summary does not contain a cases list")
    return [case for case in cases if isinstance(case, dict)]


def case_ref(case: dict[str, Any]) -> str:
    try:
        index = int(case.get("case_index"))
    except (TypeError, ValueError):
        return "case-unknown"
    if index <= 0:
        return "case-unknown"
    return f"case-{index:03d}"


def resolve_case_dir(summary_path: Path, case: dict[str, Any]) -> Path | None:
    raw = case.get("case_dir")
    if not isinstance(raw, str) or not raw.strip():
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = summary_path.parent / path
    return path


def analysis_path_for(case_dir: Path) -> Path | None:
    direct = case_dir / "analysis.json"
    if direct.is_file():
        return direct
    nested = sorted(path for path in case_dir.glob("*/analysis.json") if path.is_file())
    return nested[0] if nested else None


def text_value(value: Any, default: str = "unknown") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "supported"}


def int_value(value: Any) -> int:
    try:
        return max(0, int(float(str(value).strip())))
    except (TypeError, ValueError):
        return 0


def counter_bucket(*parts: object) -> str:
    return "/".join(text_value(part) for part in parts)


def add_issue(
    result: EvidenceGateAuditResult,
    case: dict[str, Any],
    category: str,
    message: str,
) -> None:
    result.issue_counts[category] += 1
    result.issues.append(EvidenceGateIssue(case_ref(case), category, message))


def audit_summary(summary_path: Path) -> EvidenceGateAuditResult:
    summary_path = summary_path.resolve(strict=True)
    summary = load_json_object(summary_path)
    cases = summary_cases(summary)
    result = EvidenceGateAuditResult(summary_path=summary_path, total_cases=len(cases))

    for case in cases:
        result.severity_counts[text_value(case.get("score_severity"))] += 1
        primary = case.get("case_primary_bottleneck")
        primary = primary if isinstance(primary, dict) else {}
        primary_label = text_value(primary.get("label"))
        primary_confidence = text_value(primary.get("confidence"))
        result.primary_counts[primary_label] += 1
        result.primary_confidence_counts[counter_bucket(primary_label, primary_confidence)] += 1

        case_dir = resolve_case_dir(summary_path, case)
        analysis_path = analysis_path_for(case_dir) if case_dir is not None else None
        if analysis_path is None:
            result.missing_analysis_count += 1
            continue
        try:
            analysis = load_json_object(analysis_path)
        except EvidenceGateAuditInputError:
            result.analysis_error_count += 1
            continue
        audit_analysis(result, case, analysis, primary_label)
    return result


def audit_analysis(
    result: EvidenceGateAuditResult,
    case: dict[str, Any],
    analysis: dict[str, Any],
    primary_label: str,
) -> None:
    result.analyzed_cases += 1
    profile = analysis.get("profile_format")
    profile = profile if isinstance(profile, dict) else {}
    profile_policy = primary_bottleneck_profile_policy(analysis)
    profile_dialect = text_value(profile.get("profile_dialect"))
    result.profile_dialect_counts[profile_dialect] += 1
    result.profile_policy_counts[profile_policy] += 1

    registry = analysis.get("profile_counter_registry")
    registry = registry if isinstance(registry, dict) else {}
    result.profile_counter_registry_counts[
        counter_bucket(registry.get("status"), registry.get("source"))
    ] += 1

    evidence_quality = analysis.get("evidence_quality")
    evidence_quality = evidence_quality if isinstance(evidence_quality, dict) else {}
    result.evidence_quality_counts[text_value(evidence_quality.get("level"))] += 1

    audit_client_fetch(result, case, analysis)
    audit_runtime_admission(result, case, analysis)
    audit_memory_pressure(result, case, analysis)
    audit_backend_tail(result, analysis)
    audit_scan_skew(result, case, analysis)
    audit_runtime_filters(result, case, analysis)
    audit_storage_context(result, analysis)
    audit_primary_consistency(result, case, analysis, primary_label, profile_policy)


def audit_client_fetch(
    result: EvidenceGateAuditResult,
    case: dict[str, Any],
    analysis: dict[str, Any],
) -> None:
    facts = analysis.get("client_fetch")
    facts = facts if isinstance(facts, dict) else {}
    finding_supported = bool_value(facts.get("finding_supported"))
    primary_supported = bool_value(facts.get("primary_supported"))
    stability = text_value(facts.get("counter_stability"), "UNKNOWN")
    result.client_fetch_counts[
        counter_bucket(
            facts.get("status"),
            facts.get("evidence_tier"),
            stability,
            f"finding={finding_supported}",
            f"primary={primary_supported}",
        )
    ] += 1
    if (finding_supported or primary_supported) and stability not in STABLE_COUNTER_LABELS:
        add_issue(
            result,
            case,
            "client_fetch_unstable_counter_promotion",
            "client fetch promoted without a stable counter label",
        )
    if primary_supported and not client_fetch_primary_supported(analysis):
        add_issue(
            result,
            case,
            "client_fetch_primary_gate_mismatch",
            "client fetch primary_supported disagrees with primary gate",
        )


def audit_runtime_admission(
    result: EvidenceGateAuditResult,
    case: dict[str, Any],
    analysis: dict[str, Any],
) -> None:
    facts = runtime_admission_facts_from_analysis(analysis)
    result.admission_counts[
        counter_bucket(
            facts.status,
            facts.evidence_tier,
            f"primary={facts.primary_supported}",
            text_value(facts.admission_result),
        )
    ] += 1
    if facts.primary_supported and facts.evidence_tier not in {"strong", "medium"}:
        add_issue(
            result,
            case,
            "admission_weak_primary_promotion",
            "runtime admission primary support lacks strong or medium evidence",
        )


def audit_memory_pressure(
    result: EvidenceGateAuditResult,
    case: dict[str, Any],
    analysis: dict[str, Any],
) -> None:
    facts = analysis.get("memory_pressure")
    facts = facts if isinstance(facts, dict) else {}
    finding_supported = bool_value(facts.get("finding_supported"))
    spill_count = int_value(facts.get("spill_or_scratch_evidence_count"))
    result.memory_pressure_counts[
        counter_bucket(
            facts.get("status"),
            facts.get("evidence_tier"),
            f"finding={finding_supported}",
            f"spill={spill_count > 0}",
        )
    ] += 1
    if finding_supported and spill_count <= 0:
        add_issue(
            result,
            case,
            "memory_pressure_without_spill_evidence",
            "memory pressure finding promoted without selected-query spill/scratch evidence",
        )


def audit_backend_tail(result: EvidenceGateAuditResult, analysis: dict[str, Any]) -> None:
    facts = analysis.get("backend_tail")
    facts = facts if isinstance(facts, dict) else {}
    result.backend_tail_counts[
        counter_bucket(
            f"execution_skew={text_value(facts.get('execution_skew'))}",
            f"execution_tail_candidates={min(int_value(facts.get('execution_tail_candidate_count')), 4)}",
            f"data_skew={text_value(facts.get('data_skew'))}",
        )
    ] += 1


def backend_execution_tail_primary_supported(analysis: dict[str, Any]) -> bool:
    facts = analysis.get("backend_tail")
    facts = facts if isinstance(facts, dict) else {}
    return bool(
        primary_bottleneck_profile_policy(analysis) == "supported"
        and per_instance_evidence_supports_profile_claims(analysis)
        and text_value(facts.get("execution_skew"), "no").lower() == "yes"
        and int_value(facts.get("execution_tail_candidate_count")) >= 1
        and top_finding_id(analysis) == "host_execution_tail_suspected"
    )


def audit_scan_skew(
    result: EvidenceGateAuditResult,
    case: dict[str, Any],
    analysis: dict[str, Any],
) -> None:
    facts = scan_skew_facts_from_analysis(analysis)
    result.scan_skew_counts[
        counter_bucket(
            facts.status,
            facts.evidence_tier,
            f"finding={facts.finding_supported}",
            f"primary={facts.primary_supported}",
            f"hosts={min(facts.skew_group_host_count, 4)}",
            f"corroborating={min(facts.corroborating_metric_count, 4)}",
        )
    ] += 1
    if facts.primary_supported and facts.evidence_tier != "strong":
        add_issue(
            result,
            case,
            "scan_skew_weak_primary_promotion",
            "scan skew primary support lacks strong evidence",
        )
    if facts.primary_supported and facts.skew_group_host_count < 2:
        add_issue(
            result,
            case,
            "scan_skew_single_host_primary",
            "scan skew primary support requires a multi-host group",
        )


def audit_runtime_filters(
    result: EvidenceGateAuditResult,
    case: dict[str, Any],
    analysis: dict[str, Any],
) -> None:
    facts = analysis.get("runtime_filters")
    facts = facts if isinstance(facts, dict) else {}
    finding_supported = bool_value(facts.get("finding_supported"))
    primary_supported = bool_value(facts.get("primary_supported"))
    result.runtime_filter_counts[
        counter_bucket(
            facts.get("status"),
            facts.get("evidence_tier"),
            f"finding={finding_supported}",
            f"primary={primary_supported}",
        )
    ] += 1
    if finding_supported or primary_supported:
        add_issue(
            result,
            case,
            "runtime_filter_promoted",
            "runtime filter evidence is expected to remain context-only",
        )


def audit_storage_context(result: EvidenceGateAuditResult, analysis: dict[str, Any]) -> None:
    facts = analysis.get("storage_context")
    facts = facts if isinstance(facts, dict) else {}
    result.storage_context_counts[
        counter_bucket(
            facts.get("status"),
            facts.get("storage_family"),
            facts.get("storage_semantics"),
            f"hdfs_locality={text_value(facts.get('hdfs_locality_applicable'))}",
        )
    ] += 1


def audit_primary_consistency(
    result: EvidenceGateAuditResult,
    case: dict[str, Any],
    analysis: dict[str, Any],
    primary_label: str,
    profile_policy: str,
) -> None:
    if primary_label not in PROFILE_PRIMARY_LABELS:
        return
    if profile_policy == "unsupported":
        add_issue(
            result,
            case,
            "profile_derived_primary_on_unsupported_profile",
            "profile-derived primary bottleneck emitted for unsupported profile dialect",
        )
    if profile_policy == "non_profile_only" and not (
        primary_label == "runtime_admission"
        and runtime_admission_uses_non_profile_evidence(analysis)
    ):
        add_issue(
            result,
            case,
            "profile_derived_primary_on_partial_profile",
            "profile-derived primary bottleneck emitted for partial profile dialect",
        )
    if primary_label == "runtime_admission":
        facts = runtime_admission_facts_from_analysis(analysis)
        if not facts.primary_supported:
            add_issue(
                result,
                case,
                "runtime_admission_primary_without_gate",
                "runtime_admission primary label is not backed by admission primary support",
            )
    elif primary_label == "client_fetch_tail" and not client_fetch_primary_supported(analysis):
        add_issue(
            result,
            case,
            "client_fetch_primary_without_gate",
            "client_fetch_tail primary label is not backed by client fetch primary support",
        )
    elif primary_label == "runtime_skew":
        facts = scan_skew_facts_from_analysis(analysis)
        if not (facts.primary_supported or backend_execution_tail_primary_supported(analysis)):
            add_issue(
                result,
                case,
                "runtime_skew_primary_without_gate",
                "runtime_skew primary label is not backed by scan-skew or execution-tail support",
            )
    elif primary_label == "runtime_data_movement":
        if not profile_data_movement_primary_supported(analysis):
            add_issue(
                result,
                case,
                "data_movement_primary_without_gate",
                "runtime_data_movement primary label is not backed by data-movement primary support",
            )
    elif primary_label == "runtime_storage":
        if not (
            profile_storage_supported(analysis) or runtime_diagnosis_supports_storage(analysis)
        ):
            add_issue(
                result,
                case,
                "storage_primary_without_gate",
                "runtime_storage primary label is not backed by storage profile/runtime support",
            )


def print_counter(title: str, counter: Counter[str], *, out: TextIO, limit: int) -> None:
    print(f"{title}:", file=out)
    if not counter:
        print("  <none>", file=out)
        return
    for key, count in counter.most_common(limit):
        print(f"  {key}: {count}", file=out)


def print_result(
    result: EvidenceGateAuditResult, *, out: TextIO = sys.stdout, limit: int = 12
) -> None:
    print(f"Summary: {result.summary_path}", file=out)
    print(
        "Cases: "
        f"total={result.total_cases}, analyzed={result.analyzed_cases}, "
        f"missing_analysis={result.missing_analysis_count}, "
        f"analysis_errors={result.analysis_error_count}",
        file=out,
    )
    print_counter("Severity", result.severity_counts, out=out, limit=limit)
    print_counter("Primary bottlenecks", result.primary_counts, out=out, limit=limit)
    print_counter("Primary confidence", result.primary_confidence_counts, out=out, limit=limit)
    print_counter("Profile dialects", result.profile_dialect_counts, out=out, limit=limit)
    print_counter("Profile primary policies", result.profile_policy_counts, out=out, limit=limit)
    print_counter(
        "Profile counter registry", result.profile_counter_registry_counts, out=out, limit=limit
    )
    print_counter("Evidence quality", result.evidence_quality_counts, out=out, limit=limit)
    print_counter("Client fetch gate", result.client_fetch_counts, out=out, limit=limit)
    print_counter("Admission gate", result.admission_counts, out=out, limit=limit)
    print_counter("Memory pressure gate", result.memory_pressure_counts, out=out, limit=limit)
    print_counter("Backend execution-tail gate", result.backend_tail_counts, out=out, limit=limit)
    print_counter("Scan skew gate", result.scan_skew_counts, out=out, limit=limit)
    print_counter("Runtime filter gate", result.runtime_filter_counts, out=out, limit=limit)
    print_counter("Storage context", result.storage_context_counts, out=out, limit=limit)
    if result.issues:
        print_counter("Issues", result.issue_counts, out=out, limit=limit)
        print("Issue examples:", file=out)
        for issue in result.issues[:limit]:
            print(f"  {issue.case_ref}: {issue.category}: {issue.message}", file=out)
    else:
        print("Issues: none", file=out)


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary", type=Path, help="Path to batch_summary.json")
    parser.add_argument("--limit", type=int, default=12, help="Rows to print per section")
    parser.add_argument(
        "--fail-on-issues",
        action="store_true",
        help="Return non-zero if gate inconsistencies are observed.",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = audit_summary(args.summary)
    except EvidenceGateAuditInputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print_result(result, limit=args.limit)
    if args.fail_on_issues and not result.ok:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
