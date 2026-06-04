from pathlib import Path


TRINO_LIVE_COLLECTION_DOC = (
    Path(__file__).resolve().parents[1] / "docs" / "engines" / "trino-live-collection-design.md"
)


def test_trino_live_collection_design_stays_non_supporting_and_no_execution():
    text = _normalized_doc_text()

    for required in (
        "not a live-support announcement",
        "does not add a collector",
        "Trino support is limited to sanitized offline evidence package import, bounded local event-store import, bounded local query-detail import, and bounded local query-list aggregate import, plus bounded local statement-stats import, bounded local pruned QueryInfo import, bounded HTTP event archive import, bounded HTTP query-detail archive import, event-source contract checking, and dry-run coordinator query-info target checking, plus one-query pruned coordinator query-info probing, one-query pruned coordinator fact import, a dev-only one-query handoff wrapper, a dev-only handoff-suite manifest builder, and handoff-suite readiness manifest gate over raw-free handoff artifacts, local compact diagnosis over already raw-free direct boundary JSON or selected package sample boundaries, and the isolated local /trino/compact-diagnosis page over the same already raw-free inputs",
        "start from already-produced query evidence",
        "POST /v1/statement as a collector shortcut",
        "runs the SQL string in the request body",
        "Query Doctor-generated EXPLAIN ANALYZE",
        "Trino executes the statement",
        "no Details/trusted report output, optimizer behavior, live Recent or Query ID workflow, or public README support claim",
        "The first real-cluster handoff remains sanitized package work before any broader Trino coordinator reader.",
    ):
        assert required in text


def test_trino_live_collection_design_defines_source_phases_and_bounds():
    text = _normalized_doc_text()

    for required in (
        "Phase A: Offline Fixture Import",
        "Phase B: Local Event-Store Reader",
        "Phase C: Bounded Query-Detail Import",
        "query-doctor-trino-event-store-import",
        "one explicit already-sanitized local JSON object, JSON array, or NDJSON file",
        "requires redaction-review confirmation",
        "file, record, byte, and depth limits",
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
        "require the Trino compact readiness audit's --require-one-query-boundary gate",
        "Boundaries carrying query_list_* aggregate facts must remain aggregate source-shape evidence, not one-query promotion evidence",
        "test-cluster evidence checklist",
        "trino-evidence-package-templates.md",
        "manifest, redaction_note, and samples",
        "already have fixture validators",
        "scripts/validate_trino_evidence_package.py",
        "query-doctor-trino-import",
        "query-doctor-trino-event-store-import",
        "query-doctor-trino-query-detail-import",
        "query-doctor-trino-query-list-import",
        "query-doctor-trino-statement-stats-import",
        "query-doctor-trino-query-info-pruned-import",
        "query-doctor-trino-event-source-contract-check",
        "query-doctor-trino-http-event-archive-import",
        "query-doctor-trino-http-query-detail-archive-import",
        "query-doctor-trino-coordinator-query-info-target-check",
        "query-doctor-trino-coordinator-query-info-pruned-probe",
        "query-doctor-trino-coordinator-query-info-pruned-import",
        "scripts/trino_one_query_live_handoff.py",
        "dev-only wrapper for the same real-cluster handoff",
        "scripts/build_trino_handoff_suite_manifest.py",
        "trino_one_query_handoff_suite_v1 manifest",
        "explicit redaction-review confirmation",
        "writes relative artifact references",
        "matching compact diagnosis artifact, an executed all-ok Kerberos/SPNEGO smoke summary, one-query granularity, accepted source version, supported parser coverage, and at least one supported attention area",
        "The suite gate prints only aggregate counts and safe issue categories",
        "require a minimum retained input count",
        "write a raw-free machine summary that records aggregate counts, issue categories, and requirement flags without source-version values, paths, filenames, URLs, Query IDs, auth headers, or raw QueryInfo",
        "does not crawl query history, fetch additional queries, submit SQL, add browser/report output, or become live Query ID diagnosis",
        "not installed as a product CLI",
        "does not create a live Query ID workflow, Details/trusted-report surface, optimizer workflow, or support claim",
        "query-doctor-diagnose-trino-compact",
        "--diagnosis-out",
        "For the single-boundary local query-detail, local query-list aggregate, local statement-stats, local pruned QueryInfo, HTTP query-detail archive, and pruned coordinator query-info import commands",
        "print, write, or render only safe summaries, raw-free boundary JSON, deterministic raw-free diagnosis JSON, or sanitized compact diagnosis HTML and do not add Details/trusted reports or broader Trino browser workflows",
        "The output path must differ from the input or source-contract path",
        "source type, safe auth-reference label, accepted event schema, bounds, and redaction/storage policy",
        "rejects endpoint, topic, database, credential, raw SQL, raw event-record, and extra source config fields",
        "does not accept endpoint URLs, topic names, database names, hostnames, credential values, raw event records, or arbitrary source-specific configuration",
        "a passing event-source contract check for the source family before the reader can contact that source",
        "fetches one explicit operator HTTP(S) archive URL",
        "does not contact the Trino coordinator, discover archive endpoints, accept URL credentials, echo URLs, submit SQL",
        "accepts only an explicit http_query_detail_archive contract",
        "does not contact the Trino coordinator, fetch query-info by Query ID",
        "one bounded GET /v1/query/{queryId}?pruned=true read with an operator-managed auth reference",
        "one optional local --auth-header-file containing an operator-managed Authorization header line",
        "must not print or write the auth header path or value",
        "--require-source-version trino_coordinator_query_info_target_v1",
        "--diagnosis-json <raw-free-trino-diagnosis.json>",
        "boundary source contract and stored diagnosis artifact are checked",
        "--smoke-summary <trino_smoke_summary.json> --require-executed-smoke",
        "dry-run smoke plans cannot satisfy executed test-cluster evidence",
        "The probe response may only be checked as a bounded JSON object and does not map facts",
        "for the implemented pruned import, the same source contract may allow one bounded GET /v1/query/{queryId}?pruned=true read with an operator-managed auth reference and map only allowlisted lifecycle and queryStats fields to a raw-free boundary payload",
        "for the implemented local pruned QueryInfo import, the same source contract may allow one local compact sanitized QueryInfo file with no network read and map only allowlisted lifecycle and queryStats fields to a raw-free boundary payload",
        "optional local auth-header file",
        "The local pruned QueryInfo import is a compact file import using the same source contract and performs no network read.",
        "It accepts only state and allowlisted queryStats fields and rejects raw QueryInfo fields before mapping.",
        "The compact diagnosis command and isolated local compact-diagnosis page consume only one already raw-free engine_fact_boundary_v1 payload or selected package sample boundary",
        "keeps the fetched QueryInfo outside normalized facts and outputs",
        "one explicit already-sanitized compact JSON object with redaction-review confirmation and file/payload/depth bounds",
        "one explicit already-sanitized compact JSON object with only top-level state and allowlisted queryStats fields",
        "one explicit operator-controlled HTTP(S) archive URL after an accepted http_query_detail_archive source contract",
        "It is aggregate-only and does not crawl Trino, fetch query-detail payloads, diagnose one selected query, submit SQL",
        "does not call /v1/statement",
        "non-boolean queued markers stay unknown",
        "those counts must be non-negative integers",
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
        "compact query-detail stage/task summary case",
        "unsafe raw fields rejected by redaction tests",
        "a strict one-query readiness gate that rejects aggregate query_list_* boundaries before any Trino query-detail or Query ID support promotion",
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
