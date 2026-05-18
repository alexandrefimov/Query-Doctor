"""Local action-outcome tracking for Recent scan recommendations."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from query_doctor.web.display_safety import sanitize_browser_error_text
from query_doctor.web.form_helpers import first_form_value
from query_doctor.web.models import WebError


SCHEMA_VERSION = 1
DEFAULT_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_LOAD_LIMIT = 200
OUTCOME_PATH_ENV = "QUERY_DOCTOR_ACTION_OUTCOMES_PATH"

RECOMMENDATION_LABELS = {
    "query_optimization_review.v1": "Query optimization review",
    "stats_refresh_review.v1": "Stats refresh review",
    "runtime_admission_check.v1": "Admission/runtime check",
}
ALLOWED_APPLIED = {"yes", "no", "skip"}
ALLOWED_OUTCOMES = {"improved", "no_change", "worsened", "unsure", "not_applicable"}
WORKLOAD_FINGERPRINT_RE = re.compile(r"^wf_[0-9a-f]{24}$")
CASE_ID_RE = re.compile(r"^case-[0-9]{3}$")


@dataclass(frozen=True)
class ActionOutcomeRecord:
    schema_version: int
    recorded_at_iso: str
    workload_fingerprint: str
    case_fingerprint: str
    case_id_local: str
    recommendation_id: str
    applied: str
    outcome: str
    note_redacted: str = ""


def action_outcomes_path() -> Path:
    configured = os.environ.get(OUTCOME_PATH_ENV)
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".query-doctor" / "action_outcomes.jsonl"


def safe_recommendation_label(recommendation_id: str) -> str:
    return RECOMMENDATION_LABELS.get(recommendation_id, "Unknown recommendation")


def recommendation_id_allowed(value: Any) -> bool:
    return str(value or "") in RECOMMENDATION_LABELS


def safe_workload_fingerprint(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if WORKLOAD_FINGERPRINT_RE.fullmatch(text) else ""


def safe_case_id(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if CASE_ID_RE.fullmatch(text) else ""


def case_fingerprint(workload_fingerprint: str, query_id: Any) -> str:
    query_hash = hashlib.sha256(str(query_id or "").encode("utf-8")).hexdigest()[:16]
    digest = hashlib.sha256(f"{workload_fingerprint}:{query_hash}".encode("utf-8")).hexdigest()
    return f"cf_{digest[:24]}"


def action_outcome_record_from_case(
    *,
    case_id: str,
    case: dict[str, Any],
    recommendation_id: str,
    form: dict[str, list[str]],
) -> ActionOutcomeRecord:
    if not recommendation_id_allowed(recommendation_id):
        raise WebError("Unknown recommendation outcome target.")
    safe_local_case_id = safe_case_id(case_id)
    if not safe_local_case_id:
        raise WebError("Invalid case outcome target.")
    workload_fingerprint = safe_workload_fingerprint(
        case.get("group_fingerprint") or case.get("workload_fingerprint")
    )
    if not workload_fingerprint:
        raise WebError("Outcome tracking is unavailable for this case.")

    applied = normalize_applied(first_form_value(form, "applied"))
    outcome = normalize_outcome(first_form_value(form, "outcome"), applied=applied)
    note = sanitize_browser_error_text(first_form_value(form, "note") or "", max_chars=256)
    return ActionOutcomeRecord(
        schema_version=SCHEMA_VERSION,
        recorded_at_iso=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        workload_fingerprint=workload_fingerprint,
        case_fingerprint=case_fingerprint(workload_fingerprint, case.get("query_id")),
        case_id_local=safe_local_case_id,
        recommendation_id=recommendation_id,
        applied=applied,
        outcome=outcome,
        note_redacted=note,
    )


def normalize_applied(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text not in ALLOWED_APPLIED:
        raise WebError("Invalid action outcome value.")
    return text


def normalize_outcome(value: Any, *, applied: str) -> str:
    if applied != "yes":
        return "not_applicable"
    text = str(value or "unsure").strip().lower()
    if text not in ALLOWED_OUTCOMES or text == "not_applicable":
        raise WebError("Invalid action result value.")
    return text


def append_action_outcome(
    record: ActionOutcomeRecord,
    *,
    path: Path | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> Path:
    target = path or action_outcomes_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    rotate_action_outcomes_if_needed(target, max_bytes=max_bytes)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(record), sort_keys=True) + "\n")
    return target


def rotate_action_outcomes_if_needed(path: Path, *, max_bytes: int) -> None:
    try:
        current_size = path.stat().st_size
    except OSError:
        return
    if current_size <= max_bytes:
        return
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    path.replace(path.with_name(f"{path.stem}-{stamp}{path.suffix}"))


def load_action_outcomes(
    *,
    path: Path | None = None,
    limit: int = DEFAULT_LOAD_LIMIT,
) -> list[ActionOutcomeRecord]:
    target = path or action_outcomes_path()
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    records: list[ActionOutcomeRecord] = []
    for line in lines:
        record = parse_action_outcome_line(line)
        if record is not None:
            records.append(record)
    return records[-max(0, limit) :]


def parse_action_outcome_line(line: str) -> ActionOutcomeRecord | None:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("schema_version") != SCHEMA_VERSION:
        return None
    recommendation_id = str(payload.get("recommendation_id") or "")
    applied = str(payload.get("applied") or "")
    outcome = str(payload.get("outcome") or "")
    workload_fingerprint = safe_workload_fingerprint(payload.get("workload_fingerprint"))
    case_id_local = safe_case_id(payload.get("case_id_local"))
    case_fingerprint_value = safe_case_fingerprint(payload.get("case_fingerprint"))
    if not (
        recommendation_id_allowed(recommendation_id)
        and applied in ALLOWED_APPLIED
        and outcome in ALLOWED_OUTCOMES
        and workload_fingerprint
        and case_id_local
        and case_fingerprint_value
    ):
        return None
    return ActionOutcomeRecord(
        schema_version=SCHEMA_VERSION,
        recorded_at_iso=sanitize_browser_error_text(payload.get("recorded_at_iso") or ""),
        workload_fingerprint=workload_fingerprint,
        case_fingerprint=case_fingerprint_value,
        case_id_local=case_id_local,
        recommendation_id=recommendation_id,
        applied=applied,
        outcome=outcome,
        note_redacted=sanitize_browser_error_text(
            payload.get("note_redacted") or "", max_chars=256
        ),
    )


def safe_case_fingerprint(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if re.fullmatch(r"cf_[0-9a-f]{24}", text) else ""


def action_outcome_count(*, path: Path | None = None) -> int:
    return len(load_action_outcomes(path=path, limit=1_000_000))
