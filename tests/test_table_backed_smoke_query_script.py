import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

from impala_hs2_test_support import table_rows
from query_doctor.impala.hs2_runner import ImpalaStatementError


REPO_DIR = Path(__file__).resolve().parents[1]
SCRIPT = REPO_DIR / "scripts" / "query-doctor-table-backed-smoke-query"


def load_script_module():
    # The helper has no .py suffix, so the loader has to be named outright.
    loader = importlib.machinery.SourceFileLoader("table_backed_smoke_query", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves annotations through sys.modules during exec.
    sys.modules[loader.name] = module
    loader.exec_module(module)
    return module


class FakeSession:
    def __init__(self, responder):
        self._responder = responder
        self.calls = []
        self.closed = False

    def run(self, sql, *, timeout_sec=None):
        self.calls.append(sql)
        outcome = self._responder(sql)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def close(self):
        self.closed = True


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


def write_config(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "clusters": [
                    {
                        "id": "direct",
                        "metadata_coordinator": "coordinator.example.com:21050",
                        "metadata_auth": "kerberos",
                        "metadata_protocol": "hs2",
                        "metadata_kerberos_service_name": "hive",
                        "metadata_kerberos_host_fqdn": "coordinator.example.com",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


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


def test_metadata_validation_walks_past_a_stale_candidate_on_one_session(tmp_path):
    module = load_script_module()
    config = module.MetadataValidationConfig(
        coordinator="coordinator.example.com:21050",
        auth="kerberos",
        protocol="hs2",
        kerberos_service_name="hive",
        kerberos_host_fqdn="coordinator.example.com",
        ssl=False,
        ca_cert=None,
        timeout_sec=30,
    )
    stale = module.TableCandidate(table="analytics.missing_fact", mtime_ns=2000, ordinal=0)
    fresh = module.TableCandidate(table="mart.valid_fact", mtime_ns=1000, ordinal=1)

    def respond(sql):
        if "valid_fact" in sql:
            return table_rows(("#Rows",), (10,))
        return ImpalaStatementError("AnalysisException: Could not resolve table reference")

    session = FakeSession(respond)
    selection = module.select_validated_candidate([stale, fresh], config, session=session)

    assert selection.candidate.table == "mart.valid_fact"
    assert selection.validation_attempts == 2
    assert len(session.calls) == 2
    # The caller owns an injected session, so the helper must leave it open.
    assert session.closed is False


def test_metadata_validation_connects_to_the_configured_hs2_port(tmp_path):
    module = load_script_module()
    config = module.MetadataValidationConfig(
        coordinator="coordinator.example.com:21050",
        auth="kerberos",
        protocol="hs2-http",
        kerberos_service_name="hive",
        kerberos_host_fqdn="lb.example.com",
        ssl=True,
        ca_cert="/etc/ssl/ca.pem",
        timeout_sec=17,
    )

    settings = module.connection_settings(config)

    assert (settings.host, settings.port) == ("coordinator.example.com", 21050)
    assert settings.use_http_transport is True
    assert settings.kerberos_host_fqdn == "lb.example.com"
    assert settings.timeout_sec == 17


def test_table_backed_smoke_query_metadata_validation_fails_safely(tmp_path):
    root = tmp_path / "cases"
    out = tmp_path / "query.sql"
    config = tmp_path / "config.json"
    write_config(config)
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
