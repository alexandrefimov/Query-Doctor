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
        "Use python3 query_doctor.py for this TODO.\n"
        "See [missing](missing.md).\n",
        encoding="utf-8",
    )

    failures = check_active_docs.find_failures([doc], tmp_path)

    assert any("removed root command invocation" in failure for failure in failures)
    assert any("stale marker" in failure for failure in failures)
    assert any("missing local link target: missing.md" in failure for failure in failures)


def test_find_failures_ignores_code_fences_and_external_links(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text(
        "```bash\n"
        "python3 query_doctor.py\n"
        "```\n"
        "See [external](https://example.invalid/doc).\n",
        encoding="utf-8",
    )

    assert check_active_docs.find_failures([doc], tmp_path) == []
