from pathlib import Path


TRINO_LIVE_COLLECTION_DOC = (
    Path(__file__).resolve().parents[1] / "docs" / "engines" / "trino-live-collection-design.md"
)


def test_trino_live_collection_design_stays_non_supporting_and_no_execution():
    text = _normalized_doc_text()

    for required in (
        "not a support announcement",
        "does not add a collector",
        "Query Doctor remains Apache Impala only",
        "start from already-produced query evidence",
        "POST /v1/statement as a collector shortcut",
        "runs the SQL string in the request body",
        "Query Doctor-generated EXPLAIN ANALYZE",
        "Trino executes the statement",
        "no browser route, report output, optimizer behavior, or public README support claim",
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
        "rejects oversized payloads and unsafe raw event fields",
        "reject unsafe raw event fields and unsafe raw text values before mapping",
        "read-only permissions required by the operator",
        "accepted Trino versions and source schema versions",
        "fail closed",
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
        "unsafe raw fields rejected by redaction tests",
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


def _normalized_doc_text() -> str:
    text = TRINO_LIVE_COLLECTION_DOC.read_text(encoding="utf-8").replace("`", "")
    return " ".join(text.split())
