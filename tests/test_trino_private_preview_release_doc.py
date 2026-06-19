from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TRINO_PRIVATE_PREVIEW_DOC = REPO_ROOT / "docs" / "engines" / "trino-private-preview-release.md"
TRINO_PRIVATE_PREVIEW_RU_DOC = (
    REPO_ROOT / "docs" / "engines" / "i18n" / "ru" / "trino-private-preview-release.md"
)
DOCS_INDEX = REPO_ROOT / "docs" / "README.md"
RU_DOCS_INDEX = REPO_ROOT / "docs" / "i18n" / "ru" / "README.md"
README = REPO_ROOT / "README.md"
README_RU = REPO_ROOT / "README.ru.md"
RELEASE_CHECKLIST = REPO_ROOT / "docs" / "release-checklist.md"
RU_RELEASE_CHECKLIST = REPO_ROOT / "docs" / "i18n" / "ru" / "release-checklist.md"
PUBLIC_READINESS = REPO_ROOT / "docs" / "public-release-readiness.md"
RU_PUBLIC_READINESS = REPO_ROOT / "docs" / "i18n" / "ru" / "public-release-readiness.md"
TRINO_LIVE_COLLECTION_DOC = REPO_ROOT / "docs" / "engines" / "trino-live-collection-design.md"
TRINO_EVIDENCE_CHECKLIST_DOC = (
    REPO_ROOT / "docs" / "engines" / "trino-test-cluster-evidence-checklist.md"
)


def test_trino_private_preview_release_path_stays_live_non_supporting():
    text = _normalized_doc_text(TRINO_PRIVATE_PREVIEW_DOC)

    for required in (
        "early closed test-cluster integration",
        "not a live collector",
        "not a production engine selector",
        "not a Details/trusted-report surface",
        "not an optimizer workflow",
        "not permission to execute user SQL through Query Doctor",
        "The Trino browser surfaces are the isolated local compact-diagnosis page for already raw-free direct boundary JSON excluding local metadata summary boundaries or a selected sample boundary from a package boundary export, plus the local Trino Beta retained-list Recent lane over one bounded retained pruned coordinator query-list read and selected pruned QueryInfo reads, plus the local Trino Beta One Query ID lane over one bounded pruned coordinator QueryInfo read, both with the same raw-free compact diagnosis.",
        "Trino support is limited to sanitized offline evidence package import, bounded local event-store import, bounded HTTP event archive import, bounded HTTP query-detail archive import, bounded local query-detail import, and bounded local query-list aggregate import, bounded local statement-stats import, bounded local pruned QueryInfo import, event-source contract checking, dry-run coordinator query-info target checking, metadata source-contract checking, bounded local metadata summary import, one-query pruned coordinator query-info probing/import, dev-only package-to-boundary evidence handoff audit, dev-only product-surface boundary audit over retained raw-free compact artifacts, dev-only one-query handoff and handoff-suite readiness over raw-free handoff artifacts, dev-only support-gap audit coverage for source-type registry and engine fact promotion policy, and local compact diagnosis over raw-free direct boundary JSON excluding local metadata summary boundaries or selected package sample boundaries, and the isolated local /trino/compact-diagnosis page over the same already raw-free inputs, plus the local web Trino Beta retained-list Recent lane over one bounded retained pruned coordinator query-list read and selected pruned QueryInfo reads, plus the local web Trino Beta One Query ID lane over one bounded pruned coordinator QueryInfo read, both with the same raw-free compact diagnosis.",
        "A separate event-source contract check remains the source gate for event archive readers, the coordinator query-info target check remains a dry-run gate, and the pruned coordinator query-info probe remains probe-only; the metadata source-contract check is only a dry-run relation/column allowlist gate; the local metadata summary import maps only aggregate coverage counts from an operator-prepared sanitized file; the pruned query-info import maps only allowlisted facts and can feed only the explicit Trino Beta Recent/One Query ID lanes or raw-free local artifacts.",
        "Compact diagnosis consumes only already raw-free direct boundary JSON excluding local metadata summary boundaries or a selected sample boundary from a package export, and the isolated page plus Recent/One Query ID beta lanes render only sanitized diagnosis fields; all remain outside Details/trusted reports, optimizer behavior, Running scans, metadata collection, query-history crawling, SQL execution, and production Query ID support.",
        "trino-beta-ui-readiness.md",
        "local UI beta show-readiness gate",
        "production product workflows still treat Trino as unsupported",
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
        "relation/column coverage and stats-completeness counts only",
        "without metadata reads, metadata SQL, object identifiers, metadata values, or compact diagnosis output",
        "GET /v1/query/{queryId}?pruned=true",
        "performs no network read, maps only allowlisted state and queryStats fields into raw-free boundary JSON",
        "rejects raw QueryInfo fields such as Query IDs, query text, session fields, endpoint URLs, object names, and stage/task detail",
        "operator-managed Authorization header line",
        "auth header path/value",
        "does not map QueryInfo to facts, crawl query history, submit SQL, collect production Query ID support, or add browser/report output",
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
        "live_known_query_diagnosis=one_query_pruned_query_info_beta",
        "allowed Trino web registry is still limited to compact preview surfaces plus the local Recent and One Query ID beta surfaces",
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
        "It does not crawl query history, submit SQL, collect production Query ID support, or add browser/report output.",
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
        "Before a release may describe Trino as private preview",
        "demo_trino_evidence_package.py passes and prints only the safe summary",
        "approved test cluster",
        "explicit read-only smoke tables",
        "validate_trino_evidence_package.py without --partial-ok",
        "retained Trino compact diagnosis artifacts used to discuss product-surface readiness pass python3 scripts/audit_trino_product_surface_boundary.py <raw-free-trino-boundary.json> --diagnosis-json <raw-free-trino-diagnosis.json> --summary-json <raw-free-trino-product-surface-summary-json>, or the same audit over --handoff-suite-manifest <trino-one-query-handoff-suite.json>, with trino_product_surface_boundary_audit_v1, path-free output, required diagnosis artifacts in manifest mode, optional retained product-surface summary drift checks, retained handoff summaries treated as protected input artifacts, checked diagnostic_lane source granularity, evidence readiness, verification scope, supported-attention count, fact-state counts, and live_known_query_diagnosis=one_query_pruned_query_info_beta",
        "optional retained product-surface summary drift checks",
        "retained handoff summaries treated as protected input artifacts",
        "aggregate metadata-summary boundaries must be rejected as coverage evidence, not product-surface diagnosis artifacts",
        "Before any broader Trino support-surface decision, run python3 scripts/audit_trino_support_gap_matrix.py --summary-json <raw-free-trino-support-gap-summary-json>",
        "trino_support_gap_matrix_audit_v1 evidence stay aligned with the support-gap matrix",
        "package handoff audit passes python3 scripts/audit_trino_evidence_handoff.py <sanitized-package.json> --summary-json <raw-free-trino-package-handoff-summary.json> with only raw-free machine evidence",
        "retained set of one-query handoff results passes the trino_one_query_handoff_suite_v1 manifest gate with diagnosis, executed-smoke, per-entry readiness-summary, per-entry handoff-summary, one-query, source-version, version-family breadth, parser-coverage, and supported-attention requirements, a configured minimum retained input count, and a raw-free machine summary artifact",
        "Trino support is limited to sanitized offline evidence package import, bounded local event-store import, and bounded HTTP event archive, HTTP query-detail archive, local query-detail, query-list aggregate, statement-stats, local pruned QueryInfo import, and local metadata summary import, plus event-source contract checking, dry-run coordinator query-info target checking, metadata source-contract checking, one-query pruned coordinator query-info probing/import, dev-only package-to-boundary evidence handoff audit, dev-only product-surface boundary audit over retained raw-free compact artifacts, dev-only one-query handoff and handoff-suite readiness over raw-free handoff artifacts, dev-only support-gap audit coverage for source-type registry and engine fact promotion policy, and local compact diagnosis over raw-free direct boundary JSON excluding metadata summary boundaries or selected package sample boundaries, the isolated local compact-diagnosis page over the same already raw-free inputs, and the local web Trino Beta retained-list Recent and One Query ID lanes",
        "keep scripts/audit_trino_support_gap_matrix.py green while closing the support-gap matrix for Trino facts versus Impala facts",
        "No production Trino engine selector",
        "Details/trusted report path",
        "optimizer behavior",
        "metadata collector",
        "query-history reader",
        "production support claim",
        "browser workflow beyond the isolated compact-diagnosis page and Recent/One Query ID beta lanes",
    ):
        assert required in text


def test_public_release_readiness_names_trino_beta_without_support_expansion():
    text = _normalized_doc_text(PUBLIC_READINESS)
    ru_text = _normalized_doc_text(RU_PUBLIC_READINESS)

    for required in (
        "local web Trino Beta retained-list Recent over one bounded retained pruned coordinator query-list read and selected pruned QueryInfo reads",
        "local web Trino Beta One Query ID over one bounded pruned coordinator QueryInfo read",
        "Trino is not Running live collection, query-history coordinator crawling, Details/trusted report output, optimizer behavior, metadata collection, Query Doctor-generated SQL, SQL execution, or production Trino support beyond the local retained-list Recent and One Query ID beta lanes.",
    ):
        assert required in text

    for required in (
        "Trino Beta упоминается, он описан только как local web retained-list Recent beta lane over one bounded retained pruned coordinator query-list read plus selected pruned QueryInfo reads",
        "без public engine support, Running scans, query-history crawling, metadata collection, Details/trusted report output, optimizer behavior, Query Doctor-generated Trino SQL или SQL execution",
        "local Trino Beta Recent/One Query ID boundary без public Trino support claim",
    ):
        assert required in ru_text


def test_trino_private_preview_release_path_is_indexed_and_linked():
    docs_index = DOCS_INDEX.read_text(encoding="utf-8")
    ru_docs_index = RU_DOCS_INDEX.read_text(encoding="utf-8")
    live_design = TRINO_LIVE_COLLECTION_DOC.read_text(encoding="utf-8")
    evidence_checklist = TRINO_EVIDENCE_CHECKLIST_DOC.read_text(encoding="utf-8")

    assert "engines/trino-private-preview-release.md" in docs_index
    assert "engines/i18n/ru/trino-private-preview-release.md" in docs_index
    assert "../../engines/i18n/ru/trino-private-preview-release.md" in ru_docs_index
    assert "trino-beta-ui-readiness.md" in TRINO_PRIVATE_PREVIEW_DOC.read_text(encoding="utf-8")
    assert "trino-beta-ui-readiness.md" in TRINO_PRIVATE_PREVIEW_RU_DOC.read_text(encoding="utf-8")
    assert "trino-private-preview-release.md" in live_design
    assert "trino-private-preview-release.md" in evidence_checklist
    assert "local Trino Beta Recent + One Query ID boundary без public support claim" in (
        _normalized_doc_text(RU_DOCS_INDEX)
    )


def test_readme_and_release_docs_keep_trino_limited_to_offline_import():
    for path in (README, README_RU, RELEASE_CHECKLIST, RU_RELEASE_CHECKLIST, PUBLIC_READINESS):
        text = _normalized_doc_text(path)
        lower_text = text.lower()
        assert "Trino" in text
        assert "Apache Impala" in text
        assert "public" in lower_text
        assert "offline" in lower_text
        assert "live collection" in lower_text
        assert "details/trusted report output" in lower_text
        assert "Query Doctor-generated" in text
        assert "SQL" in text


def test_release_checklists_name_trino_beta_without_support_expansion():
    text = _normalized_doc_text(RELEASE_CHECKLIST)
    ru_text = _normalized_doc_text(RU_RELEASE_CHECKLIST)

    for required in (
        "local web Trino Beta retained-list Recent lane over one bounded retained pruned coordinator query-list read plus selected pruned QueryInfo reads",
        "local web Trino Beta One Query ID lane over one bounded pruned coordinator QueryInfo read",
        "not Running live collection",
        "broader Trino coordinator query-history collection",
        "Query Doctor-generated Trino SQL",
        "production Trino support beyond the local retained-list Recent and One Query ID beta lanes",
    ):
        assert required in text

    for required in (
        "Trino Beta упоминается",
        "local web retained-list Recent beta lane over one bounded retained pruned coordinator query-list read plus selected pruned QueryInfo reads",
        "local web One Query ID beta lane over one bounded pruned coordinator QueryInfo read",
        "без public engine support",
        "Running scans",
        "query-history crawling",
        "Query Doctor-generated Trino SQL или SQL execution",
    ):
        assert required in ru_text


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


def test_trino_private_preview_release_path_has_russian_companion():
    text = _normalized_doc_text(TRINO_PRIVATE_PREVIEW_RU_DOC)

    for required in (
        "Trino private preview release path",
        "раннюю закрытую интеграцию с тестовым кластером",
        "Trino support ограничен sanitized offline evidence package import, bounded local event-store import, bounded HTTP event archive import, bounded HTTP query-detail archive import, bounded local query-detail/query-list aggregate import и bounded local statement-stats import, bounded local pruned QueryInfo import, plus event-source contract checking, dry-run coordinator query-info target checking, metadata source-contract checking, bounded local metadata summary import, plus one-query pruned coordinator query-info probing/import, dev-only package-to-boundary evidence handoff audit, dev-only product-surface boundary audit over retained raw-free compact artifacts, dev-only one-query handoff and handoff-suite readiness over raw-free handoff artifacts, dev-only support-gap audit coverage for source-type registry и engine fact promotion policy, local compact diagnosis over raw-free direct boundary JSON excluding local metadata summary boundaries или selected package sample boundaries, isolated local /trino/compact-diagnosis page over the same already raw-free inputs, local web Trino Beta retained-list Recent lane over one bounded retained pruned coordinator query-list read and selected pruned QueryInfo reads, и local web Trino Beta One Query ID lane over one bounded pruned coordinator QueryInfo read, both with the same raw-free compact diagnosis.",
        "Отдельный event-source contract check остается source gate для event archive readers, coordinator query-info target check остается dry-run gate, а pruned coordinator query-info probe остается probe-only; metadata source-contract check остается dry-run relation/column allowlist gate; local metadata summary import мапит только aggregate coverage counts из operator-prepared sanitized file; pruned query-info import мапит только allowlisted facts и может feed-ить только explicit Trino Beta Recent/One Query ID lanes или raw-free local artifacts.",
        "query-doctor-trino-event-store-import",
        "query-doctor-trino-http-event-archive-import",
        "query-doctor-trino-http-query-detail-archive-import",
        "query-doctor-trino-query-detail-import",
        "query-doctor-trino-query-list-import",
        "query-doctor-trino-statement-stats-import",
        "query-doctor-trino-event-source-contract-check",
        "query-doctor-trino-coordinator-query-info-target-check",
        "query-doctor-trino-metadata-source-contract-check",
        "query-doctor-trino-metadata-summary-import",
        "query-doctor-trino-coordinator-query-info-pruned-probe",
        "query-doctor-trino-coordinator-query-info-pruned-import",
        "python3 scripts/audit_trino_evidence_handoff.py",
        "--summary-json <raw-free-trino-package-handoff-summary.json>",
        "trino_evidence_handoff_summary_v1",
        "Retained handoff-suite audits требуют diagnostic-lane source, readiness, verification и fact-state counters и reject-ят source-granularity или fact-state counter drift между diagnostic_lane и top-level retained summary counters.",
        "Strict retained suites могут также требовать selected safe source-contract labels, например synthetic_trino_event_listener_v1, из retained package source summaries, плюс selected source-granularity labels, например one_query_boundary или aggregate_query_list, и selected verification-scope labels, например comparable_one_query_rerun, representative_query_selection или source_contract_review, из уже retained diagnostic-lane counters без reopening packages.",
        "Они также reject-ят duplicate retained handoff-summary artifact references, включая path aliases, чтобы suite-width counts не могли reuse one summary.",
        "python3 scripts/audit_trino_product_surface_boundary.py",
        "raw-free-trino-product-surface-summary-json",
        "trino_product_surface_boundary_audit_v1",
        "live_known_query_diagnosis=one_query_pruned_query_info_beta",
        "live_recent_scan=retained_query_list_beta",
        "allowed Trino web registry остается ограничен compact preview surfaces plus the local Recent and One Query ID beta surfaces",
        "Trino CLI stays preview/dev-only",
        "--handoff-suite-manifest <trino-one-query-handoff-suite.json>",
        "Product-surface summary output должен отличаться от manifest и каждого referenced boundary, diagnosis, smoke-summary, readiness-summary, handoff-summary или product-surface-summary artifact",
        "валидирует retained per-entry product-surface summaries when present",
        "--product-surface-summary-out <raw-free-trino-product-surface-summary-json>",
        "--query-id-file <operator-query-id-file>",
        "Finished QueryInfo может быть evicted раньше, чем старые QueryMonitor timeline entries исчезнут из logs",
        "HTTP 404",
        "stale-QueryInfo hint",
        "HTTP 401",
        "auth-rejected hint",
        "aggregate metadata-summary boundaries должны reject-иться как coverage evidence, а не product-surface diagnosis artifacts",
        "python3 scripts/build_trino_handoff_suite_manifest.py",
        "trino_one_query_handoff_suite_v1 manifest",
        "--boundary-json <raw-free-trino-boundary-1.json>",
        "--readiness-summary-json <raw-free-trino-readiness-summary-1.json>",
        "--handoff-summary-json <raw-free-trino-one-query-handoff-summary-json>",
        "--product-surface-summary-json <raw-free-trino-product-surface-summary-json>",
        "--handoff-suite-manifest <trino-one-query-handoff-suite.json>",
        "--require-readiness-summary-json",
        "--require-handoff-summary-json",
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
        "structured diagnostic_lane block для source granularity, evidence readiness, verification scope и fact-state counters",
        "валидирует их structured diagnostic_lane blocks и reject-ит missing или drifted source-granularity, readiness, verification-scope или fact-state counters",
        "--require-min-trino-version-families <minimum-trino-version-family-count>",
        "--require-trino-version-family <safe-trino-version-family>",
        "Single-boundary local query-detail, local query-list aggregate, local statement-stats, local pruned QueryInfo, HTTP query-detail archive и pruned coordinator query-info import commands",
        "bounded Kerberos/SPNEGO smoke",
        "sanitized evidence-package intake",
        "Не добавлены production Trino engine selector",
        "browser workflow beyond the isolated compact-diagnosis page and Recent/One Query ID beta lanes",
    ):
        assert required in text


def _normalized_doc_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("`", "")
    return " ".join(text.split())
