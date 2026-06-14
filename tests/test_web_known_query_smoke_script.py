import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import quote


REPO_DIR = Path(__file__).resolve().parents[1]
SCRIPT = REPO_DIR / "scripts" / "query-doctor-web-known-query-smoke"
QUERY_ID = "1111111111111111:2222222222222222"


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


def write_query_id_file(tmp_path: Path, query_id: str = QUERY_ID) -> Path:
    query_id_file = tmp_path / "query-id.txt"
    query_id_file.write_text(f"{query_id}\n", encoding="utf-8")
    return query_id_file


def free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_web_known_query_smoke_dry_run_uses_query_id_file_without_echo(tmp_path):
    home = tmp_path / "home"
    config = write_config(
        home,
        {
            "clusters": [
                {
                    "id": "cluster-alpha",
                    "label": "Direct Impala",
                    "query_profile_source": "impala",
                    "impala_profile_hosts": ["impalad-1.example.com"],
                }
            ]
        },
    )
    query_id_file = write_query_id_file(tmp_path)

    result = run_smoke(
        ["--dry-run", "--config", str(config), "--query-id-file", str(query_id_file)],
        home=home,
    )

    combined_output = result.stdout + result.stderr
    assert result.returncode == 0, combined_output
    assert os.access(SCRIPT, os.X_OK)
    assert "dry_run=ok" in result.stdout
    assert "query_id=provided" in result.stdout
    assert QUERY_ID not in combined_output
    assert str(query_id_file) not in combined_output
    assert str(config) not in combined_output
    assert "impalad-1.example.com" not in combined_output
    assert "cluster-alpha" not in combined_output


def test_web_known_query_smoke_rejects_unsafe_query_id_file_without_echo(tmp_path):
    home = tmp_path / "home"
    write_config(home, {"clusters": []})
    query_id_file = tmp_path / "query-id.txt"
    query_id_file.write_text(f"{QUERY_ID}\n2222222222222222:3333333333333333\n", encoding="utf-8")

    result = run_smoke(["--dry-run", "--query-id-file", str(query_id_file)], home=home)

    combined_output = result.stdout + result.stderr
    assert result.returncode == 2
    assert "exactly one non-empty line" in result.stderr
    assert QUERY_ID not in combined_output
    assert "2222222222222222:3333333333333333" not in combined_output
    assert str(query_id_file) not in combined_output


def test_web_known_query_smoke_requires_cluster_when_multiple_direct_clusters(tmp_path):
    home = tmp_path / "home"
    write_config(
        home,
        {
            "clusters": [
                {
                    "id": "direct-a",
                    "label": "Primary direct",
                    "query_profile_source": "impala",
                    "impala_profile_hosts": ["impalad-a.example.test"],
                },
                {
                    "id": "direct-b",
                    "label": "Secondary direct",
                    "cluster_type": "impala",
                    "impala_profile_hosts": ["impalad-b.example.test"],
                },
            ]
        },
    )
    query_id_file = write_query_id_file(tmp_path)

    result = run_smoke(["--dry-run", "--query-id-file", str(query_id_file)], home=home)

    assert result.returncode == 2
    assert "choose one with --cluster" in result.stderr
    assert "direct-a (Primary direct)" in result.stderr
    assert "direct-b (Secondary direct)" in result.stderr
    assert "impalad-a.example.test" not in result.stderr
    assert "impalad-b.example.test" not in result.stderr
    assert QUERY_ID not in (result.stdout + result.stderr)


def write_fake_web_wrapper(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote

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
query_id = os.environ["FAKE_QUERY_ID"]
capture = Path(os.environ["FAKE_FORM_CAPTURE"])
job_error = os.environ.get("FAKE_JOB_ERROR", "")
details_path = "/query/details/" + quote(query_id, safe="")

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
            if job_error:
                payload = {
                    "status": "failed",
                    "stage": "Failed",
                    "progress": 100,
                    "error": job_error,
                    "result_html": "",
                }
                body = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            payload = {
                "status": "ok",
                "stage": "Done",
                "progress": 100,
                "result_html": "<section>Known Query ID analysis <span>Metadata</span><span>Collected</span></section>",
            }
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == details_path:
            body = b"<html><body><h1>Known Query ID details</h1><p>Metadata collected</p></body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == details_path + "/python-report":
            body = b"<html><body><h1>Validated Specific Query report</h1><p>Safe report</p></body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path != "/analyze":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", "0"))
        form = parse_qs(self.rfile.read(length).decode(), keep_blank_values=True)
        capture.write_text(json.dumps({key: values[0] for key, values in form.items()}))
        self.send_response(303)
        self.send_header("Location", f"/jobs/{job_id}")
        self.end_headers()

ThreadingHTTPServer((host, port), Handler).serve_forever()
""",
        encoding="utf-8",
    )
    os.chmod(path, 0o755)


def test_web_known_query_smoke_runs_analyze_details_and_report(tmp_path):
    home = tmp_path / "home"
    config = write_config(
        home,
        {
            "clusters": [
                {
                    "id": "direct-impala",
                    "label": "Direct Impala",
                    "query_profile_source": "impala",
                    "impala_profile_hosts": ["impalad-1.example.com"],
                }
            ]
        },
    )
    query_id_file = write_query_id_file(tmp_path)
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
                "--query-id-file",
                str(query_id_file),
                "--web-wrapper",
                str(wrapper),
                "--port",
                str(port),
                "--timeout-sec",
                "10",
                "--poll-interval-sec",
                "0.05",
                "--require-metadata",
            ],
            home=home,
            env={
                "FAKE_JOB_ID": job_id,
                "FAKE_QUERY_ID": QUERY_ID,
                "FAKE_FORM_CAPTURE": str(capture),
            },
        )
    finally:
        shutil.rmtree(Path("/tmp") / f"query-doctor-web-batch-{job_id}", ignore_errors=True)

    combined_output = result.stdout + result.stderr
    assert result.returncode == 0, combined_output
    assert "[web-known-query-smoke] web=ready" in result.stdout
    assert "[web-known-query-smoke] analysis=ok" in result.stdout
    assert "[web-known-query-smoke] details=ok" in result.stdout
    assert "[web-known-query-smoke] python_report=ok" in result.stdout
    assert "[web-known-query-smoke] ok" in result.stdout
    assert QUERY_ID not in combined_output
    assert quote(QUERY_ID, safe="") not in combined_output
    form = json.loads(capture.read_text(encoding="utf-8"))
    assert form["query_id"] == QUERY_ID
    assert form["cluster_key"] == "direct-impala"


def test_web_known_query_smoke_redacts_query_id_from_failed_job_error(tmp_path):
    home = tmp_path / "home"
    config = write_config(
        home,
        {
            "clusters": [
                {
                    "id": "direct-impala",
                    "label": "Direct Impala",
                    "query_profile_source": "impala",
                    "impala_profile_hosts": ["impalad-1.example.com"],
                }
            ]
        },
    )
    query_id_file = write_query_id_file(tmp_path)
    wrapper = tmp_path / "fake-web-wrapper"
    write_fake_web_wrapper(wrapper)
    capture = tmp_path / "form.json"
    job_id = "1234567890abcdef1234567890abcdef"
    port = free_local_port()

    result = run_smoke(
        [
            "--config",
            str(config),
            "--query-id-file",
            str(query_id_file),
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
            "FAKE_QUERY_ID": QUERY_ID,
            "FAKE_FORM_CAPTURE": str(capture),
            "FAKE_JOB_ERROR": f"Profile not found for query {QUERY_ID}: retained window expired.",
        },
    )

    combined_output = result.stdout + result.stderr
    assert result.returncode == 2
    assert "Safe error: Profile not found for query <query-id hidden>" in result.stderr
    assert QUERY_ID not in combined_output
    assert quote(QUERY_ID, safe="") not in combined_output
    assert str(query_id_file) not in combined_output
    assert str(config) not in combined_output


def test_web_known_query_smoke_classifies_hidden_subprocess_output_error(tmp_path):
    home = tmp_path / "home"
    config = write_config(
        home,
        {
            "clusters": [
                {
                    "id": "direct-impala",
                    "label": "Direct Impala",
                    "query_profile_source": "impala",
                    "impala_profile_hosts": ["impalad-1.example.com"],
                }
            ]
        },
    )
    query_id_file = write_query_id_file(tmp_path)
    wrapper = tmp_path / "fake-web-wrapper"
    write_fake_web_wrapper(wrapper)
    capture = tmp_path / "form.json"
    job_id = "1234567890abcdef1234567890abcdef"
    port = free_local_port()

    result = run_smoke(
        [
            "--config",
            str(config),
            "--query-id-file",
            str(query_id_file),
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
            "FAKE_QUERY_ID": QUERY_ID,
            "FAKE_FORM_CAPTURE": str(capture),
            "FAKE_JOB_ERROR": (
                "Query Doctor recent scan failed with exit code 1. Captured subprocess output "
                "is not shown because it may contain raw profile text, SQL, JSON, or credentials."
            ),
        },
    )

    combined_output = result.stdout + result.stderr
    assert result.returncode == 2
    assert "Safe error: Collector subprocess failed" in result.stderr
    assert "raw profile text" not in combined_output
    assert QUERY_ID not in combined_output
    assert str(query_id_file) not in combined_output
    assert str(config) not in combined_output
