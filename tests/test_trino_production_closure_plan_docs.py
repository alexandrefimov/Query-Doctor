from pathlib import Path

from scripts import audit_trino_support_gap_matrix as audit


ENGINE_SUPPORT_MATRIX = (
    Path(__file__).resolve().parents[1] / "docs" / "engine-support-gap-matrix.md"
)


def test_trino_broader_production_closure_plan_is_documented() -> None:
    text = ENGINE_SUPPORT_MATRIX.read_text(encoding="utf-8")
    normalized_text = " ".join(text.split())

    assert "## Broader Trino Production Closure Plan" in text
    assert "broader_production_closure_status=bounded_production_claim_ready" in text
    assert "no SQL execution" in text
    assert "This is not Impala parity and not shared/broader Trino expansion" in normalized_text
    assert "### Broad Production Promotion Slice Plan" in text
    assert "Broad Trino production support is a release claim" in text
    assert "not a synonym for automatic Impala parity" in normalized_text
    assert (
        "Running scans, query-history crawling, LLM reports, Query Optimizer jobs"
        in normalized_text
    )
    assert "generated Trino SQL, and SQL execution remain unsupported" in normalized_text
    assert "Freeze the broad Trino production support definition" in normalized_text
    assert "Implement production collector/source contracts" in normalized_text
    assert "Implement and machine-check bounded production readers" in normalized_text
    assert "explicit reader modules, CLI roles, capability surfaces" in normalized_text
    assert "Retain representative raw-free real-cluster evidence suites" in normalized_text
    assert "Add query-linked resource-group, stage, task, and split coverage" in normalized_text
    assert "Add operator, connector, OpenTelemetry, OpenMetrics, JMX" in normalized_text
    assert "Promote product metadata collection" in normalized_text
    assert (
        "Wire accepted product metadata facts into diagnosis, Details, Python Report"
        in normalized_text
    )
    assert "Decide the Trino report/optimizer support boundary" in normalized_text
    assert "Close shared/non-local deployment readiness" in normalized_text
    assert "Run a browser/report regression sweep" in normalized_text
    assert "Perform the final support-claim update" in normalized_text
    for gate in audit.TRINO_BROADER_PRODUCTION_CLOSURE_GATES:
        assert gate in text
