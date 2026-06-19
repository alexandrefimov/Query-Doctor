from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DOC = REPO_ROOT / "docs" / "configuration.md"
RU_CONFIG_DOC = REPO_ROOT / "docs" / "i18n" / "ru" / "configuration.md"


def test_configuration_doc_pins_trino_beta_recent_and_one_query_boundary() -> None:
    text = normalized_doc_text(CONFIG_DOC)

    for fragment in (
        "## Trino Beta Recent And One Query ID",
        "local web lane for bounded retained-list Recent diagnosis and one explicit Query ID",
        "`trino_beta_enabled`",
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
        "Details/trusted reports",
        "optimizer behavior",
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
        "## Trino Beta Recent и One Query ID",
        "local lane для bounded retained-list Recent diagnosis и одного explicit Query ID",
        '"trino_beta_enabled": true',
        '"trino_coordinator_url"',
        '"trino_query_info_source_contract"',
        '"trino_query_list_source_contract"',
        '"trino_auth_header_file"',
        '"trino_kerberos_principal"',
        '"trino_krb5_ccname"',
        "Это не production Trino support",
        "Running scans",
        "query-history crawling",
        "metadata collection",
        "Details/trusted reports",
        "optimizer behavior",
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
