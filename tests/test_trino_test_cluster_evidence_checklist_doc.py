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
        "Details/trusted-report surface",
        "separate isolated compact-diagnosis page accepts only already raw-free direct boundary JSON excluding local metadata summary boundaries or one selected sample boundary from a package boundary export",
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
        "compact query-detail exports only after raw identifiers",
        "metadata allowlist source-contract summaries only after",
        "query-doctor-trino-metadata-source-contract-check --redaction-reviewed",
        "keep the raw relation/column allowlist local",
        "path-free, identifier-free summary",
        "compact metadata summary exports only as aggregate relation/column coverage and stats-completeness counts",
        "query-doctor-trino-metadata-summary-import --redaction-reviewed",
        "--query-id-file <operator-query-id-file>",
        "Finished QueryInfo can disappear from the coordinator before QueryMonitor logs age out",
        "HTTP 404 or 410",
        "redacted operator hint",
        "HTTP 401 or 403",
        "auth rejected",
        "--require-min-trino-version-families <minimum-trino-version-family-count>",
        "--require-trino-version-family <safe-trino-version-family>",
        "safe broad-label counters",
        "manifest that describes source type, Trino version, source schema version",
        "redaction note describing removed field classes, not removed values",
        "optional metadata source-contract summary output",
        "never the raw allowlist contract with relation or column names",
        "optional compact metadata summary import output",
        "never raw metadata values or object identifiers",
        "trino-evidence-package-templates.md",
        "Keep package labels local and safe",
        "scripts/validate_trino_evidence_package.py",
        "scripts/build_trino_evidence_package.py",
        "requires explicit redaction-review and sentinel-test confirmations",
        "writes output only after validation accepts the package",
        "must not echo raw payloads, raw values, or the input path",
        "The suite path reopens only retained raw-free summaries, not packages or raw exports.",
        "reject output/input overlap, missing or duplicate summary artifacts, unsafe references, drifted manifest schema/redaction/no-support metadata, and raw-like retained summary content",
        "suite summary remains aggregate-only machine evidence with fixed count, diagnostic-lane, issue-category, and requirement sections, not artifact references or paths",
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
        "compact query-detail stage/task summary case",
        "oversized or over-deep payload rejection case using synthetic padding only",
        "unsafe raw field rejection case using synthetic sentinel values only",
        "remove raw SQL and prepared statements",
        "remove query IDs, trace tokens, transaction IDs, session IDs, and request headers",
        "remove catalog, schema, table, column, partition, manifest, and object names",
        "remove stack traces, raw exception messages, warning payloads, and connector internals",
        "fullyBlocked and resource queued must be booleans",
        "--require-readiness-summary-json",
        "--require-handoff-summary-json",
        "per-entry readiness summary and one-query handoff summary JSON artifacts",
    ):
        assert required in text


def test_trino_test_cluster_evidence_checklist_is_indexed():
    text = DOCS_INDEX.read_text(encoding="utf-8")

    assert "engines/trino-test-cluster-evidence-checklist.md" in text
    assert "engines/i18n/ru/trino-test-cluster-evidence-checklist.md" in text


def _normalized_doc_text() -> str:
    text = TRINO_EVIDENCE_CHECKLIST_DOC.read_text(encoding="utf-8").replace("`", "")
    return " ".join(text.split())
