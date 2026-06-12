"""Shared web job progress definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from query_doctor.web.models import WebJobSnapshot


@dataclass(frozen=True)
class JobProgressStep:
    label: str
    stage_labels: tuple[str, ...]
    progress: int

    @property
    def stage_label(self) -> str:
        return self.stage_labels[0]


@dataclass(frozen=True)
class JobProgressStepView:
    label: str
    state: str
    icon: str
    detail: str


@dataclass(frozen=True)
class JobProgressView:
    current_stage: str
    current_index: int
    percent: int
    steps: tuple[JobProgressStepView, ...]


WEB_PROGRESS_STEPS = (
    JobProgressStep("Checking Query ID", ("Checking Query ID",), 4),
    JobProgressStep("Collecting or reusing profile", ("Collecting or reusing profile",), 24),
    JobProgressStep("Analyzing profile", ("Analyzing profile",), 56),
    JobProgressStep("Generating Python report", ("Generating Python report",), 76),
    JobProgressStep("Preparing deterministic result", ("Preparing deterministic result",), 90),
    JobProgressStep("Done", ("Done",), 100),
)
BATCH_PROGRESS_STEPS = (
    JobProgressStep("Checking recent scan parameters", ("Checking recent scan parameters",), 4),
    JobProgressStep("Running recent scan", ("Running recent scan",), 24),
    JobProgressStep("Reading batch_summary.json", ("Reading batch_summary.json",), 86),
    JobProgressStep("Done", ("Done",), 100),
)
REPORT_PROGRESS_STEPS = (
    JobProgressStep("Checking case", ("Checking selected batch case",), 8),
    JobProgressStep("Generating report", ("Generating validated report",), 62),
    JobProgressStep("Validating result", ("Validating result",), 88),
    JobProgressStep("Done", ("Done",), 100),
)
OPTIMIZED_QUERY_PROGRESS_STEPS = (
    JobProgressStep("Checking source SQL", ("Checking source SQL",), 8),
    JobProgressStep("Generating draft", ("Generating optimizer draft",), 45),
    JobProgressStep("Validating draft", ("Validating optimizer draft",), 88),
    JobProgressStep("Done", ("Done",), 100),
)
LLM_ACTIONS_PROGRESS_STEPS = (
    JobProgressStep("Checking case", ("Checking selected case", "Checking selected batch case"), 6),
    JobProgressStep("Generating report", ("Generating validated report",), 38),
    JobProgressStep("Generating optimizer draft", ("Generating optimizer draft",), 72),
    JobProgressStep("Done", ("Done",), 100),
)

WEB_STAGES = tuple(
    (index, step.stage_label, step.progress) for index, step in enumerate(WEB_PROGRESS_STEPS)
)
BATCH_STAGES = tuple(
    (index, step.stage_label, step.progress) for index, step in enumerate(BATCH_PROGRESS_STEPS)
)
BATCH_REPORT_STAGES = tuple(
    (index, step.stage_label, step.progress) for index, step in enumerate(REPORT_PROGRESS_STEPS)
)
OPTIMIZED_QUERY_STAGES = tuple(
    (index, step.stage_label, step.progress)
    for index, step in enumerate(OPTIMIZED_QUERY_PROGRESS_STEPS)
)
LLM_ACTIONS_STAGES = tuple(
    (index, step.stage_label, step.progress)
    for index, step in enumerate(LLM_ACTIONS_PROGRESS_STEPS)
)


def progress_step_index(
    steps: tuple[JobProgressStep, ...],
    stage_label: str,
    progress: int | float | None = None,
    *,
    default_index: int = 0,
) -> int:
    normalized = stage_label.strip().lower()
    for index, step in enumerate(steps):
        if normalized in {label.lower() for label in step.stage_labels}:
            return index
    if progress is None:
        return default_index
    bounded_progress = max(0, min(100, int(progress)))
    if bounded_progress >= 100:
        return len(steps) - 1
    if bounded_progress <= 0:
        return default_index
    step_bucket = (bounded_progress - 1) // (100 // len(steps))
    return max(default_index, min(len(steps) - 2, step_bucket))


def indexed_progress_percent(steps: tuple[JobProgressStep, ...], step_index: int) -> int:
    step_count = len(steps)
    bounded_index = max(0, min(step_count - 1, step_index))
    if step_count <= 1:
        return 0
    if bounded_index >= step_count - 1:
        return 100
    return int(round((bounded_index / step_count) * 100))


def build_progress_view(
    steps: tuple[JobProgressStep, ...],
    current_stage: str,
    progress: int | float | None,
    *,
    default_index: int = 0,
) -> JobProgressView:
    current_index = progress_step_index(steps, current_stage, progress, default_index=default_index)
    current_done = current_step_is_done(steps, current_index, current_stage, progress)
    return JobProgressView(
        current_stage=current_stage,
        current_index=current_index,
        percent=indexed_progress_percent(steps, current_index),
        steps=tuple(
            progress_step_view(
                step,
                index,
                current_index,
                current_stage,
                current_done=current_done,
            )
            for index, step in enumerate(steps)
        ),
    )


def current_step_is_done(
    steps: tuple[JobProgressStep, ...],
    current_index: int,
    current_stage: str,
    progress: int | float | None,
) -> bool:
    if not steps or current_index != len(steps) - 1 or progress is None:
        return False
    try:
        bounded_progress = max(0, min(100, int(progress)))
    except (TypeError, ValueError):
        return False
    if bounded_progress < 100:
        return False
    step = steps[current_index]
    normalized = current_stage.strip().lower()
    return normalized in {label.lower() for label in step.stage_labels}


def progress_steps_for_job_kind(kind: str) -> tuple[JobProgressStep, ...]:
    if kind in {"batch_report", "query_report", "batch_llm_report", "query_llm_report"}:
        return REPORT_PROGRESS_STEPS
    if kind in {"batch_optimized_query", "query_optimized_query"}:
        return OPTIMIZED_QUERY_PROGRESS_STEPS
    if kind in {
        "batch_case_actions",
        "query_case_actions",
        "batch_llm_actions",
        "query_llm_actions",
    }:
        return LLM_ACTIONS_PROGRESS_STEPS
    if kind in {"batch", "running"}:
        return BATCH_PROGRESS_STEPS
    return WEB_PROGRESS_STEPS


def progress_view_for_job(
    kind: str, stage_label: str, progress: int | float | None
) -> JobProgressView:
    steps = progress_steps_for_job_kind(kind)
    default_index = (
        1 if kind in {"batch_report", "query_report", "batch_llm_report", "query_llm_report"} else 0
    )
    return build_progress_view(steps, stage_label, progress, default_index=default_index)


def progress_view_from_snapshot(job: WebJobSnapshot | None) -> JobProgressView | None:
    if job is None:
        return None
    return progress_view_for_job(job.kind, job.stage_label, job.progress)


def progress_view_payload(view: JobProgressView) -> dict[str, object]:
    return {
        "current_stage": view.current_stage,
        "current_index": view.current_index,
        "percent": view.percent,
        "steps": [
            {
                "label": step.label,
                "state": step.state,
                "icon": step.icon,
                "detail": step.detail,
            }
            for step in view.steps
        ],
    }


def progress_step_view(
    step: JobProgressStep,
    step_index: int,
    current_index: int,
    current_stage: str,
    *,
    current_done: bool = False,
) -> JobProgressStepView:
    if step_index < current_index:
        return JobProgressStepView(step.label, "done", "✓", "Done")
    if step_index == current_index:
        if current_done:
            return JobProgressStepView(step.label, "done", "✓", "Done")
        return JobProgressStepView(step.label, "running", "…", current_stage)
    return JobProgressStepView(step.label, "neutral", "−", "Pending")
