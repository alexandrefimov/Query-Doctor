"""Runtime filter context facts parsed from Impala profile text."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from query_doctor.analyzer.scalars import extract_first_duration_ms, fmt_duration, parse_size_bytes


RUNTIME_FILTER_LINE_RE = re.compile(
    r"^\s*(?:\|\s*)*(?:-\s*)?runtime\s+filters?\s*:\s*(?P<value>.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
RUNTIME_FILTER_ID_RE = re.compile(r"\bRF\d+\b", re.IGNORECASE)
RUNTIME_FILTER_TYPE_RE = re.compile(r"\bRF\d+\s*\[\s*(?P<kind>[A-Za-z0-9_ -]+?)\s*\]")
MISSING_FILTER_ARRIVAL_RE = re.compile(r"\bnot\s+all\s+filters\s+arrived\b", re.IGNORECASE)
ALL_FILTERS_ARRIVED_RE = re.compile(r"\ball\s+filters\s+arrived\b", re.IGNORECASE)
WAITED_FOR_RE = re.compile(r"\bwaited\s+for\s+(?P<duration>[^\n\r,;]+)", re.IGNORECASE)
BLOOM_FILTER_BYTES_RE = re.compile(
    r"^\s*-\s*BloomFilterBytes\s*:\s*(?P<value>[^\n\r]+)",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class RuntimeFilterFacts:
    status: str
    evidence_tier: str
    finding_supported: bool
    primary_supported: bool
    profile_dialect: str
    runtime_filter_lines: int
    plan_filter_lines: int
    runtime_filter_id_count: int
    plan_producer_lines: int
    plan_consumer_lines: int
    filter_kind_counts: dict[str, int]
    arrival_status: str
    arrival_status_lines: int
    missing_arrival_lines: int
    all_arrived_lines: int
    max_arrival_wait_ms: float | None
    max_arrival_wait_human: str
    bloom_filter_counter_lines: int
    bloom_filter_counter_nonzero_lines: int
    exec_node_runtime_filter_effectiveness: str
    guardrail: str
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_runtime_filter_facts(
    text: str,
    profile_format: dict[str, Any] | None = None,
    exec_node_completeness: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build raw-free runtime-filter facts.

    The first slice is deliberately context-only. Runtime filter profile text can
    show useful producer/consumer and arrival context, but root-cause wording
    requires stronger target-scan, timing, spill, and node-completion support.
    """

    return runtime_filter_facts(text, profile_format, exec_node_completeness).to_dict()


def runtime_filter_facts(
    text: str,
    profile_format: dict[str, Any] | None = None,
    exec_node_completeness: dict[str, Any] | None = None,
) -> RuntimeFilterFacts:
    profile_format = profile_format if isinstance(profile_format, dict) else {}
    exec_node_completeness = (
        exec_node_completeness if isinstance(exec_node_completeness, dict) else {}
    )
    dialect = str(
        profile_format.get("profile_dialect") or profile_format.get("dialect") or "unknown"
    )
    runtime_filter_effectiveness = str(
        exec_node_completeness.get("runtime_filter_effectiveness") or "unknown"
    )

    guardrail = (
        "Runtime filter evidence is context-only until the analyzer maps filter "
        "producers, consumers, target scans, timing, spill context, and node "
        "completion for the selected query."
    )
    unsupported_dialect = dialect not in {"classic_text_profile", ""}
    if unsupported_dialect:
        return RuntimeFilterFacts(
            status="unknown",
            evidence_tier="unsupported",
            finding_supported=False,
            primary_supported=False,
            profile_dialect=dialect,
            runtime_filter_lines=0,
            plan_filter_lines=0,
            runtime_filter_id_count=0,
            plan_producer_lines=0,
            plan_consumer_lines=0,
            filter_kind_counts={},
            arrival_status="unknown",
            arrival_status_lines=0,
            missing_arrival_lines=0,
            all_arrived_lines=0,
            max_arrival_wait_ms=None,
            max_arrival_wait_human="n/a",
            bloom_filter_counter_lines=0,
            bloom_filter_counter_nonzero_lines=0,
            exec_node_runtime_filter_effectiveness=runtime_filter_effectiveness,
            guardrail=guardrail,
            limitations=(
                "Runtime filter profile text is not interpreted for this profile dialect.",
                "Do not claim missing, late, ineffective, or successful runtime filters from unsupported profile representations.",
            ),
        )

    filter_lines = [match.group("value").strip() for match in RUNTIME_FILTER_LINE_RE.finditer(text)]
    filter_ids = {
        match.group(0).upper()
        for line in filter_lines
        for match in RUNTIME_FILTER_ID_RE.finditer(line)
    }
    plan_filter_lines = sum(
        1
        for line in filter_lines
        if RUNTIME_FILTER_ID_RE.search(line) or "<-" in line or "->" in line
    )
    producer_lines = sum(1 for line in filter_lines if "<-" in line)
    consumer_lines = sum(1 for line in filter_lines if "->" in line)
    filter_kind_counts = safe_filter_kind_counts(filter_lines)

    missing_arrival_lines = sum(
        1 for line in filter_lines if MISSING_FILTER_ARRIVAL_RE.search(line)
    )
    all_arrived_lines = sum(
        1
        for line in filter_lines
        if ALL_FILTERS_ARRIVED_RE.search(line) and not MISSING_FILTER_ARRIVAL_RE.search(line)
    )
    arrival_status_lines = missing_arrival_lines + all_arrived_lines
    arrival_waits = [
        wait_ms for line in filter_lines if (wait_ms := runtime_filter_wait_ms(line)) is not None
    ]
    max_wait_ms = max(arrival_waits) if arrival_waits else None
    bloom_counter_values = [
        parse_size_bytes(match.group("value")) for match in BLOOM_FILTER_BYTES_RE.finditer(text)
    ]
    bloom_counter_lines = len(bloom_counter_values)
    bloom_counter_nonzero_lines = sum(
        1 for value in bloom_counter_values if value is not None and value > 0
    )
    observed = bool(filter_lines or bloom_counter_lines)

    limitations = runtime_filter_limitations(
        observed=observed,
        missing_arrival_lines=missing_arrival_lines,
        runtime_filter_effectiveness=runtime_filter_effectiveness,
    )

    return RuntimeFilterFacts(
        status="context_only" if observed else "not_observed",
        evidence_tier="context_only" if observed else "unsupported",
        finding_supported=False,
        primary_supported=False,
        profile_dialect=dialect or "classic_text_profile",
        runtime_filter_lines=len(filter_lines),
        plan_filter_lines=plan_filter_lines,
        runtime_filter_id_count=len(filter_ids),
        plan_producer_lines=producer_lines,
        plan_consumer_lines=consumer_lines,
        filter_kind_counts=filter_kind_counts,
        arrival_status=arrival_status(missing_arrival_lines, all_arrived_lines, observed),
        arrival_status_lines=arrival_status_lines,
        missing_arrival_lines=missing_arrival_lines,
        all_arrived_lines=all_arrived_lines,
        max_arrival_wait_ms=max_wait_ms,
        max_arrival_wait_human=fmt_duration(max_wait_ms) if max_wait_ms is not None else "n/a",
        bloom_filter_counter_lines=bloom_counter_lines,
        bloom_filter_counter_nonzero_lines=bloom_counter_nonzero_lines,
        exec_node_runtime_filter_effectiveness=runtime_filter_effectiveness,
        guardrail=guardrail,
        limitations=tuple(limitations),
    )


def runtime_filter_wait_ms(line: str) -> float | None:
    match = WAITED_FOR_RE.search(line)
    if not match:
        return None
    return extract_first_duration_ms(match.group("duration"))


def arrival_status(
    missing_arrival_lines: int,
    all_arrived_lines: int,
    observed: bool,
) -> str:
    if missing_arrival_lines and all_arrived_lines:
        return "mixed"
    if missing_arrival_lines:
        return "missing_observed"
    if all_arrived_lines:
        return "all_arrived_observed"
    if observed:
        return "not_reported"
    return "not_observed"


def safe_filter_kind_counts(lines: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for line in lines:
        for match in RUNTIME_FILTER_TYPE_RE.finditer(line):
            key = safe_kind(match.group("kind"))
            if not key:
                continue
            counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def safe_kind(value: object) -> str:
    text = re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower()).strip("_")
    return text[:40]


def runtime_filter_limitations(
    *,
    observed: bool,
    missing_arrival_lines: int,
    runtime_filter_effectiveness: str,
) -> list[str]:
    limitations = [
        "Runtime filter context does not independently support a root-cause or primary-bottleneck finding.",
        "Missing or late runtime filters require deterministic producer, consumer, target scan, timing, and spill-context evidence before diagnostic promotion.",
    ]
    if missing_arrival_lines:
        limitations.append(
            "Runtime filter arrival gaps were observed, but this slice keeps them as context until target scans and producer timing are mapped."
        )
    if runtime_filter_effectiveness != "supported":
        limitations.append(
            "Exec-node completeness limits runtime-filter-effectiveness conclusions for this profile."
        )
    if not observed:
        limitations.append(
            "No mapped runtime-filter plan or arrival context was observed in the parsed profile text."
        )
    return limitations
