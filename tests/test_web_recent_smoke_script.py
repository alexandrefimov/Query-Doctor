import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Optional


REPO_DIR = Path(__file__).resolve().parents[1]
SCRIPT = REPO_DIR / "scripts" / "query-doctor-web-recent-smoke"


def run_smoke(args, *, home: Path, env: Optional[dict[str, str]] = None):
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


def write_config(home: Path, payload: dict) -> Path:
    config_dir = home / ".qdcreds"
    config_dir.mkdir(parents=True)
    config = config_dir / "query-doctor-config.json"
    config.write_text(json.dumps(payload), encoding="utf-8")
    return config


def free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_web_recent_smoke_dry_run_cm_cluster_without_host_leak(tmp_path):
    home = tmp_path / "home"
    config = write_config(
        home,
        {
            "clusters": [
                {
                    "id": "cm-prod",
                    "label": "Cloudera PROD",
                    "query_profile_source": "cm",
                    "cm_url": "https://localhost:7183",
                    "cluster": "cluster-alpha",
                    "service": "impala",
                }
            ]
        },
    )

    result = run_smoke(
        ["--dry-run", "--config", str(config), "--min-duration-sec", "10"],
        home=home,
    )

    combined_output = result.stdout + result.stderr
    assert result.returncode == 0, combined_output
    assert os.access(SCRIPT, os.X_OK)
    assert "dry_run=ok" in result.stdout
    assert "provider=cloudera-manager" in result.stdout
    assert "min_duration_sec=10" in result.stdout
    assert "localhost:7183" not in combined_output
    assert "cluster-alpha" not in combined_output
    assert str(config) not in combined_output


def test_web_recent_smoke_requires_cluster_when_multiple_clusters(tmp_path):
    home = tmp_path / "home"
    write_config(
        home,
        {
            "clusters": [
                {
                    "id": "cm-prod",
                    "label": "Cloudera PROD",
                    "query_profile_source": "cm",
                    "cm_url": "https://localhost:7183",
                },
                {
                    "id": "direct-impala",
                    "label": "Impala k8s prod",
                    "query_profile_source": "impala",
                    "impala_profile_hosts": ["localhost"],
                },
            ]
        },
    )

    result = run_smoke(["--dry-run"], home=home)

    assert result.returncode == 2
    assert "choose one with --cluster" in result.stderr
    assert "cm-prod (Cloudera PROD): cloudera-manager" in result.stderr
    assert "direct-impala (Impala k8s prod): direct-impala" in result.stderr
    assert "localhost:7183" not in result.stderr


def write_fake_web_wrapper(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

host = "127.0.0.1"
port = None
args = sys.argv[1:]
for index, value in enumerate(args):
    if value == "--host":
        host = args[index + 1]
    if value == "--port":
        port = int(args[index + 1])
if port is None:
    raise SystemExit(2)

job_id = os.environ["FAKE_JOB_ID"]
capture = Path(os.environ["FAKE_FORM_CAPTURE"])
summary_dir = Path("/tmp") / f"query-doctor-web-batch-{job_id}"

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
            return
        if self.path == f"/jobs/{job_id}/status":
            payload = {"status": "ok", "stage": "Done", "progress": 100}
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/batch/case/case-001":
            body = b"<html><body><h1>Details</h1><p>Metadata collected</p></body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path != "/batch/run":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", "0"))
        form = parse_qs(self.rfile.read(length).decode(), keep_blank_values=True)
        capture.write_text(json.dumps({key: values[0] for key, values in form.items()}))
        summary_dir.mkdir(parents=True, exist_ok=True)
        summary = json.loads(os.environ.get("FAKE_SUMMARY_JSON", "null")) or {
            "selected_count": 1,
            "summaries_inspected": 2,
            "candidate_exclusion_count": 1,
            "query_type_filter": "QUERY",
            "duration_filter": ">= 10 sec",
            "candidate_reason_counts": {
                "selected: SELECT-like user query": 1,
                "eligible but not selected because recent-select limit was reached": 1
            },
            "candidate_reason_sql_verb_counts": {
                "selected: SELECT-like user query": {"SELECT": 1},
                "eligible but not selected because recent-select limit was reached": {"WITH": 1}
            },
            "cases": [
                {
                    "case_index": 1,
                    "collection_status": "ok",
                    "analysis_status": "ok",
                    "metadata_status": "collected",
                    "metadata_refreshed": True,
                    "collectable_metadata_table_count": 1,
                    "collected_metadata_table_count": 1
                }
            ]
        }
        (summary_dir / "batch_summary.json").write_text(json.dumps(summary))
        self.send_response(303)
        self.send_header("Location", f"/jobs/{job_id}")
        self.end_headers()

ThreadingHTTPServer((host, port), Handler).serve_forever()
""",
        encoding="utf-8",
    )
    os.chmod(path, 0o755)


def test_web_recent_smoke_runs_cm_form_and_checks_summary(tmp_path):
    home = tmp_path / "home"
    config = write_config(
        home,
        {
            "clusters": [
                {
                    "id": "cm-prod",
                    "label": "Cloudera PROD",
                    "query_profile_source": "cm",
                    "cm_url": "https://localhost:7183",
                }
            ]
        },
    )
    wrapper = tmp_path / "fake-web-wrapper"
    write_fake_web_wrapper(wrapper)
    capture = tmp_path / "form.json"
    job_id = "1234567890abcdef1234567890abcdef"
    port = free_local_port()
    try:
        result = run_smoke(
            [
                "--config",
                str(config),
                "--web-wrapper",
                str(wrapper),
                "--port",
                str(port),
                "--timeout-sec",
                "10",
                "--poll-interval-sec",
                "0.05",
                "--min-duration-sec",
                "10",
                "--metadata-top-limit",
                "3",
                "--limit",
                "3",
            ],
            home=home,
            env={"FAKE_JOB_ID": job_id, "FAKE_FORM_CAPTURE": str(capture)},
        )
    finally:
        shutil.rmtree(Path("/tmp") / f"query-doctor-web-batch-{job_id}", ignore_errors=True)

    combined_output = result.stdout + result.stderr
    assert result.returncode == 0, combined_output
    assert "[web-recent-smoke] web=ready" in result.stdout
    assert "provider=cloudera-manager" in result.stdout
    assert "metadata_collected=1" in result.stdout
    assert "selection=selected=1 inspected=2 excluded=1 query_type=query" in result.stdout
    assert "[web-recent-smoke] details=ok" in result.stdout
    form = json.loads(capture.read_text(encoding="utf-8"))
    assert form["cluster_key"] == "cm-prod"
    assert form["scan_target"] == "finished"
    assert form["recent_window_minutes"] == "120"
    assert form["triage_profile_limit"] == "3"
    assert form["metadata_top_limit"] == "3"
    assert form["metadata_jobs"] == "1"
    assert form["parallelism"] == "2"
    assert form["query_type"] == "QUERY"
    assert form["min_duration_sec"] == "10.0"
    assert form["order"] == "duration-desc"
    assert str(config) not in combined_output


def test_web_recent_smoke_no_cases_prints_safe_selection_diagnostics(tmp_path):
    home = tmp_path / "home"
    config = write_config(
        home,
        {
            "clusters": [
                {
                    "id": "cm-prod",
                    "label": "Cloudera PROD",
                    "query_profile_source": "cm",
                    "cm_url": "https://localhost:7183",
                }
            ]
        },
    )
    wrapper = tmp_path / "fake-web-wrapper"
    write_fake_web_wrapper(wrapper)
    capture = tmp_path / "form.json"
    job_id = "abcdef1234567890abcdef1234567890"
    port = free_local_port()
    summary = {
        "selected_count": 0,
        "summaries_inspected": 400,
        "candidate_exclusion_count": 0,
        "query_type_filter": "QUERY",
        "duration_filter": "none",
        "scan_too_broad": True,
        "cases": [],
    }
    try:
        result = run_smoke(
            [
                "--config",
                str(config),
                "--web-wrapper",
                str(wrapper),
                "--port",
                str(port),
                "--timeout-sec",
                "10",
                "--poll-interval-sec",
                "0.05",
            ],
            home=home,
            env={
                "FAKE_JOB_ID": job_id,
                "FAKE_FORM_CAPTURE": str(capture),
                "FAKE_SUMMARY_JSON": json.dumps(summary),
            },
        )
    finally:
        shutil.rmtree(Path("/tmp") / f"query-doctor-web-batch-{job_id}", ignore_errors=True)

    combined_output = result.stdout + result.stderr
    assert result.returncode == 2
    assert "selected no cases" in result.stderr
    assert "selection=selected=0 inspected=400 excluded=400 query_type=query" in result.stdout
    assert "selection_note=scan_too_broad" in result.stdout
    assert "localhost:7183" not in combined_output
    assert str(config) not in combined_output
