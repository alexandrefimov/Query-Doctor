"""Viewer identity model for owner-gated source visibility."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from query_doctor.source_visibility import normalize_source_owner_user


VIEWER_IDENTITY_UNAUTHENTICATED = "unauthenticated"
VIEWER_IDENTITY_LOCAL_FIRST = "local_first"
VIEWER_IDENTITY_AUTHENTICATED = "authenticated"


@dataclass(frozen=True)
class ViewerIdentity:
    mode: str = VIEWER_IDENTITY_UNAUTHENTICATED
    viewer_user: str | None = None
    viewer_raw_subjects: tuple[str, ...] = ()


def normalize_viewer_raw_subjects(values: Iterable[object]) -> tuple[str, ...]:
    unique: dict[str, str] = {}
    for value in values:
        subject = normalize_source_owner_user(value)
        if subject and subject not in unique:
            unique[subject] = subject
    return tuple(sorted(unique, key=lambda value: (value.casefold(), value)))


def collectable_owner_users(
    source_owner_user: object | None,
    source_owner_user_options: Iterable[object] = (),
) -> tuple[str, ...]:
    return normalize_viewer_raw_subjects((source_owner_user, *tuple(source_owner_user_options)))


def unauthenticated_viewer_identity() -> ViewerIdentity:
    return ViewerIdentity()


def local_first_viewer_identity(
    collectable_users: Iterable[object],
) -> ViewerIdentity:
    return ViewerIdentity(
        mode=VIEWER_IDENTITY_LOCAL_FIRST,
        viewer_raw_subjects=normalize_viewer_raw_subjects(collectable_users),
    )


def authenticated_viewer_identity(
    viewer_user: object,
    *,
    delegated_raw_subjects: Iterable[object] = (),
) -> ViewerIdentity:
    user = normalize_source_owner_user(viewer_user)
    if not user:
        raise ValueError("authenticated viewer identity requires viewer_user.")
    return ViewerIdentity(
        mode=VIEWER_IDENTITY_AUTHENTICATED,
        viewer_user=user,
        viewer_raw_subjects=normalize_viewer_raw_subjects((user, *tuple(delegated_raw_subjects))),
    )


def viewer_can_see_raw_query(identity: ViewerIdentity, query_user: object | None) -> bool:
    if identity.mode not in {VIEWER_IDENTITY_LOCAL_FIRST, VIEWER_IDENTITY_AUTHENTICATED}:
        return False
    try:
        subject = normalize_source_owner_user(query_user)
    except ValueError:
        return False
    if not subject:
        return False
    return subject in identity.viewer_raw_subjects
