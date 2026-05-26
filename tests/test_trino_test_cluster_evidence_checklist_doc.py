from pathlib import Path


TRINO_EVIDENCE_CHECKLIST_DOC = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "engines"
    / "trino-test-cluster-evidence-checklist.md"
)
DOCS_INDEX = Path(__file__).resolve().parents[1] / "docs" / "README.md"


def test_trino_test_cluster_evidence_checklist_stays_non_supporting():
    text = _normalized_doc_text()

    for required in (
        "not a live collector",
        "support announcement",
        "engine selector",
        "browser/report surface",
        "permission to execute Trino SQL",
        "Do not run SQL through Query Doctor.",
        "Do not use POST /v1/statement as a collection path.",
        "Do not run Query Doctor-generated EXPLAIN ANALYZE.",
        "no raw companion archive",
        "A live reader comes later",
    ):
        assert required in text


def test_trino_test_cluster_evidence_checklist_requires_sanitized_operator_exports():
    text = _normalized_doc_text()

    for required in (
        "operator-exported, sanitized evidence",
        "already-produced Trino evidence",
        "completed event-listener records",
        "statement-statistics snippets",
        "sanitized /v1/query list summary exports only as aggregate contract probes",
        "query-detail exports only after raw identifiers",
        "manifest that describes source type, Trino version, source schema version",
        "redaction note describing removed field classes, not removed values",
        "trino-evidence-package-templates.md",
        "Keep package labels local and safe",
        "scripts/validate_trino_evidence_package.py",
        "scripts/build_trino_evidence_package.py",
        "requires explicit redaction-review and sentinel-test confirmations",
        "writes output only after validation accepts the package",
        "must not echo raw payloads, raw values, or the input path",
        "Keep raw exports outside the repository and outside prompts.",
    ):
        assert required in text


def test_trino_test_cluster_evidence_checklist_pins_minimum_case_set_and_redaction():
    text = _normalized_doc_text()

    for required in (
        "successful completed query",
        "failed query with only an allowlisted failure category",
        "queued or resource-group delayed query",
        "blocked query",
        "spill observed",
        "stage or task skew candidate",
        "connector metric present",
        "connector metric absent",
        "missing-field case",
        "unknown or unsupported source-contract version case",
        "sanitized query-list contract probe aggregate",
        "oversized or over-deep payload rejection case using synthetic padding only",
        "unsafe raw field rejection case using synthetic sentinel values only",
        "remove raw SQL and prepared statements",
        "remove query IDs, trace tokens, transaction IDs, session IDs, and request headers",
        "remove catalog, schema, table, column, partition, manifest, and object names",
        "remove stack traces, raw exception messages, warning payloads, and connector internals",
    ):
        assert required in text


def test_trino_test_cluster_evidence_checklist_is_indexed():
    text = DOCS_INDEX.read_text(encoding="utf-8")

    assert "engines/trino-test-cluster-evidence-checklist.md" in text
    assert "engines/i18n/ru/trino-test-cluster-evidence-checklist.md" in text


def _normalized_doc_text() -> str:
    text = TRINO_EVIDENCE_CHECKLIST_DOC.read_text(encoding="utf-8").replace("`", "")
    return " ".join(text.split())
