"""Compatibility facade for legacy analyzer imports."""

from __future__ import annotations

from importlib import import_module

from query_doctor.analyzer.service import analyze, make_finding
from query_doctor.cli.analyze_profile import main, parse_args, resolve_paths


__all__ = ["analyze", "main", "make_finding", "parse_args", "resolve_paths"]


_LEGACY_HELPER_MODULES = (
    "query_doctor.analyzer.action_cards",
    "query_doctor.analyzer.backend_tail",
    "query_doctor.analyzer.cm_metrics",
    "query_doctor.analyzer.context_collection",
    "query_doctor.analyzer.context_files",
    "query_doctor.analyzer.evidence_quality",
    "query_doctor.analyzer.facts_renderer",
    "query_doctor.analyzer.models",
    "query_doctor.analyzer.operators",
    "query_doctor.analyzer.profile_signals",
    "query_doctor.analyzer.profile_text",
    "query_doctor.analyzer.runtime_counters",
    "query_doctor.analyzer.runtime_diagnosis",
    "query_doctor.analyzer.scalars",
    "query_doctor.analyzer.sql_sources",
    "query_doctor.analyzer.thresholds",
)


def __getattr__(name: str):
    for module_name in _LEGACY_HELPER_MODULES:
        module = import_module(module_name)
        if hasattr(module, name):
            return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
