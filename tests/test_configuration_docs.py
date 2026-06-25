from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DOC = REPO_ROOT / "docs" / "configuration.md"
RU_CONFIG_DOC = REPO_ROOT / "docs" / "i18n" / "ru" / "configuration.md"


def test_configuration_doc_pins_trino_beta_recent_and_one_query_boundary() -> None:
    text = normalized_doc_text(CONFIG_DOC)

    for fragment in (
        "## Trino Local Recent And One Query ID",
        "bounded local production lane for retained-list Recent diagnosis and one explicit Query ID",
        "`trino_support_mode`",
        "`trino_support_mode=production`",
        "`trino_beta_enabled`",
        "Legacy beta-only switch",
        "`trino_coordinator_url`",
        "`trino_query_info_source_contract`",
        "`trino_query_list_source_contract`",
        "`trino_auth_header_file`",
        "`trino_kerberos_principal`",
        "`trino_krb5_ccname`",
        "Do not combine with `trino_auth_header_file`",
        "do not enable Trino Running scans",
        "query-history crawling",
        "metadata collection",
        "LLM reports",
        "raw-free Trino Details view, deterministic Python Report, and optimizer guidance",
        "Query Optimizer jobs",
        "SQL execution",
        "generated Trino SQL",
        "Public demo mode rejects this setting",
        "web UI must not render coordinator URLs",
        "auth reference paths/values",
        "local source-contract paths",
        "raw SQL",
    ):
        assert fragment in text


def test_russian_configuration_doc_pins_trino_beta_recent_and_one_query_boundary() -> None:
    text = normalized_doc_text(RU_CONFIG_DOC)

    for fragment in (
        "## Trino Local Recent и One Query ID",
        "bounded local production lane для retained-list Recent diagnosis и одного explicit Query ID",
        '"trino_support_mode": "beta"',
        "legacy beta-only switch",
        '"trino_coordinator_url"',
        '"trino_query_info_source_contract"',
        '"trino_query_list_source_contract"',
        '"trino_auth_header_file"',
        '"trino_kerberos_principal"',
        '"trino_krb5_ccname"',
        "Production mode означает local production support только для этих surfaces",
        "Running scans",
        "query-history crawling",
        "metadata collection",
        "LLM reports",
        "Raw-free Details view, deterministic Python Report и optimizer guidance",
        "Query Optimizer jobs",
        "generated Trino SQL",
        "SQL execution",
        "не показывает coordinator URLs",
        "auth reference paths/values",
        "local source-contract paths",
        "raw SQL",
    ):
        assert fragment in text


def normalized_doc_text(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())
