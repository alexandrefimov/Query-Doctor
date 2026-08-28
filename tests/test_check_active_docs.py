from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_active_docs.py"
SPEC = importlib.util.spec_from_file_location("check_active_docs", SCRIPT_PATH)
assert SPEC is not None
check_active_docs = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = check_active_docs
SPEC.loader.exec_module(check_active_docs)


def test_find_failures_reports_stale_terms_and_missing_links(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text(
        "Use python3 query_doctor.py for this TODO.\nSee [missing](missing.md).\n",
        encoding="utf-8",
    )

    failures = check_active_docs.find_failures([doc], tmp_path)

    assert any("removed root command invocation" in failure for failure in failures)
    assert any("stale marker" in failure for failure in failures)
    assert any("missing local link target: missing.md" in failure for failure in failures)


def test_find_failures_ignores_code_fences_and_external_links(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text(
        "```bash\npython3 query_doctor.py\n```\nSee [external](https://example.invalid/doc).\n",
        encoding="utf-8",
    )

    assert check_active_docs.find_failures([doc], tmp_path) == []


def test_active_docs_require_review_header_and_status_index(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    index = docs_dir / "README.md"
    active = tmp_path / "active.md"
    active.write_text("# Active\n\nNo review header.\n", encoding="utf-8")
    index.write_text(
        "# Docs\n\n"
        "Last reviewed: 2099-01-01\n\n"
        "| Document | Status | Use |\n"
        "| --- | --- | --- |\n"
        "| [../active.md](../active.md) | active | test |\n",
        encoding="utf-8",
    )

    original_active_docs = check_active_docs.ACTIVE_DOCS
    check_active_docs.ACTIVE_DOCS = ("active.md", "docs/README.md")
    try:
        failures = check_active_docs.find_failures([active, index], tmp_path)
    finally:
        check_active_docs.ACTIVE_DOCS = original_active_docs

    assert any(
        "active doc missing Last reviewed/Last updated header" in failure for failure in failures
    )


def test_i18n_copy_requires_existing_english_source(tmp_path):
    localized_dir = tmp_path / "docs" / "i18n" / "ru"
    localized_dir.mkdir(parents=True)
    localized = localized_dir / "missing.md"
    localized.write_text("# Missing\n", encoding="utf-8")

    failures = check_active_docs.find_i18n_failures(tmp_path)

    assert failures == ["docs/i18n/ru/missing.md: English source is missing: docs/missing.md"]


def test_current_docs_require_status_index_entry(tmp_path):
    docs_dir = tmp_path / "docs"
    notes_dir = docs_dir / "ui"
    notes_dir.mkdir(parents=True)
    index = docs_dir / "README.md"
    index.write_text(
        "# Docs\n\n"
        "Last reviewed: 2099-01-01\n\n"
        "| Document | Status | Use |\n"
        "| --- | --- | --- |\n"
        "| [README.md](README.md) | active | index |\n",
        encoding="utf-8",
    )
    (notes_dir / "notes.md").write_text("# Notes\n", encoding="utf-8")

    original_active_docs = check_active_docs.ACTIVE_DOCS
    check_active_docs.ACTIVE_DOCS = ("docs/README.md",)
    try:
        failures = check_active_docs.find_failures([index], tmp_path)
    finally:
        check_active_docs.ACTIVE_DOCS = original_active_docs

    assert failures == ["docs/README.md: current docs missing from status index: docs/ui/notes.md"]


def stale_active_doc_tree(tmp_path):
    """An active doc long past the review window that also carries a broken link."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    index = docs_dir / "README.md"
    active = tmp_path / "active.md"
    active.write_text(
        "# Active\n\nLast reviewed: 2000-01-01\n\nSee [gone](missing-target.md).\n",
        encoding="utf-8",
    )
    index.write_text(
        "# Docs\n\n"
        "Last reviewed: 2099-01-01\n\n"
        "| Document | Status | Use |\n"
        "| --- | --- | --- |\n"
        "| [../active.md](../active.md) | active | test |\n",
        encoding="utf-8",
    )
    return active, index


def find_with_active_docs(paths, tmp_path, **kwargs):
    original = check_active_docs.ACTIVE_DOCS
    check_active_docs.ACTIVE_DOCS = ("active.md", "docs/README.md")
    try:
        return check_active_docs.find_failures(paths, tmp_path, **kwargs)
    finally:
        check_active_docs.ACTIVE_DOCS = original


def test_stale_review_header_fails_in_the_default_mode(tmp_path):
    active, index = stale_active_doc_tree(tmp_path)

    failures = find_with_active_docs([active, index], tmp_path)

    assert any("active doc review is older than" in failure for failure in failures)


def test_warn_mode_reports_the_stale_review_without_failing(tmp_path):
    active, index = stale_active_doc_tree(tmp_path)
    age_warnings: list[str] = []

    failures = find_with_active_docs(
        [active, index], tmp_path, age_mode="warn", age_warnings=age_warnings
    )

    assert not any("active doc review is older than" in failure for failure in failures)
    assert any("active doc review is older than" in warning for warning in age_warnings)
    # Warn mode loosens the calendar check and nothing else.
    assert any("missing local link target: missing-target.md" in failure for failure in failures)
