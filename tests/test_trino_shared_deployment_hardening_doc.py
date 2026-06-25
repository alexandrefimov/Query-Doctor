from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOC = REPO_ROOT / "docs" / "trino-shared-deployment-hardening.md"
DOCS_INDEX = REPO_ROOT / "docs" / "README.md"
CHECK_ACTIVE_DOCS = REPO_ROOT / "scripts" / "check_active_docs.py"
TRINO_UI_READINESS = REPO_ROOT / "docs" / "trino-beta-ui-readiness.md"
PUBLIC_READINESS = REPO_ROOT / "docs" / "public-release-readiness.md"
RELEASE_CHECKLIST = REPO_ROOT / "docs" / "release-checklist.md"
ENGINE_SUPPORT_MATRIX = REPO_ROOT / "docs" / "engine-support-gap-matrix.md"


def test_trino_shared_deployment_hardening_doc_pins_non_support_contract() -> None:
    text = _normalized_doc_text(DOC)

    for required in (
        "shared/non-local Trino deployment hardening contract, not a support claim",
        "`trino_support_mode=production` remains local production support only",
        "bounded raw-free retained-list Recent lane, One Query ID lane, raw-free materialized Details, deterministic Python Report, and optimizer guidance",
        "It does not promote Trino into broader/shared Trino production support.",
        "Running scans",
        "query-history crawling",
        "product metadata collection",
        "LLM reports",
        "Query Optimizer jobs",
        "generated SQL or Query Doctor-generated Trino SQL",
        "SQL execution",
        "broader/shared Trino production support",
    ):
        assert required in text


def test_trino_shared_deployment_hardening_doc_pins_identity_and_source_isolation() -> None:
    text = _normalized_doc_text(DOC)

    for required in (
        "requires trusted front-door viewer identity",
        "`viewer_identity_header`",
        "strips inbound copies of that header and sets exactly one simple owner value",
        "`--trusted-front-door-reviewed`",
        "strips inbound copies of `viewer_identity_header`, authenticates the request before it reaches Query Doctor, and injects exactly one normalized simple viewer value",
        "must not add native OIDC, SAML, SPNEGO, Kerberos, LDAP, password, MFA, session, group, RBAC, or token authentication variants",
        "must not gate raw source reveal on the Trino collection credential, keytab owner, service account, or operator identity",
        "[owner-raw-d3-deployment.md](owner-raw-d3-deployment.md)",
        "raw Trino source reveal stays isolated and disabled",
        "`source_visibility=safe`",
        "`owner_raw_source_enabled=false`",
        "must not reveal raw source data, raw QueryInfo or query-list payloads, Query IDs, source-contract paths, auth-reference paths, coordinator URLs, local paths, users, header values, object identifiers, metadata values, CLI stdout/stderr, or raw payloads",
        "must not reopen raw QueryInfo, query-list, metadata, CLI, or source-contract inputs",
    ):
        assert required in text


def test_trino_shared_deployment_hardening_doc_pins_metadata_and_audit_path() -> None:
    text = _normalized_doc_text(DOC)

    for required in (
        "The metadata CLI summary smoke is dev-only.",
        "not product metadata collection",
        "operator-installed Trino CLI",
        "python3 scripts/audit_trino_shared_deployment_preflight.py",
        "python3 scripts/audit_trino_shared_deployment_preflight.py --config <ignored-local-web-config.json>",
        "python3 scripts/audit_trino_shared_deployment_preflight.py --config <ignored-local-web-config.json> --trusted-front-door-reviewed",
        "python3 scripts/audit_trino_shared_deployment_preflight.py --config <ignored-local-web-config.json> --front-door-review-summary <raw-free-front-door-review.json>",
        "scripts/audit_owner_raw_live_front_door_review.py --require-trino-shared-hardening",
        "The front-door review summary is the retained evidence form for a real Kubernetes/proxy deployment review.",
        "python3 scripts/audit_owner_raw_live_front_door_review.py --template-json <raw-free-front-door-review.json> --require-trino-shared-hardening",
        "The template uses `review_status=unreviewed` and false proof fields",
        "preflight wraps the shared deployment boundary audit, product-surface boundary audit, support-gap audit, and active-docs check",
        "performs no coordinator network read, metadata collection, SQL execution, live smoke, or UI smoke",
        "python3 scripts/audit_trino_shared_deployment_boundary.py",
        "python3 scripts/audit_trino_shared_deployment_boundary.py --config <ignored-local-web-config.json>",
        "python3 scripts/audit_trino_shared_deployment_boundary.py --config <ignored-local-web-config.json> --trusted-front-door-reviewed",
        "`shared_deployment_requirement_tracking` entries",
        "`shared_deployment_requirement_tracking_counts`",
        "`production_review_shared_deployment_v1` profile",
        "`production_review_tracking_counts`",
        "path-free `shared_deployment_requirements` and production-review counts",
        "deployment-config, product-boundary, capability, release-gate, and documentation requirements",
        "including only the raw-free requirement-tracking counts, production-review counts, and per-requirement status entries",
        "python3 scripts/audit_trino_beta_release_readiness.py --config <ignored-local-web-config.json> --selected-query-limit 1",
        "python3 scripts/audit_trino_beta_release_readiness.py --config <ignored-local-web-config.json> --selected-query-limit 1 --trusted-front-door-reviewed",
        "`--metadata-smoke-redaction-reviewed`",
        "emit only raw-free counts and issue categories",
        "README changes are not required for this hardening layer unless the user-facing workflow, first-screen UI, CLI quickstart, or support claim changes",
    ):
        assert required in text


def test_trino_shared_deployment_hardening_doc_is_indexed_as_active() -> None:
    index = DOCS_INDEX.read_text(encoding="utf-8")
    active_docs = CHECK_ACTIVE_DOCS.read_text(encoding="utf-8")

    assert (
        "[trino-shared-deployment-hardening.md](trino-shared-deployment-hardening.md) | active"
        in index
    )
    assert '"docs/trino-shared-deployment-hardening.md"' in active_docs


def test_shared_hardening_doc_is_linked_from_durable_trino_docs() -> None:
    for path in (
        TRINO_UI_READINESS,
        PUBLIC_READINESS,
        RELEASE_CHECKLIST,
        ENGINE_SUPPORT_MATRIX,
    ):
        assert "trino-shared-deployment-hardening.md" in path.read_text(encoding="utf-8")


def _normalized_doc_text(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())
