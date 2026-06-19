"""Route-safe web job id helpers."""

from __future__ import annotations

import re


WEB_JOB_ID_PATTERN = r"[0-9a-f]{32}"
WEB_JOB_ID_RE = re.compile(rf"{WEB_JOB_ID_PATTERN}\Z")


def route_safe_job_id(value: object) -> str:
    job_id = str(value or "").strip()
    return job_id if WEB_JOB_ID_RE.fullmatch(job_id) else ""


def web_job_url(value: object) -> str:
    job_id = route_safe_job_id(value)
    return f"/jobs/{job_id}" if job_id else ""
