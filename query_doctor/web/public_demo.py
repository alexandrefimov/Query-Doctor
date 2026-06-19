"""Public synthetic demo runtime setup."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import MutableMapping

from query_doctor.web.action_outcomes import OUTCOME_PATH_ENV
from query_doctor.web.models import WebError, WebSettings


DEFAULT_PUBLIC_DEMO_DIR = Path(tempfile.gettempdir()) / "query-doctor-public-demo-pack"
SUMMARY_NAME = "batch_summary.json"
ACTION_OUTCOMES_NAME = "action_outcomes.jsonl"


@dataclass(frozen=True)
class PublicDemoRuntime:
    settings: WebSettings
    demo_dir: Path
    summary_path: Path
    action_outcomes_path: Path
    generated: bool


def default_public_demo_summary_path() -> Path:
    return DEFAULT_PUBLIC_DEMO_DIR / SUMMARY_NAME


def prepare_public_demo_runtime(
    settings: WebSettings,
    *,
    out_dir: Path | None = None,
    env: MutableMapping[str, str] | None = None,
) -> PublicDemoRuntime | None:
    if not settings.public_demo:
        return None
    target_env = os.environ if env is None else env
    generated = False
    demo_dir = settings.batch_summary.parent if settings.batch_summary is not None else None
    if out_dir is not None or settings.batch_summary == default_public_demo_summary_path():
        demo_dir = (out_dir or DEFAULT_PUBLIC_DEMO_DIR).expanduser().resolve()
        try:
            from query_doctor.cli.demo_data import generate_demo_pack

            generate_demo_pack(demo_dir, overwrite=True)
        except ValueError as exc:
            raise WebError(
                "Public demo pack could not be generated.",
                title="Public demo pack generation failed",
                reason_code="web.public_demo_generation_failed",
                stage="Preparing public demo runtime",
                next_step="Regenerate the synthetic demo pack or choose a writable demo output directory.",
            ) from exc
        summary_path = demo_dir / SUMMARY_NAME
        generated = True
    else:
        if settings.batch_summary is None:
            raise WebError(
                "Public demo mode requires a generated synthetic demo pack.",
                title="Public demo pack is not configured",
                reason_code="web.public_demo_summary_missing",
                stage="Preparing public demo runtime",
                next_step="Generate the synthetic demo pack before starting public demo mode.",
            )
        summary_path = settings.batch_summary.expanduser()
        demo_dir = summary_path.parent
        if not summary_path.is_file():
            raise WebError(
                "Public demo batch summary is not available.",
                title="Public demo batch summary is unavailable",
                reason_code="web.public_demo_summary_unavailable",
                stage="Preparing public demo runtime",
                next_step="Regenerate the synthetic demo pack or pass the generated batch summary.",
            )
    action_outcomes_path = demo_dir / ACTION_OUTCOMES_NAME
    target_env[OUTCOME_PATH_ENV] = str(action_outcomes_path)
    return PublicDemoRuntime(
        settings=replace(settings, batch_summary=summary_path, no_llm=True),
        demo_dir=demo_dir,
        summary_path=summary_path,
        action_outcomes_path=action_outcomes_path,
        generated=generated,
    )
