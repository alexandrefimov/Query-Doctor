from __future__ import annotations

import json
from pathlib import Path

from scripts import audit_owner_raw_staging_preflight as audit


def write_config(tmp_path: Path, name: str, values: dict[str, object]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(values, indent=2, sort_keys=True), encoding="utf-8")
    return path


def assert_private_fragments_hidden(text: str, tmp_path: Path) -> None:
    for forbidden in (
        str(tmp_path),
        "secret",
        "X-Secret-Viewer",
        "secret_analyst",
        "https://private.example.invalid",
        "QID-PRIVATE",
        "/private/",
    ):
        assert forbidden not in text


def test_owner_raw_staging_preflight_accepts_disabled_source_with_viewer_header(
    tmp_path: Path,
    capsys,
) -> None:
    config = write_config(
        tmp_path,
        "secret-staging-config.json",
        {
            "host": "0.0.0.0",
            "source_visibility": "owner_raw",
            "viewer_identity_header": "X-Secret-Viewer",
            "owner_raw_source_enabled": False,
            "privacy_mode": True,
            "redact": True,
            "redact_identifiers": True,
            "redact_hosts": True,
            "metadata_redact": True,
            "cm_url": "https://private.example.invalid",
            "source_owner_user": "secret_analyst",
        },
    )

    rc = audit.main(["--config", str(config), "--allow-nonlocal-web-bind"])

    captured = capsys.readouterr()
    rendered = captured.out + captured.err
    assert rc == 0
    assert "Owner raw staging preflight: ok" in captured.out
    assert "owner_raw_sources=1" in captured.out
    assert "nonlocal_owner_raw_sources=1" in captured.out
    assert "viewer_identity_header=configured" in captured.out
    assert "owner_raw_source=disabled" in captured.out
    assert "Issues: none" in captured.out
    assert_private_fragments_hidden(rendered, tmp_path)


def test_owner_raw_staging_preflight_accepts_cli_kill_switch(tmp_path: Path, capsys) -> None:
    config = write_config(
        tmp_path,
        "secret-cli-kill-switch-config.json",
        {
            "host": "0.0.0.0",
            "source_visibility": "owner_raw",
            "viewer_identity_header": "X-Secret-Viewer",
            "owner_raw_source_enabled": True,
        },
    )

    rc = audit.main(
        [
            "--config",
            str(config),
            "--allow-nonlocal-web-bind",
            "--disable-owner-raw-source",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 0
    assert "owner_raw_source=disabled" in captured.out
    assert "Issues: none" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_staging_preflight_rejects_missing_viewer_header(
    tmp_path: Path,
    capsys,
) -> None:
    config = write_config(
        tmp_path,
        "secret-missing-header-config.json",
        {
            "host": "0.0.0.0",
            "source_visibility": "owner_raw",
            "owner_raw_source_enabled": False,
        },
    )

    rc = audit.main(["--config", str(config), "--allow-nonlocal-web-bind"])

    captured = capsys.readouterr()
    assert rc == 1
    assert "Owner raw staging preflight: failed" in captured.out
    assert "viewer_identity_header_missing" in captured.out
    assert "viewer_identity_header=missing_or_invalid" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_staging_preflight_rejects_enabled_source_before_live_review(
    tmp_path: Path,
    capsys,
) -> None:
    config = write_config(
        tmp_path,
        "secret-enabled-source-config.json",
        {
            "host": "0.0.0.0",
            "source_visibility": "owner_raw",
            "viewer_identity_header": "X-Secret-Viewer",
            "owner_raw_source_enabled": True,
        },
    )

    rc = audit.main(["--config", str(config), "--allow-nonlocal-web-bind"])

    captured = capsys.readouterr()
    assert rc == 1
    assert "owner_raw_source_kill_switch_not_disabled" in captured.out
    assert "owner_raw_source=enabled" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_staging_preflight_requires_nonlocal_bind_review(
    tmp_path: Path,
    capsys,
) -> None:
    config = write_config(
        tmp_path,
        "secret-nonlocal-config.json",
        {
            "host": "0.0.0.0",
            "source_visibility": "owner_raw",
            "viewer_identity_header": "X-Secret-Viewer",
            "owner_raw_source_enabled": False,
        },
    )

    rc = audit.main(["--config", str(config)])

    captured = capsys.readouterr()
    assert rc == 1
    assert "nonlocal_web_bind_not_explicitly_reviewed" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_staging_preflight_rejects_safe_visibility_for_this_gate(
    tmp_path: Path,
    capsys,
) -> None:
    config = write_config(
        tmp_path,
        "secret-safe-config.json",
        {
            "host": "0.0.0.0",
            "source_visibility": "safe",
            "viewer_identity_header": "X-Secret-Viewer",
            "owner_raw_source_enabled": False,
        },
    )

    rc = audit.main(["--config", str(config), "--allow-nonlocal-web-bind"])

    captured = capsys.readouterr()
    assert rc == 1
    assert "owner_raw_source_visibility_missing" in captured.out
    assert "owner_raw_sources=0" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_staging_preflight_rejects_explicit_redaction_disable(
    tmp_path: Path,
    capsys,
) -> None:
    config = write_config(
        tmp_path,
        "secret-redaction-config.json",
        {
            "host": "0.0.0.0",
            "source_visibility": "owner_raw",
            "viewer_identity_header": "X-Secret-Viewer",
            "owner_raw_source_enabled": False,
            "redact_hosts": False,
        },
    )

    rc = audit.main(["--config", str(config), "--allow-nonlocal-web-bind"])

    captured = capsys.readouterr()
    assert rc == 1
    assert "redaction_explicitly_disabled" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_staging_preflight_accepts_cluster_owner_raw_config(
    tmp_path: Path,
    capsys,
) -> None:
    config = write_config(
        tmp_path,
        "secret-cluster-config.json",
        {
            "host": "0.0.0.0",
            "viewer_identity_header": "X-Secret-Viewer",
            "owner_raw_source_enabled": False,
            "clusters": [
                {"id": "one", "label": "One", "source_visibility": "safe"},
                {"id": "two", "label": "Two", "source_visibility": "owner_raw"},
            ],
        },
    )

    rc = audit.main(["--config", str(config), "--allow-nonlocal-web-bind"])

    captured = capsys.readouterr()
    assert rc == 0
    assert "source_count=2" in captured.out
    assert "owner_raw_sources=1" in captured.out
    assert "Issues: none" in captured.out
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_staging_preflight_writes_raw_free_summary(tmp_path: Path, capsys) -> None:
    config = write_config(
        tmp_path,
        "secret-summary-config.json",
        {
            "host": "0.0.0.0",
            "source_visibility": "owner_raw",
            "viewer_identity_header": "X-Secret-Viewer",
            "owner_raw_source_enabled": False,
            "cm_url": "https://private.example.invalid",
        },
    )
    summary = tmp_path / "secret-summary.json"

    rc = audit.main(
        [
            "--config",
            str(config),
            "--allow-nonlocal-web-bind",
            "--summary-json",
            str(summary),
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(summary.read_text(encoding="utf-8"))
    rendered = captured.out + captured.err + json.dumps(payload, sort_keys=True)
    assert rc == 0
    assert payload["summary_kind"] == "owner_raw_staging_preflight_v1"
    assert payload["status"] == "ok"
    assert payload["owner_raw_boundary"]["owner_raw_source_count"] == 1
    assert payload["owner_raw_boundary"]["viewer_identity_header"] == "configured"
    assert payload["owner_raw_boundary"]["owner_raw_source"] == "disabled"
    assert payload["owner_raw_boundary"]["live_review_required_before_source_enable"] is True
    assert payload["config_boundary"]["paths_printed"] is False
    assert payload["config_boundary"]["header_names_printed"] is False
    assert payload["issues"] == {"counts": {}, "items": []}
    assert_private_fragments_hidden(rendered, tmp_path)


def test_owner_raw_staging_preflight_rejects_output_overlap(tmp_path: Path, capsys) -> None:
    config = write_config(
        tmp_path,
        "secret-overlap-config.json",
        {
            "source_visibility": "owner_raw",
            "viewer_identity_header": "X-Secret-Viewer",
            "owner_raw_source_enabled": False,
        },
    )

    rc = audit.main(["--config", str(config), "--summary-json", str(config)])

    captured = capsys.readouterr()
    assert rc == 2
    assert "summary output must not overwrite input artifacts" in captured.err
    assert_private_fragments_hidden(captured.out + captured.err, tmp_path)


def test_owner_raw_staging_preflight_docs_mention_script() -> None:
    docs = (audit.ROOT / "docs" / "owner-raw-d3-deployment.md").read_text(encoding="utf-8")
    changelog = (audit.ROOT / "docs" / "changelog.md").read_text(encoding="utf-8")

    assert "scripts/audit_owner_raw_staging_preflight.py" in docs
    assert "owner_raw_staging_preflight_v1" in changelog
