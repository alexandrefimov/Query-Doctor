from __future__ import annotations

import json

from query_doctor.web.optimizer_validation import (
    EXTERNAL_REWRITE_SQL_FIELD,
    validate_external_optimizer_rewrite,
)


def test_external_optimizer_validation_rejects_symlinked_facts_outside_case_dir(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    source_sql = "SELECT a FROM db.source_table WHERE ds = 20260504"
    outside_facts = tmp_path / "analysis_facts.md"
    outside_facts.write_text("FACTS\n", encoding="utf-8")
    (case_dir / "analysis_facts.md").symlink_to(outside_facts)
    (case_dir / "cm_metadata.json").write_text(
        json.dumps({"statement": source_sql}), encoding="utf-8"
    )

    result = validate_external_optimizer_rewrite(
        case_dir,
        {EXTERNAL_REWRITE_SQL_FIELD: [f"{source_sql};\n"]},
    )

    assert result["status"] == "unavailable"
    assert result["items"] == ["Source SQL is unavailable or outside optimizer validation scope."]
