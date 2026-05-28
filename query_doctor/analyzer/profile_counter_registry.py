"""Impala profile counter stability registry.

The bundled registry is the default compatibility layer. A selected case may
also carry a safe, allowlisted registry context derived from Impala Web UI
`/profile_docs/?json`, with `/profile_docs` HTML fallback; that context can
override bundled stability labels for counter families Query Doctor already
interprets.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


CounterStabilityLabel = Literal["STABLE_HIGH", "STABLE_LOW", "UNSTABLE", "DEBUG", "UNKNOWN"]
CounterRegistrySource = Literal["bundled", "profile_docs", "unknown"]
KNOWN_COUNTER_STABILITY_LABELS: tuple[CounterStabilityLabel, ...] = (
    "STABLE_HIGH",
    "STABLE_LOW",
    "UNSTABLE",
    "DEBUG",
    "UNKNOWN",
)
PROFILE_COUNTER_REGISTRY_CONTEXT_FILENAME = "profile_counter_registry_context.json"
PROFILE_COUNTER_REGISTRY_CONTEXT_SCHEMA_VERSION = 1
_STABILITY_RANK = {
    "DEBUG": 0,
    "UNSTABLE": 0,
    "UNKNOWN": 1,
    "STABLE_LOW": 2,
    "STABLE_HIGH": 3,
}


@dataclass(frozen=True)
class ProfileCounterDefinition:
    canonical_name: str
    aliases: tuple[str, ...] = ()
    stability_label: CounterStabilityLabel = "UNKNOWN"
    source: CounterRegistrySource = "unknown"
    evidence_role: str = "unknown"
    impala_version: str | None = None
    profile_docs_source_version: str | None = None


ProfileCounterRegistry = Mapping[str, ProfileCounterDefinition]


def _registry_key(counter_name: str) -> str:
    return counter_name.strip().lower()


def build_profile_counter_registry(
    definitions: tuple[ProfileCounterDefinition, ...],
) -> dict[str, ProfileCounterDefinition]:
    registry: dict[str, ProfileCounterDefinition] = {}
    for definition in definitions:
        for name in (definition.canonical_name, *definition.aliases):
            key = _registry_key(name)
            if key:
                registry[key] = definition
    return registry


BUNDLED_PROFILE_COUNTER_DEFINITIONS: tuple[ProfileCounterDefinition, ...] = (
    ProfileCounterDefinition(
        canonical_name="ClientFetchWaitTimer",
        stability_label="STABLE_HIGH",
        source="bundled",
        evidence_role="client_fetch_wait",
    ),
    ProfileCounterDefinition(
        canonical_name="ClientFetchWaitTime",
        stability_label="STABLE_HIGH",
        source="bundled",
        evidence_role="client_fetch_wait",
    ),
    ProfileCounterDefinition(
        canonical_name="ClientFetchWaitTimeStats",
        stability_label="STABLE_HIGH",
        source="bundled",
        evidence_role="client_fetch_wait",
    ),
    ProfileCounterDefinition(
        canonical_name="ClientFetchLockWaitTimer",
        stability_label="STABLE_HIGH",
        source="bundled",
        evidence_role="client_fetch_wait",
    ),
    ProfileCounterDefinition(
        canonical_name="GetInFlightProfileTimeStats",
        stability_label="DEBUG",
        source="bundled",
        evidence_role="profile_serialization_context",
    ),
    ProfileCounterDefinition(
        canonical_name="SpilledBytes",
        aliases=("BytesSpilled", "MemorySpilled", "MemorySpilledBytes"),
        stability_label="STABLE_HIGH",
        source="bundled",
        evidence_role="spill_scratch_evidence",
    ),
    ProfileCounterDefinition(
        canonical_name="ScratchBytesWritten",
        aliases=("ScratchBytesRead", "PeakScratch", "SpilledPartitions"),
        stability_label="STABLE_HIGH",
        source="bundled",
        evidence_role="spill_scratch_evidence",
    ),
    ProfileCounterDefinition(
        canonical_name="WriteIoBytes",
        aliases=("BytesWritten",),
        stability_label="UNKNOWN",
        source="unknown",
        evidence_role="spill_write_bytes_alias_candidate",
    ),
)


DEFAULT_PROFILE_COUNTER_REGISTRY: dict[str, ProfileCounterDefinition] = (
    build_profile_counter_registry(BUNDLED_PROFILE_COUNTER_DEFINITIONS)
)


def profile_counter_definition(
    counter_name: str,
    registry: ProfileCounterRegistry = DEFAULT_PROFILE_COUNTER_REGISTRY,
) -> ProfileCounterDefinition:
    definition = registry.get(_registry_key(counter_name))
    if definition is not None:
        return definition
    return ProfileCounterDefinition(
        canonical_name=counter_name.strip() or "unknown",
        stability_label="UNKNOWN",
        source="unknown",
        evidence_role="unknown",
    )


def canonical_profile_counter_name(
    counter_name: str,
    registry: ProfileCounterRegistry = DEFAULT_PROFILE_COUNTER_REGISTRY,
) -> str:
    return profile_counter_definition(counter_name, registry).canonical_name


def profile_counter_supports_strong_evidence(definition: ProfileCounterDefinition) -> bool:
    return definition.stability_label == "STABLE_HIGH"


def profile_counter_supports_medium_evidence(definition: ProfileCounterDefinition) -> bool:
    return definition.stability_label in {"STABLE_HIGH", "STABLE_LOW"}


def cap_profile_evidence_tier_for_counter_stability(
    evidence_tier: str,
    definition: ProfileCounterDefinition,
) -> str:
    tier = evidence_tier.strip().lower()
    if tier == "strong" and not profile_counter_supports_strong_evidence(definition):
        return "medium" if profile_counter_supports_medium_evidence(definition) else "context_only"
    if tier == "medium" and not profile_counter_supports_medium_evidence(definition):
        return "context_only"
    return tier


def profile_counter_stability_payload(definition: ProfileCounterDefinition) -> dict[str, str]:
    return {
        "stability_label": definition.stability_label,
        "source": definition.source,
        "evidence_role": definition.evidence_role,
    }


def normalize_counter_stability_label(value: object) -> CounterStabilityLabel:
    label = re.sub(r"[^A-Z0-9]+", "_", str(value or "").strip().upper()).strip("_")
    if label in KNOWN_COUNTER_STABILITY_LABELS:
        return label  # type: ignore[return-value]
    return "UNKNOWN"


def most_restrictive_stability_label(
    labels: tuple[CounterStabilityLabel, ...],
) -> CounterStabilityLabel:
    if not labels:
        return "UNKNOWN"
    return min(labels, key=lambda label: _STABILITY_RANK[label])


def profile_counter_registry_context_path(case_dir: Path) -> Path:
    return case_dir / PROFILE_COUNTER_REGISTRY_CONTEXT_FILENAME


def build_profile_counter_registry_context(
    counter_labels: Mapping[str, object],
    *,
    impala_version: str | None = None,
    profile_docs_source_version: str | None = None,
    source_counter_count: int | None = None,
) -> dict[str, object]:
    """Build a safe registry context from profile-doc counter labels.

    The context stores only counter families Query Doctor already interprets.
    It deliberately omits profile-doc descriptions and unrelated counters.
    """

    normalized_labels = {
        _registry_key(name): normalize_counter_stability_label(label)
        for name, label in counter_labels.items()
        if _registry_key(str(name))
    }
    entries: list[dict[str, object]] = []
    missing_counter_count = 0
    for definition in BUNDLED_PROFILE_COUNTER_DEFINITIONS:
        matched_labels = tuple(
            normalized_labels[key]
            for name in (definition.canonical_name, *definition.aliases)
            if (key := _registry_key(name)) in normalized_labels
        )
        stability_label = most_restrictive_stability_label(matched_labels)
        if not matched_labels:
            missing_counter_count += 1
        entries.append(
            {
                "canonical_name": definition.canonical_name,
                "aliases": list(definition.aliases),
                "stability_label": stability_label,
                "source": "profile_docs",
                "evidence_role": definition.evidence_role,
                "impala_version": impala_version,
                "profile_docs_source_version": profile_docs_source_version,
            }
        )

    return {
        "schema_version": PROFILE_COUNTER_REGISTRY_CONTEXT_SCHEMA_VERSION,
        "status": "available",
        "source": "profile_docs",
        "source_counter_count": (
            len(normalized_labels) if source_counter_count is None else int(source_counter_count)
        ),
        "registry_entry_count": len(entries),
        "missing_counter_count": missing_counter_count,
        "impala_version": impala_version,
        "profile_docs_source_version": profile_docs_source_version,
        "entries": entries,
        "limitations": [
            "Profile counter docs context is limited to counter families already interpreted by Query Doctor.",
            "Missing or unlabeled counters from profile docs are treated as UNKNOWN stability.",
        ],
    }


def unavailable_profile_counter_registry_context(reason: str) -> dict[str, object]:
    return {
        "schema_version": PROFILE_COUNTER_REGISTRY_CONTEXT_SCHEMA_VERSION,
        "status": "unavailable",
        "source": "unknown",
        "source_counter_count": 0,
        "registry_entry_count": 0,
        "missing_counter_count": 0,
        "reason": safe_registry_context_reason(reason),
        "entries": [],
        "limitations": [
            "Profile counter docs were not available; bundled counter stability registry remains in use."
        ],
    }


def safe_registry_context_reason(reason: str) -> str:
    normalized = reason.strip().lower()
    if normalized in {
        "not_configured",
        "request_failed",
        "response_too_large",
        "invalid_json",
        "no_counter_labels",
    }:
        return normalized
    return "unavailable"


def profile_counter_registry_from_context(
    context: Mapping[str, object] | None,
    *,
    fallback_registry: ProfileCounterRegistry = DEFAULT_PROFILE_COUNTER_REGISTRY,
) -> ProfileCounterRegistry:
    if not context or context.get("status") != "available":
        return fallback_registry
    entries = context.get("entries")
    if not isinstance(entries, list):
        return fallback_registry
    definitions: list[ProfileCounterDefinition] = []
    for item in entries:
        if not isinstance(item, Mapping):
            continue
        canonical_name = str(item.get("canonical_name") or "").strip()
        if not canonical_name:
            continue
        aliases_value = item.get("aliases")
        aliases = (
            tuple(str(alias).strip() for alias in aliases_value if str(alias).strip())
            if isinstance(aliases_value, list)
            else ()
        )
        definitions.append(
            ProfileCounterDefinition(
                canonical_name=canonical_name,
                aliases=aliases,
                stability_label=normalize_counter_stability_label(item.get("stability_label")),
                source="profile_docs",
                evidence_role=str(item.get("evidence_role") or "unknown"),
                impala_version=string_or_none(item.get("impala_version")),
                profile_docs_source_version=string_or_none(item.get("profile_docs_source_version")),
            )
        )
    if not definitions:
        return fallback_registry
    return build_profile_counter_registry(tuple(definitions))


def load_profile_counter_registry_context(case_dir: Path) -> dict[str, object] | None:
    path = profile_counter_registry_context_path(case_dir)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return unavailable_profile_counter_registry_context("invalid_json")
    return (
        raw
        if isinstance(raw, dict)
        else unavailable_profile_counter_registry_context("invalid_json")
    )


def write_profile_counter_registry_context(case_dir: Path, context: Mapping[str, object]) -> None:
    path = profile_counter_registry_context_path(case_dir)
    path.write_text(json.dumps(context, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def profile_counter_registry_context_summary(
    context: Mapping[str, object] | None,
) -> dict[str, object]:
    if not context:
        return {
            "status": "not_observed",
            "source": "bundled",
            "registry_entry_count": len(BUNDLED_PROFILE_COUNTER_DEFINITIONS),
            "missing_counter_count": 0,
        }
    limitations = context.get("limitations")
    status = str(context.get("status") or "unknown")
    source = str(context.get("source") or "unknown")
    registry_entry_count = int_or_zero(context.get("registry_entry_count"))
    missing_counter_count = int_or_zero(context.get("missing_counter_count"))
    if status != "available":
        source = "bundled"
        registry_entry_count = len(BUNDLED_PROFILE_COUNTER_DEFINITIONS)
        missing_counter_count = 0
    return {
        "status": status,
        "source": source,
        "source_counter_count": int_or_zero(context.get("source_counter_count")),
        "registry_entry_count": registry_entry_count,
        "missing_counter_count": missing_counter_count,
        "impala_version": string_or_none(context.get("impala_version")),
        "profile_docs_source_version": string_or_none(context.get("profile_docs_source_version")),
        "limitations": (
            [str(item) for item in limitations if item] if isinstance(limitations, list) else []
        ),
    }


def string_or_none(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def int_or_zero(value: object) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0
