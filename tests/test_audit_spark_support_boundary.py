from __future__ import annotations

import json
from pathlib import Path

from scripts import audit_spark_support_boundary


ROOT = Path(__file__).resolve().parents[1]


def test_spark_support_boundary_audit_passes_without_support_claim(capsys) -> None:
    exit_code = audit_spark_support_boundary.main([])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Spark support boundary audit: ok" in captured.out
    assert "production_support=not_claimed" in captured.out
    assert "engine_registration=bounded_compact_only" in captured.out
    assert "product_surfaces=not_wired" in captured.out
    assert "spark_job_execution=not_performed" in captured.out
    assert "product_surface_imports: ok" in captured.out
    assert "Issues: none" in captured.out
    assert str(ROOT) not in captured.out
    assert captured.err == ""


def test_spark_support_boundary_audit_writes_path_free_summary_json(tmp_path, capsys) -> None:
    summary_path = tmp_path / "secret-support-boundary-summary.json"

    exit_code = audit_spark_support_boundary.main(["--summary-json", str(summary_path)])

    captured = capsys.readouterr()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    rendered = json.dumps(summary, sort_keys=True)
    assert exit_code == 0
    assert "Spark support boundary audit: ok" in captured.out
    assert summary["summary_kind"] == "spark_support_boundary_audit_v1"
    assert summary["status"] == "ok"
    assert summary["mode"] == "spark_support_boundary"
    assert summary["boundary"] == {
        "engine_registration": "bounded_compact_only",
        "product_surfaces": "not_wired",
        "production_support": "not_claimed",
        "spark_job_execution": "not_performed",
    }
    assert summary["counts"]["check_count"] >= 1
    assert summary["counts"]["failed_check_count"] == 0
    assert summary["checks"]["engine_registration"] == "ok"
    assert summary["checks"]["product_surface_imports"] == "ok"
    assert summary["issues"] == {"counts": {}, "items": []}
    for fragment in (str(tmp_path), "secret-support-boundary-summary.json"):
        assert fragment not in captured.out
        assert fragment not in captured.err
        assert fragment not in rendered


def test_spark_support_boundary_audit_flags_missing_spark_registration(monkeypatch) -> None:
    class Adapter:
        engine_name = "impala"

    monkeypatch.setattr(audit_spark_support_boundary, "list_engine_adapters", lambda: (Adapter(),))

    result = audit_spark_support_boundary.audit_spark_support_boundary()

    assert not result.ok
    assert result.checks["engine_registration"] == "failed"
    assert [issue.category for issue in result.issues] == ["engine_registration"]


def test_spark_support_boundary_audit_writes_failed_summary_without_path_echo(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    class Adapter:
        engine_name = "impala"

    summary_path = tmp_path / "secret-failed-support-boundary-summary.json"
    monkeypatch.setattr(audit_spark_support_boundary, "list_engine_adapters", lambda: (Adapter(),))

    exit_code = audit_spark_support_boundary.main(["--summary-json", str(summary_path)])

    captured = capsys.readouterr()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    rendered = json.dumps(summary, sort_keys=True)
    assert exit_code == 1
    assert "Spark support boundary audit: failed" in captured.out
    assert summary["status"] == "failed"
    assert summary["checks"]["engine_registration"] == "failed"
    assert summary["issues"]["counts"] == {"engine_registration": 1}
    assert summary["issues"]["items"] == [
        {
            "category": "engine_registration",
            "message": "Spark adapter must stay registered only for bounded compact support surfaces.",
        }
    ]
    for fragment in (str(tmp_path), "secret-failed-support-boundary-summary.json"):
        assert fragment not in captured.out
        assert fragment not in captured.err
        assert fragment not in rendered


def test_spark_support_boundary_audit_flags_product_capability_drift(monkeypatch) -> None:
    class ImpalaAdapter:
        engine_name = "impala"

    class SparkAdapter:
        engine_name = "spark"
        supports_offline_evidence_import = True
        supports_compact_diagnosis = True
        supports_history_server_compact_intake = True
        supports_recent_scan = True
        supports_query_id_mode = False
        supports_metadata_collection = False
        supports_validated_reports = False

    monkeypatch.setattr(
        audit_spark_support_boundary,
        "list_engine_adapters",
        lambda: (ImpalaAdapter(), SparkAdapter()),
    )

    result = audit_spark_support_boundary.audit_spark_support_boundary()

    assert not result.ok
    assert result.checks["engine_registration"] == "failed"
    assert [issue.category for issue in result.issues] == ["engine_registration"]


def test_spark_support_boundary_counts_forbidden_product_imports(tmp_path) -> None:
    product_surface = tmp_path / "report_surface.py"
    product_surface.write_text(
        "from query_doctor.spark.diagnosis import build_spark_compact_diagnosis\n",
        encoding="utf-8",
    )
    unrelated_surface = tmp_path / "safe_surface.py"
    unrelated_surface.write_text("from query_doctor.web.ui.spark import render\n", encoding="utf-8")

    assert (
        audit_spark_support_boundary.count_forbidden_product_imports(
            (product_surface, unrelated_surface)
        )
        == 1
    )


def test_spark_support_boundary_flags_stale_registration_wording(tmp_path) -> None:
    _write_doc(
        tmp_path / "README.md",
        "Spark compact support surfaces\nno public Spark engine support\n",
    )
    _write_doc(
        tmp_path / "docs" / "engine-support-gap-matrix.md",
        "| Fact family | Apache Impala | Trino | Spark |\n"
        "| --- | --- | --- | --- |\n"
        "| Public support status | implemented | preview | bounded compact support surfaces; not production support |\n"
        "| Engine adapter registration | implemented | preview | bounded compact intake only; no Recent scans |\n"
        "| Source/evidence contract | implemented | preview | same_application "
        "application-level job/stage/task summaries with task-duration context; "
        "SQL-execution-specific timing and failure facts stay unknown without direct evidence |\n",
    )
    _write_doc(
        tmp_path / "docs" / "README.md",
        "Bounded compact Spark History Server/event-log fact-model, compact-only adapter "
        "without public engine support.\n",
    )
    _write_doc(
        tmp_path / "docs" / "i18n" / "ru" / "README.md",
        "bounded compact research контракт для Spark History Server/event-log fact model, "
        "compact-only adapter\n",
    )
    _write_doc(
        tmp_path / "docs" / "engines" / "spark-architecture-spike.md",
        "Current status: `bounded_compact_research`.\n"
        "registered bounded compact-intake adapter\n"
        "not a Recent scan workflow, Details/trusted report surface, optimizer path, "
        "broad live collector, raw event-log path, Spark job-execution path, or public "
        "Spark support claim\n",
    )
    _write_doc(
        tmp_path / "docs" / "engines" / "spark-test-cluster-evidence-checklist.md",
        "not a live Spark support announcement\n"
        "no Spark registration beyond the compact-only adapter, Recent workflow, Details route, trusted report\n",
    )
    _write_doc(
        tmp_path / "docs" / "engine-expansion-plan.md",
        "This must not add Spark engine registration.\n",
    )
    _write_doc(tmp_path / "docs" / "engines" / "i18n" / "ru" / "spark-architecture-spike.md", "")
    _write_doc(
        tmp_path / "docs" / "engines" / "i18n" / "ru" / "spark-test-cluster-evidence-checklist.md",
        "",
    )
    _write_doc(tmp_path / "docs" / "changelog.md", "")
    _write_doc(tmp_path / "query_doctor" / "spark" / "__init__.py", "")

    result = audit_spark_support_boundary.SparkSupportBoundaryAuditResult()
    audit_spark_support_boundary._audit_docs(result, tmp_path)

    assert not result.ok
    assert result.checks["stale_registration_wording"] == "failed"


def _write_doc(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
