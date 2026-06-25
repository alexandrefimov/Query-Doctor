from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TRINO_PRIVATE_PREVIEW_DOC = REPO_ROOT / "docs" / "engines" / "trino-private-preview-release.md"
DOCS_INDEX = REPO_ROOT / "docs" / "README.md"
RU_DOCS_INDEX = REPO_ROOT / "docs" / "i18n" / "ru" / "README.md"
README = REPO_ROOT / "README.md"
README_RU = REPO_ROOT / "README.ru.md"
RELEASE_CHECKLIST = REPO_ROOT / "docs" / "release-checklist.md"
PUBLIC_READINESS = REPO_ROOT / "docs" / "public-release-readiness.md"
TRINO_LIVE_COLLECTION_DOC = REPO_ROOT / "docs" / "engines" / "trino-live-collection-design.md"
TRINO_EVIDENCE_CHECKLIST_DOC = (
    REPO_ROOT / "docs" / "engines" / "trino-test-cluster-evidence-checklist.md"
)


def test_trino_private_preview_release_path_stays_live_non_supporting():
    text = _normalized_doc_text(TRINO_PRIVATE_PREVIEW_DOC)

    for required in (
        "bounded local Trino production claim and retained private-preview evidence",
        "not a broad live collector",
        "not a broad production engine selector",
        "not an LLM report surface",
        "not an optimizer workflow",
        "not permission to execute user SQL through Query Doctor",
        "The Trino browser surfaces are the isolated local compact-diagnosis page for already raw-free direct boundary JSON excluding local metadata summary boundaries or a selected sample boundary from a package boundary export, plus the local production web Trino retained-list Recent lane over one bounded retained pruned coordinator query-list read and selected pruned QueryInfo reads, plus the local production web Trino One Query ID lane over one bounded pruned coordinator QueryInfo read, both with the same raw-free compact diagnosis, plus raw-free materialized Details and deterministic Python Report plus optimizer guidance after server-owned case materialization.",
        "Trino support is limited to sanitized offline evidence package import, bounded local event-store import, bounded HTTP event archive import, bounded HTTP query-detail archive import, bounded local query-detail import, and bounded local query-list aggregate import, bounded local statement-stats import, bounded local pruned QueryInfo import, event-source contract checking, dry-run coordinator query-info target checking, metadata source-contract checking, bounded local metadata CLI summary building, bounded local metadata summary import, dev-only metadata CLI summary smoke round-trip, one-query pruned coordinator query-info probing/import, dev-only package-to-boundary evidence handoff audit, dev-only product-surface boundary audit over retained raw-free compact artifacts, dev-only one-query handoff and handoff-suite readiness over raw-free handoff artifacts, dev-only support-gap audit coverage for source-type registry and engine fact promotion policy, and local compact diagnosis over raw-free direct boundary JSON excluding local metadata summary boundaries or selected package sample boundaries, and the isolated local /trino/compact-diagnosis page over the same already raw-free inputs, plus the local production web Trino retained-list Recent lane over one bounded retained pruned coordinator query-list read and selected pruned QueryInfo reads, plus the local production web Trino One Query ID lane over one bounded pruned coordinator QueryInfo read, both with the same raw-free compact diagnosis, raw-free materialized Details, deterministic Python Report, and optimizer guidance.",
        "A separate event-source contract check remains the source gate for event archive readers, the coordinator query-info target check remains a dry-run gate, and the pruned coordinator query-info probe remains probe-only; the metadata source-contract check is only a dry-run relation/column allowlist gate; the metadata CLI summary builder can use one accepted allowlist and an operator-installed Trino CLI to produce only aggregate coverage counts; the local metadata summary import maps only aggregate coverage counts from an operator-prepared sanitized file; the dev-only metadata CLI smoke wrapper can verify dry-run, aggregate collection, and importer round-trip while writing only raw-free summaries; the pruned query-info import maps only allowlisted facts and can feed only the explicit local production Trino Recent/One Query ID lanes or raw-free local artifacts.",
        "Compact diagnosis consumes only already raw-free direct boundary JSON excluding local metadata summary boundaries or a selected sample boundary from a package export, and the isolated page plus local production Recent/One Query ID lanes render only sanitized diagnosis fields, with materialized Details, deterministic Python Report, and optimizer guidance available only from server-owned raw-free cases; all remain outside LLM reports, Query Optimizer jobs, Running scans, product metadata collection, query-history crawling, user SQL execution, and broader/shared Query ID support.",
        "trino-beta-ui-readiness.md",
        "local UI beta show-readiness gate",
        "broader/shared product workflows outside those lanes still treat Trino as unsupported",
    ):
        assert required in text


def test_trino_private_preview_release_path_defines_demo_storyline():
    text = _normalized_doc_text(TRINO_PRIVATE_PREVIEW_DOC)

    for required in (
        "python3 scripts/demo_trino_evidence_package.py",
        "python3 scripts/trino_kerberos_smoke.py",
        "--server https://<test-trino-endpoint>",
        "--service-name HTTP",
        "built-in allowlisted read-only statement shapes",
        "bounded Trino protocol pages",
        "must not be wired into Query Doctor product workflows",
        "python3 scripts/build_trino_evidence_package.py",
        "python3 scripts/validate_trino_evidence_package.py <sanitized-package.json>",
        "python3 scripts/audit_trino_evidence_handoff.py <sanitized-package.json> --summary-json <raw-free-trino-package-handoff-summary.json>",
        "trino_evidence_handoff_summary_v1",
        "converts accepted samples to raw-free boundary payloads in memory",
        "does not require supported attention or known parser coverage for every sample by default",
        "Retained handoff-suite audits require diagnostic-lane source, readiness, verification, and fact-state counters and reject source-granularity or fact-state counter drift between diagnostic_lane and the top-level retained summary counters.",
        "Strict retained suites can also require selected safe source-contract labels, such as synthetic_trino_event_listener_v1, from retained package source summaries, plus selected source-granularity labels such as one_query_boundary or aggregate_query_list, and selected verification-scope labels, such as comparable_one_query_rerun, representative_query_selection, or source_contract_review, from already retained diagnostic-lane counters without reopening packages.",
        "They also reject duplicate retained handoff-summary artifact references, including path aliases, so suite-width counts cannot reuse one summary.",
        "query-doctor-trino-import --format boundary-json <sanitized-package.json>",
        "query-doctor-trino-event-store-import",
        "query-doctor-trino-query-detail-import",
        "query-doctor-trino-query-list-import",
        "query-doctor-trino-statement-stats-import",
        "query-doctor-trino-query-info-pruned-import",
        "query-doctor-trino-event-source-contract-check",
        "query-doctor-trino-coordinator-query-info-target-check",
        "query-doctor-trino-metadata-source-contract-check",
        "query-doctor-trino-metadata-cli-summary",
        "python3 scripts/trino_metadata_cli_summary_smoke.py",
        "trino_metadata_cli_summary_smoke_v1",
        "query-doctor-trino-metadata-summary-import",
        "query-doctor-trino-coordinator-query-info-pruned-probe",
        "query-doctor-trino-coordinator-query-info-pruned-import",
        "python3 scripts/trino_one_query_live_handoff.py",
        "python3 scripts/build_trino_handoff_suite_manifest.py",
        "trino_one_query_handoff_suite_v1 manifest",
        "--boundary-json <raw-free-trino-boundary-1.json>",
        "--readiness-summary-json <raw-free-trino-readiness-summary-1.json>",
        "--handoff-summary-json <raw-free-trino-one-query-handoff-summary-json>",
        "--product-surface-summary-json <raw-free-trino-product-surface-summary-json>",
        "--out <trino-one-query-handoff-suite.json>",
        "--handoff-suite-manifest <trino-one-query-handoff-suite.json>",
        "--require-diagnosis-json",
        "--require-readiness-summary-json",
        "--require-handoff-summary-json",
        "--fail-on-unknown-parser-coverage",
        "--require-min-inputs <minimum-retained-query-count>",
        "--require-min-trino-version-families <minimum-trino-version-family-count>",
        "--require-trino-version-family <safe-trino-version-family>",
        "--summary-json <raw-free-trino-suite-summary.json>",
        "duplicate boundary/diagnosis/readiness-summary/handoff-summary/product-surface-summary references including path aliases",
        "allows one shared smoke summary across entries",
        "rejects any smoke summary artifact that overlaps a boundary, diagnosis, readiness-summary, handoff-summary, or product-surface summary artifact",
        "statement-count/check-count consistency",
        "known safe error categories",
        "internally consistent planned/executed counters",
        "explicit not_written redaction assertions",
        "dev-only/no-product-support limitations",
        "one product-surface summary per boundary",
        "trino_one_query_handoff_summary_v1",
        "structured diagnostic_lane block for source granularity, evidence readiness, verification scope, and fact-state counters",
        "validates their structured diagnostic_lane blocks and rejects missing or drifted source-granularity, readiness, verification-scope, or fact-state counters",
        "The manifest is local handoff metadata, not a committed artifact.",
        "The builder is not an installed product CLI.",
        "relative artifact references",
        "prints only aggregate counts and safe issue categories",
        "trino_compact_readiness_summary_v1 JSON",
        "source-version requirements only as counts and boolean flags and records Trino version-family coverage only as safe broad-label counters",
        "query-doctor-diagnose-trino-compact",
        "sample_fact_boundaries",
        "--sample-index <zero-based-index>",
        "/trino/compact-diagnosis",
        "--boundary-out <raw-free-trino-boundary.json>",
        "--diagnosis-out <raw-free-trino-diagnosis.json>",
        "--product-surface-summary-out <raw-free-trino-product-surface-summary-json>",
        "--auth-header-file <operator-auth-header-file>",
        "query-doctor-trino-http-event-archive-import",
        "query-doctor-trino-http-query-detail-archive-import",
        "--redaction-reviewed",
        "<sanitized-event-store.json-or-ndjson>",
        "<sanitized-query-detail.json>",
        "<sanitized-query-list-aggregate.json>",
        "<sanitized-statement-stats.json>",
        "<sanitized-pruned-query-info.json>",
        "<sanitized-event-source-contract.json>",
        "<sanitized-query-detail-archive-contract.json>",
        "<sanitized-query-info-target-contract.json>",
        "<sanitized-metadata-source-contract.json>",
        "<operator-trino-cli>",
        "<sanitized-metadata-summary.json>",
        "https://<operator-event-archive>",
        "https://<operator-query-detail-archive>",
        "https://<trino-coordinator>",
        "operator-exported, already-sanitized compact samples only",
        "source type, safe auth-reference label, accepted event schema, bounds, and redaction/storage policy",
        "explicit relation/column allowlist shape, bounds, and redaction policy",
        "requires an accepted http_event_listener_archive source contract",
        "requires an accepted http_query_detail_archive source contract",
        "does not contact the Trino coordinator, discover endpoints, echo URLs, accept URL credentials, submit SQL",
        "does not contact the Trino coordinator, fetch query-info by Query ID",
        "does not contact Trino, issue /v1/query, fetch query-info JSON",
        "safe trino_version_family",
        "does not contact Trino, read metadata, execute metadata SQL",
        "passes statement text on stdin instead of argv",
        "safe dry-run plan, aggregate metadata collection, and local metadata-summary import round-trip",
        "The release-readiness bundle can run the same optional gate with its --metadata-smoke-* flags only after --metadata-smoke-redaction-reviewed",
        "does not turn metadata CLI output into product metadata collection",
        "not an installed product CLI",
        "relation/column coverage and stats-completeness counts only",
        "without metadata reads, metadata SQL, object identifiers, metadata values, or compact diagnosis output",
        "GET /v1/query/{queryId}?pruned=true",
        "performs no network read, maps only allowlisted state and queryStats fields into raw-free boundary JSON",
        "rejects raw QueryInfo fields such as Query IDs, query text, session fields, endpoint URLs, object names, and stage/task detail",
        "operator-managed Authorization header line",
        "auth header path/value",
        "submit SQL, run live Recent scans, collect standalone production Query ID support, or add materialized Details, Python Report, or optimizer guidance by itself",
        "maps only allowlisted lifecycle and queryStats fields into raw-free boundary JSON",
        "scripts/audit_trino_compact_readiness.py <raw-free-trino-boundary.json> --require-one-query-boundary",
        "python3 scripts/audit_trino_product_surface_boundary.py <raw-free-trino-boundary.json> --diagnosis-json <raw-free-trino-diagnosis.json> --summary-json <raw-free-trino-product-surface-summary-json>",
        "every boundary/diagnosis entry in the handoff-suite manifest",
        "Manifest mode requires every entry to reference a compact diagnosis artifact",
        "validates retained per-entry product-surface summaries when present",
        "product-surface summary output must differ from the manifest and every referenced boundary, diagnosis, smoke-summary, readiness-summary, handoff-summary, or product-surface-summary artifact",
        "trino_product_surface_boundary_audit_v1",
        "python3 scripts/audit_trino_support_gap_matrix.py --summary-json <raw-free-trino-support-gap-summary-json>",
        "trino_support_gap_matrix_audit_v1",
        "registered Trino fact families, neutral no_* gaps, blocked product adapter flags",
        "live_known_query_diagnosis=one_query_pruned_query_info_local_production",
        "allowed Trino web registry is still limited to compact preview surfaces plus the local production Recent and One Query ID surfaces",
        "Trino CLI stays preview/dev-only",
        "--require-source-version trino_coordinator_query_info_target_v1",
        "--diagnosis-json <raw-free-trino-diagnosis.json>",
        "wrapper is not an installed product CLI",
        "strict --require-one-query-boundary, --require-source-version trino_coordinator_query_info_target_v1, and --diagnosis-json <raw-free-trino-diagnosis.json> readiness checks",
        "source contract and stored compact diagnosis artifact are checked",
        "--handoff-summary-out <raw-free-trino-one-query-handoff-summary-json>",
        "--smoke-summary <trino_smoke_summary.json> --require-executed-smoke",
        "product-surface boundary audit over the written boundary/diagnosis artifacts",
        "dry-run plan cannot count as an executed test-cluster smoke",
        "output boundary path",
        "It does not crawl query history, submit SQL, collect standalone production Query ID support, or add browser/report output.",
        "reads one already raw-free engine_fact_boundary_v1 payload",
        "Single-boundary local query-detail, local query-list aggregate, local statement-stats, local pruned QueryInfo, HTTP query-detail archive, and pruned coordinator query-info import commands",
        "does not ingest raw Trino payloads, copy input summaries or string metric values, claim root causes",
        "must not echo submitted boundary JSON or render source schema, fact-group, query ID, URL, path, raw SQL, or source-contract fields",
        (
            "The diagnosis output path must differ from the input or source-contract path, "
            "and from the auth-header file path when one is used."
        ),
        "rejects endpoints, topics, database names, credentials, raw event records, and raw SQL",
        "must not print input paths, raw payloads, raw values",
    ):
        assert required in text


def test_trino_private_preview_release_path_pins_release_gates():
    text = _normalized_doc_text(TRINO_PRIVATE_PREVIEW_DOC)

    for required in (
        "Before a release may publish the bounded local Trino production and retained private-preview positioning",
        "demo_trino_evidence_package.py passes and prints only the safe summary",
        "approved test cluster",
        "explicit read-only smoke tables",
        "validate_trino_evidence_package.py without --partial-ok",
        "retained Trino compact diagnosis artifacts used to discuss product-surface readiness pass python3 scripts/audit_trino_product_surface_boundary.py <raw-free-trino-boundary.json> --diagnosis-json <raw-free-trino-diagnosis.json> --summary-json <raw-free-trino-product-surface-summary-json>, or the same audit over --handoff-suite-manifest <trino-one-query-handoff-suite.json>, with trino_product_surface_boundary_audit_v1, path-free output, required diagnosis artifacts in manifest mode, optional retained product-surface summary drift checks, retained handoff summaries treated as protected input artifacts, checked diagnostic_lane source granularity, evidence readiness, verification scope, supported-attention count, fact-state counts, and live_known_query_diagnosis=one_query_pruned_query_info_local_production",
        "optional retained product-surface summary drift checks",
        "retained handoff summaries treated as protected input artifacts",
        "aggregate metadata-summary boundaries must be rejected as coverage evidence, not product-surface diagnosis artifacts",
        "Before any broader Trino support-surface decision, run python3 scripts/audit_trino_support_gap_matrix.py --summary-json <raw-free-trino-support-gap-summary-json>",
        "trino_support_gap_matrix_audit_v1 evidence stay aligned with the support-gap matrix",
        "package handoff audit passes python3 scripts/audit_trino_evidence_handoff.py <sanitized-package.json> --summary-json <raw-free-trino-package-handoff-summary.json> with only raw-free machine evidence",
        "retained set of one-query handoff results passes the trino_one_query_handoff_suite_v1 manifest gate with diagnosis, executed-smoke, per-entry readiness-summary, per-entry handoff-summary, one-query, source-version, version-family breadth, parser-coverage, and supported-attention requirements, a configured minimum retained input count, and a raw-free machine summary artifact",
        "Trino support is limited to sanitized offline evidence package import, bounded local event-store import, and bounded HTTP event archive, HTTP query-detail archive, local query-detail, query-list aggregate, statement-stats, local pruned QueryInfo import, local metadata CLI summary building, local metadata summary import, and dev-only metadata CLI summary smoke round-trip, plus event-source contract checking, dry-run coordinator query-info target checking, metadata source-contract checking, one-query pruned coordinator query-info probing/import, dev-only package-to-boundary evidence handoff audit, dev-only product-surface boundary audit over retained raw-free compact artifacts, dev-only one-query handoff and handoff-suite readiness over raw-free handoff artifacts, dev-only support-gap audit coverage for source-type registry and engine fact promotion policy, and local compact diagnosis over raw-free direct boundary JSON excluding metadata summary boundaries or selected package sample boundaries, the isolated local compact-diagnosis page over the same already raw-free inputs, and the local production web Trino retained-list Recent, One Query ID, raw-free materialized Details, deterministic Python Report, and optimizer guidance lanes",
        "keep scripts/audit_trino_support_gap_matrix.py green while closing the support-gap matrix for Trino facts versus Impala facts",
        "No broad production Trino engine selector",
        "LLM report path",
        "Query Optimizer jobs",
        "metadata collector",
        "query-history reader",
        "broader/shared production expansion claim",
        "browser workflow beyond the isolated compact-diagnosis page and Recent/One Query ID, raw-free materialized Details, deterministic Python Report, and optimizer guidance lanes",
    ):
        assert required in text


def test_public_release_readiness_names_trino_beta_without_support_expansion():
    text = _normalized_doc_text(PUBLIC_READINESS)

    for required in (
        "local production web Trino retained-list Recent over one bounded retained pruned coordinator query-list read and selected pruned QueryInfo reads",
        "local production web Trino One Query ID over one bounded pruned coordinator QueryInfo read",
        "raw-free Trino Details over server-owned materialized web cases from those lanes",
        "Trino is not Running live collection, query-history coordinator crawling, LLM report output, Query Optimizer jobs, metadata collection, Query Doctor-generated SQL, SQL execution, or broader/shared Trino production support beyond the local retained-list Recent, One Query ID, raw-free materialized Details, Python Report, and optimizer guidance local production lanes.",
    ):
        assert required in text


def test_trino_private_preview_release_path_is_indexed_and_linked():
    docs_index = DOCS_INDEX.read_text(encoding="utf-8")
    ru_docs_index = " ".join(RU_DOCS_INDEX.read_text(encoding="utf-8").split())
    live_design = TRINO_LIVE_COLLECTION_DOC.read_text(encoding="utf-8")
    evidence_checklist = TRINO_EVIDENCE_CHECKLIST_DOC.read_text(encoding="utf-8")

    assert "engines/trino-private-preview-release.md" in docs_index
    assert "engines/i18n/ru/trino-private-preview-release.md" not in docs_index
    assert "../../engines/i18n/ru/trino-private-preview-release.md" not in ru_docs_index
    assert "engine deep-dive документы остаются English-only" in ru_docs_index
    assert "trino-beta-ui-readiness.md" in TRINO_PRIVATE_PREVIEW_DOC.read_text(encoding="utf-8")
    assert "trino-private-preview-release.md" in live_design
    assert "trino-private-preview-release.md" in evidence_checklist


def test_readme_and_release_docs_keep_trino_limited_to_offline_import():
    for path in (README, README_RU, RELEASE_CHECKLIST, PUBLIC_READINESS):
        text = _normalized_doc_text(path)
        lower_text = text.lower()
        assert "Trino" in text
        assert "Apache Impala" in text
        assert "public" in lower_text
        assert "offline" in lower_text
        assert "live collection" in lower_text
        assert "llm report output" in lower_text
        assert "raw-free" in lower_text
        assert "Query Doctor-generated" in text
        assert "SQL" in text


def test_release_checklists_name_trino_beta_without_support_expansion():
    text = _normalized_doc_text(RELEASE_CHECKLIST)

    for required in (
        "local production web Trino retained-list Recent lane over one bounded retained pruned coordinator query-list read plus selected pruned QueryInfo reads",
        "local production web Trino One Query ID lane over one bounded pruned coordinator QueryInfo read",
        "not Running live collection",
        "broader Trino coordinator query-history collection",
        "Query Doctor-generated Trino SQL",
        "raw-free Trino Details over server-owned materialized web cases",
        "broader/shared Trino production support beyond the local retained-list Recent, One Query ID, raw-free materialized Details, Python Report, and optimizer guidance local production lanes",
    ):
        assert required in text

    ru_docs_index = " ".join(RU_DOCS_INDEX.read_text(encoding="utf-8").split())
    assert "release-checklist.md" not in ru_docs_index
    assert "release, research и engine deep-dive документы остаются English-only" in ru_docs_index


def test_russian_readme_names_current_trino_pruned_query_info_surfaces():
    text = _normalized_doc_text(README_RU)

    for required in (
        "bounded local pruned QueryInfo import",
        "query-doctor-trino-query-info-pruned-import",
        "one explicit compact sanitized local pruned QueryInfo JSON",
        "query-doctor-trino-coordinator-query-info-pruned-probe",
        "query-doctor-trino-coordinator-query-info-pruned-import",
        "--auth-header-file",
        "auth header paths или values",
        "не делает network read",
        "reject-ит raw QueryInfo fields",
        "stage/task detail",
    ):
        assert required in text


def test_trino_private_preview_release_path_is_english_only():
    ru_path = REPO_ROOT / "docs" / "engines" / "i18n" / "ru" / "trino-private-preview-release.md"
    ru_docs_index = " ".join(RU_DOCS_INDEX.read_text(encoding="utf-8").split())

    assert not ru_path.exists()
    assert "trino-private-preview-release.md" not in ru_docs_index
    assert "engine deep-dive документы остаются English-only" in ru_docs_index


def _normalized_doc_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("`", "")
    return " ".join(text.split())
