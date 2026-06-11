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
        "Do not use the evidence set to broaden Spark registration beyond the compact-only adapter",
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
        "spark_compact_diagnostic_lane_v1",
        "diagnostic-lane contract",
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


def test_spark_test_cluster_evidence_checklist_records_readiness_boundary() -> None:
    text = _normalized_doc_text()

    for required in (
        "Readiness Evidence Boundary",
        "bounded one-application History Server intake can stay raw-free and warning-free",
        "evidence for the compact intake contract only",
        "not readiness for Spark production support",
        "Recent scans",
        "Details/trusted reports",
        "optimizer behavior",
        "broad live collection",
        "raw event-log reads",
        "fixture promotion",
        "same_application handoff without a selected SQL execution can summarize readable application-level jobs",
        "without raw selectors in compact output",
        "SQL-execution specific timing, failure category, and exact query linkage still require accepted SQL execution evidence",
        "Keep live validation notes, private endpoints, selectors, ports, event-log locations, output paths, and one-run checkpoint details out of committed docs",
        "Public docs should record only durable source-coverage behavior, support boundaries, and sanitization requirements",
    ):
        assert required in text

    for obsolete in (
        "Current Live Checkpoint",
        "2026-06-05 Spark 4.1 live checkpoint",
        "all six top-level endpoints readable",
        "zero source warnings",
        "supported_attention_areas=0",
        "stock cluster History Server can be reachable yet return no applications",
    ):
        assert obsolete not in text


def test_spark_test_cluster_evidence_checklist_pins_readiness_audit() -> None:
    text = _normalized_doc_text()

    for required in (
        "scripts/audit_spark_compact_readiness.py",
        "scripts/spark_evidence_package_requirements.py",
        "accepted sample cases, synthetic rejection cases, required compact source contracts, diagnostic signal groups, redaction classes, sentinel tests, and boundary assertions",
        "is not an installed product CLI",
        "--require-supported-attention",
        "--require-min-inputs 2",
        "--require-source-contract spark_history_server_compact_v1",
        "--require-source-contract spark_history_eventlog_compact_v1",
        "--fail-on-source-warnings",
        "query-doctor-build-spark-evidence-package",
        "query-doctor-validate-spark-evidence-package",
        "query-doctor-export-spark-evidence-fixtures",
        "--partial-ok",
        "--summary-json",
        "--require-promotion-candidate",
        "machine-readable package readiness verdict",
        "compact_attention_ready diagnostic lane",
        "missing required diagnostic-lane readiness",
        "diagnostic-lane schema, readiness, source-granularity",
        "before writing",
        "without creating the output file",
        "deterministic safe filenames",
        "spark_fixture_export_manifest.json",
        "--fixture-export-manifest",
        "recomputes compact diagnosis diagnostic_lane evidence readiness",
        "missing or drifted lane fields fail before retained handoff use",
        "scripts/spark_one_application_handoff.py",
        "--compact-out",
        "--diagnosis-out",
        "--boundary-facts-out",
        "--application-attempt-id",
        "selector is used only for bounded request paths",
        "is not written into compact output, diagnosis output, boundary facts, or terminal text",
        "raw-free-spark-one-application-handoff-summary.json",
        "spark_one_application_handoff_summary_v1",
        "The summary path must differ from the compact, diagnosis, and boundary output paths.",
        "--product-surface-summary-out",
        "raw-free-spark-surface-boundary-summary-json",
        "spark_product_surface_boundary_audit_v1",
        "live_known_query_diagnosis=not_wired",
        "only Spark web POST surface",
        "The product-surface summary path must differ from the compact, diagnosis, boundary, and handoff summary output paths.",
        "scripts/build_spark_one_application_handoff_suite_manifest.py",
        "--compact-json",
        "--diagnosis-json",
        "--boundary-facts-json",
        "--handoff-summary-json",
        "--product-surface-summary-json",
        "handoff_summary_json",
        "product_surface_summary_json",
        "raw-free-spark-one-application-handoff-summary-a.json",
        "raw-free-spark-surface-boundary-summary-a-json",
        "status-ok, generated with the same strict readiness requirements",
        "spark_product_surface_boundary_audit_v1 artifact is raw-free and path-free",
        "recomputes the per-entry summary",
        "protected from summary overwrite",
        "spark_one_application_handoff_suite_v1",
        "--one-application-handoff-suite-manifest",
        "raw-free-spark-one-application-suite-summary.json",
        "spark_compact_readiness_summary_v1",
        "The summary path must differ from the manifest and every listed compact, diagnosis, boundary, handoff-summary, or product-surface summary artifact.",
        "scripts/build_spark_evidence_package_from_one_application_suite.py",
        "--sample-case",
        "one explicit package sample case per manifest entry",
        "re-runs the one-application suite audit",
        "requires History Server compact source contracts",
        "rejects diagnosis/boundary drift",
        "rejects SQL-specific sample-case labels unless the compact payload has accepted exact_query SQL execution evidence",
        "SQL-specific sample-case labels require accepted exact_query SQL execution evidence and cannot be claimed from same_application application-level handoffs",
        "compact/diagnosis/boundary triples",
        "scripts/audit_spark_evidence_handoff.py",
        "scripts/build_spark_handoff_suite_manifest.py",
        "--handoff-suite-manifest",
        "spark_evidence_handoff_suite_v1",
        "retained raw-free handoff summaries",
        "--require-source-granularity",
        "--require-verification-scope",
        "raw-free-spark-support-boundary-summary-json",
        "spark_support_boundary_audit_v1",
        "boundary labels, check statuses, safe counts",
        "temporary directory",
        "temporary export",
        "machine-readable handoff readiness summary",
        "diagnostic-lane checked/readiness/source-granularity",
        "required compact_attention_ready readiness counter",
        "accepted diagnostic-lane source-granularity counters",
        "selected source-granularity and verification-scope requirements",
        "missing requested labels as path-free readiness gaps",
        "keep fact-state counters available",
        "The summary path must differ from the package input.",
        "source-contract alignment",
        "required diagnostic signal groups",
        "data movement, failure, runtime context, and adaptive plan context",
        "missing diagnostic signal groups",
        "manifest filenames",
        "compact filenames",
        "support-claim boundary",
        "fails before overwrite",
        "diagnosis-boundary or diagnostic-lane drift",
        "matching attention/source-warning and fact-state counters",
        "fixture_compact",
        "exact_sql_execution_compact",
        "--require-source-granularity and --require-verification-scope labels",
        "recorded in summary requirements",
        "missing requested labels fail as path-free readiness gaps",
        "deterministic compact payload",
        "root_cause=not_claimed",
        "no Spark job execution",
        "partial_evidence",
        "minimum_case_set_ready",
        "promotion_candidate",
        "missing sample cases",
        "safe blocker IDs",
        "must not echo compact input paths, raw filenames, raw payload values",
        "History Server URLs, request selectors, SQL, log content, or local output paths",
        "package output path",
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


def test_spark_architecture_spike_pins_isolated_page_diagnostic_lane() -> None:
    text = _normalized_path_text(SPARK_ARCHITECTURE_DOC)

    for required in (
        "isolated Spark compact page",
        "safe diagnostic-lane readiness",
        "source granularity",
        "verification scope",
        "supported-attention count",
        "source-warning count",
        "Details/trusted report output",
        "Spark support claim",
    ):
        assert required in text


def _normalized_doc_text() -> str:
    return _normalized_path_text(SPARK_EVIDENCE_CHECKLIST_DOC)


def _normalized_path_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("`", "")
    return " ".join(text.split())
