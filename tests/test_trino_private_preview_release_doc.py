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


def test_trino_private_preview_release_path_stays_non_supporting():
    text = _normalized_doc_text(TRINO_PRIVATE_PREVIEW_DOC)

    for required in (
        "early closed test-cluster integration",
        "not a public support announcement",
        "not a live collector",
        "not an engine selector",
        "not a browser/report surface",
        "not an optimizer workflow",
        "not permission to execute user SQL through Query Doctor",
        "Query Doctor production engine support remains Apache Impala only",
        "every product workflow still treats Trino as unsupported",
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
        "operator-exported, already-sanitized compact samples only",
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
        "Apache Impala is the only production engine support",
        "No Trino engine adapter",
        "public engine selector",
        "browser route",
        "trusted report path",
        "optimizer behavior",
        "metadata collector",
        "query-history reader",
        "public support claim",
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


def test_readme_and_release_docs_keep_private_preview_out_of_public_support():
    for path in (README, README_RU, RELEASE_CHECKLIST, PUBLIC_READINESS):
        text = _normalized_doc_text(path)
        lower_text = text.lower()
        assert "Trino private preview" in text
        assert "Apache Impala" in text
        assert "public" in lower_text
        assert "engine support" in lower_text
        assert "live collection" in lower_text
        assert "browser/report output" in lower_text
        assert "Query Doctor-generated SQL" in text


def test_trino_private_preview_release_path_has_russian_companion():
    text = _normalized_doc_text(TRINO_PRIVATE_PREVIEW_RU_DOC)

    for required in (
        "Trino private preview release path",
        "раннюю закрытую интеграцию с тестовым кластером",
        "Production engine support остается Apache Impala only",
        "bounded Kerberos/SPNEGO smoke",
        "sanitized evidence-package intake",
        "Не добавлены Trino engine adapter",
    ):
        assert required in text


def _normalized_doc_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("`", "")
    return " ".join(text.split())
