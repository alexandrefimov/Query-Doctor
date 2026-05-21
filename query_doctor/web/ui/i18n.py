"""Small UI language helpers for browser-safe web copy."""

from __future__ import annotations


DEFAULT_UI_LANGUAGE = "en"
SUPPORTED_UI_LANGUAGES = ("en", "ru")


_LANGUAGE_LABELS = {
    "en": "English",
    "ru": "Русский",
}


def normalize_ui_language(value: object) -> str:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in SUPPORTED_UI_LANGUAGES:
            return normalized
    return DEFAULT_UI_LANGUAGE


def language_label(language: object) -> str:
    return _LANGUAGE_LABELS[normalize_ui_language(language)]


def text(language: object, en: str, ru: str) -> str:
    return ru if normalize_ui_language(language) == "ru" else en
