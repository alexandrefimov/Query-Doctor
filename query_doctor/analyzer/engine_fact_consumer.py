"""Read-only consumer probe for normalized engine fact boundary payloads.

This module intentionally does not wire normalized facts into production
ranking, reports, or browser output. It exercises the future consumer seam with
raw-free payloads that are already safe for trusted surfaces.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

from query_doctor.analyzer.engine_facts import (
    ENGINE_FACT_BOUNDARY_SCHEMA_VERSION,
    EngineFactBundle,
    EngineFactContractError,
    engine_fact_boundary_payload,
)


ENGINE_FACT_CONSUMER_PROBE_SCHEMA_VERSION = "engine_fact_consumer_probe_v1"
FACT_GROUPS = ("timing", "resources", "stages", "limitations")


def engine_fact_consumer_probe(bundle: EngineFactBundle) -> dict[str, Any]:
    return engine_fact_consumer_probe_from_boundary(engine_fact_boundary_payload(bundle))


def engine_fact_consumer_probe_from_boundary(payload: Mapping[str, Any]) -> dict[str, Any]:
    _validate_boundary_payload(payload)

    identity = _mapping(payload["identity"])
    lifecycle = _mapping(payload["lifecycle"])
    fact_groups = _mapping(payload["fact_groups"])
    state_counts = {state: 0 for state in ("supported", "not_observed", "unknown")}
    supported_fact_ids: list[str] = []
    not_observed_fact_ids: list[str] = []
    unknown_fact_ids: list[str] = []

    for fact in _iter_facts(fact_groups):
        state = str(fact["state"])
        fact_id = str(fact["id"])
        state_counts[state] += 1
        if state == "supported":
            supported_fact_ids.append(fact_id)
        elif state == "not_observed":
            not_observed_fact_ids.append(fact_id)
        else:
            unknown_fact_ids.append(fact_id)

    attention_signal_ids = _attention_signal_ids(lifecycle, fact_groups, identity)

    return {
        "schema_version": ENGINE_FACT_CONSUMER_PROBE_SCHEMA_VERSION,
        "source_schema_version": ENGINE_FACT_BOUNDARY_SCHEMA_VERSION,
        "engine": identity["engine"],
        "parser_coverage": identity["parser_coverage"],
        "lifecycle": lifecycle["lifecycle"],
        "state_counts": state_counts,
        "attention_signal_ids": attention_signal_ids,
        "supported_fact_ids": tuple(sorted(supported_fact_ids)),
        "not_observed_fact_ids": tuple(sorted(not_observed_fact_ids)),
        "unknown_fact_ids": tuple(sorted(unknown_fact_ids)),
    }


def engine_fact_consumer_probe_text(bundle: EngineFactBundle) -> str:
    return json.dumps(engine_fact_consumer_probe(bundle), ensure_ascii=True, sort_keys=True)


def _attention_signal_ids(
    lifecycle: Mapping[str, Any],
    fact_groups: Mapping[str, Any],
    identity: Mapping[str, Any],
) -> tuple[str, ...]:
    signals: set[str] = set()
    if lifecycle["failure"] == "supported":
        signals.add("query_failed")
    if lifecycle["blocked"] == "supported":
        signals.add("blocked_or_admission_wait")
    if identity["parser_coverage"] == "unknown":
        signals.add("parser_coverage_unknown")

    for fact in _iter_facts(fact_groups):
        fact_id = str(fact["id"])
        state = str(fact["state"])
        if state == "supported" and fact_id in {"spill_or_scratch_evidence", "spilled_bytes"}:
            signals.add("spill_or_scratch_evidence")
        if state == "supported" and fact_id in {"backend_execution_tail_candidates"}:
            signals.add("execution_tail_candidate")
        if state == "unknown" and _is_limitation_fact(fact_id, fact_groups):
            signals.add(f"limitation_unknown:{fact_id}")
    return tuple(sorted(signals))


def _validate_boundary_payload(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != ENGINE_FACT_BOUNDARY_SCHEMA_VERSION:
        raise EngineFactContractError("unsupported engine fact boundary payload schema")

    identity = _required_mapping(payload, "identity")
    lifecycle = _required_mapping(payload, "lifecycle")
    fact_groups = _required_mapping(payload, "fact_groups")

    for key in ("engine", "parser_coverage"):
        if not isinstance(identity.get(key), str) or not identity[key]:
            raise EngineFactContractError(f"boundary identity missing {key}")
    _validate_state(str(identity["parser_coverage"]))

    if not isinstance(lifecycle.get("lifecycle"), str) or not lifecycle["lifecycle"]:
        raise EngineFactContractError("boundary lifecycle missing lifecycle")
    for key in ("state", "blocked", "failure"):
        if not isinstance(lifecycle.get(key), str):
            raise EngineFactContractError(f"boundary lifecycle missing {key}")
        _validate_state(str(lifecycle[key]))

    for group in FACT_GROUPS:
        facts = fact_groups.get(group)
        if not isinstance(facts, list):
            raise EngineFactContractError(f"boundary fact group missing {group}")
        for fact in facts:
            _validate_fact(fact, group)


def _validate_fact(value: Any, group: str) -> None:
    if not isinstance(value, Mapping):
        raise EngineFactContractError(f"boundary {group} fact must be an object")
    if not isinstance(value.get("id"), str) or not value["id"]:
        raise EngineFactContractError(f"boundary {group} fact missing id")
    if not isinstance(value.get("state"), str):
        raise EngineFactContractError(f"boundary {group} fact missing state")
    _validate_state(str(value["state"]))


def _validate_state(state: str) -> None:
    if state not in {"supported", "not_observed", "unknown"}:
        raise EngineFactContractError(f"unsupported boundary diagnostic state: {state}")


def _required_mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise EngineFactContractError(f"boundary payload missing {key}")
    return value


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _iter_facts(fact_groups: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    for group in FACT_GROUPS:
        facts = fact_groups.get(group)
        if isinstance(facts, list):
            for fact in facts:
                if isinstance(fact, Mapping):
                    yield fact


def _is_limitation_fact(fact_id: str, fact_groups: Mapping[str, Any]) -> bool:
    limitations = fact_groups.get("limitations")
    if not isinstance(limitations, list):
        return False
    return any(isinstance(fact, Mapping) and fact.get("id") == fact_id for fact in limitations)
