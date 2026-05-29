import json

from scripts import demo_trino_evidence_package
from query_doctor.analyzer.trino_evidence_package import (
    validate_trino_evidence_package_payload,
)


def test_demo_trino_evidence_package_prints_safe_summary_without_writing(capsys):
    exit_code = demo_trino_evidence_package.main([])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "[trino-package-demo] built synthetic fixture package" in captured.out
    assert "package_written: no" in captured.out
    assert "[trino-package] accepted" in captured.out
    assert "package_id: trino_fixture_demo" in captured.out
    assert "source_type: mixed_sanitized_export" in captured.out
    assert "trino_version_family: 477" in captured.out
    assert "source_contract_version: synthetic_trino_event_listener_v1" in captured.out
    assert "contact_surface: fixture_import_only" in captured.out
    assert "sample_count: 22" in captured.out
    assert "supported: 20" in captured.out
    assert "unknown: 2" in captured.out
    assert "failed_query_allowlisted_category: 2" in captured.out
    assert "queued_or_resource_group_delayed_query: 2" in captured.out
    assert "blocked_query: 2" in captured.out
    assert "spill_observed: 2" in captured.out
    assert "stage_or_task_skew_candidate: 2" in captured.out
    assert "connector_metric_present: 2" in captured.out
    assert "connector_metric_absent: 2" in captured.out
    assert "missing_field_case: 2" in captured.out
    assert "unknown_or_unsupported_source_contract: 2" in captured.out
    assert "query_detail_stage_task_summary: 2" in captured.out
    assert captured.err == ""

    _assert_no_demo_leaks(captured.out)


def test_demo_trino_evidence_package_writes_valid_package_without_echoing_paths(
    tmp_path,
    capsys,
):
    out_dir = tmp_path / "demo-output"

    exit_code = demo_trino_evidence_package.main(["--out-dir", str(out_dir)])

    captured = capsys.readouterr()
    output_path = out_dir / demo_trino_evidence_package.PACKAGE_FILENAME
    assert exit_code == 0
    assert output_path.exists()
    assert "package_written: yes" in captured.out
    assert str(out_dir) not in captured.out
    assert str(output_path) not in captured.out
    assert str(tmp_path) not in captured.out
    assert captured.err == ""

    result = validate_trino_evidence_package_payload(
        json.loads(output_path.read_text(encoding="utf-8"))
    )
    assert result.package_id == "trino_fixture_demo"
    assert result.parser_coverage_counts() == {"supported": 20, "unknown": 2}
    _assert_no_demo_leaks(captured.out)


def test_demo_trino_evidence_package_rejects_nonempty_output_directory_without_path_echo(
    tmp_path,
    capsys,
):
    out_dir = tmp_path / "demo-output"
    out_dir.mkdir()
    (out_dir / "existing.txt").write_text("already here", encoding="utf-8")

    exit_code = demo_trino_evidence_package.main(["--out-dir", str(out_dir)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "[trino-package-demo] rejected: output directory is not empty" in captured.err
    assert str(out_dir) not in captured.err
    assert str(tmp_path) not in captured.err


def test_demo_trino_evidence_package_overwrites_only_demo_package(
    tmp_path,
    capsys,
):
    out_dir = tmp_path / "demo-output"
    out_dir.mkdir()
    output_path = out_dir / demo_trino_evidence_package.PACKAGE_FILENAME
    output_path.write_text("old package", encoding="utf-8")

    exit_code = demo_trino_evidence_package.main(["--out-dir", str(out_dir), "--overwrite"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "package_written: yes" in captured.out
    assert str(out_dir) not in captured.out
    assert captured.err == ""
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["manifest"]["package_id"] == "trino_fixture_demo"
    _assert_no_demo_leaks(captured.out)


def _assert_no_demo_leaks(text: str) -> None:
    forbidden = (
        "tests/fixtures",
        "trino_statement_stats.json",
        "trino_completed_event.json",
        "statementStats",
        "queryCompletedEvent",
        "queryText",
        "SELECT ",
        ".json",
    )
    for needle in forbidden:
        assert needle not in text
