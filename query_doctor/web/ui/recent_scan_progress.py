"""Recent scan progress event parsing and rendering."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from query_doctor.web.presenters.recent_scan import numeric_count


def render_batch_progress_panel(progress_path: Path | None, job_status: str = "running") -> str:
    events = read_batch_progress_events(progress_path)
    summary = summarize_batch_progress(events, job_status=job_status)
    steps = "".join(
        "<div class=\"batch-progress-step batch-progress-step--{state}\">"
        "<strong>{icon} {label}</strong><span>{detail}</span></div>".format(
            state=html.escape(step["state"]),
            icon=html.escape(step["icon"]),
            label=html.escape(step["label"]),
            detail=html.escape(step["detail"]),
        )
        for step in summary["steps"]
    )
    metrics = "".join(
        f"<span>{html.escape(label)}: {html.escape(str(value))}</span>"
        for label, value in summary["metrics"]
    )
    metrics_html = f"<div class=\"batch-progress-metrics\">{metrics}</div>" if metrics else ""
    return (
        "<div class=\"batch-progress\" aria-label=\"Batch progress\">"
        f"<div class=\"batch-progress-steps\">{steps}</div>"
        f"{metrics_html}"
        "</div>"
    )


def batch_progress_percent(progress_path: Path | None, job_status: str = "running") -> int:
    events = read_batch_progress_events(progress_path)
    summary = summarize_batch_progress(events, job_status=job_status)
    steps = summary["steps"]
    if not steps:
        return 0
    complete_states = {"done", "skipped"}
    completed = sum(1 for step in steps if step.get("state") in complete_states)
    return round(completed * 100 / len(steps))


def read_batch_progress_events(progress_path: Path | None) -> list[dict[str, Any]]:
    if progress_path is None or not progress_path.is_file():
        return []
    events: list[dict[str, Any]] = []
    try:
        for line in progress_path.read_text(encoding="utf-8").splitlines()[-50000:]:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
    except OSError:
        return []
    return events


def summarize_batch_progress(events: list[dict[str, Any]], *, job_status: str) -> dict[str, Any]:
    counters = {
        "total": 0,
        "jobs": None,
        "summaries_inspected": None,
        "candidates_selected": None,
        "duration_filter": None,
        "collection_done": 0,
        "collection_failed": 0,
        "analysis_done": 0,
        "analysis_started": 0,
        "analysis_failed": 0,
        "failed": 0,
        "metadata_total": None,
        "metadata_done": 0,
        "metadata_skip_reason": None,
    }
    states = {
        "discovery": "pending",
        "collection": "pending",
        "analysis": "pending",
        "metadata": "pending",
        "summary": "pending",
        "completed": "pending",
    }
    for event in events:
        stage = str(event.get("stage") or "")
        status = str(event.get("status") or "")
        if stage == "discovery":
            if status == "started":
                states["discovery"] = "running"
            elif status == "done":
                states["discovery"] = "done"
                counters["summaries_inspected"] = event.get("summaries_inspected")
                counters["candidates_selected"] = event.get("candidates_selected")
                counters["duration_filter"] = event.get("duration_filter")
            elif status == "failed":
                states["discovery"] = "failed"
        elif stage == "case_processing":
            if status == "started":
                counters["total"] = numeric_count(event.get("total"))
                counters["jobs"] = event.get("jobs")
                states["collection"] = "running"
            elif status == "done":
                states["collection"] = "done"
                states["analysis"] = "done"
        elif stage == "case":
            if status == "collection_started" and states["collection"] != "done":
                states["collection"] = "running"
            elif status == "collection_done":
                counters["collection_done"] += 1
            elif status == "analysis_started" and states["analysis"] != "done":
                counters["analysis_started"] += 1
                if states["collection"] != "failed":
                    states["collection"] = "done"
                states["analysis"] = "running"
            elif status == "analysis_done":
                counters["analysis_done"] += 1
            elif status == "failed":
                counters["failed"] += 1
                if event.get("phase") == "collection":
                    counters["collection_failed"] += 1
                elif event.get("phase") == "analysis":
                    counters["analysis_failed"] += 1
        elif stage == "summary":
            if status == "started":
                states["collection"] = "done"
                states["analysis"] = "done"
                if states["metadata"] == "running":
                    states["metadata"] = "done"
                states["summary"] = "running"
            elif status == "done":
                states["summary"] = "done"
        elif stage == "metadata_refresh":
            if status == "started":
                if states["collection"] != "failed":
                    states["collection"] = "done"
                if states["analysis"] != "failed":
                    states["analysis"] = "done"
                states["metadata"] = "running"
                if not event.get("case_id"):
                    counters["metadata_total"] = numeric_count(event.get("total"))
            elif status == "done":
                if event.get("case_id"):
                    counters["metadata_done"] += 1
                else:
                    states["metadata"] = "done"
            elif status == "failed":
                counters["failed"] += 1
            elif status == "skipped":
                states["metadata"] = "skipped"
                counters["metadata_skip_reason"] = event.get("reason")
        elif stage == "batch":
            if status == "done":
                states["completed"] = "done"
                states["summary"] = "done"
                states["collection"] = "done"
                states["analysis"] = "done"
                if states["metadata"] == "running":
                    states["metadata"] = "done"
                elif states["metadata"] == "pending":
                    states["metadata"] = "skipped"
            elif status == "failed":
                states["completed"] = "failed"
    if job_status == "failed" and states["completed"] != "done":
        states["completed"] = "failed"
    if job_status == "ok":
        states["completed"] = "done"
        for key in ("discovery", "collection", "analysis", "summary"):
            if states[key] in {"pending", "running"}:
                states[key] = "done"
        if states["metadata"] in {"pending", "running"}:
            states["metadata"] = "skipped"
    total = numeric_count(counters["total"])
    if total:
        if counters["collection_done"] + counters["collection_failed"] >= total and states["collection"] != "failed":
            states["collection"] = "done"
        if counters["analysis_done"] + counters["analysis_failed"] >= total and states["analysis"] != "failed":
            states["analysis"] = "done"
    processed = counters["analysis_done"] + counters["failed"]
    metrics = []
    if counters["summaries_inspected"] is not None:
        metrics.append(("summaries", counters["summaries_inspected"]))
    if counters["candidates_selected"] is not None:
        metrics.append(("candidates", counters["candidates_selected"]))
    if counters["duration_filter"] is not None:
        metrics.append(("duration filter", counters["duration_filter"]))
    if total:
        metrics.append(("cases processed", f"{processed}/{total}"))
    if counters["failed"]:
        metrics.append(("failed cases", counters["failed"]))
    if counters["jobs"] is not None:
        metrics.append(("jobs", counters["jobs"]))
    return {
        "steps": [
            progress_step("CM discovery", states["discovery"], discovery_detail(counters)),
            progress_step("Profile collection", states["collection"], case_detail(counters, "collection_done")),
            progress_step("Analyzer scoring", states["analysis"], case_detail(counters, "analysis_done")),
            progress_step("Metadata refresh", states["metadata"], metadata_detail(counters)),
            progress_step("Ranking / summary", states["summary"], "summary written" if states["summary"] == "done" else "waiting"),
            progress_step("Completed", states["completed"], "batch done" if states["completed"] == "done" else "waiting"),
        ],
        "metrics": metrics,
    }


def metadata_detail(counters: dict[str, Any]) -> str:
    if counters.get("metadata_skip_reason"):
        return str(counters["metadata_skip_reason"])
    total = counters.get("metadata_total")
    done = counters.get("metadata_done", 0)
    if total is None:
        return "not requested yet"
    if not total:
        return "not requested"
    return f"{done}/{total} refreshed"


def progress_step(label: str, state: str, detail: str) -> dict[str, str]:
    icons = {"done": "✓", "running": "…", "failed": "!", "pending": "·", "skipped": "−"}
    return {"label": label, "state": state, "icon": icons.get(state, "·"), "detail": detail}


def discovery_detail(counters: dict[str, Any]) -> str:
    if counters["candidates_selected"] is not None:
        return f"{counters['candidates_selected']} selected"
    return "waiting"


def case_detail(counters: dict[str, Any], key: str) -> str:
    total = numeric_count(counters["total"])
    done = numeric_count(counters[key])
    if total:
        return f"{done}/{total}"
    return "waiting"
