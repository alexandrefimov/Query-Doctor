"""Source visibility and owner-gating helpers."""

from __future__ import annotations

from collections.abc import Iterable


SOURCE_VISIBILITY_SAFE = "safe"
SOURCE_VISIBILITY_OWNER_RAW = "owner_raw"
SOURCE_VISIBILITY_CHOICES = (SOURCE_VISIBILITY_SAFE, SOURCE_VISIBILITY_OWNER_RAW)
OWNER_USER_ENV_KEYS = ("QD_SOURCE_OWNER_USER",)
KERBEROS_PRINCIPAL_ENV_KEYS = ("QD_KRB5_PRINCIPAL", "KRB5_PRINCIPAL")
MAX_SOURCE_OWNER_USER_LENGTH = 256


def normalize_source_visibility(value: object | None) -> str:
    text = str(value or SOURCE_VISIBILITY_SAFE).strip()
    if not text:
        return SOURCE_VISIBILITY_SAFE
    if text not in SOURCE_VISIBILITY_CHOICES:
        raise ValueError(
            "source_visibility must be one of: " + ", ".join(SOURCE_VISIBILITY_CHOICES)
        )
    return text


def normalize_source_owner_user(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > MAX_SOURCE_OWNER_USER_LENGTH:
        raise ValueError("source_owner_user is too long.")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in text):
        raise ValueError("source_owner_user must not contain control characters.")
    return text


def owner_user_from_kerberos_principal(principal: object | None) -> str | None:
    text = normalize_source_owner_user(principal)
    if text is None:
        return None
    primary = text.split("@", 1)[0].strip()
    if not primary or "/" in primary:
        return None
    return normalize_source_owner_user(primary)


def collectable_owner_user(value: object | None) -> str | None:
    text = normalize_source_owner_user(value)
    if text is None:
        return None
    if "/" in text:
        return None
    if "@" in text:
        return owner_user_from_kerberos_principal(text)
    return text


def collectable_owner_users(
    source_owner_user: object | None,
    source_owner_user_options: Iterable[object] = (),
) -> tuple[str, ...]:
    unique: dict[str, str] = {}
    for value in (source_owner_user, *tuple(source_owner_user_options)):
        owner = collectable_owner_user(value)
        if owner and owner not in unique:
            unique[owner] = owner
    return tuple(sorted(unique, key=lambda item: (item.casefold(), item)))


def source_owner_user_from_env(env: dict[str, str]) -> str | None:
    for key in OWNER_USER_ENV_KEYS:
        owner = normalize_source_owner_user(env.get(key))
        if owner:
            return owner
    for key in KERBEROS_PRINCIPAL_ENV_KEYS:
        owner = owner_user_from_kerberos_principal(env.get(key))
        if owner:
            return owner
    return None
