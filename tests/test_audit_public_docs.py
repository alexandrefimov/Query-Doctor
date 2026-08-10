from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_public_docs.py"
SPEC = importlib.util.spec_from_file_location("audit_public_docs", SCRIPT_PATH)
assert SPEC is not None
audit_public_docs = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = audit_public_docs
SPEC.loader.exec_module(audit_public_docs)


def test_scan_text_blocks_local_agent_handoff_markers():
    text = "\n".join(
        [
            "Current task branch: docs/work-in-progress",
            "Next session plan: continue this local smoke.",
            "Temporary output: /private/tmp/query-doctor-local/batch_summary.json",
            "Case: aaaaaaaaaaaaaaaa_0000000000000001",
            "kubectl port-forward -n private service/private 25000:25000",
            "Output: /tmp/query-doctor-current-impala-smoke/batch_summary.json",
        ]
    )

    findings = audit_public_docs.scan_text_for_local_doc_notes(text, path="docs/codex-handoff.md")

    assert {finding.message for finding in findings} == {
        "current branch handoff belongs in local exclude-only notes",
        "transient next-session notes belong in local exclude-only notes",
        "private temporary output paths belong in local exclude-only notes",
        "real-looking case/query IDs belong in local exclude-only notes",
        "private connectivity commands belong in local exclude-only notes",
        "private generated output paths belong in local exclude-only notes",
    }
    assert {finding.severity for finding in findings} == {"blocker"}


def test_scan_text_ignores_non_public_markdown_paths():
    findings = audit_public_docs.scan_text_for_local_doc_notes(
        "Next session plan: private scratch note.",
        path="tests/fixtures/README.md",
    )

    assert findings == ()


def test_scan_text_checks_deployment_markdown_paths():
    findings = audit_public_docs.scan_text_for_local_doc_notes(
        "Next session plan: private deployment scratch note.",
        path="deploy/kubernetes/README.md",
    )

    assert len(findings) == 1
    assert findings[0].severity == "blocker"


def test_public_markdown_path_filter_includes_public_docs_only():
    assert audit_public_docs.is_public_markdown_path("AGENTS.md")
    assert audit_public_docs.is_public_markdown_path("docs/README.md")
    assert audit_public_docs.is_public_markdown_path("deploy/kubernetes/README.md")
    assert audit_public_docs.is_public_markdown_path(".github/PULL_REQUEST_TEMPLATE.md")
    assert not audit_public_docs.is_public_markdown_path("tests/fixtures/README.md")
    assert not audit_public_docs.is_public_markdown_path("scripts/audit_public_docs.py")


def test_render_findings_reports_ok_for_clean_docs():
    assert audit_public_docs.render_findings([]) == "Public documentation local-note audit: OK"


def test_scan_public_docs_ignores_deleted_tracked_docs(tmp_path):
    original = audit_public_docs.public_markdown_paths
    audit_public_docs.public_markdown_paths = lambda _repo_dir: ["docs/deleted.md"]
    try:
        assert audit_public_docs.scan_public_docs(tmp_path) == []
    finally:
        audit_public_docs.public_markdown_paths = original
