from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "audit_public_distribution_boundary.py"
)
SPEC = importlib.util.spec_from_file_location("audit_public_distribution_boundary", SCRIPT_PATH)
assert SPEC is not None
audit = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = audit
SPEC.loader.exec_module(audit)

SENTINEL = "private-platform-sentinel"
SENTINEL_FINGERPRINTS = frozenset({audit.marker_fingerprint(SENTINEL)})
CONTRACT_ROOT = "release"
CONTRACT_DIRECTORY = "contracts"
CONTRACT_FINGERPRINTS = frozenset(
    {audit.marker_fingerprint(f"{CONTRACT_ROOT}/{CONTRACT_DIRECTORY}")}
)
HISTORY_REVISION = "a1b2c3d4e5f6"
HISTORY_PATH = "docs/example.md"


def history_runners(*, blob: bytes = b"", metadata: bytes = b"safe commit"):
    def runner(_repo_dir, args):
        if args == ["rev-list", "--reverse", "public/main..release/head"]:
            return subprocess.CompletedProcess(args, 0, f"{HISTORY_REVISION}\n", "")
        raise AssertionError(args)

    def bytes_runner(_repo_dir, args):
        if args == ["show", "--no-patch", "--format=fuller", HISTORY_REVISION]:
            return subprocess.CompletedProcess(args, 0, metadata, b"")
        if args[:2] == ["diff-tree", "--root"]:
            return subprocess.CompletedProcess(args, 0, f"{HISTORY_PATH}\0".encode(), b"")
        if args == ["ls-tree", "-r", "-z", HISTORY_REVISION]:
            tree_entry = f"100644 blob deadbeef\t{HISTORY_PATH}\0".encode()
            return subprocess.CompletedProcess(args, 0, tree_entry, b"")
        if args == ["cat-file", "blob", f"{HISTORY_REVISION}:{HISTORY_PATH}"]:
            return subprocess.CompletedProcess(args, 0, blob, b"")
        raise AssertionError(args)

    return runner, bytes_runner


def test_private_runtime_paths_are_blocked():
    private_contract_path = f"{CONTRACT_ROOT}/{CONTRACT_DIRECTORY}/private-bundle.schema.json"

    assert audit.scan_path(".gitlab-ci.yml")
    assert audit.scan_path(
        private_contract_path,
        marker_fingerprints=CONTRACT_FINGERPRINTS,
    )
    assert audit.scan_path(
        "query_doctor/private-platform-sentinel/runtime.py",
        marker_fingerprints=SENTINEL_FINGERPRINTS,
    )
    assert audit.scan_path("query_doctor/recent/history_store.py") == ()


def test_private_markers_are_blocked_across_distribution_text():
    paths = (
        "docs/architecture.md",
        "deploy/helm/query-doctor/values.yaml",
        "deploy/helm/query-doctor/templates/_helpers.tpl",
        "query_doctor/platform_adapter.py",
        "scripts/helm-chart-smoke.sh",
        "query_doctor/web/static/app.js",
        "tests/fixtures/example.sql",
        ".gitleaksignore",
    )

    assert all(
        audit.scan_text(
            SENTINEL,
            path=path,
            marker_fingerprints=SENTINEL_FINGERPRINTS,
        )
        for path in paths
    )


def test_marker_matching_normalizes_separators_and_case():
    findings = audit.scan_text(
        "Private_Platform-SENTINEL",
        path="pyproject.toml",
        marker_fingerprints=SENTINEL_FINGERPRINTS,
    )

    assert len(findings) == 1
    assert SENTINEL not in findings[0].detail


def test_marker_matching_supports_more_than_four_separator_groups():
    marker = "neutral-long-sentinel-with-many-groups"
    fingerprints = frozenset({audit.marker_fingerprint(marker)})

    findings = audit.scan_text(
        "Neutral_long sentinel-with-many groups",
        path="docs/example.txt",
        marker_fingerprints=fingerprints,
    )

    assert len(findings) == 1


def test_marker_matching_detects_separator_spanning_marker_with_adjacent_text():
    marker = "neutral-long-sentinel-with-many-groups"
    fingerprints = frozenset({audit.marker_fingerprint(marker)})

    findings = audit.scan_text(
        "prefixneutral-long-sentinel-with-many-groupssuffix",
        path="docs/example.txt",
        marker_fingerprints=fingerprints,
    )

    assert len(findings) == 1


def test_marker_matching_detects_marker_split_across_lines():
    split_at = SENTINEL.index("sentinel")

    findings = audit.scan_text(
        f"{SENTINEL[:split_at]}\n{SENTINEL[split_at:]}",
        path="docs/example.txt",
        marker_fingerprints=SENTINEL_FINGERPRINTS,
    )

    assert len(findings) == 1


def test_marker_matching_blocks_private_fingerprint_artifact():
    _length, digest = next(iter(SENTINEL_FINGERPRINTS))

    findings = audit.scan_text(
        f"embedded fingerprint: {digest}",
        path="scripts/example.py",
        marker_fingerprints=SENTINEL_FINGERPRINTS,
    )

    assert len(findings) == 1


def test_private_contract_reference_is_blocked_in_packaging_text():
    contract_reference = f"{CONTRACT_ROOT}/{CONTRACT_DIRECTORY}/example.json"

    findings = audit.scan_text(
        f"package reference: {contract_reference}",
        path="pyproject.toml",
        marker_fingerprints=CONTRACT_FINGERPRINTS,
    )

    assert len(findings) == 1


def test_test_fixtures_are_scanned_as_public_distribution_text():
    assert audit.scan_text(
        SENTINEL,
        path="tests/test_internal_example.py",
        marker_fingerprints=SENTINEL_FINGERPRINTS,
    )
    assert audit.render_findings([]) == "Public distribution boundary audit: OK"


def test_private_marker_fingerprints_load_only_from_external_configuration(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    fingerprint_file = tmp_path / "private-marker-fingerprints.json"
    length, digest = audit.marker_fingerprint(SENTINEL)
    fingerprint_file.write_text(
        json.dumps(
            {
                "schema": audit.MARKER_FINGERPRINT_SCHEMA,
                "casefold": [{"length": length, "sha256": digest}],
                "caseSensitive": [],
            }
        ),
        encoding="utf-8",
    )

    casefold, case_sensitive = audit.load_marker_fingerprint_file(
        fingerprint_file,
        repo_dir=repo_dir,
    )

    assert casefold == SENTINEL_FINGERPRINTS
    assert case_sensitive == frozenset()
    assert audit.scan_text(SENTINEL, path="docs/example.md") == ()
    assert audit.scan_text(
        SENTINEL,
        path="docs/example.md",
        marker_fingerprints=casefold,
    )


def test_private_marker_fingerprint_file_must_stay_outside_repository(tmp_path):
    fingerprint_file = tmp_path / "private-marker-fingerprints.json"
    fingerprint_file.write_text("{}", encoding="utf-8")

    try:
        audit.load_marker_fingerprint_file(fingerprint_file, repo_dir=tmp_path)
    except ValueError as exc:
        assert str(exc) == "private marker fingerprint file must stay outside the repository"
    else:
        raise AssertionError("repository-local private marker configuration was accepted")


def test_history_range_blocks_marker_in_intermediate_commit():
    runner, bytes_runner = history_runners(blob=SENTINEL.encode())

    findings = audit.scan_history_range(
        Path("."),
        base_ref="public/main",
        head_ref="release/head",
        marker_fingerprints=SENTINEL_FINGERPRINTS,
        case_sensitive_marker_fingerprints=frozenset(),
        runner=runner,
        bytes_runner=bytes_runner,
    )

    assert findings == [
        audit.BoundaryFinding(
            "(git history a1b2c3d4e5f6)",
            "private platform marker",
        )
    ]


def test_history_range_blocks_marker_in_commit_metadata():
    runner, bytes_runner = history_runners(metadata=SENTINEL.encode())

    findings = audit.scan_history_range(
        Path("."),
        base_ref="public/main",
        head_ref="release/head",
        marker_fingerprints=SENTINEL_FINGERPRINTS,
        case_sensitive_marker_fingerprints=frozenset(),
        runner=runner,
        bytes_runner=bytes_runner,
    )

    assert len(findings) == 1


def test_history_range_blocks_marker_split_across_lines_in_blob():
    split_at = SENTINEL.index("sentinel")
    runner, bytes_runner = history_runners(
        blob=f"{SENTINEL[:split_at]}\n{SENTINEL[split_at:]}".encode()
    )

    findings = audit.scan_history_range(
        Path("."),
        base_ref="public/main",
        head_ref="release/head",
        marker_fingerprints=SENTINEL_FINGERPRINTS,
        case_sensitive_marker_fingerprints=frozenset(),
        runner=runner,
        bytes_runner=bytes_runner,
    )

    assert len(findings) == 1


def test_history_range_blocks_invalid_utf8_distribution_blob():
    runner, bytes_runner = history_runners(blob=b"\xff")

    findings = audit.scan_history_range(
        Path("."),
        base_ref="public/main",
        head_ref="release/head",
        marker_fingerprints=SENTINEL_FINGERPRINTS,
        case_sensitive_marker_fingerprints=frozenset(),
        runner=runner,
        bytes_runner=bytes_runner,
    )

    assert findings == [
        audit.BoundaryFinding(
            f"(git history {HISTORY_REVISION})",
            "distribution blob is not valid UTF-8",
        )
    ]


def test_repository_scan_blocks_invalid_utf8_distribution_text(tmp_path):
    invalid_doc = tmp_path / "docs" / "invalid.md"
    invalid_doc.parent.mkdir()
    invalid_doc.write_bytes(b"\xff")

    findings = audit.scan_repository(tmp_path)

    assert findings == [
        audit.BoundaryFinding(
            "docs/invalid.md",
            "distribution text is not valid UTF-8",
        )
    ]


def test_history_range_fails_closed_when_range_cannot_be_read():
    def runner(_repo_dir, args):
        return subprocess.CompletedProcess(args, 128, "", "unknown revision")

    findings = audit.scan_history_range(
        Path("."),
        base_ref="missing/base",
        head_ref="HEAD",
        runner=runner,
    )

    assert findings == [
        audit.BoundaryFinding(
            "(git history)",
            "could not scan public revision range 'missing/base..HEAD'",
        )
    ]
