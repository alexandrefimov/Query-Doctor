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
        "registered for bounded compact intake only",
        "no Recent, Details/trusted report, optimizer, metadata, raw event-log, or job-execution product workflow",
        "spark_one_application_handoff_summary_v1",
        "spark_product_surface_boundary_audit_v1",
        "optional matching handoff summaries",
        "optional matching product-surface summaries",
        "without reopening Spark",
        "same_application",
        "application-level job/stage/task summaries",
        "task-duration context",
        "SQL-execution-specific timing and failure facts",
        "raw-free diagnostic_lane summary",
        "Spark evidence-package validation, package handoff audits, and compact-readiness audits reject diagnostic-lane drift",
        "safe lane readiness/source-granularity/verification-scope counters",
    ):
        assert required in text


def test_spark_public_docs_index_package_code_under_experimental_boundary() -> None:
    code_map = _normalized(CODE_MAP)
    handoff = _normalized(CODEX_HANDOFF)
    ru_readme = _normalized(README_RU)
    ru_matrix = _normalized(RU_ENGINE_SUPPORT_MATRIX)

    assert "Spark compact History Server intake and evidence packages" in code_map
    assert "spark_evidence_package.py" in code_map
    assert "spark_evidence_package_requirements.py" in code_map
    assert "build_spark_evidence_package.py" in code_map
    assert "validate_spark_evidence_package.py" in code_map
    assert "audit_spark_evidence_handoff.py" in code_map
    assert "build_spark_handoff_suite_manifest.py" in code_map
    assert "spark_one_application_handoff.py" in code_map
    assert "build_spark_one_application_handoff_suite_manifest.py" in code_map
    assert "build_spark_evidence_package_from_one_application_suite.py" in code_map
    assert "audit_spark_product_surface_boundary.py" in code_map
    assert "audit_spark_support_boundary.py" in code_map
    assert "product-surface boundary audit over retained compact/diagnosis artifacts" in code_map
    assert "static support-boundary audit" in code_map
    assert "strict package-to-fixture handoff audit" in code_map
    assert "requirements printing from the Python-owned evidence package contract" in code_map
    assert "dev-only one-application handoff wrapper" in code_map
    assert "retained raw-free compact/diagnosis/boundary artifact triples" in code_map
    assert (
        "optional matching spark_one_application_handoff_summary_v1 and spark_product_surface_boundary_audit_v1 artifacts"
        in code_map
    )
    assert "optional raw-free compact readiness summary JSON" in code_map
    assert "one-application-suite-to-package bridge" in code_map
    assert "dev-only handoff-suite manifest metadata" in code_map
    assert "diagnostic-lane checked/readiness/source-granularity/verification-scope" in code_map
    assert "spark_support_boundary_audit_v1" in code_map
    assert "keeps the Spark adapter compact-only" in code_map
    assert "raw event-log download" in code_map

    assert "build/validation are registered bounded compact support surfaces" in handoff
    assert "accept only already compact samples for readiness handoff" in handoff
    assert "scripts/spark_one_application_handoff.py" in handoff
    assert "scripts/build_spark_one_application_handoff_suite_manifest.py" in handoff
    assert "scripts/build_spark_evidence_package_from_one_application_suite.py" in handoff
    assert "scripts/audit_spark_product_surface_boundary.py" in handoff
    assert "--one-application-handoff-suite-manifest" in handoff
    assert "write optional raw-free compact readiness summary JSON" in handoff
    assert "spark_product_surface_boundary_audit_v1 summaries" in handoff
    assert "optional retained product-surface summaries" in handoff
    assert "against the no-product-surface boundary" in handoff
    assert "sanitized package wrapper from explicit safe sample-case labels" in handoff
    assert "without becoming a product CLI" in handoff
    assert "dev-only handoff-suite manifest/audit" in handoff
    assert "retained raw-free handoff summary JSON" in handoff
    assert "diagnostic-lane checked/readiness/source-granularity/verification-scope" in handoff
    assert "spark_support_boundary_audit_v1" in handoff
    assert "not a Recent workflow" in handoff or "is not a Recent workflow" in handoff
    assert "production Spark support claim" in handoff

    assert "compact evidence-package build/validation" in ru_readme
    assert "no public Spark engine support" in ru_readme
    assert "registered bounded compact Spark History Server intake" in ru_matrix
    assert "не принимает raw event logs" in ru_matrix
    assert "diagnostic-lane drift" in ru_matrix


def _normalized(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("`", "")
    return " ".join(text.split())
