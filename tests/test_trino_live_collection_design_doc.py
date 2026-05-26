from pathlib import Path


TRINO_LIVE_COLLECTION_DOC = (
    Path(__file__).resolve().parents[1] / "docs" / "engines" / "trino-live-collection-design.md"
)


def test_trino_live_collection_design_stays_non_supporting_and_no_execution():
    text = _normalized_doc_text()

    for required in (
        "not a support announcement",
        "does not add a collector",
        "Query Doctor production engine support remains Apache Impala only",
        "start from already-produced query evidence",
        "POST /v1/statement as a collector shortcut",
        "runs the SQL string in the request body",
        "Query Doctor-generated EXPLAIN ANALYZE",
        "Trino executes the statement",
        "no browser route, report output, optimizer behavior, or public README support claim",
        "The first real-cluster handoff is sanitized fixture work, not a direct reader.",
    ):
        assert required in text


def test_trino_live_collection_design_defines_source_phases_and_bounds():
    text = _normalized_doc_text()

    for required in (
        "Phase A: Offline Fixture Import",
        "Phase B: Local Event-Store Reader",
        "Phase C: Bounded Query-Detail Import",
        "explicit configuration for source type, time window, max records, max bytes",
        "no default network discovery",
        "no mutation, offsets commits, topic creation, table writes, or retention changes",
        "rejects oversized statement-statistics and event-listener payloads",
        "unsafe raw field names and text values",
        "sanitized /v1/query aggregate list-shape evidence",
        "does not fetch query-detail payloads and does not submit SQL statements",
        "reject unsafe raw fixture field names and unsafe raw text values before mapping",
        "read-only permissions required by the operator",
        "accepted Trino versions and source schema versions",
        "fail closed",
        "test-cluster evidence checklist",
        "trino-evidence-package-templates.md",
        "manifest, redaction_note, and samples",
        "already have fixture validators",
        "scripts/validate_trino_evidence_package.py",
        "prints only a safe summary and does not add live collection",
    ):
        assert required in text


def test_trino_live_collection_design_requires_raw_free_boundary_and_fixtures():
    text = _normalized_doc_text()

    for required in (
        "raw SQL and prepared statements",
        "query IDs, trace tokens, transaction IDs, session IDs, and request headers",
        "catalog, schema, table, column, partition, manifest, and object names",
        "stack traces, raw exception messages, warning payloads, and connector internals",
        "engine_fact_boundary_payload()",
        "Required Fixtures Before Code",
        "successful completed query",
        "failed query with redacted failure category",
        "queued/resource-group delayed query",
        "oversized payload rejection",
        "sanitized query-list contract probe aggregate",
        "unsafe raw fields rejected by redaction tests",
        "first operator-exported test-cluster handoff",
    ):
        assert required in text


def test_trino_live_collection_design_links_primary_trino_docs():
    text = TRINO_LIVE_COLLECTION_DOC.read_text(encoding="utf-8")

    for link in (
        "https://trino.io/docs/current/develop/event-listener.html",
        "https://trino.io/docs/current/admin/event-listeners-kafka.html",
        "https://trino.io/docs/current/develop/client-protocol.html",
        "https://trino.io/docs/current/client/client-protocol.html",
        "https://trino.io/docs/current/sql/explain-analyze.html",
    ):
        assert link in text
    assert "trino-test-cluster-evidence-checklist.md" in text
    assert "trino-evidence-package-templates.md" in text


def _normalized_doc_text() -> str:
    text = TRINO_LIVE_COLLECTION_DOC.read_text(encoding="utf-8").replace("`", "")
    return " ".join(text.split())
