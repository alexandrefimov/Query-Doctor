from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.analyzer.spark_evidence_package import (
    validate_spark_evidence_package_payload,
)
from query_doctor.analyzer.spark_evidence_package_builder import (
    SparkEvidencePackageSampleSpec,
    build_spark_evidence_package_payload,
)
from query_doctor.analyzer.trino_evidence_package import (
    validate_trino_evidence_package_payload,
)
from query_doctor.analyzer.trino_evidence_package_builder import (
    TrinoEvidencePackageSampleSpec,
    build_trino_evidence_package_payload,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "engine_facts"


@pytest.mark.parametrize(
    ("mutate", "expected_fragment"),
    (
        (lambda note: note.pop("redaction_note_version"), "missing redaction_note_version"),
        (lambda note: note.pop("prepared_by_role"), "missing prepared_by_role"),
        (lambda note: note.pop("manual_reviewer_role"), "missing manual_reviewer_role"),
        (
            lambda note: note.__setitem__(
                "synthetic_sentinel_tests",
                sorted(note["synthetic_sentinel_tests"]),
            ),
            "missing synthetic_sentinel_tests",
        ),
        (
            lambda note: note["boundary_assertions"].__setitem__(
                next(iter(note["boundary_assertions"])),
                False,
            ),
            "boundary assertion failed",
        ),
        (
            lambda note: note.__setitem__("raw_companion_archive", "retained"),
            "raw companion archive is not allowed",
        ),
    ),
)
def test_redaction_note_v1_rejections_match_across_evidence_package_engines(
    mutate: Callable[[dict[str, Any]], object],
    expected_fragment: str,
) -> None:
    for package, validate in (
        (_trino_package(), validate_trino_evidence_package_payload),
        (_spark_package(), validate_spark_evidence_package_payload),
    ):
        mutated = copy.deepcopy(package)
        mutate(mutated["redaction_note"])

        with pytest.raises(EngineFactContractError) as exc_info:
            validate(mutated, require_minimum_cases=False)

        assert expected_fragment in str(exc_info.value)


def _trino_package() -> dict[str, Any]:
    return build_trino_evidence_package_payload(
        package_id="trino_redaction_note_pack",
        prepared_date_utc="2026-06-04",
        export_window_start_utc="2026-06-04T09:00:00Z",
        export_window_end_utc="2026-06-04T10:00:00Z",
        samples=(
            TrinoEvidencePackageSampleSpec(
                case="successful_completed_query",
                source_type="statement_stats_export",
                payload=_load_fixture("trino_statement_stats.json"),
            ),
        ),
        synthetic_rejection_counts={
            "oversized_or_over_deep_rejection_synthetic": 1,
            "unsafe_raw_field_rejection_synthetic": 1,
        },
        redaction_reviewed=True,
        sentinel_tests_passed=True,
    )


def _spark_package() -> dict[str, Any]:
    return build_spark_evidence_package_payload(
        package_id="spark_redaction_note_pack",
        prepared_date_utc="2026-06-04",
        samples=(
            SparkEvidencePackageSampleSpec(
                case="finished_sql_exact_linkage",
                source_type="spark_eventlog_compact",
                payload=_load_fixture("spark_history_eventlog_compact.json"),
            ),
        ),
        synthetic_rejection_counts={
            "oversized_or_over_deep_rejection_synthetic": 1,
            "unsafe_raw_field_rejection_synthetic": 1,
        },
        redaction_reviewed=True,
        sentinel_tests_passed=True,
    )


def _load_fixture(fixture_name: str) -> dict[str, Any]:
    payload = json.loads((FIXTURE_DIR / fixture_name).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload
