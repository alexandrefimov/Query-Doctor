"""CM sample smoke candidate selection helpers."""

from __future__ import annotations

from typing import Any

from query_doctor.cm.models import CMQuerySummary


SUCCESS_STATUSES = {"success", "succeeded", "finished", "completed", "ok"}
QUERY_TYPES = {"query"}


class SelectionDiagnostics:
    def __init__(self, *, summaries_fetched: int) -> None:
        self.summaries_fetched = summaries_fetched
        self.summaries_considered = 0
        self.selected_candidates = 0
        self.skipped_missing_query_id = 0
        self.skipped_missing_duration = 0
        self.skipped_duration_above_max = 0
        self.skipped_duration_below_min = 0
        self.skipped_non_success_status = 0
        self.skipped_non_query_type = 0
        self.skipped_other_filter = 0


def normalized(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip().lower()
    return text or None


def is_success_status(status: str | None) -> bool:
    value = normalized(status)
    return value is None or value in SUCCESS_STATUSES


def is_query_type(query_type: str | None) -> bool:
    value = normalized(query_type)
    return value is None or value in QUERY_TYPES


def summary_duration_sec(summary: CMQuerySummary) -> float | None:
    return summary.duration_sec


def is_eligible_summary(summary: CMQuerySummary, config: Any) -> bool:
    return selection_skip_reason(summary, config) is None


def selection_skip_reason(summary: CMQuerySummary, config: Any) -> str | None:
    if not summary.query_id:
        return "missing_query_id"
    if not is_query_type(summary.query_type):
        return "non_query_type"

    duration = summary_duration_sec(summary)
    if duration is None and (config.sample == "slow" or not config.include_missing_duration):
        return "missing_duration"

    if config.sample == "healthy":
        if not is_success_status(summary.status):
            return "non_success_status"
        if (
            config.min_duration_sec_explicit
            and duration is not None
            and duration < config.min_duration_sec
        ):
            return "duration_below_min"
        if duration is not None and duration > config.max_duration_sec:
            return "duration_above_max"
        return None

    if duration is not None and duration < config.min_duration_sec:
        return "duration_below_min"
    return None


def record_selection_skip(diagnostics: SelectionDiagnostics, reason: str) -> None:
    if reason == "missing_query_id":
        diagnostics.skipped_missing_query_id += 1
    elif reason == "missing_duration":
        diagnostics.skipped_missing_duration += 1
    elif reason == "duration_above_max":
        diagnostics.skipped_duration_above_max += 1
    elif reason == "duration_below_min":
        diagnostics.skipped_duration_below_min += 1
    elif reason == "non_success_status":
        diagnostics.skipped_non_success_status += 1
    elif reason == "non_query_type":
        diagnostics.skipped_non_query_type += 1
    else:
        diagnostics.skipped_other_filter += 1


def select_sample(summaries: list[CMQuerySummary], config: Any) -> list[CMQuerySummary]:
    selected, _diagnostics = select_sample_with_diagnostics(summaries, config)
    return selected


def select_sample_with_diagnostics(
    summaries: list[CMQuerySummary],
    config: Any,
) -> tuple[list[CMQuerySummary], SelectionDiagnostics]:
    diagnostics = SelectionDiagnostics(summaries_fetched=len(summaries))
    eligible: list[CMQuerySummary] = []
    for summary in summaries:
        diagnostics.summaries_considered += 1
        reason = selection_skip_reason(summary, config)
        if reason is None:
            eligible.append(summary)
        else:
            record_selection_skip(diagnostics, reason)

    if config.sample == "healthy":
        selected = sorted(
            eligible,
            key=lambda item: (
                summary_duration_sec(item) is None,
                summary_duration_sec(item) if summary_duration_sec(item) is not None else float("inf"),
                item.query_id,
            ),
        )[: config.limit]
    else:
        selected = sorted(
            eligible,
            key=lambda item: (
                -(summary_duration_sec(item) or 0),
                item.query_id,
            ),
        )[: config.limit]
    diagnostics.selected_candidates = len(selected)
    return selected, diagnostics


def display_duration(summary: CMQuerySummary) -> str:
    duration = summary_duration_sec(summary)
    if duration is None:
        return "n/a"
    if duration == int(duration):
        return f"{int(duration)}s"
    return f"{duration:.3f}s"


def print_candidate_table(candidates: list[CMQuerySummary]) -> None:
    headers = ["query_id", "duration", "status", "user", "query_type"]
    rows = [
        [
            summary.query_id,
            display_duration(summary),
            summary.status or "<unknown>",
            "<user>" if summary.user else "<unknown>",
            summary.query_type or "<unknown>",
        ]
        for summary in candidates
    ]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows)) if rows else len(headers[index])
        for index in range(len(headers))
    ]
    print(" | ".join(headers[index].ljust(widths[index]) for index in range(len(headers))))
    print(" | ".join("-" * widths[index] for index in range(len(headers))))
    for row in rows:
        print(" | ".join(row[index].ljust(widths[index]) for index in range(len(headers))))


def print_selection_diagnostics(
    config: Any,
    diagnostics: SelectionDiagnostics,
    *,
    show_zero_hint: bool,
) -> None:
    print("Selection diagnostics:")
    print(f"- Summaries fetched: {diagnostics.summaries_fetched}")
    print(f"- Considered: {diagnostics.summaries_considered}")
    print(f"- Selected: {diagnostics.selected_candidates}")
    skip_lines = [
        ("Skipped missing query id", diagnostics.skipped_missing_query_id),
        ("Skipped missing duration", diagnostics.skipped_missing_duration),
        (f"Skipped duration > {config.max_duration_sec}s", diagnostics.skipped_duration_above_max),
        (f"Skipped duration < {config.min_duration_sec}s", diagnostics.skipped_duration_below_min),
        ("Skipped non-success status", diagnostics.skipped_non_success_status),
        ("Skipped non-QUERY type", diagnostics.skipped_non_query_type),
        ("Skipped other explicit filter", diagnostics.skipped_other_filter),
    ]
    for label, count in skip_lines:
        if count:
            print(f"- {label}: {count}")
    if diagnostics.selected_candidates == 0 and show_zero_hint:
        print(
            "No candidates selected. Try increasing --max-duration-sec or --candidate-scan-limit, "
            "or inspect whether CM summary rows include duration/status/query type fields."
        )
