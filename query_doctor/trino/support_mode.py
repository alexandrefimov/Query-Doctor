"""Trino support-mode normalization.

The legacy ``trino_beta_enabled`` boolean remains beta-only. New configurations
must use ``trino_support_mode`` so beta deployments are not silently promoted.
"""

from __future__ import annotations

from typing import Literal


TRINO_SUPPORT_MODE_OFF = "off"
TRINO_SUPPORT_MODE_BETA = "beta"
TRINO_SUPPORT_MODE_PRODUCTION = "production"
TRINO_SUPPORT_MODES = frozenset(
    {
        TRINO_SUPPORT_MODE_OFF,
        TRINO_SUPPORT_MODE_BETA,
        TRINO_SUPPORT_MODE_PRODUCTION,
    }
)
TrinoSupportMode = Literal["off", "beta", "production"]


def normalize_trino_support_mode(
    value: object,
    *,
    legacy_beta_enabled: object = False,
) -> TrinoSupportMode:
    """Return the explicit Trino support mode.

    ``trino_beta_enabled=true`` maps only to beta when no explicit mode is set.
    If an explicit production mode is paired with the legacy beta flag, callers
    should reject the configuration instead of guessing intent.
    """

    if value is None or value == "":
        if legacy_beta_enabled is True:
            return TRINO_SUPPORT_MODE_BETA
        return TRINO_SUPPORT_MODE_OFF
    mode = str(value).strip().lower()
    if mode not in TRINO_SUPPORT_MODES:
        raise ValueError("trino_support_mode must be one of: off, beta, production")
    return mode  # type: ignore[return-value]


def trino_support_mode_enabled(mode: object) -> bool:
    return str(mode or "").strip().lower() in {
        TRINO_SUPPORT_MODE_BETA,
        TRINO_SUPPORT_MODE_PRODUCTION,
    }


def trino_support_mode_is_beta(mode: object) -> bool:
    return str(mode or "").strip().lower() == TRINO_SUPPORT_MODE_BETA


def trino_support_mode_is_production(mode: object) -> bool:
    return str(mode or "").strip().lower() == TRINO_SUPPORT_MODE_PRODUCTION
