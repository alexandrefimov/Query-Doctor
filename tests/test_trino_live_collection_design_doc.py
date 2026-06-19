from pathlib import Path


TRINO_LIVE_COLLECTION_DOC = (
    Path(__file__).resolve().parents[1] / "docs" / "engines" / "trino-live-collection-design.md"
)


def test_trino_live_collection_design_stays_non_supporting_and_no_execution():
    text = _normalized_doc_text()

    for required in (
        "not a live-support announcement",
        "does not add a collector",
        "Trino support is limited to sanitized offline evidence package import, bounded local event-store import, bounded local query-detail import, and bounded local query-list aggregate import, plus bounded local statement-stats import, bounded local pruned QueryInfo import, bounded HTTP event archive import, bounded HTTP query-detail archive import, event-source contract checking, dry-run coordinator query-info target checking, metadata source-contract checking, bounded local metadata summary import, plus one-query pruned coordinator query-info probing, one-query pruned coordinator fact import, a dev-only package-to-boundary evidence handoff audit, a dev-only one-query handoff wrapper, a dev-only handoff-suite manifest builder, and handoff-suite readiness manifest gate over raw-free handoff artifacts, local compact diagnosis over already raw-free direct boundary JSON excluding local metadata summary boundaries or selected package sample boundaries, and the isolated local /trino/compact-diagnosis page over the same already raw-free inputs, plus the local web Trino Beta retained-list Recent lane over one bounded retained pruned coordinator query-list read plus selected pruned QueryInfo reads, and the local web Trino Beta One Query ID lane over one bounded pruned coordinator QueryInfo read, both with the same raw-free compact diagnosis",
        "Those beta lanes are not broader Trino live collection",
        "start from already-produced query evidence",
        "POST /v1/statement as a collector shortcut",
        "runs the SQL string in the request body",
        "Query Doctor-generated EXPLAIN ANALYZE",
        "Trino executes the statement",
        "no Details/trusted report output, optimizer behavior, Running workflow, metadata collection, query-history crawling, generated SQL, or production support claim",
        "The current public README beta claim is limited to local web retained-list Recent and One Query ID lanes",
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
        "safe trino_version_family source scope",
        "unsafe version-family values",
        "fail closed",
        "require the Trino compact readiness audit's --require-one-query-boundary gate",
        "Boundaries carrying query_list_* aggregate facts or trino_metadata_* aggregate summary facts must remain aggregate source-shape or metadata-coverage evidence, not one-query promotion evidence",
        "test-cluster evidence checklist",
        "trino-evidence-package-templates.md",
        "manifest, redaction_note, and samples",
        "already have fixture validators",
        "scripts/validate_trino_evidence_package.py",
        "scripts/audit_trino_evidence_handoff.py",
        "dev-only package-to-boundary readiness audit",
        "trino_evidence_handoff_summary_v1",
        "does not require supported attention or known parser coverage for every sample by default",
        "Retained package-level handoff-suite audits can require selected safe source-contract labels from retained package source summaries, plus selected diagnostic-lane source granularities and verification scopes from already retained summaries",
        "reject unsafe or duplicate handoff-summary references, output/input overlap, missing artifacts, drifted manifest schema/redaction/no-support metadata, and raw-like retained summary content",
        "suite summary records only fixed aggregate counts, diagnostic-lane counters, requirement flags, and safe issue categories rather than artifact paths or references",
        "synthetic_trino_event_listener_v1",
        "one_query_boundary",
        "aggregate_query_list",
        "comparable_one_query_rerun",
        "representative_query_selection",
        "source_contract_review",
        "scripts/audit_trino_product_surface_boundary.py",
        "dev-only gate for retained compact boundary/diagnosis artifacts",
        "live_known_query_diagnosis=one_query_pruned_query_info_beta",
        "trino_product_surface_boundary_audit_v1",
        "allowed Trino web registry remains limited to the compact preview page plus local Recent and One Query ID beta surfaces",
        "Trino CLI stays preview/dev-only",
        "consume the trino_one_query_handoff_suite_v1 manifest",
        "requiring every entry to include a compact diagnosis artifact",
        "scripts/audit_trino_support_gap_matrix.py",
        "registered Trino fact-family coverage",
        "neutral no_* gaps",
        "trino_support_gap_matrix_audit_v1 summary",
        "support-gap matrix updates plus a passing python3 scripts/audit_trino_support_gap_matrix.py --summary-json <raw-free-trino-support-gap-summary-json> run",
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
        "query-doctor-trino-metadata-source-contract-check",
        "query-doctor-trino-metadata-summary-import",
        "query-doctor-trino-coordinator-query-info-pruned-probe",
        "query-doctor-trino-coordinator-query-info-pruned-import",
        "scripts/trino_one_query_live_handoff.py",
        "dev-only wrapper for the same real-cluster handoff",
        "--product-surface-summary-out",
        "product-surface boundary audit over those retained artifacts",
        "trino_product_surface_boundary_audit_v1 raw-free summary without printing the summary path",
        "--handoff-summary-out",
        "trino_one_query_handoff_summary_v1",
        "optional matching retained trino_product_surface_boundary_audit_v1 summaries",
        "boundary/diagnosis/readiness-summary/handoff-summary/product-surface-summary refs must be unique",
        "scripts/build_trino_handoff_suite_manifest.py",
        "trino_one_query_handoff_suite_v1 manifest",
        "explicit redaction-review confirmation",
        "writes relative artifact references",
        "duplicate boundary, diagnosis, readiness-summary, handoff-summary, or product-surface-summary references",
        "allows one shared smoke summary across entries",
        "rejects any smoke summary artifact that overlaps a boundary, diagnosis, readiness-summary, handoff-summary, or product-surface summary artifact",
        "matching compact diagnosis artifact, an executed all-ok Kerberos/SPNEGO smoke summary, one matching readiness summary artifact, one matching handoff summary artifact, one-query granularity, accepted source version, supported parser coverage, safe Trino version-family coverage, at least one supported attention area",
        "statement count, safe error categories, planned/executed counters",
        "not_written redaction assertions",
        "dev-only/no-product-support limitations",
        "The suite gate prints only aggregate counts and safe issue categories",
        "require a minimum retained input count",
        "write a raw-free machine summary that records aggregate counts, issue categories, and requirement flags plus safe version-family counters without source-version values, paths, filenames, URLs, Query IDs, auth headers, raw QueryInfo, or raw version strings",
        "does not crawl query history, fetch additional queries, submit SQL, add browser/report output, or become production Query ID support",
        "not installed as a product CLI",
        "does not create a production Query ID workflow, Details/trusted-report surface, optimizer workflow, or support claim beyond the explicit local web Recent and One Query ID beta lanes",
        "query-doctor-diagnose-trino-compact",
        "--diagnosis-out",
        "For the single-boundary local query-detail, local query-list aggregate, local statement-stats, local pruned QueryInfo, HTTP query-detail archive, and pruned coordinator query-info import commands",
        "print, write, or render only safe summaries, raw-free boundary JSON, deterministic raw-free diagnosis JSON, or sanitized compact diagnosis HTML and do not add Details/trusted reports or broader Trino browser workflows",
        "The output path must differ from the input or source-contract path",
        "source type, safe auth-reference label, accepted event schema, bounds, and redaction/storage policy",
        "explicit relation/column allowlist shape with simple unquoted identifiers",
        "performs no metadata read, executes no metadata SQL",
        "The local metadata summary import command may read one explicit compact sanitized aggregate metadata summary JSON after an accepted metadata_allowlist source contract",
        "maps only relation/column coverage and stats-completeness counts to raw-free facts",
        "performs no network read, executes no metadata SQL, emits no object identifiers or metadata values",
        "does not become live metadata collection support",
        "rejects endpoint, topic, database, credential, raw SQL, raw event-record, and extra source config fields",
        "does not accept endpoint URLs, topic names, database names, hostnames, credential values, raw event records, or arbitrary source-specific configuration",
        "a passing event-source contract check for the source family before the reader can contact that source",
        "a passing metadata source-contract check before any metadata reader can use a Trino relation or column allowlist",
        "fetches one explicit operator HTTP(S) archive URL",
        "does not contact the Trino coordinator, discover archive endpoints, accept URL credentials, echo URLs, submit SQL",
        "accepts only an explicit http_query_detail_archive contract",
        "does not contact the Trino coordinator, fetch query-info by Query ID",
        "one bounded GET /v1/query/{queryId}?pruned=true read with an operator-managed auth reference",
        "one optional local --auth-header-file containing an operator-managed Authorization header line",
        "must not print or write the auth header path or value",
        "--require-source-version trino_coordinator_query_info_target_v1",
        "--require-min-trino-version-families 1",
        "--diagnosis-json <raw-free-trino-diagnosis.json>",
        "boundary source contract, safe version-family evidence, and stored diagnosis artifact are checked",
        "--smoke-summary <trino_smoke_summary.json> --require-executed-smoke",
        "dry-run smoke plans cannot satisfy executed test-cluster evidence",
        "--query-id-file <operator-query-id-file>",
        "Finished QueryInfo may be evicted from the coordinator before older QueryMonitor timeline entries age out",
        "HTTP 404 or 410",
        "redacted stale-QueryInfo hint",
        "HTTP 401 or 403",
        "auth-rejected hint",
        "The probe response may only be checked as a bounded JSON object and does not map facts",
        "for the implemented pruned import, the same source contract may allow one bounded GET /v1/query/{queryId}?pruned=true read with an operator-managed auth reference and map only allowlisted lifecycle and queryStats fields to a raw-free boundary payload",
        "for the implemented local pruned QueryInfo import, the same source contract may allow one local compact sanitized QueryInfo file with no network read and map only allowlisted lifecycle and queryStats fields to a raw-free boundary payload",
        "optional local auth-header file",
        "The local pruned QueryInfo import is a compact file import using the same source contract and performs no network read.",
        "It accepts only state and allowlisted queryStats fields and rejects raw QueryInfo fields before mapping.",
        "The compact diagnosis command and isolated local compact-diagnosis page consume only one already raw-free engine_fact_boundary_v1 payload or selected package sample boundary from an accepted Trino import path, excluding local metadata summary boundaries",
        "metadata-coverage evidence, not compact diagnosis inputs",
        "keeps the fetched QueryInfo outside normalized facts and outputs",
        "one explicit already-sanitized compact JSON object with redaction-review confirmation and file/payload/depth bounds",
        "one explicit already-sanitized compact JSON object with only top-level state and allowlisted queryStats fields",
        "one compact aggregate summary after that source contract",
        "rejects raw metadata storage, identifier output, raw SQL fields, object identifiers, metadata values, and arbitrary summary detail before mapping facts",
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
        "a strict one-query readiness gate that rejects aggregate query_list_* and trino_metadata_* boundaries before any Trino query-detail or Query ID support promotion, and can require safe Trino version-family breadth plus matching retained readiness-summary and handoff-summary artifacts for real-cluster handoff suites",
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
