from query_doctor.analyzer.profile_counter_registry import (
    ProfileCounterDefinition,
    build_profile_counter_registry,
    cap_profile_evidence_tier_for_counter_stability,
    profile_counter_definition,
)


def test_registry_defaults_unknown_for_unmapped_counter():
    definition = profile_counter_definition("FutureCounter")

    assert definition.canonical_name == "FutureCounter"
    assert definition.stability_label == "UNKNOWN"
    assert definition.source == "unknown"
    assert cap_profile_evidence_tier_for_counter_stability("strong", definition) == "context_only"


def test_bundled_registry_normalizes_supported_spill_aliases():
    definition = profile_counter_definition("BytesSpilled")

    assert definition.canonical_name == "SpilledBytes"
    assert definition.stability_label == "STABLE_HIGH"
    assert definition.source == "bundled"
    assert definition.evidence_role == "spill_scratch_evidence"


def test_write_bytes_alias_candidate_stays_unknown_until_mapped():
    definition = profile_counter_definition("BytesWritten")

    assert definition.canonical_name == "WriteIoBytes"
    assert definition.stability_label == "UNKNOWN"
    assert definition.source == "unknown"
    assert cap_profile_evidence_tier_for_counter_stability("strong", definition) == "context_only"


def test_stable_low_counter_caps_strong_to_medium():
    registry = build_profile_counter_registry(
        (
            ProfileCounterDefinition(
                canonical_name="FutureCounter",
                stability_label="STABLE_LOW",
                source="profile_docs",
                evidence_role="supporting_context",
            ),
        )
    )
    definition = profile_counter_definition("FutureCounter", registry)

    assert cap_profile_evidence_tier_for_counter_stability("strong", definition) == "medium"
    assert cap_profile_evidence_tier_for_counter_stability("medium", definition) == "medium"
