from __future__ import annotations

import hashlib
import json
from pathlib import Path

from query_doctor.web import trusted_artifacts
from query_doctor.web.jobs import WebJobStore


def test_trusted_artifacts_exposes_optimizer_artifact_status_helpers():
    assert trusted_artifacts.optimizer_artifact_status_for_case({}) == "unknown"
    assert trusted_artifacts.OPTIMIZER_STATUS_ORDER["trusted_draft"] > trusted_artifacts.OPTIMIZER_STATUS_ORDER["not_run"]


def write_optimizer_marker(case_dir, *, source_sql, draft_name="optimized_query.sql", source_scope="read_only_statement"):
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


def write_trusted_optimizer_draft(case_dir: Path, *, source_sql: str, draft_sql: str | None = None) -> None:
    (case_dir / "cm_metadata.json").write_text(json.dumps({"statement": source_sql}), encoding="utf-8")
    (case_dir / "optimized_query.sql").write_text(draft_sql or f"{source_sql};\n", encoding="utf-8")
    write_optimizer_marker(case_dir, source_sql=source_sql)


def batch_settings(tmp_path: Path, case_dir: Path) -> trusted_artifacts.WebSettings:
    summary = tmp_path / "batch_summary.json"
    summary.write_text(
        json.dumps({"cases": [{"case_index": 1, "query_id": "abc", "case_dir": str(case_dir)}]}),
        encoding="utf-8",
    )
    return trusted_artifacts.WebSettings(config=Path(".query-doctor-cm.local.json"), batch_summary=summary)


def test_optimizer_artifact_status_uses_strict_trust_check_for_source_scope(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    source_sql = "SELECT a FROM db.source_table WHERE ds = 20260504"
    (case_dir / "analysis_facts.md").write_text("FACTS\n", encoding="utf-8")
    (case_dir / "cm_metadata.json").write_text(json.dumps({"statement": source_sql}), encoding="utf-8")
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
    (case_dir / "cm_metadata.json").write_text(json.dumps({"statement": source_sql}), encoding="utf-8")
    (case_dir / "optimized_query.sql").write_text("DROP TABLE db.source_table;\n", encoding="utf-8")
    write_optimizer_marker(case_dir, source_sql=source_sql)

    assert not trusted_artifacts.optimized_query_validated_exists(case_dir)
    assert trusted_artifacts.optimizer_artifact_status_for_dir(case_dir) == "partial_untrusted"


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


def test_specific_query_trusted_detail_artifacts_hide_stale_outputs(tmp_path):
    case_dir = tmp_path / "query-case"
    case_dir.mkdir()
    source_sql = "SELECT a FROM db.source_table WHERE ds = 20260504"
    (case_dir / "analysis_facts.md").write_text("FACTS\n", encoding="utf-8")
    write_trusted_report(case_dir, "# Report\n\nsafe body\n")
    write_trusted_optimizer_draft(case_dir, source_sql=source_sql)
    (case_dir / "diagnosis.md").write_text("# Report\n\nchanged after validation\n", encoding="utf-8")
    (case_dir / "optimized_query.sql").write_text("SELECT a FROM db.source_table;\n", encoding="utf-8")

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
