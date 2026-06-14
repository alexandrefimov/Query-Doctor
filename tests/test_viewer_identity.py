import pytest

from query_doctor.web.viewer_identity import (
    VIEWER_IDENTITY_AUTHENTICATED,
    VIEWER_IDENTITY_LOCAL_FIRST,
    collectable_owner_users,
    authenticated_viewer_identity,
    local_first_viewer_identity,
    unauthenticated_viewer_identity,
    viewer_can_see_raw_query,
)


def test_local_first_raw_subjects_equal_collectable_owner_users():
    collectable = collectable_owner_users("sa", ("analyst_one", "sa"))
    identity = local_first_viewer_identity(collectable)

    assert collectable == ("analyst_one", "sa")
    assert identity.mode == VIEWER_IDENTITY_LOCAL_FIRST
    assert identity.viewer_user is None
    assert identity.viewer_raw_subjects == collectable
    assert viewer_can_see_raw_query(identity, "analyst_one") is True
    assert viewer_can_see_raw_query(identity, "other_user") is False


def test_collectable_owner_users_excludes_service_principals():
    collectable = collectable_owner_users(
        "impala/host.example.com@EXAMPLE.COM",
        ("analyst_one@EXAMPLE.COM", "hive/host.example.com@EXAMPLE.COM"),
    )

    assert collectable == ("analyst_one",)


def test_authenticated_viewer_identity_can_differ_from_collectable_users():
    collectable = collectable_owner_users("operator_keytab_user", ("batch_owner",))
    identity = authenticated_viewer_identity("analyst_one")

    assert collectable == ("batch_owner", "operator_keytab_user")
    assert identity.mode == VIEWER_IDENTITY_AUTHENTICATED
    assert identity.viewer_user == "analyst_one"
    assert identity.viewer_raw_subjects == ("analyst_one",)
    assert identity.viewer_raw_subjects != collectable
    assert viewer_can_see_raw_query(identity, "analyst_one") is True
    assert viewer_can_see_raw_query(identity, "operator_keytab_user") is False


def test_authenticated_viewer_identity_includes_explicit_delegated_subjects():
    identity = authenticated_viewer_identity(
        "analyst_one",
        delegated_raw_subjects=("delegate_owner", "analyst_one"),
    )

    assert identity.viewer_raw_subjects == ("analyst_one", "delegate_owner")
    assert viewer_can_see_raw_query(identity, "delegate_owner") is True


def test_unauthenticated_viewer_identity_is_fail_closed_for_raw_queries():
    identity = unauthenticated_viewer_identity()

    assert viewer_can_see_raw_query(identity, "analyst_one") is False
    assert viewer_can_see_raw_query(identity, None) is False
    assert viewer_can_see_raw_query(identity, "bad\nuser") is False


def test_authenticated_viewer_identity_requires_simple_user():
    with pytest.raises(ValueError, match="requires viewer_user"):
        authenticated_viewer_identity("")
