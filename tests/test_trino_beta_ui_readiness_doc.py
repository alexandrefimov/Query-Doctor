from pathlib import Path


DOC = Path(__file__).resolve().parents[1] / "docs" / "trino-beta-ui-readiness.md"


def test_trino_beta_ui_readiness_doc_pins_showable_surface_and_prerequisites() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "local Trino Beta UI\nsurface" in text
    assert "not production engine support" in text
    assert "Trino Beta" in text
    assert "One Query ID" in text
    assert "`trino_beta_enabled=true`" in text
    assert "`trino_coordinator_url`" in text
    assert "`trino_query_info_source_contract`" in text
    assert "`trino_query_list_source_contract`" in text
    assert "bounded retained pruned coordinator\nquery-list read" in text
    assert "one bounded pruned\ncoordinator QueryInfo read" in text
    assert "complete\nTrino Beta product output for the selected workflow" in text


def test_trino_beta_ui_readiness_doc_pins_blocked_surfaces() -> None:
    text = DOC.read_text(encoding="utf-8")

    for fragment in (
        "Running scans",
        "query-history crawling",
        "metadata collection",
        "Details pages",
        "trusted reports",
        "optimizer behavior",
        "Query Doctor-generated Trino SQL",
        "SQL execution",
        "production Trino support",
    ):
        assert fragment in text
    assert (
        "Recent must be disabled unless the\n  selected source has the query-list source contract"
        in text
    )


def test_trino_beta_ui_readiness_doc_lists_release_gates() -> None:
    text = DOC.read_text(encoding="utf-8")

    for command in (
        "python3 scripts/audit_trino_beta_release_readiness.py --config <ignored-local-web-config.json> --selected-query-limit 1",
        "python3 scripts/audit_trino_web_beta_readiness.py --require-query-id --require-recent",
        "python3 scripts/audit_trino_web_beta_live_smoke.py --config <ignored-local-web-config.json> --selected-query-limit 1",
        "scripts/query-doctor-web-trino-beta-smoke --config <ignored-local-web-config.json> --limit 1",
        "python3 -m pytest -q tests/test_web_trino_beta_query.py",
        "python3 -m pytest -q tests/test_web_ui_help.py tests/test_web_ui_home.py",
        "python3 scripts/audit_trino_product_surface_boundary.py --registry-only",
        "python3 scripts/audit_trino_support_gap_matrix.py",
        "tests/*trino*.py tests/test_engine_capabilities.py",
    ):
        assert command in text
    assert "performs no coordinator network read or SQL execution" in text
    assert "performs the bounded Trino Beta Recent path and\nselected QueryInfo diagnosis" in text
    assert "submits One Query ID using one\nselected retained Query ID without printing it" in text
    assert "--static-only` mode runs only static audits and focused tests" in text
    assert "does not require a README screenshot refresh by itself" in text
