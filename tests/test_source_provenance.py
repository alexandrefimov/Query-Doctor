from __future__ import annotations

from query_doctor.analyzer.facts_renderer import render_source_provenance
from query_doctor.analyzer.source_provenance import build_source_provenance


def test_source_provenance_redacts_metadata_error_details() -> None:
    provenance = build_source_provenance(
        {
            "table_metadata_context": {
                "context_file": "error",
                "error": (
                    "failed to read /Users/example/query-doctor/cases/case-001; "
                    "SHOW CREATE TABLE private.customer_orders token=secret-value"
                ),
            },
        }
    )

    text = "\n".join(render_source_provenance({"source_provenance": provenance}))

    assert "Metadata context could not be read; source availability is unavailable." in text
    assert "/Users/example" not in text
    assert "SHOW CREATE TABLE" not in text
    assert "private.customer_orders" not in text
    assert "secret-value" not in text
