"""Shared workspace lifecycle helpers for local smoke scripts."""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SAFE_REPLACE_PREFIX = "query-doctor-"


@dataclass(frozen=True)
class SmokeWorkDir:
    path: Path
    cleanup: bool


class SmokeWorkDirError(RuntimeError):
    """Safe workspace lifecycle error for smoke scripts."""


def prepare_smoke_work_dir(
    work_dir_arg: Path | None,
    *,
    keep_work_dir: bool,
    replace_work_dir: bool,
    temp_prefix: str,
    protected_roots: Iterable[Path] = (),
) -> SmokeWorkDir:
    if work_dir_arg is None:
        if replace_work_dir:
            raise SmokeWorkDirError("--replace-work-dir requires --work-dir")
        return SmokeWorkDir(
            path=Path(tempfile.mkdtemp(prefix=temp_prefix)),
            cleanup=not keep_work_dir,
        )

    work_dir = work_dir_arg.expanduser().resolve()
    if replace_work_dir:
        _validate_replace_target(work_dir, protected_roots=protected_roots)
        if work_dir.exists():
            shutil.rmtree(work_dir)
        work_dir.mkdir(parents=True, exist_ok=False)
    else:
        if work_dir.exists() and any(work_dir.iterdir()):
            raise SmokeWorkDirError(
                f"--work-dir already exists and is not empty: {work_dir}. "
                "Use --replace-work-dir to clear it, choose a fresh --work-dir, "
                "or omit --work-dir."
            )
        work_dir.mkdir(parents=True, exist_ok=True)
    return SmokeWorkDir(path=work_dir, cleanup=False)


def _validate_replace_target(work_dir: Path, *, protected_roots: Iterable[Path]) -> None:
    if work_dir == Path(work_dir.anchor):
        raise SmokeWorkDirError("Refusing to replace a filesystem root.")
    if work_dir == Path.home().resolve():
        raise SmokeWorkDirError("Refusing to replace the home directory.")
    if not work_dir.name.startswith(SAFE_REPLACE_PREFIX):
        raise SmokeWorkDirError(
            f"Refusing to replace --work-dir unless its final path component starts "
            f"with {SAFE_REPLACE_PREFIX!r}: {work_dir}"
        )
    for root in protected_roots:
        root_resolved = root.expanduser().resolve()
        if work_dir == root_resolved or _is_parent_of(work_dir, root_resolved):
            raise SmokeWorkDirError(f"Refusing to replace repository or parent path: {work_dir}")


def _is_parent_of(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True
