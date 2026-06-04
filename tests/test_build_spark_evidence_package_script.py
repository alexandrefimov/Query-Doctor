import json
from pathlib import Path

import pytest

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.analyzer.spark_evidence_package import (
    validate_spark_evidence_package_payload,
)
from query_doctor.analyzer.spark_evidence_package_builder import (
    SparkEvidencePackageSampleSpec,
    build_spark_evidence_package_payload,
)
from query_doctor.cli import build_spark_evidence_package


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "engine_facts"
SAMPLE_FIXTURES = (
    (
        "finished_sql_exact_linkage",
        "spark_eventlog_compact",
        "spark_history_eventlog_compact.json",
    ),
    (
        "missing_or_partial_history_server_endpoint",
        "spark_history_server_compact",
        "spark_history_server_compact_source_warning.json",
    ),
)


def test_spark_evidence_package_builder_assembles_valid_wrapper() -> None:
    payload = build_spark_evidence_package_payload(
        package_id="spark_compact_pkg",
        prepared_date_utc="2026-06-04",
        samples=_sample_specs(),
        known_omissions=("no_streaming_coverage",),
        unsupported_sources=("raw_event_logs",),
        synthetic_rejection_counts={
            "oversized_or_over_deep_rejection_synthetic": 1,
            "unsafe_raw_field_rejection_synthetic": 1,
        },
        redaction_reviewed=True,
        sentinel_tests_passed=True,
    )

    result = validate_spark_evidence_package_payload(payload, require_minimum_cases=False)

    assert set(payload) == {"manifest", "redaction_note", "samples"}
    assert result.package_id == "spark_compact_pkg"
    assert result.sample_count == len(SAMPLE_FIXTURES)
    assert result.source_summary.spark_version_families == ("spark_4_1",)
    assert result.source_summary.max_record_bytes > 0
    assert result.source_summary.max_nested_depth > 0
    assert dict(result.sample_count_by_case)["unsafe_raw_field_rejection_synthetic"] == 1


def test_spark_evidence_package_builder_requires_explicit_review_confirmation() -> None:
    with pytest.raises(EngineFactContractError, match="redaction review is required"):
        build_spark_evidence_package_payload(
            package_id="spark_compact_pkg",
            prepared_date_utc="2026-06-04",
            samples=_sample_specs(),
            sentinel_tests_passed=True,
        )


def test_build_spark_evidence_package_script_writes_valid_package_without_echoing_paths(
    tmp_path,
    capsys,
) -> None:
    output_path = tmp_path / "built-spark-package.json"

    exit_code = build_spark_evidence_package.main(_builder_args(output_path))

    captured = capsys.readouterr()
    assert exit_code == 0
    assert output_path.exists()
    assert "[spark-package-builder] written" in captured.out
    assert "package_id: spark_compact_pkg" in captured.out
    assert "source_summary:" in captured.out
    assert "sample_count: 2" in captured.out
    assert "finished_sql_exact_linkage: 1" in captured.out
    assert "missing_or_partial_history_server_endpoint: 1" in captured.out
    assert str(output_path) not in captured.out
    assert "spark_history_eventlog_compact.json" not in captured.out
    assert "spark_history_server_compact_source_warning.json" not in captured.out
    assert captured.err == ""

    result = validate_spark_evidence_package_payload(
        json.loads(output_path.read_text(encoding="utf-8")),
        require_minimum_cases=False,
    )
    assert result.source_contract_counts() == {
        "spark_history_eventlog_compact_v1": 1,
        "spark_history_server_compact_v1": 1,
    }


def test_build_spark_evidence_package_script_rejects_raw_sample_without_writing_output(
    tmp_path,
    capsys,
) -> None:
    raw_sample_path = tmp_path / "raw-spark-sample.json"
    raw_sample = _load_fixture("spark_history_eventlog_compact.json")
    raw_sample["sqlExecution"]["sqlText"] = "SELECT secret_col FROM guarded_table"
    raw_sample_path.write_text(json.dumps(raw_sample), encoding="utf-8")
    output_path = tmp_path / "built-spark-package.json"

    exit_code = build_spark_evidence_package.main(
        [
            "--out",
            str(output_path),
            "--package-id",
            "spark_compact_pkg",
            "--prepared-date-utc",
            "2026-06-04",
            "--redaction-reviewed",
            "--sentinel-tests-passed",
            "--partial-ok",
            "--sample",
            f"finished_sql_exact_linkage:spark_eventlog_compact:{raw_sample_path}",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert not output_path.exists()
    assert captured.out == ""
    assert "[spark-package-builder] rejected:" in captured.err
    for fragment in (
        str(raw_sample_path),
        str(output_path),
        "SELECT",
        "secret_col",
        "guarded_table",
    ):
        assert fragment not in captured.err


def test_build_spark_evidence_package_script_rejects_output_sample_overlap(
    capsys,
) -> None:
    sample_path = FIXTURE_DIR / "spark_history_eventlog_compact.json"

    exit_code = build_spark_evidence_package.main(
        [
            "--out",
            str(sample_path),
            "--package-id",
            "spark_compact_pkg",
            "--prepared-date-utc",
            "2026-06-04",
            "--redaction-reviewed",
            "--sentinel-tests-passed",
            "--partial-ok",
            "--sample",
            f"finished_sql_exact_linkage:spark_eventlog_compact:{sample_path}",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "output path must be distinct from sample inputs" in captured.err
    assert str(sample_path) not in captured.err


def _builder_args(output_path: Path) -> list[str]:
    args = [
        "--out",
        str(output_path),
        "--package-id",
        "spark_compact_pkg",
        "--prepared-date-utc",
        "2026-06-04",
        "--known-omission",
        "no_streaming_coverage",
        "--unsupported-source",
        "raw_event_logs",
        "--synthetic-rejection",
        "oversized_or_over_deep_rejection_synthetic:1",
        "--synthetic-rejection",
        "unsafe_raw_field_rejection_synthetic:1",
        "--redaction-reviewed",
        "--sentinel-tests-passed",
        "--partial-ok",
    ]
    for case, source_type, fixture_name in SAMPLE_FIXTURES:
        args.extend(["--sample", f"{case}:{source_type}:{FIXTURE_DIR / fixture_name}"])
    return args


def _sample_specs() -> tuple[SparkEvidencePackageSampleSpec, ...]:
    return tuple(
        SparkEvidencePackageSampleSpec(
            case=case,
            source_type=source_type,
            payload=_load_fixture(fixture_name),
        )
        for case, source_type, fixture_name in SAMPLE_FIXTURES
    )


def _load_fixture(fixture_name: str) -> dict:
    payload = json.loads((FIXTURE_DIR / fixture_name).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload
