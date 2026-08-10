"""Case-contained loader for already-provided Impala EXPLAIN artifacts."""

from __future__ import annotations

import errno
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from query_doctor.analyzer.impala_explain import (
    DEFAULT_EXPLAIN_LIMITS,
    ExplainParseLimits,
    parse_impala_explain,
    unknown_impala_explain_facts,
)


SOURCE_CANDIDATES = (
    ("impala_context", ("impala_context", "explain.txt")),
    ("case_root", ("explain.txt",)),
)

DIRECTORY_OPEN_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
FILE_OPEN_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)


@dataclass
class _OpenedCandidate:
    slot: str
    status: str
    descriptor: int | None = None
    size: int | None = None

    def close(self) -> None:
        if self.descriptor is not None:
            os.close(self.descriptor)
            self.descriptor = None


def load_impala_explain_facts(
    case_dir: Path,
    *,
    profile_operators: Iterable[Mapping[str, Any]] = (),
    limits: ExplainParseLimits = DEFAULT_EXPLAIN_LIMITS,
) -> dict[str, Any]:
    """Load one accepted case artifact without executing or generating EXPLAIN."""

    case_descriptor = _open_case_directory(case_dir)
    if case_descriptor is None:
        return unknown_impala_explain_facts(
            artifact_status="invalid",
            source_slot="none",
            limitation_codes=("artifact_invalid",),
        )

    candidates: list[_OpenedCandidate] = []
    try:
        candidates = [
            _open_candidate(case_descriptor, slot, components)
            for slot, components in SOURCE_CANDIDATES
        ]
        present = [candidate for candidate in candidates if candidate.status != "absent"]
        if not present:
            return unknown_impala_explain_facts(
                artifact_status="missing",
                source_slot="none",
                limitation_codes=("artifact_missing",),
            )
        if len(present) != 1:
            return unknown_impala_explain_facts(
                artifact_status="ambiguous",
                source_slot="ambiguous",
                candidate_count=len(present),
                limitation_codes=("artifact_ambiguous",),
            )

        candidate = present[0]
        if candidate.status != "available" or candidate.descriptor is None:
            artifact_status = "unreadable" if candidate.status == "unreadable" else "invalid"
            limitation = (
                "artifact_unreadable" if artifact_status == "unreadable" else "artifact_invalid"
            )
            return unknown_impala_explain_facts(
                artifact_status=artifact_status,
                source_slot=candidate.slot,
                candidate_count=1,
                limitation_codes=(limitation,),
            )
        if candidate.size is not None and candidate.size > limits.max_bytes:
            return unknown_impala_explain_facts(
                artifact_status="too_large",
                source_slot=candidate.slot,
                candidate_count=1,
                input_bytes=candidate.size,
                limitation_codes=("artifact_too_large",),
            )

        raw = _read_bounded(candidate.descriptor, limits.max_bytes)
        if raw is None:
            return unknown_impala_explain_facts(
                artifact_status="unreadable",
                source_slot=candidate.slot,
                candidate_count=1,
                limitation_codes=("artifact_unreadable",),
            )
        if len(raw) > limits.max_bytes:
            return unknown_impala_explain_facts(
                artifact_status="too_large",
                source_slot=candidate.slot,
                candidate_count=1,
                input_bytes=len(raw),
                limitation_codes=("artifact_too_large",),
            )
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return unknown_impala_explain_facts(
                artifact_status="invalid",
                source_slot=candidate.slot,
                candidate_count=1,
                input_bytes=len(raw),
                limitation_codes=("invalid_text",),
            )

        facts = parse_impala_explain(text, profile_operators=profile_operators, limits=limits)
        facts["source_slot"] = candidate.slot
        facts["candidate_count"] = 1
        facts["input_bytes"] = len(raw)
        return facts
    finally:
        for candidate in candidates:
            candidate.close()
        os.close(case_descriptor)


def _open_case_directory(case_dir: Path) -> int | None:
    if os.open not in os.supports_dir_fd or not getattr(os, "O_NOFOLLOW", 0):
        return None
    try:
        descriptor = os.open(case_dir, DIRECTORY_OPEN_FLAGS)
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            os.close(descriptor)
            return None
        return descriptor
    except (OSError, RuntimeError):
        return None


def _open_candidate(
    case_descriptor: int,
    slot: str,
    components: tuple[str, ...],
) -> _OpenedCandidate:
    parent_descriptor = os.dup(case_descriptor)
    try:
        for component in components[:-1]:
            try:
                next_descriptor = os.open(
                    component,
                    DIRECTORY_OPEN_FLAGS,
                    dir_fd=parent_descriptor,
                )
            except OSError as exc:
                return _candidate_open_error(slot, exc)
            os.close(parent_descriptor)
            parent_descriptor = next_descriptor

        try:
            descriptor = os.open(
                components[-1],
                FILE_OPEN_FLAGS,
                dir_fd=parent_descriptor,
            )
        except OSError as exc:
            return _candidate_open_error(slot, exc)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                os.close(descriptor)
                return _OpenedCandidate(slot=slot, status="invalid")
            return _OpenedCandidate(
                slot=slot,
                status="available",
                descriptor=descriptor,
                size=metadata.st_size,
            )
        except OSError:
            os.close(descriptor)
            return _OpenedCandidate(slot=slot, status="unreadable")
    finally:
        os.close(parent_descriptor)


def _candidate_open_error(slot: str, exc: OSError) -> _OpenedCandidate:
    if exc.errno == errno.ENOENT:
        return _OpenedCandidate(slot=slot, status="absent")
    if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
        return _OpenedCandidate(slot=slot, status="invalid")
    return _OpenedCandidate(slot=slot, status="unreadable")


def _read_bounded(descriptor: int, max_bytes: int) -> bytes | None:
    chunks: list[bytes] = []
    remaining = max_bytes + 1
    try:
        while remaining > 0:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
    except OSError:
        return None
    return b"".join(chunks)
