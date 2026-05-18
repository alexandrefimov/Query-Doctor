from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from query_doctor.web import trusted_artifacts
from query_doctor.web.jobs import WebJobStore


def test_trusted_artifacts_exposes_optimizer_artifact_status_helpers():
    assert trusted_artifacts.optimizer_artifact_status_for_case({}) == "unknown"
    assert (
        trusted_artifacts.OPTIMIZER_STATUS_ORDER["trusted_draft"]
        > trusted_artifacts.OPTIMIZER_STATUS_ORDER["not_run"]
    )
    assert (
        trusted_artifacts.trusted_report_download_filename("abc:def$$$")
        == "query-doctor-report-abcdef.md"
    )
    assert (
        trusted_artifacts.trusted_report_download_filename("$$$") == "query-doctor-report-report.md"
    )


def test_trusted_markers_reexport_through_trusted_artifacts():
    from query_doctor.web import trusted_markers

    assert (
        trusted_artifacts.batch_case_validated_report_exists
        is trusted_markers.batch_case_validated_report_exists
    )
    assert (
        trusted_artifacts.optimized_query_validated_exists
        is trusted_markers.optimized_query_validated_exists
    )


def test_report_evidence_reexport_through_trusted_artifacts():
    from query_doctor.web import report_evidence

    assert trusted_artifacts.report_evidence_inventory is report_evidence.report_evidence_inventory
    assert trusted_artifacts.ReportEvidenceInventory is report_evidence.ReportEvidenceInventory


def test_trusted_artifacts_uses_canonical_progress_view_from_snapshot():
    from query_doctor.web import job_progress

    assert trusted_artifacts.progress_view_from_snapshot is job_progress.progress_view_from_snapshot
    assert callable(job_progress.progress_view_from_snapshot)


def test_running_report_state_carries_non_null_progress_view(tmp_path):
    from query_doctor.web.job_progress import JobProgressView

    case_dir = tmp_path / "case-001"
    store = WebJobStore()
    snapshot = store.create_batch_report("case-001")

    state = trusted_artifacts.load_batch_case_report_state(
        batch_settings(tmp_path, case_dir),
        "case-001",
        {"case_index": 1, "query_id": "abc", "case_dir": str(case_dir)},
        store,
        job=snapshot,
    )

    assert state["status"] == "running"
    assert isinstance(state["progress_view"], JobProgressView)


def test_running_optimized_query_state_carries_non_null_progress_view(tmp_path):
    from query_doctor.web.job_progress import JobProgressView

    case_dir = tmp_path / "case-001"
    case_dir.mkdir()
    store = WebJobStore()
    snapshot = store.create_batch_optimized_query("case-001")

    state = trusted_artifacts.load_optimized_query_state(
        case_dir,
        store,
        batch_case_id="case-001",
        job=snapshot,
    )

    assert state["status"] == "running"
    assert isinstance(state["progress_view"], JobProgressView)


def test_no_private_path_helpers_remain_in_trust_modules():
    from query_doctor.web import report_evidence

    assert not hasattr(trusted_artifacts, "_case_has_any_artifact")
    assert not hasattr(trusted_artifacts, "_case_has_relative_file")
    assert not hasattr(trusted_artifacts, "_case_relative_file_path")
    assert not hasattr(trusted_artifacts, "_read_case_relative_text")
    assert not hasattr(report_evidence, "_case_has_any_artifact")


def test_report_evidence_inventory_returns_safe_categories_without_filenames(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "profile_digest.md").write_text("PROFILE\n", encoding="utf-8")
    (case_dir / "analysis_facts.md").write_text("FACTS\n", encoding="utf-8")
    (case_dir / "impala_context.json").write_text("{}\n", encoding="utf-8")

    inventory = trusted_artifacts.report_evidence_inventory(case_dir)

    category_labels = tuple(category.label for category in inventory.categories)
    completeness = {item.label: item.state for item in inventory.completeness}
    assert "Profile digest" in category_labels
    assert "Analyzer facts" in category_labels
    assert "Impala metadata JSON" in category_labels
    assert completeness["Profile"] == "available"
    assert completeness["SQL"] == "not collected"
    assert completeness["Metadata"] == "available"
    assert inventory.profile_evidence_state == "available"
    assert inventory.analyzer_facts_state == "available"
    assert "profile_digest.md" not in repr(inventory)
    assert "analysis_facts.md" not in repr(inventory)
    assert str(case_dir) not in repr(inventory)


def test_report_evidence_inventory_ignores_symlinked_artifacts_outside_case_dir(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    outside_profile = tmp_path / "profile_digest.md"
    outside_facts = tmp_path / "analysis_facts.md"
    outside_profile.write_text("PROFILE\n", encoding="utf-8")
    outside_facts.write_text("FACTS\n", encoding="utf-8")
    (case_dir / "profile_digest.md").symlink_to(outside_profile)
    (case_dir / "analysis_facts.md").symlink_to(outside_facts)

    inventory = trusted_artifacts.report_evidence_inventory(case_dir)

    category_labels = tuple(category.label for category in inventory.categories)
    completeness = {item.label: item.state for item in inventory.completeness}
    assert "Profile digest" not in category_labels
    assert "Analyzer facts" not in category_labels
    assert completeness["Profile"] == "not collected"
    assert inventory.profile_evidence_state == "not observed"
    assert inventory.analyzer_facts_state == "not observed"


def test_case_has_analyzer_facts_hides_raw_filename_contract(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()

    assert trusted_artifacts.case_has_analyzer_facts(case_dir) is False

    (case_dir / "analysis_facts.md").write_text("FACTS\n", encoding="utf-8")

    assert trusted_artifacts.case_has_analyzer_facts(case_dir) is True


def test_load_case_analyzer_facts_text_is_bounded_and_path_safe(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "analysis_facts.md").write_text("FACTS\n", encoding="utf-8")

    assert trusted_artifacts.load_case_analyzer_facts_text(case_dir) == "FACTS\n"
    assert trusted_artifacts.load_case_analyzer_facts_text(case_dir, max_bytes=4) is None

    missing_dir = tmp_path / "missing"
    assert trusted_artifacts.load_case_analyzer_facts_text(missing_dir) is None


def test_load_case_impala_context_artifact_is_bounded_and_path_safe(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "impala_context.json").write_text(
        '{"tables": ["db.safe_table"]}\n', encoding="utf-8"
    )

    artifact = trusted_artifacts.load_case_impala_context_artifact(case_dir)

    assert artifact is not None
    assert artifact.case_dir == case_dir.resolve()
    assert artifact.context_path == (case_dir / "impala_context.json").resolve()
    assert artifact.payload == {"tables": ["db.safe_table"]}
    assert trusted_artifacts.case_has_impala_context_artifact(case_dir) is True
    assert trusted_artifacts.load_case_impala_context_artifact(case_dir, max_bytes=4) is None

    unsafe_case_dir = tmp_path / "unsafe-case"
    unsafe_case_dir.mkdir()
    outside_context = tmp_path / "outside.json"
    outside_context.write_text('{"tables": ["db.outside"]}\n', encoding="utf-8")
    (unsafe_case_dir / "impala_context.json").symlink_to(outside_context)
    assert trusted_artifacts.case_has_impala_context_artifact(unsafe_case_dir) is False
    assert trusted_artifacts.load_case_impala_context_artifact(unsafe_case_dir) is None

    assert trusted_artifacts.load_case_impala_context_artifact(tmp_path / "missing") is None


def write_optimizer_marker(
    case_dir, *, source_sql, draft_name="optimized_query.sql", source_scope="read_only_statement"
):
    marker = {
        "draft": draft_name,
        "draft_sha256": trusted_artifacts.file_sha256(case_dir / draft_name),
        "facts_sha256": trusted_artifacts.file_sha256(case_dir / "analysis_facts.md"),
        "risk_mode": "rewrite_allowed",
        "risk_reasons": [],
        "schema_version": trusted_artifacts.OPTIMIZED_QUERY_MARKER_SCHEMA_VERSION,
        "source": "query_doctor_optimize_query",
        "source_scope": source_scope,
        "source_sql_sha256": hashlib.sha256(source_sql.encode("utf-8")).hexdigest(),
        "validated": True,
        "validation_mode": trusted_artifacts.OPTIMIZED_QUERY_VALIDATION_MODE,
    }
    (case_dir / "optimized_query.validated.json").write_text(json.dumps(marker), encoding="utf-8")


def write_trusted_report(case_dir: Path, text: str) -> None:
    (case_dir / "diagnosis.md").write_text(text, encoding="utf-8")
    trusted_artifacts.write_batch_case_report_validation_marker(case_dir)


def write_trusted_optimizer_draft(
    case_dir: Path, *, source_sql: str, draft_sql: str | None = None
) -> None:
    (case_dir / "cm_metadata.json").write_text(
        json.dumps({"statement": source_sql}), encoding="utf-8"
    )
    (case_dir / "optimized_query.sql").write_text(draft_sql or f"{source_sql};\n", encoding="utf-8")
    write_optimizer_marker(case_dir, source_sql=source_sql)


def batch_settings(tmp_path: Path, case_dir: Path) -> trusted_artifacts.WebSettings:
    summary = tmp_path / "batch_summary.json"
    summary.write_text(
        json.dumps({"cases": [{"case_index": 1, "query_id": "abc", "case_dir": str(case_dir)}]}),
        encoding="utf-8",
    )
    return trusted_artifacts.WebSettings(
        config=Path(".query-doctor-cm.local.json"), batch_summary=summary
    )


def test_resolve_batch_case_report_dir_ignores_profile_symlink_outside_case_dir(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    outside_profile = tmp_path / "profile_digest.md"
    outside_profile.write_text("PROFILE\n", encoding="utf-8")
    (case_dir / "profile_digest.md").symlink_to(outside_profile)

    assert (
        trusted_artifacts.resolve_batch_case_report_dir(
            batch_settings(tmp_path, case_dir),
            {"case_index": 1, "query_id": "abc", "case_dir": str(case_dir)},
        )
        is None
    )


def test_optimizer_artifact_status_uses_strict_trust_check_for_source_scope(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    source_sql = "SELECT a FROM db.source_table WHERE ds = 20260504"
    (case_dir / "analysis_facts.md").write_text("FACTS\n", encoding="utf-8")
    (case_dir / "cm_metadata.json").write_text(
        json.dumps({"statement": source_sql}), encoding="utf-8"
    )
    (case_dir / "optimized_query.sql").write_text(
        "SELECT a FROM db.source_table WHERE ds = 20260504;\n",
        encoding="utf-8",
    )
    write_optimizer_marker(case_dir, source_sql=source_sql, source_scope="wrong_scope")

    assert not trusted_artifacts.optimized_query_validated_exists(case_dir)
    assert trusted_artifacts.optimizer_artifact_status_for_dir(case_dir) == "partial_untrusted"


def test_optimizer_artifact_status_uses_strict_trust_check_for_draft_sql_safety(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    source_sql = "SELECT a FROM db.source_table WHERE ds = 20260504"
    (case_dir / "analysis_facts.md").write_text("FACTS\n", encoding="utf-8")
    (case_dir / "cm_metadata.json").write_text(
        json.dumps({"statement": source_sql}), encoding="utf-8"
    )
    (case_dir / "optimized_query.sql").write_text("DROP TABLE db.source_table;\n", encoding="utf-8")
    write_optimizer_marker(case_dir, source_sql=source_sql)

    assert not trusted_artifacts.optimized_query_validated_exists(case_dir)
    assert trusted_artifacts.optimizer_artifact_status_for_dir(case_dir) == "partial_untrusted"


def test_trusted_report_artifacts_include_text_and_safe_download_name(tmp_path):
    batch_case_dir = tmp_path / "cases" / "case-001"
    specific_case_dir = tmp_path / "specific"
    sibling_path = "/tmp/query-doctor-sibling-case/diagnosis.md"
    user_path = "/Users/example/query-doctor/leak.md"
    batch_case_dir.mkdir(parents=True)
    specific_case_dir.mkdir()
    for case_dir in (batch_case_dir, specific_case_dir):
        (case_dir / "profile_digest.md").write_text("PROFILE\n", encoding="utf-8")
        (case_dir / "analysis_facts.md").write_text("FACTS\n", encoding="utf-8")
        write_trusted_report(
            case_dir,
            f"# Report\n\nsafe body from {case_dir}\n{sibling_path}\n{user_path}\n",
        )

    batch_artifact = trusted_artifacts.load_batch_case_trusted_report_artifact(
        batch_settings(tmp_path, batch_case_dir),
        "case:001$$$",
        {"case_index": 1, "query_id": "abc", "case_dir": str(batch_case_dir)},
    )
    specific_artifact = trusted_artifacts.load_specific_query_trusted_report_artifact(
        "abc:def$$$",
        specific_case_dir,
    )

    assert batch_artifact is not None
    assert batch_artifact.source_id == "case:001$$$"
    assert batch_artifact.download_filename == "query-doctor-report-case001.md"
    assert "[local case path hidden]" in batch_artifact.text
    assert str(batch_case_dir) not in batch_artifact.text
    assert sibling_path not in batch_artifact.text
    assert user_path not in batch_artifact.text
    assert specific_artifact is not None
    assert specific_artifact.source_id == "abc:def$$$"
    assert specific_artifact.download_filename == "query-doctor-report-abcdef.md"
    assert "[local case path hidden]" in specific_artifact.text
    assert str(specific_case_dir) not in specific_artifact.text
    assert sibling_path not in specific_artifact.text
    assert user_path not in specific_artifact.text


def test_trusted_report_artifacts_hide_stale_report_text(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "analysis_facts.md").write_text("FACTS\n", encoding="utf-8")
    write_trusted_report(case_dir, "# Report\n\nsafe body\n")
    (case_dir / "diagnosis.md").write_text(
        "# Report\n\nchanged after validation\n", encoding="utf-8"
    )

    assert (
        trusted_artifacts.load_batch_case_trusted_report_artifact(
            batch_settings(tmp_path, case_dir),
            "case-001",
            {"case_index": 1, "query_id": "abc", "case_dir": str(case_dir)},
        )
        is None
    )
    assert trusted_artifacts.load_specific_query_trusted_report_artifact("abc", case_dir) is None


def test_trusted_report_artifacts_reject_report_symlink_outside_case_dir(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    outside_report = tmp_path / "diagnosis.md"
    outside_report.write_text("# Report\n\noutside body\n", encoding="utf-8")
    (case_dir / "analysis_facts.md").write_text("FACTS\n", encoding="utf-8")
    (case_dir / "diagnosis.md").symlink_to(outside_report)

    assert not trusted_artifacts.case_has_batch_report_output(case_dir)
    with pytest.raises(ValueError, match="case-contained report"):
        trusted_artifacts.write_batch_case_report_validation_marker(case_dir)
    assert not trusted_artifacts.batch_case_validated_report_exists(case_dir)
    assert trusted_artifacts.load_specific_query_trusted_report_artifact("abc", case_dir) is None


def test_batch_case_trusted_detail_artifacts_loads_only_validated_outputs(tmp_path):
    case_dir = tmp_path / "cases" / "case-001"
    case_dir.mkdir(parents=True)
    source_sql = "SELECT a FROM db.source_table WHERE ds = 20260504"
    (case_dir / "profile_digest.md").write_text("PROFILE\n", encoding="utf-8")
    (case_dir / "analysis_facts.md").write_text("FACTS\n", encoding="utf-8")
    write_trusted_report(case_dir, f"# Report\n\nsafe body from {case_dir}\n")
    write_trusted_optimizer_draft(case_dir, source_sql=source_sql)

    artifacts = trusted_artifacts.load_batch_case_trusted_detail_artifacts(
        batch_settings(tmp_path, case_dir),
        "case-001",
        {"case_index": 1, "query_id": "abc", "case_dir": str(case_dir)},
        WebJobStore(),
    )

    assert artifacts.artifact_dir == case_dir
    assert artifacts.report_state["trusted"] is True
    assert artifacts.optimized_query_state["trusted"] is True
    assert artifacts.trusted_report_text is not None
    assert "[local case path hidden]" in artifacts.trusted_report_text
    assert str(case_dir) not in artifacts.trusted_report_text
    assert artifacts.trusted_optimized_query == f"{source_sql};\n"
    assert artifacts.trusted_optimizer_recommendations is None


def test_trusted_optimizer_artifacts_reject_draft_symlink_outside_case_dir(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    source_sql = "SELECT a FROM db.source_table WHERE ds = 20260504"
    outside_draft = tmp_path / "optimized_query.sql"
    outside_draft.write_text(f"{source_sql};\n", encoding="utf-8")
    (case_dir / "analysis_facts.md").write_text("FACTS\n", encoding="utf-8")
    (case_dir / "cm_metadata.json").write_text(
        json.dumps({"statement": source_sql}), encoding="utf-8"
    )
    (case_dir / "optimized_query.sql").symlink_to(outside_draft)
    write_optimizer_marker(case_dir, source_sql=source_sql)

    assert not trusted_artifacts.optimized_query_validated_exists(case_dir)
    assert trusted_artifacts.load_validated_optimized_query(case_dir) is None


def test_trusted_optimizer_artifacts_reject_recommendations_symlink_outside_case_dir(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    source_sql = "SELECT a FROM db.source_table WHERE ds = 20260504"
    facts_text = "FACTS\n"
    outside_recommendations = tmp_path / "optimized_query_recommendations.md"
    outside_recommendations.write_text("- Collect table and column statistics.\n", encoding="utf-8")
    (case_dir / "analysis_facts.md").write_text(facts_text, encoding="utf-8")
    (case_dir / "cm_metadata.json").write_text(
        json.dumps({"statement": source_sql}), encoding="utf-8"
    )
    (case_dir / "optimized_query_recommendations.md").symlink_to(outside_recommendations)
    marker = {
        "facts_sha256": hashlib.sha256(facts_text.encode("utf-8")).hexdigest(),
        "output_kind": "recommendations_only",
        "recommendations": "optimized_query_recommendations.md",
        "recommendations_sha256": trusted_artifacts.file_sha256(
            case_dir / "optimized_query_recommendations.md"
        ),
        "risk_mode": "recommendations_only",
        "risk_reasons": ["too_many_ctes_for_safe_rewrite"],
        "schema_version": trusted_artifacts.OPTIMIZED_QUERY_MARKER_SCHEMA_VERSION,
        "source": "query_doctor_optimize_query",
        "source_scope": "read_only_statement",
        "source_sql_sha256": hashlib.sha256(source_sql.encode("utf-8")).hexdigest(),
        "validated": True,
        "validation_mode": trusted_artifacts.OPTIMIZED_QUERY_VALIDATION_MODE,
    }
    (case_dir / "optimized_query.validated.json").write_text(json.dumps(marker), encoding="utf-8")

    assert not trusted_artifacts.optimized_query_validated_exists(case_dir)
    assert trusted_artifacts.load_validated_optimizer_recommendations(case_dir) is None


def test_specific_query_trusted_detail_artifacts_hide_stale_outputs(tmp_path):
    case_dir = tmp_path / "query-case"
    case_dir.mkdir()
    source_sql = "SELECT a FROM db.source_table WHERE ds = 20260504"
    (case_dir / "analysis_facts.md").write_text("FACTS\n", encoding="utf-8")
    write_trusted_report(case_dir, "# Report\n\nsafe body\n")
    write_trusted_optimizer_draft(case_dir, source_sql=source_sql)
    (case_dir / "diagnosis.md").write_text(
        "# Report\n\nchanged after validation\n", encoding="utf-8"
    )
    (case_dir / "optimized_query.sql").write_text(
        "SELECT a FROM db.source_table;\n", encoding="utf-8"
    )

    artifacts = trusted_artifacts.load_specific_query_trusted_detail_artifacts(
        trusted_artifacts.WebSettings(config=Path(".query-doctor-cm.local.json")),
        "abc",
        case_dir,
        WebJobStore(),
    )

    assert artifacts.artifact_dir == case_dir
    assert artifacts.report_state["trusted"] is False
    assert artifacts.optimized_query_state["trusted"] is False
    assert artifacts.optimized_query_state["status"] == "partial_untrusted"
    assert artifacts.trusted_report_text is None
    assert artifacts.trusted_optimized_query is None
    assert artifacts.trusted_optimizer_recommendations is None
