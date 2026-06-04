from pathlib import Path


SPARK_EVIDENCE_CHECKLIST_DOC = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "engines"
    / "spark-test-cluster-evidence-checklist.md"
)
DOCS_INDEX = Path(__file__).resolve().parents[1] / "docs" / "README.md"
RU_DOCS_INDEX = Path(__file__).resolve().parents[1] / "docs" / "i18n" / "ru" / "README.md"
SPARK_ARCHITECTURE_DOC = (
    Path(__file__).resolve().parents[1] / "docs" / "engines" / "spark-architecture-spike.md"
)


def test_spark_test_cluster_evidence_checklist_stays_non_supporting() -> None:
    text = _normalized_doc_text()

    for required in (
        "not a live Spark support announcement",
        "engine selector",
        "Recent workflow",
        "Details/trusted-report surface",
        "optimizer path",
        "permission to execute Spark jobs or Spark SQL through Query Doctor",
        "Do not run Spark jobs",
        "Do not run Query Doctor-generated EXPLAIN",
        "Do not use broad History Server crawls",
        "Do not use the evidence set to add Spark engine registration",
        "This does not require live query execution.",
        "Product support comes later",
    ):
        assert required in text


def test_spark_test_cluster_evidence_checklist_requires_compact_raw_free_evidence() -> None:
    text = _normalized_doc_text()

    for required in (
        "operator-reviewed compact evidence",
        "bounded read-only collection",
        "compact Spark History Server summaries",
        "query-doctor-collect-spark-history",
        "spark_history_eventlog_compact_v1",
        "raw-free engine fact boundary JSON",
        "deterministic Spark compact diagnosis JSON",
        "redaction note describing removed field classes, not removed values",
        "explicit-application, summary-only, bounded per endpoint",
        "Private or loopback History Server targets require explicit local opt-in",
    ):
        assert required in text


def test_spark_test_cluster_evidence_checklist_pins_cases_and_redaction() -> None:
    text = _normalized_doc_text()

    for required in (
        "finished Spark SQL application with one accepted SQL execution linkage",
        "application-only collection where query linkage is same_application",
        "failed or killed application with only an allowlisted safe failure category",
        "missing or partial History Server endpoint coverage",
        "spill observed",
        "stage or task skew candidate",
        "adaptive execution checked enabled and checked disabled cases",
        "dynamic allocation observed and unknown cases",
        "high aggregate executor memory utilization",
        "unsafe raw field rejection case using synthetic sentinel values only",
        "remove raw SQL, SQL descriptions, plan descriptions, and physical plans",
        "remove application, attempt, SQL execution, job, stage, task, and executor identifiers",
        "remove stack traces, raw exception messages, warning payloads, log lines",
        "replace source-specific detail with compact checked booleans",
    ):
        assert required in text


def test_spark_test_cluster_evidence_checklist_pins_readiness_audit() -> None:
    text = _normalized_doc_text()

    for required in (
        "scripts/audit_spark_compact_readiness.py",
        "--require-supported-attention",
        "--require-min-inputs 2",
        "--require-source-contract spark_history_server_compact_v1",
        "--require-source-contract spark_history_eventlog_compact_v1",
        "--fail-on-source-warnings",
        "query-doctor-build-spark-evidence-package",
        "query-doctor-validate-spark-evidence-package",
        "--partial-ok",
        "must not echo compact input paths, raw filenames, raw payload values",
        "History Server URLs, request selectors, SQL, log content, or local output paths",
        "Keep raw exports outside the repository and outside prompts.",
    ):
        assert required in text


def test_spark_test_cluster_evidence_checklist_is_indexed_and_cross_linked() -> None:
    docs_index = DOCS_INDEX.read_text(encoding="utf-8")
    ru_docs_index = RU_DOCS_INDEX.read_text(encoding="utf-8")
    architecture = SPARK_ARCHITECTURE_DOC.read_text(encoding="utf-8")

    assert "engines/spark-test-cluster-evidence-checklist.md" in docs_index
    assert "engines/i18n/ru/spark-test-cluster-evidence-checklist.md" in docs_index
    assert "spark-test-cluster-evidence-checklist.md" in ru_docs_index
    assert "spark-test-cluster-evidence-checklist.md" in architecture


def _normalized_doc_text() -> str:
    text = SPARK_EVIDENCE_CHECKLIST_DOC.read_text(encoding="utf-8").replace("`", "")
    return " ".join(text.split())
