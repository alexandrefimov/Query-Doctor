"""Local workload fingerprint history and regression labeling."""

from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from query_doctor.cli import collect_cm_profiles as cm_profiles


SCHEMA_VERSION = 1
DEFAULT_WORKLOAD_HISTORY_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_BASELINE_WINDOW = 30
WORKLOAD_HISTORY_PATH_ENV = "QUERY_DOCTOR_WORKLOAD_HISTORY_PATH"
WORKLOAD_FINGERPRINT_RE = re.compile(r"^wf_[0-9a-f]{24}$")
REGRESSION_LABELS = {"none", "mild", "strong", "unknown"}


@dataclass(frozen=True)
class WorkloadHistoryRecord:
    schema_version: int
    recorded_at_iso: str
    workload_fingerprint: str
    count: int
    duration_sec_p50: float | None
    duration_sec_p95: float | None
    duration_sec_total: float | None
    pool_top: str | None
    primary_bottleneck_top: str | None
    score_top: str | None


@dataclass(frozen=True)
class WorkloadBaseline:
    regression: str
    baseline_duration_sec_p95: float | None
    baseline_sample_count: int


def default_workload_history_path() -> Path:
    configured = os.environ.get(WORKLOAD_HISTORY_PATH_ENV)
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".query-doctor" / "workload_history.jsonl"


def update_summary_with_workload_history(
    summary: dict[str, object],
    *,
    path: Path | None = None,
    max_bytes: int = DEFAULT_WORKLOAD_HISTORY_MAX_BYTES,
    baseline_window: int = DEFAULT_BASELINE_WINDOW,
) -> None:
    """Annotate a batch summary from prior local history and append current aggregates.

    The input summary is already the raw-free batch summary. This function never
    reads case directories, SQL, profiles, metadata, or optimizer artifacts.
    """

    target = path or default_workload_history_path()
    history = load_workload_history(target, limit_per_fingerprint=baseline_window)
    current_records = history_records_from_summary(summary)
    baselines = {
        record.workload_fingerprint: baseline_from_history(
            current=record,
            history=history.get(record.workload_fingerprint, ()),
        )
        for record in current_records
    }
    apply_baselines_to_summary(summary, baselines)
    append_status = append_workload_history(current_records, path=target, max_bytes=max_bytes)
    summary["workload_history"] = {
        "schema_version": SCHEMA_VERSION,
        "enabled": True,
        "loaded_record_count": sum(len(records) for records in history.values()),
        "appended_record_count": len(current_records) if append_status == "ok" else 0,
        "append_status": append_status,
        "regression_counts": regression_counts(baselines.values()),
    }


def load_workload_history(
    path: Path,
    *,
    limit_per_fingerprint: int = DEFAULT_BASELINE_WINDOW,
) -> dict[str, tuple[WorkloadHistoryRecord, ...]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    grouped: dict[str, list[WorkloadHistoryRecord]] = {}
    for line in lines:
        record = parse_workload_history_line(line)
        if record is None:
            continue
        grouped.setdefault(record.workload_fingerprint, []).append(record)
    window = max(0, limit_per_fingerprint)
    return {
        fingerprint: tuple(records[-window:])
        for fingerprint, records in grouped.items()
        if window and records
    }


def parse_workload_history_line(line: str) -> WorkloadHistoryRecord | None:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        return None
    fingerprint = safe_workload_fingerprint(payload.get("workload_fingerprint"))
    count = numeric_int(payload.get("count"))
    if not fingerprint or count is None or count <= 0:
        return None
    return WorkloadHistoryRecord(
        schema_version=SCHEMA_VERSION,
        recorded_at_iso=safe_text(payload.get("recorded_at_iso")),
        workload_fingerprint=fingerprint,
        count=count,
        duration_sec_p50=numeric_float(payload.get("duration_sec_p50")),
        duration_sec_p95=numeric_float(payload.get("duration_sec_p95")),
        duration_sec_total=numeric_float(payload.get("duration_sec_total")),
        pool_top=safe_optional_label(payload.get("pool_top")),
        primary_bottleneck_top=safe_optional_label(payload.get("primary_bottleneck_top")),
        score_top=safe_optional_label(payload.get("score_top")),
    )


def history_records_from_summary(summary: dict[str, object]) -> list[WorkloadHistoryRecord]:
    cases = summary.get("cases")
    raw_cases = (
        [case for case in cases if isinstance(case, dict)] if isinstance(cases, list) else []
    )
    grouped: dict[str, list[dict[str, object]]] = {}
    for case in raw_cases:
        if case.get("workload_fingerprint_incomplete"):
            continue
        fingerprint = safe_workload_fingerprint(
            case.get("group_fingerprint") or case.get("workload_fingerprint")
        )
        if not fingerprint:
            continue
        grouped.setdefault(fingerprint, []).append(case)
    recorded_at_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    records = []
    for fingerprint, members in sorted(grouped.items()):
        aggregates = workload_aggregates(members)
        records.append(
            WorkloadHistoryRecord(
                schema_version=SCHEMA_VERSION,
                recorded_at_iso=recorded_at_iso,
                workload_fingerprint=fingerprint,
                count=len(members),
                duration_sec_p50=aggregates.get("duration_sec_p50"),
                duration_sec_p95=aggregates.get("duration_sec_p95"),
                duration_sec_total=aggregates.get("duration_sec_total"),
                pool_top=aggregates.get("pool_top"),
                primary_bottleneck_top=aggregates.get("primary_bottleneck_top"),
                score_top=aggregates.get("score_top"),
            )
        )
    return records


def workload_aggregates(members: list[dict[str, object]]) -> dict[str, Any]:
    durations = sorted(
        value
        for member in members
        if (value := numeric_float(member.get("duration_sec"))) is not None
    )
    return {
        "duration_sec_total": round(sum(durations), 3) if durations else None,
        "duration_sec_p50": percentile_value(durations, 0.50),
        "duration_sec_p95": percentile_value(durations, 0.95),
        "pool_top": modal_label(member.get("pool") for member in members),
        "primary_bottleneck_top": modal_label(
            primary_bottleneck_label(member) for member in members
        ),
        "score_top": modal_label(member.get("score_severity") for member in members),
    }


def baseline_from_history(
    *,
    current: WorkloadHistoryRecord,
    history: tuple[WorkloadHistoryRecord, ...],
) -> WorkloadBaseline:
    values = sorted(
        value
        for record in history
        if (value := numeric_float(record.duration_sec_p95)) is not None and value > 0
    )
    current_p95 = numeric_float(current.duration_sec_p95)
    if not values or current_p95 is None or current_p95 <= 0:
        return WorkloadBaseline(
            regression="unknown",
            baseline_duration_sec_p95=None,
            baseline_sample_count=len(values),
        )
    baseline = percentile_value(values, 0.50)
    if baseline is None or baseline <= 0:
        regression = "unknown"
    else:
        ratio = current_p95 / baseline
        delta = current_p95 - baseline
        if ratio >= 2.0 and delta >= 10:
            regression = "strong"
        elif ratio >= 1.5 and delta >= 5:
            regression = "mild"
        else:
            regression = "none"
    return WorkloadBaseline(
        regression=regression,
        baseline_duration_sec_p95=baseline,
        baseline_sample_count=len(values),
    )


def apply_baselines_to_summary(
    summary: dict[str, object],
    baselines: dict[str, WorkloadBaseline],
) -> None:
    cases = summary.get("cases")
    raw_cases = (
        [case for case in cases if isinstance(case, dict)] if isinstance(cases, list) else []
    )
    for case in raw_cases:
        fingerprint = safe_workload_fingerprint(
            case.get("group_fingerprint") or case.get("workload_fingerprint")
        )
        baseline = baselines.get(fingerprint)
        if baseline is None:
            continue
        case["workload_regression"] = baseline.regression
        case["workload_baseline_sample_count"] = baseline.baseline_sample_count
        if baseline.baseline_duration_sec_p95 is not None:
            case["workload_baseline_duration_sec_p95"] = baseline.baseline_duration_sec_p95

    workload_groups = summary.get("workload_groups")
    if not isinstance(workload_groups, dict):
        return
    groups = workload_groups.get("groups")
    if not isinstance(groups, list):
        return
    for group in groups:
        if not isinstance(group, dict):
            continue
        fingerprint = safe_workload_fingerprint(group.get("fingerprint"))
        baseline = baselines.get(fingerprint)
        if baseline is None:
            continue
        group["baseline"] = {
            "schema_version": SCHEMA_VERSION,
            "regression": baseline.regression,
            "sample_count": baseline.baseline_sample_count,
            "duration_sec_p95": baseline.baseline_duration_sec_p95,
        }


def append_workload_history(
    records: list[WorkloadHistoryRecord],
    *,
    path: Path,
    max_bytes: int = DEFAULT_WORKLOAD_HISTORY_MAX_BYTES,
) -> str:
    if not records:
        return "empty"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        rotate_workload_history_if_needed(path, max_bytes=max_bytes)
        with path.open("a", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(asdict(record), sort_keys=True) + "\n")
    except OSError:
        return "failed"
    return "ok"


def rotate_workload_history_if_needed(path: Path, *, max_bytes: int) -> None:
    try:
        current_size = path.stat().st_size
    except OSError:
        return
    if current_size <= max_bytes:
        return
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    path.replace(path.with_name(f"{path.stem}-{stamp}{path.suffix}"))


def regression_counts(baselines: object) -> dict[str, int]:
    counter = Counter(
        baseline.regression for baseline in baselines if baseline.regression in REGRESSION_LABELS
    )
    return dict(sorted(counter.items(), key=lambda item: item[0]))


def percentile_value(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    index = max(0, min(len(values) - 1, int((len(values) * percentile) + 0.999999) - 1))
    return round(values[index], 3)


def modal_label(values: object) -> str | None:
    counter: Counter[str] = Counter()
    for value in values:
        text = safe_optional_label(value)
        if text:
            counter[text] += 1
    if not counter:
        return None
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]


def primary_bottleneck_label(summary: dict[str, object]) -> object:
    primary = summary.get("case_primary_bottleneck")
    return primary.get("label") if isinstance(primary, dict) else None


def safe_workload_fingerprint(value: object) -> str:
    text = str(value or "").strip().lower()
    return text if WORKLOAD_FINGERPRINT_RE.fullmatch(text) else ""


def safe_optional_label(value: object) -> str | None:
    text = safe_text(value).strip().lower()[:160]
    return text or None


def safe_text(value: object) -> str:
    return cm_profiles.sanitize_text_for_log(str(value or ""))


def numeric_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def numeric_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None
