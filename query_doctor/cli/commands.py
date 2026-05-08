"""Logical CLI role to command prefix mapping."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from os import environ
from pathlib import Path
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class CommandSpec:
    module: str
    console_script: str


COMMAND_SPECS = MappingProxyType(
    {
        "analyze": CommandSpec(
            module="query_doctor.cli.analyze_profile",
            console_script="query-doctor-analyze",
        ),
        "batch_recent": CommandSpec(
            module="query_doctor.cli.batch_recent",
            console_script="query-doctor-batch-recent",
        ),
        "collect_cm": CommandSpec(
            module="query_doctor.cli.collect_cm_profiles",
            console_script="query-doctor-collect-cm-profiles",
        ),
        "cm_events": CommandSpec(
            module="query_doctor.cli.cm_events",
            console_script="query-doctor-cm-events",
        ),
        "collect_impala_context": CommandSpec(
            module="query_doctor.cli.collect_impala_context",
            console_script="query-doctor-collect-impala-context",
        ),
        "optimize_query": CommandSpec(
            module="query_doctor.cli.optimize_query",
            console_script="query-doctor-optimize-query",
        ),
        "pipeline": CommandSpec(
            module="query_doctor.cli.pipeline",
            console_script="query-doctor-pipeline",
        ),
        "report": CommandSpec(
            module="query_doctor.cli.report",
            console_script="query-doctor-report",
        ),
    }
)
COMMAND_BACKENDS = ("module", "console")
COMMAND_BACKEND_ENV = "QD_COMMAND_BACKEND"
DEFAULT_COMMAND_BACKEND = "module"


def command_spec(role: str) -> CommandSpec:
    try:
        return COMMAND_SPECS[role]
    except KeyError as exc:
        known = ", ".join(sorted(COMMAND_SPECS))
        raise ValueError(f"Unknown Query Doctor CLI role {role!r}; known roles: {known}") from exc


def module_name(role: str) -> str:
    return command_spec(role).module


def console_script_name(role: str) -> str:
    return command_spec(role).console_script


def resolve_command_backend(
    backend: str | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> str:
    selected = backend
    if selected is None:
        source_env = environ if env is None else env
        selected = source_env.get(COMMAND_BACKEND_ENV, DEFAULT_COMMAND_BACKEND)
    selected = selected.strip().lower()
    if selected in COMMAND_BACKENDS:
        return selected
    allowed = ", ".join(COMMAND_BACKENDS)
    raise ValueError(f"Unsupported Query Doctor command backend {selected!r}; allowed: {allowed}")


def command_prefix(
    repo_dir: Path,
    role: str,
    *,
    backend: str | None = None,
    env: Mapping[str, str] | None = None,
    python_executable: str | None = None,
) -> list[str]:
    spec = command_spec(role)
    selected = resolve_command_backend(backend, env=env)
    python = sys.executable if python_executable is None else python_executable
    if selected == "module":
        return [python, "-m", spec.module]
    if selected == "console":
        return [spec.console_script]
    raise AssertionError(f"unreachable Query Doctor command backend: {selected}")
