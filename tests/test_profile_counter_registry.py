from query_doctor.analyzer.profile_counter_registry import (
    ProfileCounterDefinition,
    build_profile_counter_registry_context,
    build_profile_counter_registry,
    cap_profile_evidence_tier_for_counter_stability,
    profile_counter_definition,
    profile_counter_registry_context_summary,
    profile_counter_registry_from_context,
    unavailable_profile_counter_registry_context,
    normalize_counter_stability_label,
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


def test_counter_stability_label_normalizes_profile_docs_html_variants():
    assert normalize_counter_stability_label("STABLE & HIGH") == "STABLE_HIGH"
    assert normalize_counter_stability_label("STABLE & LOW") == "STABLE_LOW"
    assert normalize_counter_stability_label("UNSTABLE") == "UNSTABLE"


def test_profile_docs_context_overrides_bundled_stability_for_known_counters():
    context = build_profile_counter_registry_context(
        {
            "ClientFetchWaitTimer": "STABLE_LOW",
            "SpilledBytes": "STABLE_HIGH",
        },
        impala_version="4.5.0",
    )
    registry = profile_counter_registry_from_context(context)

    client_fetch = profile_counter_definition("ClientFetchWaitTimer", registry)
    scratch = profile_counter_definition("ScratchBytesWritten", registry)

    assert client_fetch.stability_label == "STABLE_LOW"
    assert client_fetch.source == "profile_docs"
    assert client_fetch.impala_version == "4.5.0"
    assert scratch.stability_label == "UNKNOWN"
    assert scratch.source == "profile_docs"
    assert context["missing_counter_count"] > 0
    assert "ScratchBytesWritten" in context["missing_counter_names"]
    assert any(
        entry["canonical_name"] == "ClientFetchWaitTimer" and entry["matched"] is True
        for entry in context["entries"]
    )
    assert any(
        entry["canonical_name"] == "ScratchBytesWritten" and entry["matched"] is False
        for entry in context["entries"]
    )


def test_profile_docs_context_summary_does_not_expose_counter_dump():
    context = build_profile_counter_registry_context(
        {"ClientFetchWaitTimer": "STABLE_HIGH"},
        source_counter_count=100,
    )

    summary = profile_counter_registry_context_summary(context)

    assert summary["status"] == "available"
    assert summary["source"] == "profile_docs"
    assert summary["source_counter_count"] == 100
    assert "ScratchBytesWritten" in summary["missing_counter_names"]
    assert "entries" not in summary


def test_unavailable_profile_docs_summary_reports_bundled_fallback():
    context = unavailable_profile_counter_registry_context("request_failed")

    summary = profile_counter_registry_context_summary(context)

    assert summary["status"] == "unavailable"
    assert summary["source"] == "bundled"
    assert summary["registry_entry_count"] > 0
    assert summary["missing_counter_count"] == 0
    assert "entries" not in summary
