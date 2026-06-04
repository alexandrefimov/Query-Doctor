from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENGINE_SUPPORT_MATRIX = ROOT / "docs" / "engine-support-gap-matrix.md"
RU_ENGINE_SUPPORT_MATRIX = ROOT / "docs" / "i18n" / "ru" / "engine-support-gap-matrix.md"
CODE_MAP = ROOT / "docs" / "code-map.md"
CODEX_HANDOFF = ROOT / "docs" / "codex-handoff.md"
README_RU = ROOT / "README.ru.md"


def test_spark_support_matrix_records_package_handoff_without_support_claim() -> None:
    text = _normalized(ENGINE_SUPPORT_MATRIX)

    for required in (
        "separate local Spark compact evidence-package build/validation/fixture export accepts only already compact samples for readiness work",
        "spark_evidence_package.py",
        "compact evidence-package readiness validation",
        "compact evidence-package build/validation without path or payload echo",
        "local compact evidence-package build/validation/fixture export is package-only over already accepted samples",
        "evidence-package schemas reject raw SQL",
        "no Recent workflow",
        "Spark support claim",
        "no engine registration or product workflow",
    ):
        assert required in text


def test_spark_public_docs_index_package_code_under_experimental_boundary() -> None:
    code_map = _normalized(CODE_MAP)
    handoff = _normalized(CODEX_HANDOFF)
    ru_readme = _normalized(README_RU)
    ru_matrix = _normalized(RU_ENGINE_SUPPORT_MATRIX)

    assert "Spark compact History Server intake and evidence packages" in code_map
    assert "spark_evidence_package.py" in code_map
    assert "build_spark_evidence_package.py" in code_map
    assert "validate_spark_evidence_package.py" in code_map
    assert "audit_spark_evidence_handoff.py" in code_map
    assert "strict package-to-fixture handoff audit" in code_map
    assert "no Spark engine registration" in code_map
    assert "raw event-log download" in code_map

    assert "compact evidence-package build/validation remain experimental research" in handoff
    assert "accept only already compact samples for readiness handoff" in handoff
    assert "not a Recent workflow" in handoff
    assert "Spark support claim" in handoff

    assert "compact evidence-package build/validation" in ru_readme
    assert "no public Spark engine support" in ru_readme
    assert "local compact evidence-package build/validation" in ru_matrix
    assert "не принимает raw event logs" in ru_matrix


def _normalized(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("`", "")
    return " ".join(text.split())
