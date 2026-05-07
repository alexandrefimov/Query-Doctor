import hashlib
import json

from query_doctor.web import trusted_artifacts


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
