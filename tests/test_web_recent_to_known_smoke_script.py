import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional


REPO_DIR = Path(__file__).resolve().parents[1]
SCRIPT = REPO_DIR / "scripts" / "query-doctor-web-recent-to-known-smoke"
HELPER = REPO_DIR / "scripts" / "query-doctor-known-query-input-from-summary"
QUERY_ID = "1111111111111111:2222222222222222"
STALE_QUERY_ID = "3333333333333333:4444444444444444"


def run_wrapper(args, *, home: Path, env: Optional[dict[str, str]] = None):
    merged_env = dict(os.environ)
    for name in (
        "QD_CONFIG",
        "KRB5CCNAME",
        "QD_CREDS_DIR",
        "QD_KEYTAB",
        "QD_KRB5_PRINCIPAL",
        "KRB5_PRINCIPAL",
        "CM_USERNAME",
        "CM_USER",
        "CM_PASSWORD",
        "CM_TOKEN",
    ):
        merged_env.pop(name, None)
    merged_env["HOME"] = str(home)
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


def write_fake_recent_script(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
Path(os.environ["FAKE_RECENT_ARGS"]).write_text(json.dumps(args), encoding="utf-8")
if os.environ.get("FAKE_RECENT_FAIL"):
    print("[web-recent-smoke] raw query 1111111111111111:2222222222222222 at /tmp/raw-profile", file=sys.stderr)
    raise SystemExit(2)
if "--dry-run" in args:
    print("[web-recent-smoke] dry_run=ok")
    print("[web-recent-smoke] provider=direct-impala")
    raise SystemExit(0)
if not os.environ.get("FAKE_SKIP_SUMMARY"):
    root = Path(os.environ["FAKE_SUMMARY_ROOT"])
    job_id = os.environ["FAKE_JOB_ID"]
    summary_dir = root / f"query-doctor-web-batch-{job_id}"
    summary_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "selected_count": 1,
        "summaries_inspected": 2,
        "cases": [
            {
                "case_index": 1,
                "query_id": os.environ["FAKE_QUERY_ID"],
                "collection_status": "ok",
                "analysis_status": "ok",
                "metadata_status": os.environ.get("FAKE_METADATA_STATUS", "collected"),
                "metadata_refreshed": True,
                "collectable_metadata_table_count": 1,
                "collected_metadata_table_count": 1,
            }
        ],
    }
    (summary_dir / "batch_summary.json").write_text(json.dumps(summary), encoding="utf-8")
print("[web-recent-smoke] web=ready")
print("[web-recent-smoke] scan=provider=direct-impala selected=1 cases=1 metadata_collected=1 metadata_refreshed=1 collection_ok=1 analysis_ok=1")
print("[web-recent-smoke] details=ok")
print("[web-recent-smoke] ok")
""",
        encoding="utf-8",
    )
    os.chmod(path, 0o755)


def write_fake_known_script(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
Path(os.environ["FAKE_KNOWN_ARGS"]).write_text(json.dumps(args), encoding="utf-8")
query_file = Path(args[args.index("--query-id-file") + 1])
Path(os.environ["FAKE_KNOWN_QUERY"]).write_text(query_file.read_text(encoding="utf-8"), encoding="utf-8")
print("[web-known-query-smoke] web=ready")
print("[web-known-query-smoke] analysis=ok")
print("[web-known-query-smoke] details=ok")
print("[web-known-query-smoke] python_report=ok")
print("[web-known-query-smoke] ok")
""",
        encoding="utf-8",
    )
    os.chmod(path, 0o755)


def write_stale_summary(root: Path) -> None:
    summary_dir = root / "query-doctor-web-batch-00000000000000000000000000000000"
    summary_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "cases": [
            {
                "case_index": 1,
                "query_id": STALE_QUERY_ID,
                "collection_status": "ok",
                "analysis_status": "ok",
                "metadata_status": "collected",
                "metadata_refreshed": True,
                "collectable_metadata_table_count": 1,
                "collected_metadata_table_count": 1,
            }
        ]
    }
    (summary_dir / "batch_summary.json").write_text(json.dumps(summary), encoding="utf-8")


def base_args(tmp_path: Path, recent_script: Path, known_script: Path) -> list[str]:
    return [
        "--recent-smoke-script",
        str(recent_script),
        "--input-helper-script",
        str(HELPER),
        "--known-query-smoke-script",
        str(known_script),
        "--summary-search-root",
        str(tmp_path / "summary-root"),
        "--cluster",
        "direct-impala",
        "--window-minutes",
        "43200",
        "--limit",
        "5",
        "--metadata-top-limit",
        "3",
        "--query-type",
        "QUERY",
        "--timeout-sec",
        "10",
        "--poll-interval-sec",
        "0.05",
    ]


def test_recent_to_known_chain_selects_new_summary_without_echoing_identifiers(tmp_path):
    home = tmp_path / "home"
    summary_root = tmp_path / "summary-root"
    write_stale_summary(summary_root)
    recent_script = tmp_path / "fake-recent"
    known_script = tmp_path / "fake-known"
    write_fake_recent_script(recent_script)
    write_fake_known_script(known_script)
    recent_args = tmp_path / "recent-args.json"
    known_args = tmp_path / "known-args.json"
    known_query = tmp_path / "known-query.txt"

    result = run_wrapper(
        base_args(tmp_path, recent_script, known_script),
        home=home,
        env={
            "FAKE_RECENT_ARGS": str(recent_args),
            "FAKE_KNOWN_ARGS": str(known_args),
            "FAKE_KNOWN_QUERY": str(known_query),
            "FAKE_SUMMARY_ROOT": str(summary_root),
            "FAKE_JOB_ID": "1234567890abcdef1234567890abcdef",
            "FAKE_QUERY_ID": QUERY_ID,
        },
    )

    combined_output = result.stdout + result.stderr
    assert result.returncode == 0, combined_output
    assert os.access(SCRIPT, os.X_OK)
    assert "[recent-to-known-smoke] warning=large_window" in result.stdout
    assert "[recent-to-known-smoke] summary=selected" in result.stdout
    assert "known_query_input=selected" in result.stdout
    assert "selected_metadata_status=collected" in result.stdout
    assert "[web-known-query-smoke] ok" in result.stdout
    assert "[recent-to-known-smoke] query_id_input=removed" in result.stdout
    assert "[recent-to-known-smoke] ok" in result.stdout
    assert known_query.read_text(encoding="utf-8") == QUERY_ID + "\n"
    assert QUERY_ID not in combined_output
    assert STALE_QUERY_ID not in combined_output
    assert str(summary_root) not in combined_output
    assert str(tmp_path) not in combined_output

    recent_argv = json.loads(recent_args.read_text(encoding="utf-8"))
    assert recent_argv[recent_argv.index("--cluster") + 1] == "direct-impala"
    assert recent_argv[recent_argv.index("--window-minutes") + 1] == "43200"
    assert recent_argv[recent_argv.index("--limit") + 1] == "5"
    assert recent_argv[recent_argv.index("--metadata-top-limit") + 1] == "3"
    assert recent_argv[recent_argv.index("--query-type") + 1] == "QUERY"

    known_argv = json.loads(known_args.read_text(encoding="utf-8"))
    assert "--require-metadata" in known_argv
    assert "--query-id" not in known_argv
    assert known_argv[known_argv.index("--cluster") + 1] == "direct-impala"
    query_file = Path(known_argv[known_argv.index("--query-id-file") + 1])
    assert not query_file.exists()


def test_recent_to_known_accepts_partial_metadata_with_collected_tables(tmp_path):
    home = tmp_path / "home"
    summary_root = tmp_path / "summary-root"
    recent_script = tmp_path / "fake-recent"
    known_script = tmp_path / "fake-known"
    write_fake_recent_script(recent_script)
    write_fake_known_script(known_script)
    known_query = tmp_path / "known-query.txt"

    result = run_wrapper(
        base_args(tmp_path, recent_script, known_script),
        home=home,
        env={
            "FAKE_RECENT_ARGS": str(tmp_path / "recent-args.json"),
            "FAKE_KNOWN_ARGS": str(tmp_path / "known-args.json"),
            "FAKE_KNOWN_QUERY": str(known_query),
            "FAKE_SUMMARY_ROOT": str(summary_root),
            "FAKE_JOB_ID": "1234567890abcdef1234567890abcdef",
            "FAKE_QUERY_ID": QUERY_ID,
            "FAKE_METADATA_STATUS": "partial",
        },
    )

    combined_output = result.stdout + result.stderr
    assert result.returncode == 0, combined_output
    assert "selected_metadata_status=partial" in result.stdout
    assert "[web-known-query-smoke] ok" in result.stdout
    assert known_query.read_text(encoding="utf-8") == QUERY_ID + "\n"
    assert QUERY_ID not in combined_output
    assert str(tmp_path) not in combined_output


def test_recent_to_known_can_require_collected_metadata(tmp_path):
    home = tmp_path / "home"
    summary_root = tmp_path / "summary-root"
    recent_script = tmp_path / "fake-recent"
    known_script = tmp_path / "fake-known"
    write_fake_recent_script(recent_script)
    write_fake_known_script(known_script)

    result = run_wrapper(
        [*base_args(tmp_path, recent_script, known_script), "--require-collected-metadata"],
        home=home,
        env={
            "FAKE_RECENT_ARGS": str(tmp_path / "recent-args.json"),
            "FAKE_KNOWN_ARGS": str(tmp_path / "known-args.json"),
            "FAKE_KNOWN_QUERY": str(tmp_path / "known-query.txt"),
            "FAKE_SUMMARY_ROOT": str(summary_root),
            "FAKE_JOB_ID": "1234567890abcdef1234567890abcdef",
            "FAKE_QUERY_ID": QUERY_ID,
            "FAKE_METADATA_STATUS": "partial",
        },
    )

    combined_output = result.stdout + result.stderr
    assert result.returncode == 2
    assert "No successful metadata-backed Known Query ID candidate" in result.stderr
    assert QUERY_ID not in combined_output
    assert str(tmp_path) not in combined_output


def test_recent_to_known_dry_run_only_runs_recent_child(tmp_path):
    home = tmp_path / "home"
    recent_script = tmp_path / "fake-recent"
    known_script = tmp_path / "fake-known"
    write_fake_recent_script(recent_script)
    write_fake_known_script(known_script)
    recent_args = tmp_path / "recent-args.json"
    known_args = tmp_path / "known-args.json"

    result = run_wrapper(
        [*base_args(tmp_path, recent_script, known_script), "--dry-run"],
        home=home,
        env={
            "FAKE_RECENT_ARGS": str(recent_args),
            "FAKE_KNOWN_ARGS": str(known_args),
            "FAKE_KNOWN_QUERY": str(tmp_path / "known-query.txt"),
            "FAKE_SUMMARY_ROOT": str(tmp_path / "summary-root"),
            "FAKE_JOB_ID": "1234567890abcdef1234567890abcdef",
            "FAKE_QUERY_ID": QUERY_ID,
        },
    )

    combined_output = result.stdout + result.stderr
    assert result.returncode == 0, combined_output
    assert "[recent-to-known-smoke] dry_run=ok" in result.stdout
    assert "[recent-to-known-smoke] known_query=skipped" in result.stdout
    assert QUERY_ID not in combined_output
    recent_argv = json.loads(recent_args.read_text(encoding="utf-8"))
    assert "--dry-run" in recent_argv
    assert not known_args.exists()


def test_recent_to_known_reports_missing_summary_without_path_leak(tmp_path):
    home = tmp_path / "home"
    recent_script = tmp_path / "fake-recent"
    known_script = tmp_path / "fake-known"
    write_fake_recent_script(recent_script)
    write_fake_known_script(known_script)

    result = run_wrapper(
        base_args(tmp_path, recent_script, known_script),
        home=home,
        env={
            "FAKE_RECENT_ARGS": str(tmp_path / "recent-args.json"),
            "FAKE_KNOWN_ARGS": str(tmp_path / "known-args.json"),
            "FAKE_KNOWN_QUERY": str(tmp_path / "known-query.txt"),
            "FAKE_SUMMARY_ROOT": str(tmp_path / "summary-root"),
            "FAKE_JOB_ID": "1234567890abcdef1234567890abcdef",
            "FAKE_QUERY_ID": QUERY_ID,
            "FAKE_SKIP_SUMMARY": "1",
        },
    )

    combined_output = result.stdout + result.stderr
    assert result.returncode == 2
    assert "no new retained batch summary" in result.stderr
    assert QUERY_ID not in combined_output
    assert str(tmp_path) not in combined_output


def test_recent_to_known_redacts_child_output_on_failure(tmp_path):
    home = tmp_path / "home"
    recent_script = tmp_path / "fake-recent"
    known_script = tmp_path / "fake-known"
    write_fake_recent_script(recent_script)
    write_fake_known_script(known_script)

    result = run_wrapper(
        base_args(tmp_path, recent_script, known_script),
        home=home,
        env={
            "FAKE_RECENT_ARGS": str(tmp_path / "recent-args.json"),
            "FAKE_KNOWN_ARGS": str(tmp_path / "known-args.json"),
            "FAKE_KNOWN_QUERY": str(tmp_path / "known-query.txt"),
            "FAKE_SUMMARY_ROOT": str(tmp_path / "summary-root"),
            "FAKE_JOB_ID": "1234567890abcdef1234567890abcdef",
            "FAKE_QUERY_ID": QUERY_ID,
            "FAKE_RECENT_FAIL": "1",
        },
    )

    combined_output = result.stdout + result.stderr
    assert result.returncode == 2
    assert "<query-id hidden>" in combined_output
    assert "<path hidden>" in combined_output
    assert QUERY_ID not in combined_output
    assert "/tmp/raw-profile" not in combined_output
