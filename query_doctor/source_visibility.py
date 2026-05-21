"""Source visibility and owner-gating helpers."""

from __future__ import annotations


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
