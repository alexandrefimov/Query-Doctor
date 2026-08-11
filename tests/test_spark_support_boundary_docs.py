from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENGINE_SUPPORT_MATRIX = ROOT / "docs" / "engine-support-gap-matrix.md"
CODE_MAP = ROOT / "docs" / "code-map.md"
CODEX_HANDOFF = ROOT / "docs" / "codex-handoff.md"
README_RU = ROOT / "README.ru.md"
RU_DOCS_INDEX = ROOT / "docs" / "i18n" / "ru" / "README.md"


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
    ru_support_boundary = _normalized(
        ROOT / "docs" / "i18n" / "ru" / "support-boundary.md"
    )
    ru_docs_index = _normalized(RU_DOCS_INDEX)

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

    assert "current support status" in handoff
    assert "exact command, script, registry, and route ownership" in handoff
    assert "Do not copy those inventories into this handoff" in handoff
    assert "Spark is bounded to compact History Server intake" in handoff
    assert "compact evidence-package build/validation/fixture export" in handoff
    assert (
        "retained raw-free readiness/product-surface/support audits listed in the support matrix"
        in handoff
    )
    assert "The Spark adapter remains compact-only" in handoff
    assert "no Recent workflow" in handoff
    assert "production Spark support claim" in handoff
    assert "same_application" in handoff
    assert (
        "application-level jobs, stages, scheduler delay, spill, and task-duration context"
        in handoff
    )

    assert "compact evidence-package build/validation" in ru_support_boundary
    assert "no public Spark engine support" in ru_support_boundary
    assert "engine deep-dive документы остаются English-only" in ru_docs_index
    assert "engine-support-gap-matrix.md" in ru_docs_index


def _normalized(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("`", "")
    return " ".join(text.split())
