from query_doctor.web.owner_raw_policy import (
    OWNER_RAW_SOURCE_REASON_ALLOWED,
    OWNER_RAW_SOURCE_REASON_DISABLED,
    OWNER_RAW_SOURCE_REASON_NONLOCAL_WITHOUT_AUTH,
    OWNER_RAW_SOURCE_REASON_OWNER_MISMATCH,
    OWNER_RAW_SOURCE_REASON_ROUTE_CLASS,
    OWNER_RAW_SOURCE_REASON_SOURCE_VISIBILITY,
    OwnerRawSourcePolicyInput,
    authenticated_viewer_identity_configured_for_policy,
    decide_owner_raw_source_policy,
)
from query_doctor.web.viewer_identity import (
    authenticated_viewer_identity,
    authenticated_viewer_identity_from_header_value,
    local_first_viewer_identity,
    unauthenticated_viewer_identity,
)


def test_owner_raw_policy_allows_local_owner_match():
    decision = decide_owner_raw_source_policy(
        OwnerRawSourcePolicyInput(
            source_visibility="owner_raw",
            owner_raw_source_enabled=True,
            viewer_identity=local_first_viewer_identity(("analyst",)),
            query_user="analyst",
        )
    )

    assert decision.allowed is True
    assert decision.reason_code == OWNER_RAW_SOURCE_REASON_ALLOWED
    assert decision.raw_free_summary() == {
        "allowed": True,
        "reason_code": "viewer_matches_query_user",
        "route_surface_class": "isolated_owner_raw_source_web",
        "source_visibility": "owner_raw",
        "source_switch": "enabled",
        "viewer_mode": "local_first",
        "bind_scope": "local",
        "authenticated_viewer_configured": False,
    }


def test_owner_raw_policy_denies_safe_mode_before_viewer_match():
    decision = decide_owner_raw_source_policy(
        OwnerRawSourcePolicyInput(
            source_visibility="safe",
            owner_raw_source_enabled=True,
            viewer_identity=local_first_viewer_identity(("analyst",)),
            query_user="analyst",
        )
    )

    assert decision.allowed is False
    assert decision.reason_code == OWNER_RAW_SOURCE_REASON_SOURCE_VISIBILITY


def test_owner_raw_policy_denies_wrong_surface_class():
    decision = decide_owner_raw_source_policy(
        OwnerRawSourcePolicyInput(
            source_visibility="owner_raw",
            owner_raw_source_enabled=True,
            viewer_identity=local_first_viewer_identity(("analyst",)),
            query_user="analyst",
            route_surface_class="details",
        )
    )

    assert decision.allowed is False
    assert decision.reason_code == OWNER_RAW_SOURCE_REASON_ROUTE_CLASS


def test_owner_raw_policy_denies_nonlocal_owner_raw_without_authenticated_viewer():
    decision = decide_owner_raw_source_policy(
        OwnerRawSourcePolicyInput(
            source_visibility="owner_raw",
            owner_raw_source_enabled=False,
            viewer_identity=local_first_viewer_identity(("analyst",)),
            query_user="analyst",
            host="0.0.0.0",
            allow_nonlocal_web_bind=True,
            authenticated_viewer_configured=False,
        )
    )

    assert decision.allowed is False
    assert decision.reason_code == OWNER_RAW_SOURCE_REASON_NONLOCAL_WITHOUT_AUTH


def test_owner_raw_policy_denies_disabled_after_d3_auth_is_configured():
    identity = authenticated_viewer_identity_from_header_value("analyst")
    decision = decide_owner_raw_source_policy(
        OwnerRawSourcePolicyInput(
            source_visibility="owner_raw",
            owner_raw_source_enabled=False,
            viewer_identity=identity,
            query_user="analyst",
            host="0.0.0.0",
            allow_nonlocal_web_bind=True,
            authenticated_viewer_configured=True,
        )
    )

    assert decision.allowed is False
    assert decision.reason_code == OWNER_RAW_SOURCE_REASON_DISABLED


def test_owner_raw_policy_denies_missing_or_mismatched_viewer():
    for identity in (
        unauthenticated_viewer_identity(),
        authenticated_viewer_identity("other_user"),
        authenticated_viewer_identity_from_header_value("analyst@EXAMPLE.COM"),
    ):
        decision = decide_owner_raw_source_policy(
            OwnerRawSourcePolicyInput(
                source_visibility="owner_raw",
                owner_raw_source_enabled=True,
                viewer_identity=identity,
                query_user="analyst",
                authenticated_viewer_configured=True,
            )
        )

        assert decision.allowed is False
        assert decision.reason_code == OWNER_RAW_SOURCE_REASON_OWNER_MISMATCH


def test_authenticated_viewer_configured_policy_keeps_header_and_subjects_separate():
    assert (
        authenticated_viewer_identity_configured_for_policy(
            unauthenticated_viewer_identity(),
            viewer_identity_header="X-QD-Viewer",
        )
        is True
    )
    assert (
        authenticated_viewer_identity_configured_for_policy(
            authenticated_viewer_identity("analyst"),
            viewer_identity_header=None,
        )
        is True
    )
    assert (
        authenticated_viewer_identity_configured_for_policy(
            local_first_viewer_identity(("analyst",)),
            viewer_identity_header=None,
        )
        is False
    )
