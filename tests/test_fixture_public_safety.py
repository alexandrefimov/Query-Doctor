from __future__ import annotations

from pathlib import Path

from query_doctor.cli.demo_preflight import is_public_release_text_file, scan_public_release_text


REPO_DIR = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPO_DIR / "tests" / "fixtures"


def test_committed_fixture_text_has_no_public_release_findings():
    findings = []
    for path in sorted(FIXTURE_ROOT.rglob("*")):
        relative_path = path.relative_to(REPO_DIR).as_posix()
        if not path.is_file() or not is_public_release_text_file(relative_path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        findings.extend(scan_public_release_text(text, path=relative_path))

    assert findings == []
