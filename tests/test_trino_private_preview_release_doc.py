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
PUBLIC_READINESS = REPO_ROOT / "docs" / "public-release-readiness.md"
TRINO_LIVE_COLLECTION_DOC = REPO_ROOT / "docs" / "engines" / "trino-live-collection-design.md"
TRINO_EVIDENCE_CHECKLIST_DOC = (
    REPO_ROOT / "docs" / "engines" / "trino-test-cluster-evidence-checklist.md"
)


def test_trino_private_preview_release_path_stays_live_non_supporting():
    text = _normalized_doc_text(TRINO_PRIVATE_PREVIEW_DOC)

    for required in (
        "early closed test-cluster integration",
        "not a live collector",
        "not a live engine selector",
        "not a Details/trusted-report surface",
        "not an optimizer workflow",
        "not permission to execute user SQL through Query Doctor",
        "The only Trino browser surface is the isolated local compact-diagnosis page for already raw-free direct boundary JSON or a selected sample boundary from a package boundary export.",
        "Trino support is limited to sanitized offline evidence package import, bounded local event-store import, bounded HTTP event archive import, bounded HTTP query-detail archive import, bounded local query-detail import, and bounded local query-list aggregate import, bounded local statement-stats import, bounded local pruned QueryInfo import, event-source contract checking, dry-run coordinator query-info target checking, one-query pruned coordinator query-info probing/import, dev-only one-query handoff and handoff-suite readiness over raw-free handoff artifacts, and local compact diagnosis over raw-free direct boundary JSON or selected package sample boundaries, and the isolated local /trino/compact-diagnosis page over the same already raw-free inputs.",
        "A separate event-source contract check remains the source gate for event archive readers, the coordinator query-info target check remains a dry-run gate, and the pruned coordinator query-info probe remains probe-only; the pruned query-info import maps only allowlisted facts and remains outside browser/report collection.",
        "Compact diagnosis consumes only already raw-free direct boundary JSON or a selected sample boundary from a package export, and the isolated page renders only sanitized diagnosis fields; both remain outside Details/trusted reports, optimizer behavior, live Recent scans, and live Query ID diagnosis.",
        "live product workflows still treat Trino as unsupported",
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
        "query-doctor-trino-import --format boundary-json <sanitized-package.json>",
        "query-doctor-trino-event-store-import",
        "query-doctor-trino-query-detail-import",
        "query-doctor-trino-query-list-import",
        "query-doctor-trino-statement-stats-import",
        "query-doctor-trino-query-info-pruned-import",
        "query-doctor-trino-event-source-contract-check",
        "query-doctor-trino-coordinator-query-info-target-check",
        "query-doctor-trino-coordinator-query-info-pruned-probe",
        "query-doctor-trino-coordinator-query-info-pruned-import",
        "python3 scripts/trino_one_query_live_handoff.py",
        "python3 scripts/build_trino_handoff_suite_manifest.py",
        "trino_one_query_handoff_suite_v1 manifest",
        "--boundary-json <raw-free-trino-boundary-1.json>",
        "--out <trino-one-query-handoff-suite.json>",
        "--handoff-suite-manifest <trino-one-query-handoff-suite.json>",
        "--require-diagnosis-json",
        "--fail-on-unknown-parser-coverage",
        "--require-min-inputs <minimum-retained-query-count>",
        "--summary-json <raw-free-trino-suite-summary.json>",
        "The manifest is local handoff metadata, not a committed artifact.",
        "The builder is not an installed product CLI.",
        "relative artifact references",
        "prints only aggregate counts and safe issue categories",
        "trino_compact_readiness_summary_v1 JSON",
        "source-version requirements only as counts and boolean flags",
        "query-doctor-diagnose-trino-compact",
        "sample_fact_boundaries",
        "--sample-index <zero-based-index>",
        "/trino/compact-diagnosis",
        "--boundary-out <raw-free-trino-boundary.json>",
        "--diagnosis-out <raw-free-trino-diagnosis.json>",
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
        "https://<operator-event-archive>",
        "https://<operator-query-detail-archive>",
        "https://<trino-coordinator>",
        "operator-exported, already-sanitized compact samples only",
        "source type, safe auth-reference label, accepted event schema, bounds, and redaction/storage policy",
        "requires an accepted http_event_listener_archive source contract",
        "requires an accepted http_query_detail_archive source contract",
        "does not contact the Trino coordinator, discover endpoints, echo URLs, accept URL credentials, submit SQL",
        "does not contact the Trino coordinator, fetch query-info by Query ID",
        "does not contact Trino, issue /v1/query, fetch query-info JSON",
        "GET /v1/query/{queryId}?pruned=true",
        "performs no network read, maps only allowlisted state and queryStats fields into raw-free boundary JSON",
        "rejects raw QueryInfo fields such as Query IDs, query text, session fields, endpoint URLs, object names, and stage/task detail",
        "operator-managed Authorization header line",
        "auth header path/value",
        "does not map QueryInfo to facts, crawl query history, submit SQL, collect live Query ID diagnosis, or add browser/report output",
        "maps only allowlisted lifecycle and queryStats fields into raw-free boundary JSON",
        "scripts/audit_trino_compact_readiness.py <raw-free-trino-boundary.json> --require-one-query-boundary",
        "--require-source-version trino_coordinator_query_info_target_v1",
        "--diagnosis-json <raw-free-trino-diagnosis.json>",
        "wrapper is not an installed product CLI",
        "strict --require-one-query-boundary, --require-source-version trino_coordinator_query_info_target_v1, and --diagnosis-json <raw-free-trino-diagnosis.json> readiness checks",
        "source contract and stored compact diagnosis artifact are checked",
        "--smoke-summary <trino_smoke_summary.json> --require-executed-smoke",
        "dry-run plan cannot count as an executed test-cluster smoke",
        "output boundary path",
        "It does not crawl query history, submit SQL, collect live Query ID diagnosis, or add browser/report output.",
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
        "retained set of one-query handoff results passes the trino_one_query_handoff_suite_v1 manifest gate with diagnosis, executed-smoke, one-query, source-version, parser-coverage, and supported-attention requirements, a configured minimum retained input count, and a raw-free machine summary artifact",
        "Trino support is limited to sanitized offline evidence package import, bounded local event-store import, and bounded HTTP event archive, HTTP query-detail archive, local query-detail, query-list aggregate, statement-stats, and local pruned QueryInfo import, plus event-source contract checking, dry-run coordinator query-info target checking, one-query pruned coordinator query-info probing/import, dev-only one-query handoff and handoff-suite readiness over raw-free handoff artifacts, and local compact diagnosis over raw-free direct boundary JSON or selected package sample boundaries, and the isolated local compact-diagnosis page over the same already raw-free inputs",
        "No live Trino engine selector",
        "Details/trusted report path",
        "optimizer behavior",
        "metadata collector",
        "query-history reader",
        "live support claim",
        "browser workflow beyond the isolated compact-diagnosis page",
    ):
        assert required in text


def test_trino_private_preview_release_path_is_indexed_and_linked():
    docs_index = DOCS_INDEX.read_text(encoding="utf-8")
    ru_docs_index = RU_DOCS_INDEX.read_text(encoding="utf-8")
    live_design = TRINO_LIVE_COLLECTION_DOC.read_text(encoding="utf-8")
    evidence_checklist = TRINO_EVIDENCE_CHECKLIST_DOC.read_text(encoding="utf-8")

    assert "engines/trino-private-preview-release.md" in docs_index
    assert "engines/i18n/ru/trino-private-preview-release.md" in docs_index
    assert "../../engines/i18n/ru/trino-private-preview-release.md" in ru_docs_index
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
        assert "details/trusted report output" in lower_text
        assert "Query Doctor-generated" in text
        assert "SQL" in text


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
        "Trino support ограничен sanitized offline evidence package import, bounded local event-store import, bounded HTTP event archive import, bounded HTTP query-detail archive import, bounded local query-detail/query-list aggregate import и bounded local statement-stats import, bounded local pruned QueryInfo import, plus event-source contract checking и dry-run coordinator query-info target checking, plus one-query pruned coordinator query-info probing/import, dev-only one-query handoff and handoff-suite readiness over raw-free handoff artifacts, local compact diagnosis over raw-free direct boundary JSON или selected package sample boundaries и isolated local /trino/compact-diagnosis page over the same already raw-free inputs.",
        "Отдельный event-source contract check остается source gate для event archive readers, coordinator query-info target check остается dry-run gate, а pruned coordinator query-info probe остается probe-only; pruned query-info import мапит только allowlisted facts и не становится browser/report collection.",
        "query-doctor-trino-event-store-import",
        "query-doctor-trino-http-event-archive-import",
        "query-doctor-trino-http-query-detail-archive-import",
        "query-doctor-trino-query-detail-import",
        "query-doctor-trino-query-list-import",
        "query-doctor-trino-statement-stats-import",
        "query-doctor-trino-event-source-contract-check",
        "query-doctor-trino-coordinator-query-info-target-check",
        "query-doctor-trino-coordinator-query-info-pruned-probe",
        "query-doctor-trino-coordinator-query-info-pruned-import",
        "python3 scripts/build_trino_handoff_suite_manifest.py",
        "trino_one_query_handoff_suite_v1 manifest",
        "--boundary-json <raw-free-trino-boundary-1.json>",
        "--handoff-suite-manifest <trino-one-query-handoff-suite.json>",
        "--summary-json <raw-free-trino-suite-summary.json>",
        "Single-boundary local query-detail, local query-list aggregate, local statement-stats, local pruned QueryInfo, HTTP query-detail archive и pruned coordinator query-info import commands",
        "bounded Kerberos/SPNEGO smoke",
        "sanitized evidence-package intake",
        "Не добавлены live Trino engine selector",
    ):
        assert required in text


def _normalized_doc_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("`", "")
    return " ".join(text.split())
