"""Bundled Impala profile counter stability registry.

This registry is a conservative local compatibility layer. It does not fetch
Impala Web UI `/profile_docs`; live profile-doc ingestion belongs in a later
collector slice after the source contract and fixtures exist.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal


CounterStabilityLabel = Literal["STABLE_HIGH", "STABLE_LOW", "UNSTABLE", "DEBUG", "UNKNOWN"]
CounterRegistrySource = Literal["bundled", "profile_docs", "unknown"]


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
