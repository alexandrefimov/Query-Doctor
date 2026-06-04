from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from query_doctor.cli import (
    trino_coordinator_query_info_pruned_import,
    trino_http_query_detail_archive_import,
    trino_query_detail_import,
    trino_query_info_pruned_import,
    trino_query_list_import,
    trino_statement_stats_import,
)


@dataclass(frozen=True)
class DiagnosisOutputOverlapCase:
    case_id: str
    main: Callable[[list[str]], int]
    argv: tuple[str, ...]
    expected_error: str
    protected_names: tuple[str, ...]


def test_trino_single_boundary_imports_reject_diagnosis_output_path_overlap(
    tmp_path: Path,
    capsys,
) -> None:
    cases = _diagnosis_output_overlap_cases(tmp_path)

    for case in cases:
        exit_code = case.main(list(case.argv))
        captured = capsys.readouterr()
        output = captured.out + captured.err

        assert exit_code == 2, case.case_id
        assert captured.out == "", case.case_id
        assert case.expected_error in captured.err, case.case_id
        for protected_name in case.protected_names:
            assert protected_name not in output, case.case_id


def _diagnosis_output_overlap_cases(tmp_path: Path) -> tuple[DiagnosisOutputOverlapCase, ...]:
    query_detail = tmp_path / "operator-query-detail.json"
    query_list = tmp_path / "operator-query-list.json"
    statement_stats = tmp_path / "operator-statement-stats.json"
    query_info = tmp_path / "operator-query-info-pruned.json"
    local_contract = tmp_path / "operator-query-info-contract.json"
    http_contract = tmp_path / "operator-http-query-detail-contract.json"
    coordinator_contract = tmp_path / "operator-coordinator-query-info-contract.json"
    auth_header = tmp_path / "operator-auth-header.txt"
    separate_input = tmp_path / "operator-separate-input.json"

    return (
        DiagnosisOutputOverlapCase(
            case_id="local_query_detail_input",
            main=trino_query_detail_import.main,
            argv=(
                "--redaction-reviewed",
                "--diagnosis-out",
                str(query_detail),
                str(query_detail),
            ),
            expected_error="compact diagnosis output must differ from input",
            protected_names=(query_detail.name,),
        ),
        DiagnosisOutputOverlapCase(
            case_id="local_query_list_input",
            main=trino_query_list_import.main,
            argv=(
                "--redaction-reviewed",
                "--diagnosis-out",
                str(query_list),
                str(query_list),
            ),
            expected_error="compact diagnosis output must differ from input",
            protected_names=(query_list.name,),
        ),
        DiagnosisOutputOverlapCase(
            case_id="local_statement_stats_input",
            main=trino_statement_stats_import.main,
            argv=(
                "--redaction-reviewed",
                "--diagnosis-out",
                str(statement_stats),
                str(statement_stats),
            ),
            expected_error="compact diagnosis output must differ from input",
            protected_names=(statement_stats.name,),
        ),
        DiagnosisOutputOverlapCase(
            case_id="local_query_info_input",
            main=trino_query_info_pruned_import.main,
            argv=(
                "--redaction-reviewed",
                "--diagnosis-out",
                str(query_info),
                "--source-contract",
                str(local_contract),
                str(query_info),
            ),
            expected_error="compact diagnosis output must differ from input",
            protected_names=(query_info.name, local_contract.name),
        ),
        DiagnosisOutputOverlapCase(
            case_id="local_query_info_source_contract",
            main=trino_query_info_pruned_import.main,
            argv=(
                "--redaction-reviewed",
                "--diagnosis-out",
                str(local_contract),
                "--source-contract",
                str(local_contract),
                str(query_info),
            ),
            expected_error="compact diagnosis output must differ from source contract",
            protected_names=(query_info.name, local_contract.name),
        ),
        DiagnosisOutputOverlapCase(
            case_id="http_query_detail_source_contract",
            main=trino_http_query_detail_archive_import.main,
            argv=(
                "--redaction-reviewed",
                "--diagnosis-out",
                str(http_contract),
                "--source-contract",
                str(http_contract),
                "--archive-url",
                "https://operator.example.invalid/query-detail.json",
            ),
            expected_error="compact diagnosis output must differ from input",
            protected_names=(http_contract.name, "operator.example.invalid"),
        ),
        DiagnosisOutputOverlapCase(
            case_id="coordinator_query_info_source_contract",
            main=trino_coordinator_query_info_pruned_import.main,
            argv=(
                "--redaction-reviewed",
                "--diagnosis-out",
                str(coordinator_contract),
                "--source-contract",
                str(coordinator_contract),
                "--coordinator-url",
                "https://trino.example.invalid",
                "--query-id",
                "20260604_123456_00001_abcd1",
            ),
            expected_error="compact diagnosis output must differ from input",
            protected_names=(
                coordinator_contract.name,
                "trino.example.invalid",
                "20260604_123456_00001_abcd1",
            ),
        ),
        DiagnosisOutputOverlapCase(
            case_id="coordinator_query_info_auth_header",
            main=trino_coordinator_query_info_pruned_import.main,
            argv=(
                "--redaction-reviewed",
                "--diagnosis-out",
                str(auth_header),
                "--source-contract",
                str(coordinator_contract),
                "--coordinator-url",
                "https://trino.example.invalid",
                "--query-id",
                "20260604_123456_00001_abcd1",
                "--auth-header-file",
                str(auth_header),
            ),
            expected_error="compact diagnosis output must differ from auth header file",
            protected_names=(
                auth_header.name,
                coordinator_contract.name,
                "trino.example.invalid",
                "20260604_123456_00001_abcd1",
            ),
        ),
        DiagnosisOutputOverlapCase(
            case_id="coordinator_query_info_auth_header_ignores_unread_input",
            main=trino_coordinator_query_info_pruned_import.main,
            argv=(
                "--redaction-reviewed",
                "--diagnosis-out",
                str(auth_header),
                "--source-contract",
                str(separate_input),
                "--coordinator-url",
                "https://trino.example.invalid",
                "--query-id",
                "20260604_123456_00001_abcd1",
                "--auth-header-file",
                str(auth_header),
            ),
            expected_error="compact diagnosis output must differ from auth header file",
            protected_names=(
                auth_header.name,
                separate_input.name,
                "trino.example.invalid",
                "20260604_123456_00001_abcd1",
            ),
        ),
    )
