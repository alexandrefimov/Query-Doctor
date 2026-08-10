"""Bounded raw-free parsing for already-provided Impala EXPLAIN text."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from query_doctor.analyzer.scalars import parse_scaled_number, parse_size_bytes


@dataclass(frozen=True)
class ExplainParseLimits:
    max_bytes: int = 2 * 1024 * 1024
    max_lines: int = 20_000
    max_line_chars: int = 16_384
    max_nodes: int = 4_096
    max_fragments: int = 1_024


DEFAULT_EXPLAIN_LIMITS = ExplainParseLimits()

LIMITATION_TEXT = {
    "artifact_missing": "An Impala EXPLAIN artifact was not provided for this case.",
    "artifact_ambiguous": (
        "More than one accepted Impala EXPLAIN artifact is present; no plan was parsed."
    ),
    "artifact_invalid": "The Impala EXPLAIN artifact is not a safe case-contained regular file.",
    "artifact_too_large": "The Impala EXPLAIN artifact exceeds the bounded parser input limit.",
    "artifact_unreadable": "The Impala EXPLAIN artifact could not be read safely.",
    "invalid_text": "The Impala EXPLAIN artifact is not supported UTF-8 text.",
    "empty_input": "The Impala EXPLAIN artifact is empty.",
    "line_limit_reached": "Only a bounded prefix of EXPLAIN lines was inspected.",
    "overlong_line_ignored": "At least one overlong EXPLAIN line was ignored.",
    "node_limit_reached": "Only a bounded number of EXPLAIN plan nodes was retained.",
    "fragment_limit_reached": "Only a bounded number of EXPLAIN fragments was retained.",
    "unsupported_fragment_header": (
        "At least one fragment-like header did not match a supported EXPLAIN layout."
    ),
    "unsupported_fragment_partitioning": (
        "At least one fragment partitioning line did not match a supported EXPLAIN layout."
    ),
    "unsupported_node_header_attributes": (
        "At least one plan node header contained unsupported trailing attributes."
    ),
    "unmapped_node_headers": "At least one EXPLAIN node type is not mapped by this parser.",
    "duplicate_plan_node_identity": (
        "Duplicate engine-local plan node identities make structural linkage ambiguous."
    ),
    "duplicate_plan_fragment_identity": (
        "Duplicate engine-local plan fragment identities make fragment linkage ambiguous."
    ),
    "no_supported_nodes": "No supported Impala EXPLAIN plan nodes were recognized.",
}

GUARDRAILS = (
    "EXPLAIN facts describe optimizer intent and estimates, not runtime behavior or root cause.",
    "Case co-location does not prove that SQL, EXPLAIN, and profile artifacts share one statement revision.",
    "Structural plan/profile overlap cannot promote a diagnosis without direct runtime evidence.",
)

SHELL_BORDER_RE = re.compile(r"^\s*\+(?:-+\+)+\s*$")
SUPPORTED_SIZE_UNIT = r"(?:KiB|MiB|GiB|TiB|KB|MB|GB|TB|B)"
TOKEN_DELIMITER = r"(?=$|[\s,;)\]])"
NODE_HEADER_RE = re.compile(
    r"^\s*(?P<prefix>(?:\|\s*)*(?:(?:\||\+)?-{2,}\s*)?)"
    r"(?P<id>\d{1,4})\s*:\s*(?P<label>[^|]+?)\s*$",
    re.IGNORECASE,
)
MODERN_FRAGMENT_RE = re.compile(
    r"^\s*(?:\|\s*)*F(?P<id>\d{1,4})\s*:\s*PLAN\s+FRAGMENT"
    r"(?:\s*\[(?P<attrs>[^]]*)\])?"
    r"(?:\s+hosts=\d{1,9}\s+instances=\d{1,9})?\s*$",
    re.IGNORECASE,
)
FRAGMENT_HEADER_LIKE_RE = re.compile(
    r"^\s*(?:\|\s*)*(?:F[^:]*:\s*PLAN\s+FRAGMENT|PLAN\s+FRAGMENT\b)",
    re.IGNORECASE,
)
LEGACY_FRAGMENT_RE = re.compile(
    r"^\s*(?:\|\s*)*PLAN\s+FRAGMENT\s+(?P<id>\d{1,4})\s*$",
    re.IGNORECASE,
)
SINK_RE = re.compile(
    r"^\s*(?:\|\s*)*(?:DATASTREAM|STREAM\s+DATA|PLAN(?:\s+|-)ROOT|TABLE)\s+SINK\b",
    re.IGNORECASE,
)
PARTITIONING_RE = re.compile(
    r"^PARTITION(?:ING)?\s*[:=]\s*"
    r"(?P<value>UNPARTITIONED|RANDOM|BROADCAST|HASH(?:\s*\([^)]*\))?)$",
    re.IGNORECASE,
)
CARDINALITY_RE = re.compile(
    r"\bcardinality\s*[:=]\s*"
    r"(?P<value>[-+]?\d[\d,]*(?:\.\d+)?(?:[eE][+-]?\d+)?[KMBT]?|unavailable)"
    rf"{TOKEN_DELIMITER}",
    re.IGNORECASE,
)
ROW_SIZE_RE = re.compile(
    r"\brow-size\s*[:=]\s*"
    rf"(?P<value>[-+]?\d[\d,]*(?:\.\d+)?(?:\s*{SUPPORTED_SIZE_UNIT})?)"
    rf"{TOKEN_DELIMITER}",
    re.IGNORECASE,
)
PER_HOST_MEMORY_RE = re.compile(
    r"\bper-host(?:\s+memory|-mem)\s*[:=]\s*"
    rf"(?P<value>[-+]?\d[\d,]*(?:\.\d+)?(?:\s*{SUPPORTED_SIZE_UNIT})?)"
    rf"{TOKEN_DELIMITER}",
    re.IGNORECASE,
)
HOSTS_RE = re.compile(rf"\bhosts\s*[:=]\s*(?P<value>\d+){TOKEN_DELIMITER}", re.IGNORECASE)
SCAN_PARTITIONS_RE = re.compile(
    r"(?:#\s*)?partitions\s*[:=]\s*(?P<selected>\d+)\s*/\s*(?P<total>\d+)"
    rf"{TOKEN_DELIMITER}",
    re.IGNORECASE,
)
SCAN_FILES_RE = re.compile(rf"\bfiles\s*[:=]\s*(?P<value>\d+){TOKEN_DELIMITER}", re.IGNORECASE)
SCAN_SIZE_RE = re.compile(
    r"(?<![A-Za-z0-9_-])size\s*[:=]\s*"
    rf"(?P<value>[-+]?\d[\d,]*(?:\.\d+)?\s*{SUPPORTED_SIZE_UNIT})"
    rf"{TOKEN_DELIMITER}",
    re.IGNORECASE,
)
STORED_STATISTICS_START_RE = re.compile(r"^stored\s+statistics\s*:\s*$", re.IGNORECASE)
STORED_TABLE_STATS_RE = re.compile(
    r"^table\s*:\s*rows=(?P<rows>\d[\d,]*(?:\.\d+)?[KMBT]?|unavailable)\s+"
    rf"size=(?P<size>\d[\d,]*(?:\.\d+)?\s*{SUPPORTED_SIZE_UNIT}|unavailable)\s*$",
    re.IGNORECASE,
)
STORED_PARTITION_STATS_RE = re.compile(
    r"^partitions\s*:\s*\d+\s*/\s*\d+\s+"
    r"rows=(?:\d[\d,]*(?:\.\d+)?[KMBT]?|unavailable)\s*$",
    re.IGNORECASE,
)
STORED_COLUMNS_ALL_RE = re.compile(r"^columns\s*:\s*all\s*$", re.IGNORECASE)
STORED_COLUMNS_MISSING_RE = re.compile(
    r"^columns\s+missing\s+stats\s*:\s*(?P<columns>\S.*)$", re.IGNORECASE
)
EXTRAPOLATED_ROWS_DETAIL_RE = re.compile(
    r"^extrapolated-rows=(?:disabled|unavailable|\d[\d,]*(?:\.\d+)?[KMBT]?)\s+"
    r"max-scan-range-rows=(?:unavailable|\d[\d,]*(?:\.\d+)?[KMBT]?)\s*$",
    re.IGNORECASE,
)
NODE_RESOURCE_DETAIL_RE = re.compile(
    rf"^mem-estimate=(?:\d[\d,]*(?:\.\d+)?\s*{SUPPORTED_SIZE_UNIT}|unavailable)\s+"
    rf"mem-reservation=(?:\d[\d,]*(?:\.\d+)?\s*{SUPPORTED_SIZE_UNIT}|unavailable)\s+"
    rf"(?:spill-buffer=(?:\d[\d,]*(?:\.\d+)?\s*{SUPPORTED_SIZE_UNIT}|unavailable)\s+)?"
    r"thread-reservation=\d+(?:\s+cost=\d[\d,]*(?:\.\d+)?[KMBT]?)?\s*$",
    re.IGNORECASE,
)
PIPELINE_DETAIL_RE = re.compile(
    r"^in\s+pipelines\s*:\s*\d{1,4}\((?:GETNEXT|OPEN)\)"
    r"(?:\s*,\s*\d{1,4}\((?:GETNEXT|OPEN)\))*\s*$",
    re.IGNORECASE,
)
TUPLE_DETAIL_RE = re.compile(
    r"^tuple(?:-ids|\s+ids)\s*[:=]\s*\d{1,4}(?:\s*,\s*\d{1,4})*\s+"
    rf"row-size=(?:\d[\d,]*(?:\.\d+)?(?:\s*{SUPPORTED_SIZE_UNIT})?)\s+"
    r"cardinality=(?:\d[\d,]*(?:\.\d+)?(?:[eE][+-]?\d+)?[KMBT]?|unavailable)"
    r"(?:\s+cost=\d[\d,]*(?:\.\d+)?[KMBT]?)?\s*$",
    re.IGNORECASE,
)
RESOURCE_MEMORY_RE = re.compile(
    r"\b(?:Memory|Mem)\s*[:=]\s*"
    rf"(?P<value>[-+]?\d[\d,]*(?:\.\d+)?(?:\s*{SUPPORTED_SIZE_UNIT})?)"
    rf"{TOKEN_DELIMITER}",
    re.IGNORECASE,
)
RESOURCE_VCORES_RE = re.compile(
    rf"\bVCores?\s*[:=]\s*(?P<value>\d+){TOKEN_DELIMITER}", re.IGNORECASE
)
ESTIMATED_PER_HOST_RE = re.compile(r"^\s*Estimated\s+Per-Host\b", re.IGNORECASE)
LEGACY_FRAGMENT_PARTITION_RE = re.compile(
    r"^\s*(?:\|\s*)*PARTITION\s*:\s*"
    r"(?P<value>UNPARTITIONED|RANDOM|BROADCAST|HASH(?:\s*\([^)]*\))?)\s*$",
    re.IGNORECASE,
)
LEGACY_FRAGMENT_PARTITION_LIKE_RE = re.compile(
    r"^\s*(?:\|\s*)*PARTITION\s*:",
    re.IGNORECASE,
)
MISSING_STATS_WARNING_START_RE = re.compile(
    r"^\s*WARNING:\s+The following tables are missing relevant table and/or column"
    r"(?P<complete>\s+statistics\b.*)?$",
    re.IGNORECASE,
)
MISSING_STATS_WARNING_CONTINUATION_RE = re.compile(r"^\s*statistics\b", re.IGNORECASE)

OPERATOR_KIND_MAP = {
    "AGGREGATE": ("aggregate", "aggregate"),
    "AGGREGATION": ("aggregate", "aggregate"),
    "HASH AGGREGATE": ("hash_aggregate", "aggregate"),
    "STREAMING AGGREGATE": ("streaming_aggregate", "aggregate"),
    "ANALYTIC": ("analytic", "analytic"),
    "CARDINALITY CHECK": ("cardinality_check", "validation"),
    "CROSS JOIN": ("cross_join", "join"),
    "EMPTYSET": ("empty_set", "source"),
    "EXCHANGE": ("exchange", "exchange"),
    "HASH JOIN": ("hash_join", "join"),
    "HBASE SCAN": ("hbase_scan", "scan"),
    "HDFS SCAN": ("hdfs_scan", "scan"),
    "KUDU SCAN": ("kudu_scan", "scan"),
    "MERGING EXCHANGE": ("merging_exchange", "exchange"),
    "NESTED LOOP JOIN": ("nested_loop_join", "join"),
    "SELECT": ("select", "filter"),
    "SINGULAR ROW SRC": ("singular_row_source", "source"),
    "SORT": ("sort", "sort"),
    "SUBPLAN": ("subplan", "subplan"),
    "TOP N": ("top_n", "sort"),
    "UNION": ("union", "union"),
    "UNNEST": ("unnest", "source"),
}

JOIN_KIND_TOKENS = {
    "LEFT ANTI JOIN": "left_anti",
    "LEFT SEMI JOIN": "left_semi",
    "RIGHT ANTI JOIN": "right_anti",
    "RIGHT SEMI JOIN": "right_semi",
    "LEFT OUTER JOIN": "left_outer",
    "RIGHT OUTER JOIN": "right_outer",
    "FULL OUTER JOIN": "full_outer",
    "INNER JOIN": "inner",
    "CROSS JOIN": "cross",
}


@dataclass
class _Node:
    node_id: int
    operator_kind: str
    operator_family: str
    fragment_id: int | None
    tree_depth: int
    join_kind: str = "unknown"
    join_distribution: str = "unknown"
    partitioning: str = "unknown"
    estimated_cardinality: float | None = None
    estimated_row_size_bytes: float | None = None
    estimated_per_host_memory_bytes: float | None = None
    estimated_host_count: int | None = None
    scan_partitions_selected: int | None = None
    scan_partitions_total: int | None = None
    scan_file_count: int | None = None
    estimated_scan_bytes: float | None = None
    table_stats_state: str = "unknown"
    column_stats_state: str = "unknown"
    predicate_section_observed: bool = False
    runtime_filter_section_observed: bool = False
    opaque_detail_section_observed: bool = False
    stored_statistics_section_active: bool = False

    def public_projection(self, fragment_partitioning: str) -> dict[str, Any]:
        partition_state = (
            "supported"
            if self.scan_partitions_selected is not None and self.scan_partitions_total is not None
            else "unknown"
        )
        if partition_state == "supported":
            if self.scan_partitions_selected < self.scan_partitions_total:
                pruning = "pruned"
            elif self.scan_partitions_selected == self.scan_partitions_total:
                pruning = "full_selection"
            else:
                pruning = "unknown"
        else:
            pruning = "unknown"
        return {
            "operator_kind": self.operator_kind,
            "operator_family": self.operator_family,
            "fragment_observed": self.fragment_id is not None,
            "fragment_partitioning": fragment_partitioning,
            "tree_depth": self.tree_depth,
            "join_kind": self.join_kind,
            "join_distribution": self.join_distribution,
            "partitioning": self.partitioning,
            "estimated_cardinality_state": _numeric_state(self.estimated_cardinality),
            "estimated_cardinality": self.estimated_cardinality,
            "estimated_row_size_state": _numeric_state(self.estimated_row_size_bytes),
            "estimated_row_size_bytes": self.estimated_row_size_bytes,
            "estimated_per_host_memory_state": _numeric_state(self.estimated_per_host_memory_bytes),
            "estimated_per_host_memory_bytes": self.estimated_per_host_memory_bytes,
            "estimated_host_count_state": _numeric_state(self.estimated_host_count),
            "estimated_host_count": self.estimated_host_count,
            "scan_partition_state": partition_state,
            "scan_partitions_selected": self.scan_partitions_selected,
            "scan_partitions_total": self.scan_partitions_total,
            "scan_partition_selection": pruning,
            "scan_file_count_state": _numeric_state(self.scan_file_count),
            "scan_file_count": self.scan_file_count,
            "estimated_scan_bytes_state": _numeric_state(self.estimated_scan_bytes),
            "estimated_scan_bytes": self.estimated_scan_bytes,
            "table_stats_state": self.table_stats_state,
            "column_stats_state": self.column_stats_state,
            "predicate_section_state": (
                "supported" if self.predicate_section_observed else "unknown"
            ),
            "runtime_filter_section_state": (
                "supported" if self.runtime_filter_section_observed else "unknown"
            ),
        }


@dataclass
class _Fragment:
    fragment_id: int
    partitioning: str = "unknown"


@dataclass
class _ParsedPlan:
    nodes: list[_Node] = field(default_factory=list)
    fragments: list[_Fragment] = field(default_factory=list)
    input_bytes: int = 0
    inspected_line_count: int = 0
    total_line_count: int = 0
    unmapped_node_header_count: int = 0
    estimated_per_host_memory_bytes: float | None = None
    estimated_vcores: int | None = None
    missing_stats_warning_observed: bool = False
    limitations: list[str] = field(default_factory=list)


def parse_impala_explain(
    text: str,
    *,
    profile_operators: Iterable[Mapping[str, Any]] = (),
    limits: ExplainParseLimits = DEFAULT_EXPLAIN_LIMITS,
) -> dict[str, Any]:
    """Parse Impala EXPLAIN text into a bounded raw-free public projection."""

    if not isinstance(text, str):
        return _unknown_facts(
            artifact_status="invalid",
            source_slot="provided_text",
            limitation_codes=("invalid_text",),
        )
    try:
        input_bytes = len(text.encode("utf-8"))
    except UnicodeEncodeError:
        return _unknown_facts(
            artifact_status="invalid",
            source_slot="provided_text",
            limitation_codes=("invalid_text",),
        )
    if input_bytes > limits.max_bytes:
        return _unknown_facts(
            artifact_status="too_large",
            source_slot="provided_text",
            input_bytes=input_bytes,
            limitation_codes=("artifact_too_large",),
        )
    if "\x00" in text:
        return _unknown_facts(
            artifact_status="invalid",
            source_slot="provided_text",
            input_bytes=input_bytes,
            limitation_codes=("invalid_text",),
        )
    if not text.strip():
        return _unknown_facts(
            artifact_status="available",
            source_slot="provided_text",
            input_bytes=input_bytes,
            limitation_codes=("empty_input",),
        )

    parsed = _parse_plan(text, limits=limits)
    return _project_plan(parsed, profile_operators=profile_operators, source_slot="provided_text")


def _parse_plan(text: str, *, limits: ExplainParseLimits) -> _ParsedPlan:
    raw_lines = text.splitlines()
    if raw_lines:
        raw_lines[0] = raw_lines[0].removeprefix("\ufeff")
    parsed = _ParsedPlan(input_bytes=len(text.encode("utf-8")), total_line_count=len(raw_lines))
    if len(raw_lines) > limits.max_lines:
        parsed.limitations.append("line_limit_reached")
    lines = raw_lines[: limits.max_lines]
    parsed.inspected_line_count = len(lines)
    current_fragment: _Fragment | None = None
    current_node: _Node | None = None
    legacy_fragment_partition_pending = False
    missing_stats_warning_pending = False

    for raw_line in lines:
        if len(raw_line) > limits.max_line_chars:
            _append_once(parsed.limitations, "overlong_line_ignored")
            current_node = None
            current_fragment = None
            legacy_fragment_partition_pending = False
            missing_stats_warning_pending = False
            continue
        line = _unwrap_shell_line(raw_line)
        if line is None:
            continue
        warning_start = MISSING_STATS_WARNING_START_RE.match(line)
        if warning_start:
            missing_stats_warning_pending = warning_start.group("complete") is None
            if not missing_stats_warning_pending:
                parsed.missing_stats_warning_observed = True
        elif missing_stats_warning_pending and MISSING_STATS_WARNING_CONTINUATION_RE.match(line):
            parsed.missing_stats_warning_observed = True
            missing_stats_warning_pending = False
        else:
            missing_stats_warning_pending = False
        _parse_resource_requirements(line, parsed)

        modern_fragment_match = MODERN_FRAGMENT_RE.match(line)
        legacy_fragment_match = LEGACY_FRAGMENT_RE.match(line)
        fragment_match = modern_fragment_match or legacy_fragment_match
        if fragment_match:
            current_node = None
            legacy_fragment_partition_pending = legacy_fragment_match is not None
            if len(parsed.fragments) >= limits.max_fragments:
                _append_once(parsed.limitations, "fragment_limit_reached")
                current_fragment = None
                legacy_fragment_partition_pending = False
                continue
            current_fragment = _Fragment(
                fragment_id=int(fragment_match.group("id")),
                partitioning=_partitioning_kind(
                    fragment_match.groupdict().get("attrs") or "", allow_bare=True
                ),
            )
            parsed.fragments.append(current_fragment)
            continue
        if FRAGMENT_HEADER_LIKE_RE.match(line):
            current_node = None
            current_fragment = None
            legacy_fragment_partition_pending = False
            _append_once(parsed.limitations, "unsupported_fragment_header")
            continue

        if legacy_fragment_partition_pending:
            legacy_fragment_partition_pending = False
            legacy_partition = LEGACY_FRAGMENT_PARTITION_RE.match(line)
            if legacy_partition and current_fragment is not None:
                current_fragment.partitioning = _partitioning_kind(
                    legacy_partition.group("value"), allow_bare=True
                )
                continue
            if LEGACY_FRAGMENT_PARTITION_LIKE_RE.match(line):
                _append_once(parsed.limitations, "unsupported_fragment_partitioning")
                continue

        node_match = NODE_HEADER_RE.match(line)
        if node_match:
            operator = _operator_kind(node_match.group("label"))
            if operator is None:
                parsed.unmapped_node_header_count += 1
                current_node = None
                continue
            if len(parsed.nodes) >= limits.max_nodes:
                _append_once(parsed.limitations, "node_limit_reached")
                current_node = None
                continue
            operator_kind, operator_family = operator
            label = node_match.group("label")
            attrs = _header_attributes(label)
            if "[" in label and not label.rstrip().endswith("]"):
                _append_once(parsed.limitations, "unsupported_node_header_attributes")
            join_kind, join_distribution = _join_header_facts(attrs, operator_kind)
            current_node = _Node(
                node_id=int(node_match.group("id")),
                operator_kind=operator_kind,
                operator_family=operator_family,
                fragment_id=current_fragment.fragment_id if current_fragment else None,
                tree_depth=_tree_depth(node_match.group("prefix")),
                join_kind=join_kind,
                join_distribution=join_distribution,
                partitioning=_node_partitioning_kind(attrs, operator_kind=operator_kind),
            )
            parsed.nodes.append(current_node)
            continue

        if SINK_RE.match(line):
            current_node = None
            continue
        if current_node is not None:
            _apply_node_detail(current_node, line)

    if parsed.unmapped_node_header_count:
        _append_once(parsed.limitations, "unmapped_node_headers")
    node_id_counts: dict[int, int] = {}
    for node in parsed.nodes:
        node_id_counts[node.node_id] = node_id_counts.get(node.node_id, 0) + 1
    if any(count > 1 for count in node_id_counts.values()):
        _append_once(parsed.limitations, "duplicate_plan_node_identity")
    fragment_id_counts: dict[int, int] = {}
    for fragment in parsed.fragments:
        fragment_id_counts[fragment.fragment_id] = (
            fragment_id_counts.get(fragment.fragment_id, 0) + 1
        )
    if any(count > 1 for count in fragment_id_counts.values()):
        _append_once(parsed.limitations, "duplicate_plan_fragment_identity")
    if not parsed.nodes:
        _append_once(parsed.limitations, "no_supported_nodes")
    return parsed


def _project_plan(
    parsed: _ParsedPlan,
    *,
    profile_operators: Iterable[Mapping[str, Any]],
    source_slot: str,
) -> dict[str, Any]:
    if not parsed.nodes:
        return _unknown_facts(
            artifact_status="available",
            source_slot=source_slot,
            candidate_count=1,
            input_bytes=parsed.input_bytes,
            limitation_codes=tuple(parsed.limitations),
        )

    status = "supported"
    parser_status = "partial" if parsed.limitations else "supported"

    fragment_id_counts = _counts(str(fragment.fragment_id) for fragment in parsed.fragments)
    fragment_partitioning = {
        fragment.fragment_id: fragment.partitioning
        for fragment in parsed.fragments
        if fragment_id_counts[str(fragment.fragment_id)] == 1
    }
    public_nodes = [
        node.public_projection(fragment_partitioning.get(node.fragment_id, "unknown"))
        for node in parsed.nodes
    ]
    family_counts = _counts(node.operator_family for node in parsed.nodes)
    kind_counts = _counts(node.operator_kind for node in parsed.nodes)
    join_distribution_counts = _counts(
        node.join_distribution
        for node in parsed.nodes
        if node.operator_family == "join" and node.join_distribution != "unknown"
    )
    fragment_partitioning_counts = _counts(
        fragment.partitioning for fragment in parsed.fragments if fragment.partitioning != "unknown"
    )
    correlation = _structural_correlation(
        parsed.nodes,
        profile_operators,
        plan_coverage_complete=not parsed.limitations,
    )
    detail_hint = _detail_hint(parsed)
    fully_inspected = not any(
        code in parsed.limitations
        for code in ("line_limit_reached", "overlong_line_ignored", "node_limit_reached")
    )
    missing_stats_state = (
        "supported"
        if parsed.missing_stats_warning_observed
        else "not_observed"
        if parsed.nodes and fully_inspected
        else "unknown"
    )
    missing_stats_observed = (
        True
        if parsed.missing_stats_warning_observed
        else False
        if missing_stats_state == "not_observed"
        else None
    )
    return {
        "status": status,
        "artifact_status": "available",
        "source_kind": "impala_explain_text",
        "source_slot": source_slot,
        "candidate_count": 1,
        "parser_status": parser_status,
        "detail_hint": detail_hint,
        "input_bytes": parsed.input_bytes,
        "total_line_count": parsed.total_line_count,
        "inspected_line_count": parsed.inspected_line_count,
        "observed_fragment_count": len(parsed.fragments),
        "observed_node_count": len(parsed.nodes),
        "unmapped_node_header_count": parsed.unmapped_node_header_count,
        "observed_operator_family_counts": family_counts,
        "observed_operator_kind_counts": kind_counts,
        "observed_join_distribution_counts": join_distribution_counts,
        "observed_fragment_partitioning_counts": fragment_partitioning_counts,
        "resource_estimates": {
            "estimated_per_host_memory_state": _numeric_state(
                parsed.estimated_per_host_memory_bytes
            ),
            "estimated_per_host_memory_bytes": parsed.estimated_per_host_memory_bytes,
            "estimated_vcores_state": _numeric_state(parsed.estimated_vcores),
            "estimated_vcores": parsed.estimated_vcores,
        },
        "missing_stats_warning_state": missing_stats_state,
        "missing_stats_warning_observed": missing_stats_observed,
        "nodes": public_nodes,
        "correlation": correlation,
        "causal_claim_supported": False,
        "engine_recommendation_supported": False,
        "limitation_codes": list(parsed.limitations),
        "limitations": [LIMITATION_TEXT[code] for code in parsed.limitations],
        "guardrails": list(GUARDRAILS),
    }


def _unknown_facts(
    *,
    artifact_status: str,
    source_slot: str,
    limitation_codes: tuple[str, ...],
    candidate_count: int = 0,
    input_bytes: int | None = None,
) -> dict[str, Any]:
    return {
        "status": "unknown",
        "artifact_status": artifact_status,
        "source_kind": "impala_explain_text",
        "source_slot": source_slot,
        "candidate_count": candidate_count,
        "parser_status": "unknown",
        "detail_hint": "unknown",
        "input_bytes": input_bytes,
        "total_line_count": None,
        "inspected_line_count": None,
        "observed_fragment_count": None,
        "observed_node_count": None,
        "unmapped_node_header_count": None,
        "observed_operator_family_counts": None,
        "observed_operator_kind_counts": None,
        "observed_join_distribution_counts": None,
        "observed_fragment_partitioning_counts": None,
        "resource_estimates": {
            "estimated_per_host_memory_state": "unknown",
            "estimated_per_host_memory_bytes": None,
            "estimated_vcores_state": "unknown",
            "estimated_vcores": None,
        },
        "missing_stats_warning_state": "unknown",
        "missing_stats_warning_observed": None,
        "nodes": None,
        "correlation": _unknown_correlation(),
        "causal_claim_supported": False,
        "engine_recommendation_supported": False,
        "limitation_codes": list(limitation_codes),
        "limitations": [LIMITATION_TEXT[code] for code in limitation_codes],
        "guardrails": list(GUARDRAILS),
    }


def unknown_impala_explain_facts(
    *,
    artifact_status: str,
    source_slot: str,
    limitation_codes: tuple[str, ...],
    candidate_count: int = 0,
    input_bytes: int | None = None,
) -> dict[str, Any]:
    """Build the stable raw-free unknown projection for the bounded loader."""

    return _unknown_facts(
        artifact_status=artifact_status,
        source_slot=source_slot,
        limitation_codes=limitation_codes,
        candidate_count=candidate_count,
        input_bytes=input_bytes,
    )


def _unwrap_shell_line(raw_line: str) -> str | None:
    stripped = raw_line.strip()
    if not stripped or SHELL_BORDER_RE.fullmatch(stripped):
        return None
    if stripped.startswith("|") and stripped.endswith("|") and len(stripped) >= 2:
        inner = stripped[1:-1].rstrip()
        if inner.strip().lower() == "explain string":
            return None
        return inner
    return raw_line.rstrip()


def _operator_kind(label: str) -> tuple[str, str] | None:
    name = label.split("[", 1)[0].strip().upper()
    name = re.sub(r"[-_]+", " ", name)
    name = re.sub(r"\s+", " ", name)
    if name.startswith("SCAN "):
        name = f"{name[5:]} SCAN"
    return OPERATOR_KIND_MAP.get(name)


def _header_attributes(label: str) -> str:
    if not label.rstrip().endswith("]"):
        return ""
    _, separator, tail = label.partition("[")
    return tail.rsplit("]", 1)[0] if separator else ""


def _tree_depth(prefix: str) -> int:
    pipe_depth = prefix.count("|")
    if pipe_depth:
        return min(pipe_depth, 64)
    return min(len(prefix) // 2, 64)


def _join_header_facts(attributes: str, operator_kind: str) -> tuple[str, str]:
    if operator_kind not in {"cross_join", "hash_join", "nested_loop_join"}:
        return "unknown", "unknown"
    tokens = [_normalized_token(token) for token in attributes.split(",")]
    join_kind = "cross" if operator_kind == "cross_join" else "unknown"
    distribution = "unknown"
    for token in tokens:
        if token in JOIN_KIND_TOKENS:
            join_kind = JOIN_KIND_TOKENS[token]
        elif token == "BROADCAST":
            distribution = "broadcast"
        elif token == "PARTITIONED":
            distribution = "partitioned"
    return join_kind, distribution


def _join_op_facts(content: str) -> tuple[str, str]:
    _, separator, value = content.partition(":")
    if not separator:
        return "unknown", "unknown"
    normalized = _normalized_token(value)
    for token, join_kind in JOIN_KIND_TOKENS.items():
        if normalized == token:
            return join_kind, "unknown"
        for suffix, distribution in (
            (" (BROADCAST)", "broadcast"),
            (", BROADCAST", "broadcast"),
            (" (PARTITIONED)", "partitioned"),
            (", PARTITIONED", "partitioned"),
        ):
            if normalized == f"{token}{suffix}":
                return join_kind, distribution
    return "unknown", "unknown"


def _partitioning_kind(text: str, *, allow_bare: bool = False) -> str:
    upper = _normalized_token(text)
    value = ""
    for token in upper.split(","):
        match = PARTITIONING_RE.fullmatch(token.strip())
        if match:
            value = _normalized_token(match.group("value"))
            break
    if not value and allow_bare:
        value = upper
    if value == "UNPARTITIONED":
        return "unpartitioned"
    if value == "BROADCAST":
        return "broadcast"
    if value == "HASH" or re.fullmatch(r"HASH\s*\([^)]*\)", value):
        return "hash"
    if value == "RANDOM":
        return "random"
    return "unknown"


def _node_partitioning_kind(attributes: str, *, operator_kind: str) -> str:
    explicit = _partitioning_kind(attributes)
    if explicit != "unknown":
        return explicit
    if operator_kind == "exchange":
        return _partitioning_kind(attributes, allow_bare=True)
    if operator_kind in {"hbase_scan", "hdfs_scan", "kudu_scan"}:
        tokens = attributes.rsplit(",", 1)
        if len(tokens) == 2:
            return _partitioning_kind(tokens[1], allow_bare=True)
    return "unknown"


def _normalized_token(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().upper())


def _parse_resource_requirements(line: str, parsed: _ParsedPlan) -> None:
    if not ESTIMATED_PER_HOST_RE.search(line):
        return
    memory_match = RESOURCE_MEMORY_RE.search(line)
    if memory_match:
        value = _safe_size_or_bytes(memory_match.group("value"))
        if value is not None:
            parsed.estimated_per_host_memory_bytes = value
    vcores_match = RESOURCE_VCORES_RE.search(line)
    if vcores_match:
        value = _safe_int(vcores_match.group("value"))
        if value is not None:
            parsed.estimated_vcores = value


def _apply_node_detail(node: _Node, line: str) -> None:
    content = _detail_content(line)
    lower = content.lower()

    if lower.startswith(
        ("predicates:", "hash predicates:", "kudu predicates:", "other predicates:")
    ):
        node.predicate_section_observed = True
        node.opaque_detail_section_observed = True
        node.stored_statistics_section_active = False
        return
    if lower.startswith("runtime filters:"):
        node.runtime_filter_section_observed = True
        node.opaque_detail_section_observed = True
        node.stored_statistics_section_active = False
        return
    if node.opaque_detail_section_observed:
        return
    if node.stored_statistics_section_active:
        if lower.startswith("table:"):
            table_stats_state = _stored_table_stats_state(content)
            if table_stats_state == "unknown":
                node.stored_statistics_section_active = False
                node.opaque_detail_section_observed = True
                return
            node.table_stats_state = table_stats_state
            return
        if STORED_PARTITION_STATS_RE.fullmatch(content):
            return
        if STORED_COLUMNS_ALL_RE.fullmatch(content):
            node.column_stats_state = "reported_available"
            return
        if STORED_COLUMNS_MISSING_RE.fullmatch(content):
            node.column_stats_state = "reported_partial"
            return
        if not _is_known_post_stored_statistics_detail(content):
            node.stored_statistics_section_active = False
            node.opaque_detail_section_observed = True
            return
        node.stored_statistics_section_active = False
    if STORED_STATISTICS_START_RE.fullmatch(content):
        node.stored_statistics_section_active = True
        return
    if lower.startswith("join op:") and node.operator_family == "join":
        join_kind, distribution = _join_op_facts(content)
        if node.join_kind == "unknown":
            node.join_kind = join_kind
        if node.join_distribution == "unknown":
            node.join_distribution = distribution
        return
    if lower.startswith("table stats:"):
        node.table_stats_state = _stats_state(content, kind="table")
        return
    if lower.startswith("column stats:"):
        node.column_stats_state = _stats_state(content, kind="column")
        return

    if re.match(r"^tuple(?:-ids|\s+ids)\s*[:=]", lower):
        if not TUPLE_DETAIL_RE.fullmatch(content):
            node.opaque_detail_section_observed = True
            return
        _apply_cardinality_and_row_size(node, content)
        return
    if lower.startswith(("cardinality=", "cardinality:")):
        cardinality_match = CARDINALITY_RE.search(content)
        if cardinality_match:
            node.estimated_cardinality = _safe_scaled_number(cardinality_match.group("value"))
        return
    if lower.startswith(("hosts=", "hosts:")):
        hosts_match = HOSTS_RE.search(content)
        if hosts_match:
            node.estimated_host_count = _safe_int(hosts_match.group("value"))
        memory_match = PER_HOST_MEMORY_RE.search(content)
        if memory_match:
            node.estimated_per_host_memory_bytes = _safe_size_or_bytes(memory_match.group("value"))
        return
    if lower.startswith(("per-host memory:", "per-host memory=", "per-host-mem=")):
        memory_match = PER_HOST_MEMORY_RE.search(content)
        if memory_match:
            node.estimated_per_host_memory_bytes = _safe_size_or_bytes(memory_match.group("value"))
        return
    if lower.startswith(("row-size=", "row-size:")):
        row_size_match = ROW_SIZE_RE.search(content)
        if row_size_match:
            node.estimated_row_size_bytes = _safe_size_or_bytes(row_size_match.group("value"))
        return
    if node.operator_family == "scan":
        if _apply_scan_detail(node, content):
            return
    if _is_known_nonprojected_detail(content):
        return
    node.opaque_detail_section_observed = True


def _detail_content(line: str) -> str:
    content = line.strip()
    while content.startswith("|"):
        content = content[1:].lstrip()
    return content


def _apply_cardinality_and_row_size(node: _Node, content: str) -> None:
    cardinality_match = CARDINALITY_RE.search(content)
    if cardinality_match:
        node.estimated_cardinality = _safe_scaled_number(cardinality_match.group("value"))
    row_size_match = ROW_SIZE_RE.search(content)
    if row_size_match:
        node.estimated_row_size_bytes = _safe_size_or_bytes(row_size_match.group("value"))


def _apply_scan_detail(node: _Node, content: str) -> bool:
    lower = content.lower()
    if lower.startswith("table="):
        partition_marker = re.search(r"\s+#?partitions\s*[:=]", content, re.IGNORECASE)
        if not partition_marker:
            return False
        detail = content[partition_marker.start() :]
    elif re.match(r"^(?:hdfs\s+)?#?partitions\s*[:=]", lower):
        detail = content
    else:
        return False

    partitions_match = SCAN_PARTITIONS_RE.search(detail)
    if partitions_match:
        selected = _safe_int(partitions_match.group("selected"))
        total = _safe_int(partitions_match.group("total"))
        if selected is not None and total is not None and selected <= total:
            node.scan_partitions_selected = selected
            node.scan_partitions_total = total
    files_match = SCAN_FILES_RE.search(detail)
    if files_match:
        node.scan_file_count = _safe_int(files_match.group("value"))
    size_match = SCAN_SIZE_RE.search(detail)
    if size_match:
        node.estimated_scan_bytes = _safe_size_or_bytes(size_match.group("value"))
    return True


def _stored_table_stats_state(content: str) -> str:
    match = STORED_TABLE_STATS_RE.fullmatch(content)
    if match is None:
        return "unknown"
    rows = match.group("rows")
    size = match.group("size")
    rows_available = _safe_scaled_number(rows) is not None
    size_available = _safe_size_or_bytes(size) is not None
    rows_unavailable = rows.lower() == "unavailable"
    size_unavailable = size.lower() == "unavailable"
    if rows_available and size_available:
        return "reported_available"
    if rows_unavailable and size_unavailable:
        return "reported_unavailable"
    if (rows_available or rows_unavailable) and (size_available or size_unavailable):
        return "reported_partial"
    return "unknown"


def _is_known_post_stored_statistics_detail(content: str) -> bool:
    return bool(
        EXTRAPOLATED_ROWS_DETAIL_RE.fullmatch(content)
        or NODE_RESOURCE_DETAIL_RE.fullmatch(content)
        or TUPLE_DETAIL_RE.fullmatch(content)
        or PIPELINE_DETAIL_RE.fullmatch(content)
    )


def _is_known_nonprojected_detail(content: str) -> bool:
    return bool(
        EXTRAPOLATED_ROWS_DETAIL_RE.fullmatch(content)
        or NODE_RESOURCE_DETAIL_RE.fullmatch(content)
        or PIPELINE_DETAIL_RE.fullmatch(content)
    )


def _stats_state(line: str, *, kind: str) -> str:
    _, _, value = line.partition(":")
    normalized = value.strip().lower()
    if not normalized:
        return "unknown"
    if normalized in {"unavailable", "missing", "none"}:
        return "reported_unavailable"
    if normalized in {"partial", "some"}:
        return "reported_partial"
    if kind == "column" and normalized == "all":
        return "reported_available"
    if kind == "table" and re.fullmatch(r"\d[\d,]*(?:\.\d+)?\s+rows?\s+total", normalized):
        return "reported_available"
    return "unknown"


def _safe_scaled_number(value: str) -> float | None:
    text = str(value or "").strip()
    if not text or text.startswith(("-", "+")) or text.lower() == "unavailable":
        return None
    parsed = parse_scaled_number(text)
    return _finite_nonnegative(parsed)


def _safe_size_or_bytes(value: str) -> float | None:
    text = str(value or "").strip()
    if not text or text.startswith(("-", "+")) or text.lower() == "unavailable":
        return None
    parsed = parse_size_bytes(text)
    if parsed is None:
        parsed = parse_scaled_number(text)
    return _finite_nonnegative(parsed)


def _safe_int(value: str) -> int | None:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if 0 <= parsed <= 1_000_000_000 else None


def _finite_nonnegative(value: float | None) -> float | None:
    if value is None or not math.isfinite(value) or value < 0:
        return None
    return float(value)


def _numeric_state(value: object) -> str:
    return (
        "supported"
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        else "unknown"
    )


def _counts(values: Iterable[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        result[value] = result.get(value, 0) + 1
    return dict(sorted(result.items()))


def _detail_hint(parsed: _ParsedPlan) -> str:
    extended = any(
        node.estimated_cardinality is not None
        or node.estimated_per_host_memory_bytes is not None
        or node.estimated_row_size_bytes is not None
        for node in parsed.nodes
    )
    if parsed.fragments and extended:
        return "verbose_like"
    if extended:
        return "extended_like"
    if parsed.nodes:
        return "basic"
    return "unknown"


def _structural_correlation(
    nodes: list[_Node],
    profile_operators: Iterable[Mapping[str, Any]],
    *,
    plan_coverage_complete: bool,
) -> dict[str, Any]:
    profile_map: dict[int, list[str]] = {}
    unmapped_profile_operators = 0
    for operator in profile_operators:
        node_id = _profile_node_id(operator.get("operator_id"))
        operator_kind = _operator_kind(str(operator.get("operator_name") or ""))
        if node_id is None or operator_kind is None:
            unmapped_profile_operators += 1
            continue
        profile_map.setdefault(node_id, []).append(operator_kind[0])
    if not profile_map or not nodes:
        correlation = _unknown_correlation(identity_link_basis="unbound_external_artifact")
        if unmapped_profile_operators:
            correlation["unmapped_profile_operator_count"] = unmapped_profile_operators
        return correlation

    plan_id_counts: dict[int, int] = {}
    for node in nodes:
        plan_id_counts[node.node_id] = plan_id_counts.get(node.node_id, 0) + 1
    plan_ids = set(plan_id_counts)
    checked_profile_operators = sum(len(families) for families in profile_map.values())
    extra_profile_operators = sum(
        len(families) for node_id, families in profile_map.items() if node_id not in plan_ids
    )

    matched = ambiguous = mismatch = unmatched = 0
    for node in nodes:
        if plan_id_counts[node.node_id] > 1:
            ambiguous += 1
            continue
        kinds = profile_map.get(node.node_id)
        if not kinds:
            unmatched += 1
        elif len(kinds) > 1:
            ambiguous += 1
        elif node.operator_kind in kinds:
            matched += 1
        else:
            mismatch += 1

    if ambiguous:
        status = "ambiguous"
    elif mismatch:
        status = "mismatch"
    elif (
        plan_coverage_complete
        and matched == len(nodes)
        and extra_profile_operators == 0
        and unmapped_profile_operators == 0
    ):
        status = "matched"
    elif matched:
        status = "partial"
    else:
        status = "unknown"
    return {
        "structural_match_status": status,
        "method": "engine_local_operator_identity_and_kind",
        "checked_plan_node_count": len(nodes),
        "checked_profile_operator_count": checked_profile_operators,
        "matched_plan_node_count": matched,
        "ambiguous_plan_node_count": ambiguous,
        "mismatched_plan_node_count": mismatch,
        "unmatched_plan_node_count": unmatched,
        "extra_profile_operator_count": extra_profile_operators,
        "unmapped_profile_operator_count": unmapped_profile_operators,
        "identity_link_basis": "unbound_external_artifact",
        "execution_identity_status": "unknown",
        "statement_identity_status": "unknown",
    }


def _unknown_correlation(*, identity_link_basis: str = "no_accepted_plan_source") -> dict[str, Any]:
    return {
        "structural_match_status": "unknown",
        "method": "engine_local_operator_identity_and_kind",
        "checked_plan_node_count": None,
        "checked_profile_operator_count": None,
        "matched_plan_node_count": None,
        "ambiguous_plan_node_count": None,
        "mismatched_plan_node_count": None,
        "unmatched_plan_node_count": None,
        "extra_profile_operator_count": None,
        "unmapped_profile_operator_count": None,
        "identity_link_basis": identity_link_basis,
        "execution_identity_status": "unknown",
        "statement_identity_status": "unknown",
    }


def _profile_node_id(value: object) -> int | None:
    text = str(value or "").strip()
    if not re.fullmatch(r"\d{1,4}", text):
        return None
    return int(text)


def _append_once(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)
