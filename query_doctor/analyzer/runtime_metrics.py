"""Provider-neutral runtime metrics accessors for analyzer-owned facts."""

from __future__ import annotations

from typing import Any


def runtime_metrics_context(analysis: dict[str, Any]) -> dict[str, Any] | None:
    """Return canonical runtime metrics context with legacy CM fallback."""

    context = analysis.get("metrics_context")
    if isinstance(context, dict):
        return context
    context = analysis.get("cm_timeseries_context")
    return context if isinstance(context, dict) else None


def runtime_metrics_correlation(analysis: dict[str, Any]) -> dict[str, Any] | None:
    """Return canonical runtime metrics correlation with legacy CM fallback."""

    correlation = analysis.get("metrics_correlation")
    if isinstance(correlation, dict):
        return correlation
    correlation = analysis.get("cm_metrics_correlation")
    return correlation if isinstance(correlation, dict) else None


def runtime_metrics_facts(analysis: dict[str, Any]) -> dict[str, Any] | None:
    """Return canonical runtime metrics facts with legacy CM fallback."""

    facts = analysis.get("metrics_facts")
    if isinstance(facts, dict):
        return facts
    facts = analysis.get("cm_metrics_facts")
    return facts if isinstance(facts, dict) else None
