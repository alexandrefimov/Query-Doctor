import json
import os
import subprocess
import sys
from pathlib import Path


REPO_DIR = Path(__file__).resolve().parents[1]
SCRIPT = REPO_DIR / "scripts" / "query-doctor-table-backed-smoke-query"


def run_helper(args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=REPO_DIR,
        text=True,
        capture_output=True,
        check=False,
    )


def write_analysis(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_table_backed_smoke_query_writes_sql_without_echoing_table_or_paths(tmp_path):
    root = tmp_path / "cases"
    out = tmp_path / "generated" / "query.sql"
    write_analysis(
        root / "case-001" / "analysis.json",
        {
            "table_metadata_context": {
                "tables": [
                    {"table": "<db>.<table>"},
                    {"table": "db.table"},
                    {"table": "analytics.events_fact"},
                ]
            },
            "referenced_tables": ["database.table", "redacted.hidden"],
        },
    )

    result = run_helper(["--search-root", str(root), "--out", str(out), "--limit", "250"])

    combined_output = result.stdout + result.stderr
    assert result.returncode == 0, combined_output
    assert os.access(SCRIPT, os.X_OK)
    assert "[table-backed-smoke-query] generated=ok" in result.stdout
    assert "[table-backed-smoke-query] candidate_tables=1" in result.stdout
    assert "[table-backed-smoke-query] output=written" in result.stdout
    assert "analytics" not in combined_output
    assert "events_fact" not in combined_output
    assert "db.table" not in combined_output
    assert str(root) not in combined_output
    assert str(out) not in combined_output

    sql = out.read_text(encoding="utf-8")
    assert "FROM `analytics`.`events_fact`" in sql
    assert "LIMIT 250" in sql
    assert "db.table" not in sql
    assert "<db>" not in sql
    assert "<table>" not in sql


def test_table_backed_smoke_query_fails_without_nonplaceholder_table(tmp_path):
    root = tmp_path / "cases"
    out = tmp_path / "query.sql"
    write_analysis(
        root / "case-001" / "analysis.json",
        {
            "table_metadata_context": {
                "tables": [
                    {"table": "<db>.<table>"},
                    {"table": "db.table"},
                    {"table": "unknown.table"},
                ]
            },
            "referenced_tables": ["redacted.hidden"],
        },
    )

    result = run_helper(["--search-root", str(root), "--out", str(out)])

    combined_output = result.stdout + result.stderr
    assert result.returncode == 2
    assert "No non-placeholder table-backed metadata reference was found" in result.stderr
    assert "db.table" not in combined_output
    assert "unknown.table" not in combined_output
    assert str(root) not in combined_output
    assert str(out) not in combined_output
    assert not out.exists()


def test_table_backed_smoke_query_prefers_latest_analysis_candidate(tmp_path):
    root = tmp_path / "cases"
    out = tmp_path / "query.sql"
    older = root / "case-001" / "analysis.json"
    newer = root / "case-002" / "analysis.json"
    write_analysis(
        older,
        {"table_metadata_context": {"tables": [{"table": "analytics.old_fact"}]}},
    )
    write_analysis(
        newer,
        {"table_metadata_context": {"tables": [{"table": "mart.new_fact"}]}},
    )
    os.utime(older, (1000, 1000))
    os.utime(newer, (2000, 2000))

    result = run_helper(["--search-root", str(root), "--out", str(out)])

    assert result.returncode == 0, result.stdout + result.stderr
    sql = out.read_text(encoding="utf-8")
    assert "FROM `mart`.`new_fact`" in sql
    assert "old_fact" not in sql
    assert "mart" not in result.stdout
    assert "new_fact" not in result.stdout
