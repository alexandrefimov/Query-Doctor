"""Exec-node lifecycle guardrails for row-count conclusions."""

from __future__ import annotations

import re
from typing import Any

from query_doctor.analyzer.models import OperatorFact
from query_doctor.analyzer.operators import RAW_NODE_HEADER_RE, RAW_NODE_NAME_MAP, raw_node_section


ROW_UNSAFE_STATES = {"cancelled", "incomplete"}

QUERY_STATE_RE = re.compile(
    r"^\s*Query\s+(?:State|Status)\s*:\s*(?P<value>.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
NODE_STATUS_RE = re.compile(
    r"^\s*-\s*(?:ExecStatus|Status|State|ExecState|NodeState|Lifecycle)\s*:\s*(?P<value>.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
NODE_COMPLETION_RE = re.compile(
    r"^\s*-\s*(?:Completed|Complete|Done|IsDone|IsCompleted)\s*:\s*(?P<value>.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
NODE_CANCELLED_RE = re.compile(
    r"^\s*-\s*(?:Cancelled|Canceled|IsCancelled|IsCanceled|TimedOut|Timed\s+Out)\s*:\s*(?P<value>.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def build_exec_node_completeness_facts(
    text: str,
    operators: list[OperatorFact],
    query_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return raw-free facts describing whether row-count conclusions are safe."""

    profile_state, profile_reasons = profile_wide_state(text, query_context)
    node_states = explicit_node_states(text, operators)
    affected = affected_operators(operators, node_states, profile_state)
    unsafe_count = len(affected)
    row_support = "limited" if unsafe_count else "supported"
    limitations = []
    if unsafe_count:
        limitations.append(
            {
                "id": "incomplete_or_cancelled_exec_nodes",
                "state": "unknown",
                "summary": (
                    "One or more exec nodes may be incomplete or cancelled; "
                    "row/cardinality, scan-selectivity, and runtime-filter-effectiveness "
                    "conclusions are limited for affected nodes."
                ),
            }
        )
        limitations.append(
            {
                "id": "zero_rows_not_meaningful_for_incomplete_nodes",
                "state": "unknown",
                "summary": (
                    "Zero rows on affected nodes must not be interpreted as an empty table, "
                    "meaningful zero-row selectivity, or runtime filters filtering everything."
                ),
            }
        )

    return {
        "profile_wide_state": profile_state,
        "profile_wide_reasons": profile_reasons,
        "row_count_conclusions": row_support,
        "cardinality_conclusions": row_support,
        "scan_selectivity_conclusions": row_support,
        "runtime_filter_effectiveness": row_support,
        "unsafe_operator_count": unsafe_count,
        "affected_operators": affected,
        "limitations": limitations,
    }


def profile_wide_state(
    text: str, query_context: dict[str, Any] | None = None
) -> tuple[str, list[str]]:
    context = query_context or {}
    for key in ("query_state", "query_status", "status"):
        state, reason = classify_lifecycle_value(context.get(key))
        if state in ROW_UNSAFE_STATES:
            return state, [f"context_{reason}"]

    for match in QUERY_STATE_RE.finditer(text):
        state, reason = classify_lifecycle_value(match.group("value"))
        if state in ROW_UNSAFE_STATES:
            return state, [f"profile_{reason}"]
        if state == "complete":
            return state, [f"profile_{reason}"]

    return "unknown", []


def explicit_node_states(text: str, operators: list[OperatorFact]) -> dict[str, dict[str, Any]]:
    lines = text.splitlines()
    known_ids = {op.operator_id for op in operators}
    states: dict[str, dict[str, Any]] = {}
    for index, line in enumerate(lines):
        match = RAW_NODE_HEADER_RE.match(line)
        if not match:
            continue
        operator_id = match.group("id").zfill(2)
        if known_ids and operator_id not in known_ids:
            continue
        section = raw_node_section(lines, index)
        state, reasons = classify_node_section(section)
        if state not in ROW_UNSAFE_STATES:
            continue
        states[operator_id] = {
            "operator_id": operator_id,
            "operator_name": RAW_NODE_NAME_MAP.get(match.group("node"), match.group("node")),
            "state": state,
            "reasons": reasons,
        }
    return states


def classify_node_section(section: str) -> tuple[str, list[str]]:
    reasons: list[str] = []
    for match in NODE_CANCELLED_RE.finditer(section):
        if bool_value(match.group("value")) is True:
            return "cancelled", ["node_cancelled_true"]

    for match in NODE_STATUS_RE.finditer(section):
        state, reason = classify_lifecycle_value(match.group("value"))
        if state in ROW_UNSAFE_STATES:
            reasons.append(f"node_{reason}")
            return state, reasons

    for match in NODE_COMPLETION_RE.finditer(section):
        value = bool_value(match.group("value"))
        if value is False:
            return "incomplete", ["node_completed_false"]

    return "unknown", reasons


def classify_lifecycle_value(value: object) -> tuple[str, str]:
    normalized = normalize_lifecycle_value(value)
    if not normalized:
        return "unknown", "state_unknown"
    if re.search(r"\b(?:cancelled|canceled|cancel|timed_out|timed out|timeout)\b", normalized):
        return "cancelled", "state_cancelled"
    if re.search(r"\b(?:failed|error|exception|aborted|closed_early|closed early)\b", normalized):
        return "incomplete", "state_incomplete"
    if re.search(
        r"\b(?:running|executing|in_flight|in flight|in_progress|in progress|"
        r"pending|queued|not_started|not started|not_executed|not executed|"
        r"incomplete|not_complete|not complete|not_completed|not completed)\b",
        normalized,
    ):
        return "incomplete", "state_incomplete"
    if re.search(r"\b(?:finished|succeeded|success|complete|completed|done|ok)\b", normalized):
        return "complete", "state_complete"
    return "unknown", "state_unknown"


def normalize_lifecycle_value(value: object) -> str:
    return re.sub(r"[^a-z0-9_ ]+", " ", str(value or "").strip().lower())


def bool_value(value: object) -> bool | None:
    normalized = normalize_lifecycle_value(value)
    if normalized in {"true", "yes", "y", "1"}:
        return True
    if normalized in {"false", "no", "n", "0"}:
        return False
    return None


def affected_operators(
    operators: list[OperatorFact],
    node_states: dict[str, dict[str, Any]],
    profile_wide_state: str,
) -> list[dict[str, Any]]:
    affected: list[dict[str, Any]] = []
    profile_wide_unsafe = profile_wide_state in ROW_UNSAFE_STATES
    for op in operators:
        state = node_states.get(op.operator_id)
        if not state and not profile_wide_unsafe:
            continue
        reasons = list(state.get("reasons", [])) if state else [f"profile_{profile_wide_state}"]
        affected.append(
            {
                "operator_id": op.operator_id,
                "operator_name": op.operator_name,
                "label": f"{op.operator_id}:{op.operator_name}",
                "state": state.get("state") if state else profile_wide_state,
                "reasons": reasons,
            }
        )
    return affected


def operator_row_conclusions_supported(
    op: OperatorFact,
    completeness: dict[str, Any],
) -> bool:
    affected = completeness.get("affected_operators")
    if not isinstance(affected, list):
        return True
    return not any(str(item.get("operator_id") or "") == op.operator_id for item in affected)
