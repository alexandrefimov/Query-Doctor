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


def write_config(path: Path, impala_shell: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "clusters": [
                    {
                        "id": "direct",
                        "metadata_coordinator": "coordinator.example.com:21000",
                        "metadata_impala_shell": str(impala_shell),
                        "metadata_auth": "kerberos",
                        "metadata_protocol": "beeswax",
                        "metadata_kerberos_service_name": "hive",
                        "metadata_kerberos_host_fqdn": "coordinator.example.com",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def write_fake_impala_shell(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import sys

sql = sys.argv[sys.argv.index("-q") + 1] if "-q" in sys.argv else ""
if "valid_fact" in sql:
    print("fake metadata ok for valid_fact")
    raise SystemExit(0)
print("fake metadata failed for missing_fact", file=sys.stderr)
raise SystemExit(1)
""",
        encoding="utf-8",
    )
    os.chmod(path, 0o755)


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


def test_table_backed_smoke_query_metadata_validation_skips_stale_candidate(tmp_path):
    root = tmp_path / "cases"
    out = tmp_path / "query.sql"
    config = tmp_path / "config.json"
    fake_shell = tmp_path / "fake-impala-shell"
    write_fake_impala_shell(fake_shell)
    write_config(config, fake_shell)
    stale = root / "case-002" / "analysis.json"
    valid = root / "case-001" / "analysis.json"
    write_analysis(
        stale,
        {"table_metadata_context": {"tables": [{"table": "analytics.missing_fact"}]}},
    )
    write_analysis(
        valid,
        {"table_metadata_context": {"tables": [{"table": "mart.valid_fact"}]}},
    )
    os.utime(valid, (1000, 1000))
    os.utime(stale, (2000, 2000))

    result = run_helper(
        [
            "--search-root",
            str(root),
            "--out",
            str(out),
            "--validate-with-metadata",
            "--config",
            str(config),
            "--cluster",
            "direct",
        ]
    )

    combined_output = result.stdout + result.stderr
    assert result.returncode == 0, combined_output
    assert "metadata_validation=enabled" in result.stdout
    assert "metadata_validation_attempts=2" in result.stdout
    assert "analytics" not in combined_output
    assert "missing_fact" not in combined_output
    assert "mart" not in combined_output
    assert "valid_fact" not in combined_output
    assert str(root) not in combined_output
    assert str(out) not in combined_output
    assert str(config) not in combined_output
    assert "fake metadata failed" not in combined_output
    sql = out.read_text(encoding="utf-8")
    assert "FROM `mart`.`valid_fact`" in sql
    assert "missing_fact" not in sql


def test_table_backed_smoke_query_metadata_validation_fails_safely(tmp_path):
    root = tmp_path / "cases"
    out = tmp_path / "query.sql"
    config = tmp_path / "config.json"
    fake_shell = tmp_path / "fake-impala-shell"
    write_fake_impala_shell(fake_shell)
    write_config(config, fake_shell)
    write_analysis(
        root / "case-001" / "analysis.json",
        {"table_metadata_context": {"tables": [{"table": "analytics.missing_fact"}]}},
    )

    result = run_helper(
        [
            "--search-root",
            str(root),
            "--out",
            str(out),
            "--validate-with-metadata",
            "--config",
            str(config),
            "--cluster",
            "direct",
        ]
    )

    combined_output = result.stdout + result.stderr
    assert result.returncode == 2
    assert "No candidate table passed metadata validation" in result.stderr
    assert "analytics" not in combined_output
    assert "missing_fact" not in combined_output
    assert "fake metadata failed" not in combined_output
    assert str(root) not in combined_output
    assert str(out) not in combined_output
    assert str(config) not in combined_output
    assert not out.exists()
