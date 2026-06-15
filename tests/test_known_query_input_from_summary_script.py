import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional


REPO_DIR = Path(__file__).resolve().parents[1]
SCRIPT = REPO_DIR / "scripts" / "query-doctor-known-query-input-from-summary"
QUERY_A = "1111111111111111:2222222222222222"
QUERY_B = "3333333333333333:4444444444444444"


def run_helper(args, *, env: Optional[dict[str, str]] = None):
    merged_env = dict(os.environ)
    if env:
        merged_env.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=REPO_DIR,
        env=merged_env,
        text=True,
        capture_output=True,
        check=False,
    )


def write_summary(path: Path, cases: list[dict[str, object]]) -> Path:
    path.write_text(
        json.dumps({"mode": "recent-query-batch", "cases": cases}),
        encoding="utf-8",
    )
    return path


def metadata_case(
    query_id: str,
    *,
    status: str,
    collected_tables: int,
    case_index: int,
) -> dict[str, object]:
    return {
        "case_index": case_index,
        "query_id": query_id,
        "collection_status": "ok",
        "analysis_status": "ok",
        "metadata_status": status,
        "metadata_refreshed": True,
        "collectable_metadata_table_count": max(collected_tables, 1),
        "collected_metadata_table_count": collected_tables,
    }


def test_writes_collected_metadata_query_id_without_echoing_identifiers(tmp_path):
    summary = write_summary(
        tmp_path / "batch_summary.json",
        [
            metadata_case(QUERY_A, status="partial", collected_tables=3, case_index=1),
            metadata_case(QUERY_B, status="collected", collected_tables=1, case_index=2),
        ],
    )
    out = tmp_path / "query-id.input"

    result = run_helper(["--summary", str(summary), "--out", str(out)])

    combined_output = result.stdout + result.stderr
    assert result.returncode == 0, combined_output
    assert out.read_text(encoding="utf-8") == QUERY_B + "\n"
    assert "known_query_input=selected" in result.stdout
    assert "cases_scanned=2" in result.stdout
    assert "metadata_candidates=2" in result.stdout
    assert "selected_metadata_status=collected" in result.stdout
    assert "output=written" in result.stdout
    assert QUERY_A not in combined_output
    assert QUERY_B not in combined_output
    assert str(summary) not in combined_output
    assert str(out) not in combined_output


def test_accepts_partial_metadata_when_no_collected_case(tmp_path):
    summary = write_summary(
        tmp_path / "batch_summary.json",
        [metadata_case(QUERY_A, status="partial", collected_tables=2, case_index=1)],
    )
    out = tmp_path / "query-id.input"

    result = run_helper(["--summary", str(summary), "--out", str(out)])

    assert result.returncode == 0, result.stderr
    assert out.read_text(encoding="utf-8") == QUERY_A + "\n"
    assert "selected_metadata_status=partial" in result.stdout


def test_require_collected_rejects_partial_without_echoing_query_id(tmp_path):
    summary = write_summary(
        tmp_path / "batch_summary.json",
        [metadata_case(QUERY_A, status="partial", collected_tables=2, case_index=1)],
    )
    out = tmp_path / "query-id.input"

    result = run_helper(["--summary", str(summary), "--out", str(out), "--require-collected"])

    combined_output = result.stdout + result.stderr
    assert result.returncode == 2
    assert not out.exists()
    assert "No successful metadata-backed Known Query ID candidate" in result.stderr
    assert "cases_scanned=1" in result.stderr
    assert "query_id_candidates=1" in result.stderr
    assert "metadata_candidates=0" in result.stderr
    assert QUERY_A not in combined_output
    assert str(summary) not in combined_output
    assert str(out) not in combined_output


def test_rejects_non_tmp_output_unless_explicitly_allowed(tmp_path):
    summary = write_summary(
        tmp_path / "batch_summary.json",
        [metadata_case(QUERY_A, status="collected", collected_tables=1, case_index=1)],
    )
    out = REPO_DIR / "known-query.input"

    result = run_helper(["--summary", str(summary), "--out", str(out)])

    combined_output = result.stdout + result.stderr
    assert result.returncode == 2
    assert not out.exists()
    assert "Output path must be under a system temporary directory" in result.stderr
    assert QUERY_A not in combined_output
    assert str(summary) not in combined_output
    assert str(out) not in combined_output


def test_dry_run_selects_without_writing(tmp_path):
    summary = write_summary(
        tmp_path / "batch_summary.json",
        [metadata_case(QUERY_A, status="collected", collected_tables=1, case_index=1)],
    )
    out = tmp_path / "query-id.input"

    result = run_helper(["--summary", str(summary), "--out", str(out), "--dry-run"])

    combined_output = result.stdout + result.stderr
    assert result.returncode == 0, combined_output
    assert not out.exists()
    assert "output=dry_run" in result.stdout
    assert QUERY_A not in combined_output
