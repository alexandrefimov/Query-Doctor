"""Structured browser-safe errors for unexpected web job failures."""

from __future__ import annotations

from query_doctor.web.models import WebError


_WORKFLOW_LABELS = {
    "query": "Specific Query analysis",
    "trino_query": "Trino Query ID diagnosis",
    "batch": "Recent scan",
    "running": "Running scan",
    "trino_recent": "Trino Recent scan",
    "batch_report": "Finished-query report generation",
    "batch_llm_report": "Finished-query LLM report generation",
    "query_report": "Specific Query report generation",
    "query_llm_report": "Specific Query LLM report generation",
    "batch_optimized_query": "Finished-query optimizer generation",
    "query_optimized_query": "Specific Query optimizer generation",
    "batch_case_actions": "Finished-query report and optimizer action",
    "query_case_actions": "Specific Query report and optimizer action",
}


def unexpected_job_failure_error(kind: str, *, workflow_label: str | None = None) -> WebError:
    """Return a classified raw-free error for defensive job exception handlers."""

    safe_kind = _safe_job_kind(kind)
    label = workflow_label or _WORKFLOW_LABELS.get(safe_kind, "web job")
    return WebError(
        f"{label} failed unexpectedly. Internal exception details are hidden because "
        "they may contain sensitive data.",
        title=f"{label} failed unexpectedly",
        reason_code=f"{safe_kind}.unexpected_failure",
        next_step=_next_step_for_kind(safe_kind),
        details=(
            "The failing internal step did not raise a classified web error.",
            "Use terminal diagnostics for the matching request/job while keeping browser output raw-free.",
        ),
    )


def _safe_job_kind(kind: str) -> str:
    return (
        "".join(char for char in str(kind or "job").lower() if char.isalnum() or char == "_")
        or "job"
    )


def _next_step_for_kind(kind: str) -> str:
    if kind in {"trino_query", "trino_recent"}:
        return (
            "Check the selected Trino local source, source contracts, auth reference, "
            "and coordinator reachability, then retry."
        )
    if kind in {"batch", "running"}:
        return "Review the selected source, local config, credentials, and scan bounds, then retry."
    if kind in {"query"}:
        return (
            "Review the selected Query ID, source config, and available case artifacts, then retry."
        )
    if kind.endswith("_optimized_query") or kind.endswith("_case_actions"):
        return "Review the selected case artifacts, source SQL availability, and local config, then retry."
    if kind.endswith("_report") or kind.endswith("_llm_report"):
        return "Review the selected case artifacts, report settings, and local config, then retry."
    return "Review the selected inputs and local configuration, then retry."
