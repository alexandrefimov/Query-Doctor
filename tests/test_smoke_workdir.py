from __future__ import annotations

from pathlib import Path

import pytest

from scripts.smoke_workdir import SmokeWorkDirError, prepare_smoke_work_dir


def test_prepare_smoke_work_dir_rejects_non_empty_explicit_dir(tmp_path: Path) -> None:
    work_dir = tmp_path / "query-doctor-smoke"
    work_dir.mkdir()
    (work_dir / "leftover.txt").write_text("old run\n", encoding="utf-8")

    with pytest.raises(SmokeWorkDirError, match="already exists and is not empty"):
        prepare_smoke_work_dir(
            work_dir,
            keep_work_dir=False,
            replace_work_dir=False,
            temp_prefix="query-doctor-test-",
        )

    assert (work_dir / "leftover.txt").is_file()


def test_prepare_smoke_work_dir_replaces_safe_query_doctor_dir(tmp_path: Path) -> None:
    work_dir = tmp_path / "query-doctor-smoke"
    work_dir.mkdir()
    (work_dir / "leftover.txt").write_text("old run\n", encoding="utf-8")

    prepared = prepare_smoke_work_dir(
        work_dir,
        keep_work_dir=False,
        replace_work_dir=True,
        temp_prefix="query-doctor-test-",
    )

    assert prepared.path == work_dir.resolve()
    assert prepared.cleanup is False
    assert prepared.path.is_dir()
    assert not (prepared.path / "leftover.txt").exists()


def test_prepare_smoke_work_dir_refuses_unsafe_replace_name(tmp_path: Path) -> None:
    work_dir = tmp_path / "not-query-doctor-smoke"
    work_dir.mkdir()

    with pytest.raises(SmokeWorkDirError, match="final path component"):
        prepare_smoke_work_dir(
            work_dir,
            keep_work_dir=False,
            replace_work_dir=True,
            temp_prefix="query-doctor-test-",
        )


def test_prepare_smoke_work_dir_refuses_repository_parent(tmp_path: Path) -> None:
    work_dir = tmp_path / "query-doctor-parent"
    repo = work_dir / "repo"
    repo.mkdir(parents=True)

    with pytest.raises(SmokeWorkDirError, match="repository or parent path"):
        prepare_smoke_work_dir(
            work_dir,
            keep_work_dir=False,
            replace_work_dir=True,
            temp_prefix="query-doctor-test-",
            protected_roots=(repo,),
        )
