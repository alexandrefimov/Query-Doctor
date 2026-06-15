"""Recent scan progress event parsing and rendering."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from query_doctor.web.presenters.recent_scan import numeric_count


def render_batch_progress_panel(progress_path: Path | None, job_status: str = "running") -> str:
    summary = batch_progress_summary(progress_path, job_status)
    steps = "".join(
        '<div class="batch-progress-step batch-progress-step--{state}">'
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
    metrics_html = f'<div class="batch-progress-metrics">{metrics}</div>' if metrics else ""
    return (
        '<div class="batch-progress" aria-label="Batch progress">'
        f'<div class="batch-progress-steps">{steps}</div>'
        f"{metrics_html}"
        "</div>"
    )


def batch_progress_percent(progress_path: Path | None, job_status: str = "running") -> int:
    return batch_progress_percent_from_summary(batch_progress_summary(progress_path, job_status))


def batch_progress_summary(
    progress_path: Path | None, job_status: str = "running"
) -> dict[str, Any]:
    events = read_batch_progress_events(progress_path)
    return summarize_batch_progress(events, job_status=job_status)


def batch_progress_percent_from_summary(summary: dict[str, Any]) -> int:
    steps = summary["steps"]
    if not steps:
        return 0
    complete_states = {"done", "skipped"}
    completed = sum(1 for step in steps if step.get("state") in complete_states)
    return round(completed * 100 / len(steps))


def batch_progress_view_payload(
    progress_path: Path | None, job_status: str = "running"
) -> dict[str, object]:
    summary = batch_progress_summary(progress_path, job_status)
    steps = summary["steps"]
    current_index = batch_progress_current_step_index(steps)
    current_stage = str(steps[current_index]["label"]) if steps else "Batch progress"
    return {
        "current_stage": current_stage,
        "current_index": current_index,
        "percent": batch_progress_percent_from_summary(summary),
        "steps": [batch_progress_step_payload(step) for step in steps],
    }


def batch_progress_current_step_index(steps: list[dict[str, str]]) -> int:
    if not steps:
        return 0
    for state in ("failed", "running"):
        for index, step in enumerate(steps):
            if step.get("state") == state:
                return index
    for index, step in enumerate(steps):
        if step.get("state") == "pending":
            return index
    return len(steps) - 1


def batch_progress_step_payload(step: dict[str, str]) -> dict[str, str]:
    state = step.get("state", "pending")
    if state == "pending":
        state = "neutral"
    icon = "−" if state == "neutral" else step.get("icon", "·")
    return {
        "label": str(step.get("label", "")),
        "state": state,
        "icon": icon,
        "detail": str(step.get("detail", "")),
    }


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
        "discovery_seconds": None,
        "cm_events_status": None,
        "cm_events_product_status": None,
        "cm_events_seconds": None,
        "collection_seconds": None,
        "collection_done": 0,
        "collection_failed": 0,
        "analysis_seconds": None,
        "analysis_done": 0,
        "analysis_started": 0,
        "analysis_failed": 0,
        "failed": 0,
        "cm_metrics_total": None,
        "cm_metrics_done": 0,
        "cm_metrics_failed": 0,
        "cm_metrics_active": 0,
        "cm_metrics_jobs": None,
        "cm_metrics_skip_reason": None,
        "cm_metrics_seconds": None,
        "metadata_total": None,
        "metadata_done": 0,
        "metadata_skip_reason": None,
        "metadata_seconds": None,
        "summary_seconds": None,
        "total_seconds": None,
    }
    states = {
        "discovery": "pending",
        "cm_events": "pending",
        "collection": "pending",
        "analysis": "pending",
        "cm_metrics": "pending",
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
                set_duration(counters, "discovery_seconds", event.get("seconds"))
            elif status == "failed":
                states["discovery"] = "failed"
                set_duration(counters, "discovery_seconds", event.get("seconds"))
        elif stage == "profile_collection":
            if status == "started":
                states["collection"] = "running"
                counters["total"] = numeric_count(event.get("total"))
                counters["jobs"] = event.get("cm_jobs") or counters["jobs"]
            elif status == "done":
                states["collection"] = "done"
                counters["total"] = numeric_count(event.get("total")) or counters["total"]
                set_duration(counters, "collection_seconds", event.get("seconds"))
        elif stage == "analyzer_scoring":
            if status == "started":
                if states["collection"] != "failed":
                    states["collection"] = "done"
                states["analysis"] = "running"
                counters["total"] = numeric_count(event.get("total"))
                counters["jobs"] = event.get("jobs") or counters["jobs"]
            elif status == "done":
                states["analysis"] = "done"
                counters["total"] = numeric_count(event.get("total")) or counters["total"]
                set_duration(counters, "analysis_seconds", event.get("seconds"))
        elif stage == "case_processing":
            if status == "started":
                counters["total"] = numeric_count(event.get("total"))
                counters["jobs"] = event.get("jobs")
                if states["cm_events"] == "pending":
                    states["cm_events"] = "skipped"
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
                if states["cm_events"] == "running":
                    states["cm_events"] = "done"
                elif states["cm_events"] == "pending":
                    states["cm_events"] = "skipped"
                states["collection"] = "done"
                states["analysis"] = "done"
                if states["metadata"] == "running":
                    states["metadata"] = "done"
                if states["cm_metrics"] == "running":
                    states["cm_metrics"] = "done"
                elif states["cm_metrics"] == "pending":
                    states["cm_metrics"] = "skipped"
                states["summary"] = "running"
            elif status == "done":
                states["summary"] = "done"
                set_duration(counters, "summary_seconds", event.get("seconds"))
        elif stage == "cm_timeseries_refresh":
            if status == "started":
                if states["collection"] != "failed":
                    states["collection"] = "done"
                if states["analysis"] != "failed":
                    states["analysis"] = "done"
                states["cm_metrics"] = "running"
                if not event.get("case_id"):
                    counters["cm_metrics_total"] = numeric_count(event.get("total"))
                    counters["cm_metrics_jobs"] = event.get("jobs")
                else:
                    counters["cm_metrics_active"] += 1
            elif status == "done":
                if event.get("case_id"):
                    counters["cm_metrics_done"] += 1
                    counters["cm_metrics_active"] = max(0, counters["cm_metrics_active"] - 1)
                else:
                    states["cm_metrics"] = "done"
                    if event.get("total") is not None:
                        counters["cm_metrics_total"] = numeric_count(event.get("total"))
                    if event.get("jobs") is not None:
                        counters["cm_metrics_jobs"] = event.get("jobs")
                    set_duration(counters, "cm_metrics_seconds", event.get("seconds"))
            elif status == "failed":
                counters["cm_metrics_failed"] += 1
                counters["cm_metrics_active"] = max(0, counters["cm_metrics_active"] - 1)
            elif status == "skipped":
                states["cm_metrics"] = "skipped"
                counters["cm_metrics_skip_reason"] = event.get("reason")
        elif stage == "metadata_refresh":
            if status == "started":
                if states["collection"] != "failed":
                    states["collection"] = "done"
                if states["analysis"] != "failed":
                    states["analysis"] = "done"
                if states["cm_metrics"] == "running":
                    states["cm_metrics"] = "done"
                elif states["cm_metrics"] == "pending":
                    states["cm_metrics"] = "skipped"
                states["metadata"] = "running"
                if not event.get("case_id"):
                    counters["metadata_total"] = numeric_count(event.get("total"))
            elif status == "done":
                if event.get("case_id"):
                    counters["metadata_done"] += 1
                else:
                    states["metadata"] = "done"
                    if event.get("total") is not None:
                        counters["metadata_total"] = numeric_count(event.get("total"))
                    set_duration(counters, "metadata_seconds", event.get("seconds"))
            elif status == "failed":
                counters["failed"] += 1
            elif status == "skipped":
                states["metadata"] = "skipped"
                counters["metadata_skip_reason"] = event.get("reason")
        elif stage == "cm_events":
            counters["cm_events_status"] = status
            if event.get("seconds") is not None:
                counters["cm_events_seconds"] = event.get("seconds")
            if event.get("product_status") is not None:
                counters["cm_events_product_status"] = event.get("product_status")
            if status == "started":
                states["cm_events"] = "running"
            elif status == "done":
                states["cm_events"] = "done"
            elif status == "partial":
                states["cm_events"] = "done"
            elif status == "failed":
                states["cm_events"] = "failed"
            elif status == "skipped":
                states["cm_events"] = "skipped"
        elif stage == "batch":
            set_duration(counters, "total_seconds", event.get("total_seconds"))
            if status == "done":
                states["completed"] = "done"
                states["summary"] = "done"
                if states["cm_events"] == "running":
                    states["cm_events"] = "done"
                elif states["cm_events"] == "pending":
                    states["cm_events"] = "skipped"
                states["collection"] = "done"
                states["analysis"] = "done"
                if states["cm_metrics"] == "running":
                    states["cm_metrics"] = "done"
                elif states["cm_metrics"] == "pending":
                    states["cm_metrics"] = "skipped"
                if states["metadata"] == "running":
                    states["metadata"] = "done"
                elif states["metadata"] == "pending":
                    states["metadata"] = "skipped"
            elif status == "failed":
                states["completed"] = "failed"
    if job_status == "failed" and states["completed"] != "done":
        states["completed"] = "failed"
    if job_status == "cancelled" and states["completed"] != "done":
        states["completed"] = "failed"
    if job_status == "ok":
        states["completed"] = "done"
        for key in ("discovery", "collection", "analysis", "summary"):
            if states[key] in {"pending", "running"}:
                states[key] = "done"
        if states["cm_events"] in {"pending", "running"}:
            states["cm_events"] = "skipped"
        if states["cm_metrics"] in {"pending", "running"}:
            states["cm_metrics"] = "skipped"
        if states["metadata"] in {"pending", "running"}:
            states["metadata"] = "skipped"
    total = numeric_count(counters["total"])
    if total:
        collection_complete = counters["collection_done"] + counters["collection_failed"] >= total
        if collection_complete and states["collection"] != "failed":
            states["collection"] = "done"
        analysis_complete = counters["analysis_done"] + counters["analysis_failed"] >= total
        if analysis_complete and states["analysis"] != "failed":
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
            progress_step("Query discovery", states["discovery"], discovery_detail(counters)),
            progress_step("Cluster event context", states["cm_events"], cm_events_detail(counters)),
            progress_step(
                "Profile collection",
                states["collection"],
                case_detail(counters, "collection_done"),
            ),
            progress_step(
                "Analyzer scoring",
                states["analysis"],
                case_detail(counters, "analysis_done"),
            ),
            progress_step("Runtime metrics", states["cm_metrics"], cm_metrics_detail(counters)),
            progress_step("Metadata refresh", states["metadata"], metadata_detail(counters)),
            progress_step(
                "Ranking / summary",
                states["summary"],
                detail_with_time(
                    "summary written" if states["summary"] == "done" else "waiting",
                    counters.get("summary_seconds"),
                ),
            ),
            progress_step(
                "Completed",
                states["completed"],
                completed_detail(states["completed"], counters),
            ),
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
    return detail_with_time(f"{done}/{total} refreshed", counters.get("metadata_seconds"))


def cm_metrics_detail(counters: dict[str, Any]) -> str:
    if counters.get("cm_metrics_skip_reason"):
        return str(counters["cm_metrics_skip_reason"])
    total = counters.get("cm_metrics_total")
    done = counters.get("cm_metrics_done", 0)
    failed = counters.get("cm_metrics_failed", 0)
    if total is None:
        return "not requested yet"
    if not total:
        return "not requested"
    suffix = ""
    if counters.get("cm_metrics_active"):
        suffix = f", {counters['cm_metrics_active']} active"
    if failed:
        suffix = f", {failed} failed"
    return detail_with_time(f"{done}/{total} refreshed{suffix}", counters.get("cm_metrics_seconds"))


def cm_events_detail(counters: dict[str, Any]) -> str:
    product_status = counters.get("cm_events_product_status")
    seconds = counters.get("cm_events_seconds")
    if product_status:
        return detail_with_time(str(product_status), seconds)
    status = counters.get("cm_events_status")
    if status == "skipped":
        return "not requested"
    if status:
        return detail_with_time(str(status), seconds)
    return "waiting"


def progress_step(label: str, state: str, detail: str) -> dict[str, str]:
    icons = {"done": "✓", "running": "…", "failed": "!", "pending": "·", "skipped": "−"}
    return {"label": label, "state": state, "icon": icons.get(state, "·"), "detail": detail}


def discovery_detail(counters: dict[str, Any]) -> str:
    if counters["candidates_selected"] is not None:
        return detail_with_time(
            f"{counters['candidates_selected']} selected", counters.get("discovery_seconds")
        )
    return "reading query summaries; broad CM windows can take a minute"


def case_detail(counters: dict[str, Any], key: str) -> str:
    total = numeric_count(counters["total"])
    done = numeric_count(counters[key])
    seconds_key = "collection_seconds" if key == "collection_done" else "analysis_seconds"
    if total:
        return detail_with_time(f"{done}/{total}", counters.get(seconds_key))
    return "waiting"


def completed_detail(state: str, counters: dict[str, Any]) -> str:
    if state == "done":
        return detail_with_total_time("batch done", counters.get("total_seconds"))
    if state == "failed":
        return detail_with_total_time("failed", counters.get("total_seconds"))
    return "waiting"


def detail_with_time(detail: str, seconds: object) -> str:
    formatted = format_duration(seconds)
    if formatted is None:
        return detail
    return f"{detail}, elapsed {formatted}"


def detail_with_total_time(detail: str, seconds: object) -> str:
    formatted = format_duration(seconds)
    if formatted is None:
        return detail
    return f"{detail}, total elapsed {formatted}"


def set_duration(counters: dict[str, Any], key: str, value: object) -> None:
    seconds = numeric_duration(value)
    if seconds is not None:
        counters[key] = seconds


def numeric_duration(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed < 0:
        return None
    return round(parsed, 3)


def format_duration(value: object) -> str | None:
    seconds = numeric_duration(value)
    if seconds is None:
        return None
    if seconds < 10:
        return f"{seconds:.1f}s"
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = seconds / 60
    if minutes < 10:
        return f"{minutes:.1f}m"
    return f"{minutes:.0f}m"
