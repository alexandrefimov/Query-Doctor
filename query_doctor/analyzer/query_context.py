"""Provider-neutral query context accessors for analyzer-owned facts."""

from __future__ import annotations

from typing import Any


def query_context(analysis: dict[str, Any]) -> dict[str, Any] | None:
    """Return canonical query context with legacy CM metadata fallback."""

    context = analysis.get("query_context")
    if isinstance(context, dict):
        return context
    context = analysis.get("cm_query_context")
    return context if isinstance(context, dict) else None
