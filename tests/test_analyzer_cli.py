import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional


REPO_DIR = Path(__file__).resolve().parents[1]


def load_analyzer_module():
    from query_doctor.analyzer import facade

    return facade


def test_analyzer_package_facade_keeps_legacy_helper_lookup():
    from query_doctor.analyzer import facade
    from query_doctor.analyzer.sql_sources import extract_referenced_tables_from_sql

    assert facade.extract_referenced_tables_from_sql is extract_referenced_tables_from_sql


def test_analyzer_cli_module_owns_cli_helpers():
    from query_doctor.cli import analyze_profile

    assert analyze_profile.parse_args(["case-dir"]).input == "case-dir"
    manual_args = analyze_profile.parse_args(
        [
            "--profile-text",
            "exported-profile.txt",
            "--out",
            "cases/cm-corpus",
        ]
    )
    assert manual_args.input is None
    assert str(manual_args.profile_text) == "exported-profile.txt"
    assert manual_args.query_id is None
    assert (
        analyze_profile.resolve_paths(REPO_DIR / "tests" / "fixtures" / "minimal_case", None)[
            0
        ].name
        == "profile_digest.md"
    )


def run_analyzer(case_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "query_doctor.cli.analyze_profile",
            str(case_dir),
        ],
        cwd=str(REPO_DIR),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def run_profile_text_analyzer(
    profile: Path,
    *,
    query_id: Optional[str] = None,
    out_dir: Path,
) -> subprocess.CompletedProcess[str]:
    query_args = ["--query-id", query_id] if query_id is not None else []
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "query_doctor.cli.analyze_profile",
            "--profile-text",
            str(profile),
            *query_args,
            "--out",
            str(out_dir),
        ],
        cwd=str(REPO_DIR),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def copy_minimal_case(tmp_path):
    src_case = REPO_DIR / "tests" / "fixtures" / "minimal_case"
    case_dir = tmp_path / "case"
    shutil.copytree(src_case, case_dir)
    return case_dir


def copy_fixture_case(tmp_path, fixture_name: str):
    src_case = REPO_DIR / "tests" / "fixtures" / fixture_name
    case_dir = tmp_path / fixture_name
    shutil.copytree(src_case, case_dir)
    return case_dir


def write_case(tmp_path, digest_text: str) -> Path:
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "profile_digest.md").write_text(digest_text, encoding="utf-8")
    return case_dir


def raw_exported_profile_text() -> str:
    return """Query Runtime Profile
Query ID: aaaaaaaaaaaaaaaa:0000000000000001
User: alice
Request Pool: pool_a
Start Time: 2026-06-11 10:00:00.000000000
End Time: 2026-06-11 10:05:00.000000000
Coordinator: impalad-01.example.invalid.example.com:22000

ExecSummary:
Operator              #Hosts   Avg Time   Max Time    #Rows  Est. #Rows  Peak Mem  Est. Peak Mem  Detail
01:SCAN HDFS               1       1s000ms  2s000ms   1.00M      10.00K  128.00 MB      64.00 MB  table=analytics_demo.fact_events
02:HASH JOIN               1       2s000ms  4s000ms   1.00M      10.00K  256.00 MB      64.00 MB  INNER JOIN, PARTITIONED

Query Timeline:
   Query submitted: 0ns
   Query finished: 5m

TotalTime: 5m
TotalBytesRead: 12.00 GiB
TotalBytesSent: 2.00 GiB
"""


def test_analyzer_facts_omit_source_digest_path_and_raw_digest_name(tmp_path):
    case_dir = copy_minimal_case(tmp_path)

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "Source digest:" not in text
    assert "profile_digest.md" not in text
    assert str(case_dir) not in text


def test_analyzer_cli_runs_with_python_m(tmp_path):
    case_dir = copy_minimal_case(tmp_path)

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    assert (case_dir / "analysis_facts.md").is_file()


def test_analyzer_profile_text_stages_redacted_case_and_analysis_json(tmp_path):
    profile = tmp_path / "raw-exported-profile.txt"
    profile.write_text(raw_exported_profile_text(), encoding="utf-8")
    out_dir = tmp_path / "cm-corpus"

    result = run_profile_text_analyzer(profile, out_dir=out_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    case_dir = out_dir / "aaaaaaaaaaaaaaaa_0000000000000001"
    assert f"Output case directory: {case_dir}" in result.stdout
    staged_profile = (case_dir / "profile_digest.md").read_text(encoding="utf-8")
    assert "alice" not in staged_profile
    assert "pool_a" not in staged_profile
    assert "Request Pool: <pool>" in staged_profile
    assert "impalad-01.example.invalid.example.com" not in staged_profile
    assert "Coordinator: host_01:22000" in staged_profile
    metadata = json.loads((case_dir / "query_metadata.json").read_text(encoding="utf-8"))
    assert metadata["query_id"] == "aaaaaaaaaaaaaaaa:0000000000000001"
    assert metadata["profile_source"] == "manual_profile_text"
    assert metadata["profile_response_format"] == "text"
    assert metadata["profile_fetch_attempt_count"] == 0
    assert metadata["profile_query_id_verified"] is True
    assert metadata["profile_filename_query_id_verified"] is False
    assert metadata["profile_query_id_source"] == "profile_text"
    assert metadata["user"] == "<user>"
    assert metadata["pool"] == "<pool>"
    warnings = (case_dir / "collection_warnings.txt").read_text(encoding="utf-8")
    assert "without network collection" in warnings
    facts_text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "Local exported Impala text profile" in facts_text
    assert "profile_digest.md" not in facts_text
    analysis_json = json.loads((case_dir / "analysis.json").read_text(encoding="utf-8"))
    assert analysis_json["query_context"]["profile_source"] == "manual_profile_text"
    assert len(analysis_json["operators"]) >= 1


def test_analyzer_profile_text_allows_explicit_query_id_when_profile_header_missing(tmp_path):
    profile = tmp_path / "raw-exported-profile.txt"
    profile.write_text(
        raw_exported_profile_text().replace(
            "Query ID: aaaaaaaaaaaaaaaa:0000000000000001\n",
            "",
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "cm-corpus"

    result = run_profile_text_analyzer(
        profile,
        query_id="aaaaaaaaaaaaaaaa:0000000000000001",
        out_dir=out_dir,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    case_dir = out_dir / "aaaaaaaaaaaaaaaa_0000000000000001"
    metadata = json.loads((case_dir / "query_metadata.json").read_text(encoding="utf-8"))
    assert metadata["query_id"] == "aaaaaaaaaaaaaaaa:0000000000000001"
    assert metadata["profile_query_id_verified"] is False
    assert metadata["profile_filename_query_id_verified"] is False
    assert metadata["profile_query_id_source"] == "query_id_argument"


def test_analyzer_profile_text_uses_impala_web_download_filename_when_header_missing(tmp_path):
    profile = tmp_path / "profile_aaaaaaaaaaaaaaaa_0000000000000001"
    profile.write_text(
        raw_exported_profile_text().replace(
            "Query ID: aaaaaaaaaaaaaaaa:0000000000000001\n",
            "",
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "cm-corpus"

    result = run_profile_text_analyzer(profile, out_dir=out_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    case_dir = out_dir / "aaaaaaaaaaaaaaaa_0000000000000001"
    metadata = json.loads((case_dir / "query_metadata.json").read_text(encoding="utf-8"))
    assert metadata["query_id"] == "aaaaaaaaaaaaaaaa:0000000000000001"
    assert metadata["profile_query_id_verified"] is False
    assert metadata["profile_filename_query_id_verified"] is True
    assert metadata["profile_query_id_source"] == "impala_web_profile_filename"


def test_analyzer_profile_text_requires_query_id_when_profile_header_missing(tmp_path):
    profile = tmp_path / "raw-exported-profile.txt"
    profile.write_text(
        raw_exported_profile_text().replace(
            "Query ID: aaaaaaaaaaaaaaaa:0000000000000001\n",
            "",
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "cm-corpus"

    result = run_profile_text_analyzer(profile, out_dir=out_dir)

    assert result.returncode == 2
    assert "Profile text does not include a Query ID" in result.stderr
    assert not out_dir.exists()


def test_analyzer_profile_text_accepts_query_header_id_form(tmp_path):
    profile = tmp_path / "raw-exported-profile.txt"
    profile.write_text(
        raw_exported_profile_text().replace(
            "Query Runtime Profile\nQuery ID: aaaaaaaaaaaaaaaa:0000000000000001\n",
            "Query (id=aaaaaaaaaaaaaaaa:0000000000000001)\n",
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "cm-corpus"

    result = run_profile_text_analyzer(profile, out_dir=out_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    metadata = json.loads(
        (out_dir / "aaaaaaaaaaaaaaaa_0000000000000001" / "query_metadata.json").read_text(
            encoding="utf-8"
        )
    )
    assert metadata["query_id"] == "aaaaaaaaaaaaaaaa:0000000000000001"
    assert metadata["profile_query_id_verified"] is True


def test_analyzer_profile_text_accepts_web_ui_execsummary_tree_prefixes(tmp_path):
    profile = tmp_path / "web-ui-exported-profile.txt"
    profile.write_text(
        """Query (id=aaaaaaaaaaaaaaaa:0000000000000001)
User: alice

ExecSummary:
Operator              #Hosts   Avg Time   Max Time    #Rows  Est. #Rows  Peak Mem  Est. Peak Mem  Detail
|--02:HASH JOIN            1       2s000ms  4s000ms   1.00M      10.00K  256.00 MB      64.00 MB  INNER JOIN, PARTITIONED
|  |--01:SCAN HDFS         1       1s000ms  2s000ms   1.00M      10.00K  128.00 MB      64.00 MB  table=analytics_demo.fact_events

TotalTime: 5m
TotalBytesRead: 12.00 GiB
TotalBytesSent: 2.00 GiB
""",
        encoding="utf-8",
    )
    out_dir = tmp_path / "cm-corpus"

    result = run_profile_text_analyzer(profile, out_dir=out_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    case_dir = out_dir / "aaaaaaaaaaaaaaaa_0000000000000001"
    metadata = json.loads((case_dir / "query_metadata.json").read_text(encoding="utf-8"))
    assert metadata["profile_query_id_verified"] is True
    analysis_json = json.loads((case_dir / "analysis.json").read_text(encoding="utf-8"))
    assert len(analysis_json["operators"]) >= 1
    facts_text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "Local exported Impala text profile" in facts_text


def test_analyzer_profile_text_rejects_mismatched_profile_query_id_without_writing_case(
    tmp_path,
):
    profile = tmp_path / "wrong-exported-profile.txt"
    mismatched_profile_query_id = "bbbbbbbbbbbbbbbb:0000000000000002"
    requested_query_id = "aaaaaaaaaaaaaaaa:0000000000000001"
    profile.write_text(
        raw_exported_profile_text().replace(requested_query_id, mismatched_profile_query_id),
        encoding="utf-8",
    )
    out_dir = tmp_path / "cm-corpus"

    result = run_profile_text_analyzer(
        profile,
        query_id=requested_query_id,
        out_dir=out_dir,
    )

    assert result.returncode == 2
    assert "Profile Query ID does not match --query-id" in result.stderr
    assert mismatched_profile_query_id not in result.stderr
    assert requested_query_id not in result.stderr
    assert not out_dir.exists()


def test_analyzer_profile_text_rejects_mismatched_download_filename_without_writing_case(
    tmp_path,
):
    profile = tmp_path / "profile_bbbbbbbbbbbbbbbb_0000000000000002"
    embedded_query_id = "aaaaaaaaaaaaaaaa:0000000000000001"
    profile.write_text(raw_exported_profile_text(), encoding="utf-8")
    out_dir = tmp_path / "cm-corpus"

    result = run_profile_text_analyzer(profile, out_dir=out_dir)

    assert result.returncode == 2
    assert "Profile filename Query ID does not match" in result.stderr
    assert embedded_query_id not in result.stderr
    assert "bbbbbbbbbbbbbbbb:0000000000000002" not in result.stderr
    assert not out_dir.exists()


def test_analyzer_profile_text_rejects_json_payload_without_writing_case(tmp_path):
    profile = tmp_path / "profile.json"
    profile.write_text('{"profile": "raw json"}\n', encoding="utf-8")
    out_dir = tmp_path / "cm-corpus"

    result = run_profile_text_analyzer(profile, out_dir=out_dir)

    assert result.returncode == 2
    assert "exported text profiles only" in result.stderr
    assert not out_dir.exists()


def test_analyzer_maps_classic_json_profile_counters_without_primary_promotion(tmp_path):
    case_dir = write_case(
        tmp_path,
        json.dumps(
            {
                "profile_version": 1,
                "runtime_profile": {
                    "name": "Query",
                    "counters": [
                        {"name": "TotalTime", "value": "100s"},
                        {"name": "ClientFetchWaitTimer", "value": "45s"},
                        {"name": "ScratchBytesWritten", "value": "4.0 KiB"},
                    ],
                },
            }
        ),
    )
    (case_dir / "query_metadata.json").write_text(
        json.dumps(
            {
                "query_id": "abc:def",
                "profile_source": "impala_daemon",
                "profile_source_label": "raw-host.example.com should not render",
                "profile_response_format": "json",
                "profile_fetch_attempt_count": 1,
                "profile_json_probe_enabled": True,
                "profile_docs_probe_enabled": True,
                "profile_docs_fetch_attempt_count": 2,
                "impala_daemon_product": "apache_impala",
                "impala_daemon_version": "5.0.0-SNAPSHOT",
                "impala_daemon_version_label": "impalad version 5.0.0-SNAPSHOT RELEASE",
                "impala_daemon_build_type": "RELEASE",
                "impala_daemon_server_mode": "coordinator",
                "impala_daemon_local_catalog_mode": True,
            }
        ),
        encoding="utf-8",
    )
    json_path = case_dir / "analysis.json"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "query_doctor.cli.analyze_profile",
            str(case_dir),
            "--json",
            str(json_path),
        ],
        cwd=str(REPO_DIR),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    analysis = json.loads(json_path.read_text(encoding="utf-8"))
    facts_text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")

    assert analysis["profile_format"]["profile_dialect"] == "classic_json_profile"
    assert analysis["profile_format"]["layout"] == "json_mapped_counters"
    assert analysis["profile_format"]["primary_bottleneck_policy"] == "unsupported"
    assert analysis["profile_format"]["source_label"] == "Impala daemon profile endpoint"
    assert analysis["profile_format"]["source_capabilities"] == {
        "profile_response_format": "json",
        "profile_fetch_attempt_count": 1,
        "json_profile_probe": "enabled",
        "profile_docs_probe": "enabled",
        "profile_docs_fetch_attempt_count": 2,
        "json_profile_payload": "mapped_limited",
        "text_profile_payload": "not_selected",
        "primary_profile_routing": "unsupported",
    }
    assert (
        analysis["profile_format"]["section_mappings"]["profile_resources"]["state"]
        == "unsupported"
    )
    assert analysis["profile_format"]["section_mappings"]["profile_counters"]["state"] == "limited"
    assert analysis["profile_format"]["section_mappings"]["memory_pressure"]["state"] == "limited"
    assert analysis["client_fetch"]["counter_stability"] == "STABLE_HIGH"
    assert analysis["client_fetch"]["evidence_tier"] == "context_only"
    assert analysis["client_fetch"]["section_mapping"] == "limited"
    assert analysis["client_fetch"]["finding_supported"] is False
    assert analysis["memory_pressure"]["status"] == "context_only"
    assert analysis["memory_pressure"]["evidence_tier"] == "context_only"
    assert analysis["memory_pressure"]["finding_supported"] is False
    assert analysis["memory_pressure"]["spill_or_scratch_evidence_count"] == 0
    assert analysis["memory_pressure"]["limited_spill_or_scratch_counter_count"] == 1
    assert analysis["case_primary_bottleneck"] == {
        "label": "unknown",
        "confidence": "low",
        "reasons": ["profile_dialect_not_supported_for_primary"],
    }
    assert "- source: Impala daemon profile endpoint" in facts_text
    assert (
        "- source_capabilities: endpoint_format=json, json_probe=enabled, "
        "json_payload=mapped_limited, text_payload=not_selected, "
        "profile_docs_probe=enabled"
    ) in facts_text
    assert "json_profile_mapping: mapped_counter_count=3" in facts_text
    assert "profile_counters=limited" in facts_text
    assert "memory_pressure=limited" in facts_text
    assert "limited_spill_or_scratch_counter_count: 1" in facts_text
    assert "### Spill or scratch I/O" not in facts_text
    assert "raw-host.example.com" not in facts_text


def test_analyzer_uses_profile_docs_registry_context_for_counter_stability(tmp_path):
    case_dir = write_case(
        tmp_path,
        "Query Runtime Profile\n"
        "- TotalTime: 100s\n"
        "- ClientFetchWaitTimer: 45s\n"
        "- SpilledBytes: 2.0 GiB\n",
    )
    (case_dir / "profile_counter_registry_context.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "available",
                "source": "profile_docs",
                "source_counter_count": 1,
                "registry_entry_count": 2,
                "missing_counter_count": 1,
                "entries": [
                    {
                        "canonical_name": "ClientFetchWaitTimer",
                        "aliases": [],
                        "stability_label": "STABLE_LOW",
                        "source": "profile_docs",
                        "evidence_role": "client_fetch_wait",
                    },
                    {
                        "canonical_name": "SpilledBytes",
                        "aliases": ["BytesSpilled"],
                        "stability_label": "UNKNOWN",
                        "source": "profile_docs",
                        "evidence_role": "spill_scratch_evidence",
                    },
                ],
                "limitations": ["Missing or unlabeled counters are UNKNOWN stability."],
            }
        ),
        encoding="utf-8",
    )
    json_path = case_dir / "analysis.json"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "query_doctor.cli.analyze_profile",
            str(case_dir),
            "--json",
            str(json_path),
        ],
        cwd=str(REPO_DIR),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    analysis = json.loads(json_path.read_text(encoding="utf-8"))
    facts_text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")

    assert analysis["profile_counter_registry"]["status"] == "available"
    assert analysis["profile_counter_registry"]["source"] == "profile_docs"
    assert analysis["client_fetch"]["counter_registry_source"] == "profile_docs"
    assert analysis["client_fetch"]["counter_stability"] == "STABLE_LOW"
    assert analysis["client_fetch"]["evidence_tier"] == "medium"
    assert analysis["client_fetch"]["finding_supported"] is False
    assert analysis["memory_pressure"]["status"] == "not_observed"
    assert analysis["memory_pressure"]["spill_or_scratch_evidence_count"] == 0
    assert "## Profile Counter Registry" in facts_text
    assert "profile_counter_registry_context.json" not in facts_text


def test_analyzer_facts_include_safe_batch_cluster_event_context(tmp_path):
    batch_dir = tmp_path / "batch"
    case_dir = batch_dir / "cases" / "case-001" / "actual"
    shutil.copytree(REPO_DIR / "tests" / "fixtures" / "minimal_case", case_dir)
    (batch_dir / "cluster_context.json").write_text(
        json.dumps(
            {
                "product": "cluster_doctor",
                "status": "degraded_service_candidate",
                "available": True,
                "sources": [
                    {
                        "source": "cm_events",
                        "available": True,
                        "status": "ok",
                        "product_status": "degraded_service_candidate",
                    }
                ],
                "window": {
                    "service_scope": "IMPALA-1",
                    "window_minutes": 60,
                    "max_events": 10,
                    "alerts_only": False,
                    "severity_filter": ["critical", "important", "informational"],
                },
                "signal_counts": {
                    "impala_daemon_error_event": 3,
                    "catalog_error_event": 1,
                },
                "signals": [
                    {
                        "signal_id": "impala_daemon_error_event",
                        "status": "observed",
                        "severity": "critical",
                        "event_count": 3,
                        "alert_count": 1,
                        "trend": "new",
                        "claim_level": "cluster_candidate",
                        "raw_event_id": "RAW_EVENT_ID_SHOULD_NOT_RENDER",
                    }
                ],
                "next_checks": [
                    "Check Impala service health, daemon errors, and affected query windows."
                ],
                "limitations": [
                    "Raw event content, log lines, event ids, hostnames, principals, paths, and query text are excluded.",
                    "Provider returned /tmp/raw/path and RAW_EVENT_ID_SHOULD_NOT_RENDER",
                ],
                "raw_payload": {"event": "RAW_EVENT_ID_SHOULD_NOT_RENDER"},
            }
        ),
        encoding="utf-8",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Cluster Event Context" in text
    assert "- status: degraded_service_candidate" in text
    assert "- available: yes" in text
    assert "- source_status: cm_events=ok/degraded_service_candidate" in text
    assert "service_scope=IMPALA-1" in text
    assert "impala_daemon_error_event=3" in text
    assert "Check Impala service health" in text
    assert "not prove root cause" in text
    assert "RAW_EVENT_ID_SHOULD_NOT_RENDER" not in text
    assert "/tmp/raw/path" not in text
    assert str(batch_dir) not in text


def test_analyzer_facts_include_safe_admission_aggregate_context(tmp_path):
    case_dir = copy_minimal_case(tmp_path)
    (case_dir / "admission_context.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "available": True,
                "status": "available",
                "source": "impala_admission_debug",
                "source_label": "raw-host.example.com should not render",
                "scope": "selected_pool",
                "pool_count": 3,
                "matched_pool_count": 1,
                "queue_present": "yes",
                "running_present": "yes",
                "queued_pool_count": 1,
                "running_pool_count": 2,
                "max_queue_depth_bucket": "1",
                "max_running_bucket": "2_4",
                "avg_queue_time_bucket": "5s_30s",
                "pool_pressure": "medium",
                "freshness": "fresh",
                "raw_pool_name": "root.secret_pool",
                "queued_queries": [{"query_id": "raw-query-id"}],
                "limitations": [
                    "Admission debug context is aggregate pool context. It must not promote runtime_admission without selected-query admission wait or result evidence.",
                    "Raw /tmp/provider/path should not render.",
                ],
            }
        ),
        encoding="utf-8",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Admission Context" in text
    assert "- scope: selected_pool" in text
    assert "- queue_present: yes" in text
    assert "- avg_queue_time_bucket: 5s_30s" in text
    assert "- pool_pressure: medium" in text
    assert "without selected-query admission wait or result evidence" in text
    assert "## Runtime Admission Evidence" in text
    assert "- primary_supported: no" in text
    assert "raw-host.example.com" not in text
    assert "root.secret_pool" not in text
    assert "raw-query-id" not in text
    assert "/tmp/provider/path" not in text


def test_analyzer_keeps_unavailable_direct_admission_context_unknown(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic direct Impala digest

## ExecSummary

```text
01:SCAN HDFS  1  1s000ms  1s000ms  10  10  1.00 MB  1.00 MB
```

## Metric lines

```text
- TotalTime: 20s
```
""",
    )
    (case_dir / "query_metadata.json").write_text(
        json.dumps(
            {
                "query_id": "abc:def",
                "duration_ms": 20_000,
                "profile_source": "impala_daemon",
                "profile_source_label": "raw-host.example.com should not render",
                "profile_response_format": "text",
                "profile_fetch_attempt_count": 1,
                "profile_json_probe_enabled": True,
                "profile_docs_probe_enabled": True,
                "profile_docs_fetch_attempt_count": 2,
                "admission_context_probe_enabled": True,
                "admission_context_fetch_attempt_count": 1,
            }
        ),
        encoding="utf-8",
    )
    (case_dir / "admission_context.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "available": False,
                "status": "unavailable",
                "source": "http://internal.example/admission",
                "source_label": "raw-host.example.com should not render",
                "scope": "raw_pool_scope",
                "queue_present": "raw-query-id",
                "pool_pressure": "http://internal.example/pool",
                "reason": "https://internal.example/admission?token=secret",
                "raw_pool_name": "root.secret_pool",
                "queued_queries": [{"query_id": "raw-query-id"}],
                "limitations": [
                    "Impala admission debug context was unavailable or unmapped; keep pool/admission context unknown.",
                    "Raw /tmp/provider/path should not render.",
                ],
            }
        ),
        encoding="utf-8",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Profile Format" in text
    assert "- source: Impala daemon profile endpoint" in text
    assert "profile_docs_probe=enabled" in text
    assert "## Admission Context" in text
    assert "- status: unavailable" in text
    assert "- available: no" in text
    assert "- source: Impala admission debug endpoint" in text
    assert "- scope: unknown" in text
    assert "- reason: request_failed" in text
    assert "- queue_present: unknown" in text
    assert "- pool_pressure: unknown" in text
    assert "keep pool/admission context unknown" in text
    assert "## Runtime Admission Evidence" in text
    assert "- evidence_tier: context_only" in text
    assert "- primary_supported: no" in text
    assert "- label: runtime_admission" not in text
    assert "raw-host.example.com" not in text
    assert "root.secret_pool" not in text
    assert "raw-query-id" not in text
    assert "/tmp/provider/path" not in text
    assert "internal.example" not in text
    assert_no_banned_or_unsupported_claims(text)


def write_cm_timeseries_context(
    case_dir: Path,
    *,
    cpu_user_max: float = 22,
    cpu_user_avg: float = 5,
    cpu_system_max: float = 3,
    memory_min_gib: float = 10,
    memory_max_gib: float = 23,
    network_max_mib: float = 200,
    network_avg_mib: float = 20,
    disk_max_mib: Optional[float] = None,
    disk_avg_mib: Optional[float] = None,
    hdfs_read_max_mib: Optional[float] = None,
    hdfs_read_avg_mib: Optional[float] = None,
    hdfs_local_reads_max: Optional[float] = None,
    hdfs_remote_reads_max: Optional[float] = None,
    admission_queued_max: Optional[float] = None,
    admission_queued_avg: Optional[float] = None,
    admission_rejected_max: Optional[float] = None,
    admission_timed_out_max: Optional[float] = None,
) -> None:
    queries = [
        {
            "id": "impala_daemon_memory",
            "label": "Impala daemon memory",
            "status": "ok",
            "point_count": 10,
            "min": memory_min_gib * 1024 * 1024 * 1024,
            "max": memory_max_gib * 1024 * 1024 * 1024,
            "avg": ((memory_min_gib + memory_max_gib) / 2) * 1024 * 1024 * 1024,
            "latest": memory_max_gib * 1024 * 1024 * 1024,
        },
        {
            "id": "host_cpu_user",
            "label": "Host CPU user",
            "status": "ok",
            "point_count": 10,
            "min": 1,
            "max": cpu_user_max,
            "avg": cpu_user_avg,
            "latest": cpu_user_avg,
        },
        {
            "id": "host_cpu_system",
            "label": "Host CPU system",
            "status": "ok",
            "point_count": 10,
            "min": 0,
            "max": cpu_system_max,
            "avg": min(cpu_system_max, 5),
            "latest": min(cpu_system_max, 5),
        },
        {
            "id": "host_network_io",
            "label": "Host network I/O",
            "status": "ok",
            "point_count": 10,
            "min": 1 * 1024 * 1024,
            "max": network_max_mib * 1024 * 1024,
            "avg": network_avg_mib * 1024 * 1024,
            "latest": min(network_max_mib, network_avg_mib) * 1024 * 1024,
        },
    ]
    if disk_max_mib is not None and disk_avg_mib is not None:
        queries.extend(
            [
                {
                    "id": "host_disk_read_rate",
                    "label": "Host disk read rate",
                    "status": "ok",
                    "point_count": 10,
                    "min": 1 * 1024 * 1024,
                    "max": disk_max_mib * 1024 * 1024,
                    "avg": disk_avg_mib * 1024 * 1024,
                    "latest": disk_avg_mib * 1024 * 1024,
                },
                {
                    "id": "host_disk_write_rate",
                    "label": "Host disk write rate",
                    "status": "ok",
                    "point_count": 10,
                    "min": 1 * 1024 * 1024,
                    "max": 8 * 1024 * 1024,
                    "avg": 2 * 1024 * 1024,
                    "latest": 2 * 1024 * 1024,
                },
            ]
        )
    if hdfs_read_max_mib is not None and hdfs_read_avg_mib is not None:
        local_reads = 100.0 if hdfs_local_reads_max is None else hdfs_local_reads_max
        remote_reads = 0.0 if hdfs_remote_reads_max is None else hdfs_remote_reads_max
        queries.extend(
            [
                {
                    "id": "hdfs_datanode_read_bytes_rate",
                    "label": "HDFS DataNode read bytes rate",
                    "status": "ok",
                    "point_count": 10,
                    "min": 1 * 1024 * 1024,
                    "max": hdfs_read_max_mib * 1024 * 1024,
                    "avg": hdfs_read_avg_mib * 1024 * 1024,
                    "latest": hdfs_read_avg_mib * 1024 * 1024,
                },
                {
                    "id": "hdfs_datanode_local_reads_rate",
                    "label": "HDFS DataNode local reads rate",
                    "status": "ok",
                    "point_count": 10,
                    "min": 0,
                    "max": local_reads,
                    "avg": local_reads / 2,
                    "latest": local_reads / 2,
                },
                {
                    "id": "hdfs_datanode_remote_reads_rate",
                    "label": "HDFS DataNode remote reads rate",
                    "status": "ok",
                    "point_count": 10,
                    "min": 0,
                    "max": remote_reads,
                    "avg": remote_reads / 2,
                    "latest": remote_reads / 2,
                },
            ]
        )
    if admission_queued_max is not None:
        queued_avg = 0.0 if admission_queued_avg is None else admission_queued_avg
        queries.extend(
            [
                {
                    "id": "impala_pool_queued_rate",
                    "label": "Impala admission queued rate",
                    "status": "ok",
                    "point_count": 10,
                    "min": 0,
                    "max": admission_queued_max,
                    "avg": queued_avg,
                    "latest": queued_avg,
                },
                {
                    "id": "impala_pool_rejected_rate",
                    "label": "Impala admission rejected rate",
                    "status": "ok",
                    "point_count": 10,
                    "min": 0,
                    "max": 0.0 if admission_rejected_max is None else admission_rejected_max,
                    "avg": 0,
                    "latest": 0,
                },
                {
                    "id": "impala_pool_timed_out_rate",
                    "label": "Impala admission timed-out rate",
                    "status": "ok",
                    "point_count": 10,
                    "min": 0,
                    "max": 0.0 if admission_timed_out_max is None else admission_timed_out_max,
                    "avg": 0,
                    "latest": 0,
                },
            ]
        )
    (case_dir / "cm_timeseries_context.json").write_text(
        json.dumps(
            {
                "available": True,
                "metrics_profile": "cm6",
                "limits": {
                    "max_response_bytes": 12345,
                    "max_points_per_query": 10,
                },
                "window": {
                    "from": "2026-05-04T09:59:00Z",
                    "to": "2026-05-04T10:06:00Z",
                    "padding_sec": 60,
                },
                "queries": queries,
            }
        ),
        encoding="utf-8",
    )


def test_extract_referenced_tables_from_common_sql_patterns():
    module = load_analyzer_module()

    sql = """
    INSERT OVERWRITE TABLE `example_mart`.`target_table`
    WITH cte AS (
        SELECT *
        FROM `example_db1`.`table_a` a
        JOIN example_db2.table_b AS b ON a.id = b.id
    )
    SELECT *
    FROM cte
    JOIN example_db3.table_c c ON cte.id = c.id
    """

    assert module.extract_referenced_tables_from_sql(sql) == [
        "example_db1.table_a",
        "example_db2.table_b",
        "example_db3.table_c",
        "example_mart.target_table",
    ]


def test_extract_referenced_tables_handles_insert_into_aliases_and_comma_joins():
    module = load_analyzer_module()

    sql = """
    INSERT INTO TABLE example_db0.out_table
    SELECT *
    FROM example_db2.table_b b, example_db1.table_a AS a
    LEFT JOIN example_db3.table_c c ON b.id = c.id
    """

    assert module.extract_referenced_tables_from_sql(sql) == [
        "example_db0.out_table",
        "example_db1.table_a",
        "example_db2.table_b",
        "example_db3.table_c",
    ]


def test_extract_referenced_tables_ignores_cte_references_and_reads_nested_subqueries():
    module = load_analyzer_module()

    sql = """
    WITH recent_orders AS (
      SELECT * FROM example_warehouse.orders
    ),
    ranked_customers AS (
      SELECT * FROM example_warehouse.customers
    )
    SELECT *
    FROM (
      SELECT * FROM recent_orders
      JOIN ranked_customers rc ON recent_orders.customer_id = rc.id
      JOIN example_warehouse.payments p ON p.order_id = recent_orders.id
    ) nested
    """

    assert module.extract_referenced_tables_from_sql(sql) == [
        "example_warehouse.customers",
        "example_warehouse.orders",
        "example_warehouse.payments",
    ]


def test_extract_referenced_tables_ignores_comments_strings_and_functions():
    module = load_analyzer_module()

    sql = """
    -- FROM example_guarded.comment_table
    SELECT parse_url('FROM example_guarded.string_table') AS url_part
    FROM explode(items) e
    JOIN safe_db.real_table rt ON e.id = rt.id
    WHERE note = 'JOIN example_guarded.hidden h'
    /* INSERT INTO example_guarded.comment_target SELECT * FROM example_guarded.comment_source */
    """

    assert module.extract_referenced_tables_from_sql(sql) == ["safe_db.real_table"]


def test_extract_referenced_tables_ignores_nested_expression_commas_after_from():
    module = load_analyzer_module()

    sql = """
    SELECT item
    FROM safe_db.real_table rt
    LATERAL VIEW explode(array(col_a, col_b, col_c)) exploded AS item
    WHERE item IS NOT NULL
    """

    assert module.extract_referenced_tables_from_sql(sql) == ["safe_db.real_table"]


def test_extract_referenced_tables_handles_mixed_quote_literals():
    module = load_analyzer_module()

    sql = """
    SELECT "May'24" AS season, note
    FROM smoke_db.table_a a
    JOIN smoke_db.table_b b ON a.id = b.id
    WHERE note = 'JOIN example_guarded.hidden h'
    """

    assert module.extract_referenced_tables_from_sql(sql) == [
        "smoke_db.table_a",
        "smoke_db.table_b",
    ]


def test_extract_referenced_tables_sorts_and_deduplicates():
    module = load_analyzer_module()

    sql = """
    SELECT *
    FROM example_z_db.last_table z
    JOIN example_db_a.first_table a ON z.id = a.id
    JOIN example_z_db.last_table z2 ON z2.id = a.id
    """

    assert module.extract_referenced_tables_from_sql(sql) == [
        "example_db_a.first_table",
        "example_z_db.last_table",
    ]


def test_extract_referenced_tables_ignores_select_list_qualified_columns():
    module = load_analyzer_module()

    sql = """
    SELECT a.id, b.name
    FROM smoke_db.table_a a
    JOIN smoke_db.table_b b ON a.id = b.id
    """

    assert module.extract_referenced_tables_from_sql(sql) == [
        "smoke_db.table_a",
        "smoke_db.table_b",
    ]


def test_extract_referenced_tables_ignores_filter_group_order_columns():
    module = load_analyzer_module()

    sql = """
    SELECT a.category, count(*)
    FROM smoke_db.table_a a
    WHERE a.id > 0
    GROUP BY a.category
    ORDER BY a.created_at
    """

    assert module.extract_referenced_tables_from_sql(sql) == ["smoke_db.table_a"]


def test_extract_join_filter_column_references_from_sql_returns_safe_pairs():
    module = load_analyzer_module()

    sql = """
    SELECT a.id, b.name
    FROM example_mart.fact_orders a
    JOIN example_mart.dim_customer b ON a.customer_id = b.customer_id
    WHERE a.event_day >= '2026-05-01'
      AND b.segment = 'vip'
    GROUP BY a.id, b.name
    """

    assert module.extract_join_filter_column_references_from_sql(sql) == [
        ("example_mart.dim_customer", "customer_id"),
        ("example_mart.dim_customer", "segment"),
        ("example_mart.fact_orders", "customer_id"),
        ("example_mart.fact_orders", "event_day"),
    ]


def test_extract_referenced_tables_ignores_cte_alias_columns_after_subquery():
    module = load_analyzer_module()

    sql = """
    WITH x AS (
        SELECT id FROM smoke_db.table_a
    )
    SELECT x.id, b.name
    FROM x
    JOIN smoke_db.table_b b ON x.id = b.id
    """

    assert module.extract_referenced_tables_from_sql(sql) == [
        "smoke_db.table_a",
        "smoke_db.table_b",
    ]


def test_analyzer_renders_referenced_tables_from_sql_without_raw_sql(tmp_path):
    case_dir = copy_minimal_case(tmp_path)
    (case_dir / "sql.sql").write_text(
        """
        -- FROM example_hidden.comment_table
        SELECT *
        FROM example_db1.table_a a
        JOIN example_db2.table_b AS b ON a.id = b.id
        WHERE a.note = 'FROM example_hidden.string_table'
        """,
        encoding="utf-8",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Referenced Tables" in text
    assert "- `example_db1.table_a`" in text
    assert "- `example_db2.table_b`" in text
    assert "example_hidden.comment_table" not in text
    assert "example_hidden.string_table" not in text
    assert "SELECT *" not in text


def test_analyzer_extracts_referenced_tables_from_profile_digest_sql_block(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## SQL

```sql
SELECT *
FROM example_raw_db.profile_table p
JOIN example_dim_db.lookup l ON p.id = l.id
```

## ExecSummary

```text
01:SCAN HDFS 1 1ms 1ms 1 1 1.00 MB 1.00 MB example_raw_db.profile_table
```
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "- `example_dim_db.lookup`" in text
    assert "- `example_raw_db.profile_table`" in text
    assert "SELECT *" not in text


def test_analyzer_extracts_referenced_tables_from_json_sql_statement(tmp_path):
    details = """
Query (id=abc:def)
  Summary
    Sql Statement: SELECT a.id, b.name FROM smoke_db.table_a a JOIN smoke_db.table_b b ON a.id = b.id
    Coordinator: host_01:22000
  Plan:
"""
    case_dir = write_case(tmp_path, json.dumps({"details": details}))

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "- `smoke_db.table_a`" in text
    assert "- `smoke_db.table_b`" in text
    assert "b.name" not in text
    assert "a.id" not in text


def test_analyzer_extracts_referenced_tables_from_multiline_profile_sql(tmp_path):
    details = """
Query (id=abc:def)
  Summary
    Sql Statement: WITH src AS (
      SELECT "May'24" AS season, a.id
      FROM smoke_db.table_a a

      JOIN smoke_db.table_b b ON a.id = b.id
    )
    SELECT *
    FROM src
    Coordinator: host_01:22000
  Plan:
"""
    case_dir = write_case(tmp_path, json.dumps({"details": details}))

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "- `smoke_db.table_a`" in text
    assert "- `smoke_db.table_b`" in text
    assert "May'24" not in text


def test_analyzer_extracts_default_database_from_json_profile_summary(tmp_path):
    details = """
Query (id=abc:def)
  Summary
    Default Db: te_ruby_agg
    Sql Statement: SELECT * FROM click_event
    Coordinator: host_01:22000
  Plan:
"""
    case_dir = write_case(tmp_path, json.dumps({"details": details}))

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## SQL Context" in text
    assert "- default_database: `te_ruby_agg`" in text
    assert "- `click_event`" in text
    assert "SELECT *" not in text


def test_analyzer_prefers_sql_file_over_profile_digest_sql(tmp_path):
    details = """
Query (id=abc:def)
  Summary
    Sql Statement: SELECT * FROM example_profile_db.profile_table
    Coordinator: host_01:22000
"""
    case_dir = write_case(tmp_path, json.dumps({"details": details}))
    (case_dir / "sql.sql").write_text(
        "SELECT * FROM example_explicit_db.sql_file_table\n",
        encoding="utf-8",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "- `example_explicit_db.sql_file_table`" in text
    assert "example_profile_db.profile_table" not in text


def test_analyzer_handles_profile_digest_without_sql_safely(tmp_path):
    case_dir = write_case(
        tmp_path,
        json.dumps({"details": "Query (id=abc:def)\n  Summary\n    Coordinator: host_01:22000\n"}),
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "- not_observed: no referenced table names were parsed" in text


def test_analyzer_creates_analysis_facts(tmp_path):
    case_dir = copy_minimal_case(tmp_path)

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout

    facts = case_dir / "analysis_facts.md"
    assert facts.exists()

    text = facts.read_text(encoding="utf-8")
    assert "Parsed operators" in text or "operators" in text.lower()
    assert "Cardinality" in text or "cardinality" in text.lower()
    assert "## Impala Context" not in text
    assert "## Table Metadata Context" in text
    assert "- context file: not_observed" in text
    assert "- table metadata facts: unknown" in text


def test_analyzer_includes_safe_cm_query_context_without_sql_or_user(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
01:SCAN HDFS  1  1s000ms  1s000ms  10  10  1.00 MB  1.00 MB
```
""",
    )
    (case_dir / "query_metadata.json").write_text(
        json.dumps(
            {
                "query_id": "abc:def",
                "status": "succeeded",
                "query_state": "FINISHED",
                "query_type": "QUERY",
                "pool": "etl",
                "duration_ms": 90000,
                "admission_result": "admitted",
                "admission_wait_ms": 250,
                "rows_produced": 123456,
                "bytes_read": 1048576,
                "bytes_sent": 2097152,
                "memory_aggregate_peak": 3221225472,
                "user": "alice",
                "statement": "SELECT secret_col FROM example_guarded.table",
            }
        ),
        encoding="utf-8",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Query Wall Clock" in text
    assert "- duration: 1.50m" in text
    assert "- source: CM Query Context" in text
    assert "- confidence: high" in text
    assert "## CM Query Context" in text
    assert "- status: succeeded" in text
    assert "- query_state: FINISHED" in text
    assert "- pool: etl" in text
    assert "- duration: 1.50m" in text
    assert "- admission_wait: 250ms" in text
    assert "- rows_produced: 123.46K" in text
    assert "- bytes_read: 1.00 MiB" in text
    assert "- bytes_sent: 2.00 MiB" in text
    assert "- memory_aggregate_peak: 3.00 GiB" in text
    assert "SELECT secret_col" not in text
    assert "alice" not in text


def test_analyzer_labels_direct_impala_profile_context_without_cm_copy(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
01:SCAN HDFS  1  1s000ms  1s000ms  10  10  1.00 MB  1.00 MB
```
""",
    )
    (case_dir / "cm_metadata.json").write_text(
        json.dumps(
            {
                "query_id": "abc:def",
                "status": "FINISHED",
                "query_type": "QUERY",
                "duration_ms": 90000,
                "user": "alice",
                "statement": "SELECT secret_col FROM example_guarded.table",
                "profile_source": "impala_daemon",
                "profile_source_label": "Impala daemon profile endpoint",
            }
        ),
        encoding="utf-8",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Query Profile Context" in text
    assert "## CM Query Context" not in text
    assert "- source: Impala daemon profile endpoint" in text
    assert "- duration: 1.50m" in text
    assert "SELECT secret_col" not in text
    assert "alice" not in text


def test_analyzer_renders_safe_profile_format_for_fresh_impala_layout(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
Summary:
  Impala Version: impalad version 5.0.0-SNAPSHOT RELEASE (build abcdef123456)
  Plan:
F00:
  HDFS_SCAN_NODE (id=00)
    - RowsProduced: 10 (10)
    - TotalTime: 1s (1000000000)
  Instance q:001 (host=worker-a.example.net:22000):
    Fragment Instance Lifecycle Event Timeline: 1s
    Fragment Instance Lifecycle Timings:
    - RowsProduced: 10 (10)
    - TotalTime: 1s (1000000000)
  Per Host Number of Fragment Instances: 1
  Backend startup latencies: Count: 1
  Per Node Peak Memory Usage: 1.00 MiB
  Admission result: Admitted
""",
    )
    (case_dir / "query_metadata.json").write_text(
        json.dumps(
            {
                "query_id": "abc:def",
                "duration_ms": 1000,
                "profile_source": "impala_daemon",
                "profile_source_label": "Impala daemon profile endpoint",
                "profile_response_format": "text",
                "profile_fetch_attempt_count": 2,
                "profile_json_probe_enabled": True,
                "profile_docs_probe_enabled": False,
                "profile_docs_fetch_attempt_count": 0,
                "impala_daemon_product": "apache_impala",
                "impala_daemon_version": "5.0.0-SNAPSHOT",
                "impala_daemon_version_label": "impalad version 5.0.0-SNAPSHOT RELEASE",
                "impala_daemon_build_type": "RELEASE",
                "impala_daemon_server_mode": "coordinator",
                "impala_daemon_local_catalog_mode": True,
            }
        ),
        encoding="utf-8",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Profile Format" in text
    assert "- family: impala_runtime_profile" in text
    assert "- source: Impala daemon profile endpoint" in text
    assert (
        "- source_capabilities: endpoint_format=text, json_probe=enabled, "
        "json_payload=not_selected, text_payload=observed, profile_docs_probe=not_configured"
        in text
    )
    assert "- distribution: apache_impala" in text
    assert "- version: 5.0.0-SNAPSHOT" in text
    assert "- build_type: RELEASE" in text
    assert "- daemon_server_mode: coordinator" in text
    assert "- daemon_local_catalog_mode: yes" in text
    assert "- dialect: classic_text_profile" in text
    assert "- layout: raw_runtime_nodes_with_lifecycle" in text
    assert "- compatibility: supported" in text
    assert "- analysis_support: supported" in text
    assert "- primary_bottleneck_policy: supported" in text
    assert (
        "- raw_profile_features: runtime_nodes=1, fragments=1, instances=1, lifecycle_headers=yes"
        in text
    )
    assert (
        "- resource_sections: admission=yes, backend_startup_latencies=yes, "
        "per_node_peak_memory=yes, per_node_bytes_read=no, per_node_user_time=no, "
        "per_node_system_time=no, per_host_fragment_instances=yes"
    ) in text
    assert "## Source Provenance" in text
    assert (
        "- engine: available; source=Apache Impala; coverage=distribution=apache_impala, version=5.0.0-SNAPSHOT"
        in text
    )
    assert (
        "- profile: available; source=Impala daemon profile endpoint; "
        "coverage=dialect=classic_text_profile, layout=raw_runtime_nodes_with_lifecycle, "
        "compatibility=supported, analysis=supported"
    ) in text
    assert "- metrics: none; source=Runtime metrics; coverage=not_collected" in text
    assert "- events: none; source=Cluster event context; coverage=not_collected" in text
    assert "- metadata: none; source=Impala metadata context; coverage=not_collected" in text
    assert "abcdef123456" not in text
    assert "worker-a.example.net" not in text
    assert_no_banned_or_unsupported_claims(text)


def test_analyzer_unknown_profile_format_disables_primary_classification(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
This payload is not a recognized Impala runtime profile representation.
""",
    )
    (case_dir / "query_metadata.json").write_text(
        json.dumps(
            {
                "query_id": "abc:def",
                "duration_ms": 120000,
                "admission_result": "Admitted (queued)",
                "admission_wait_ms": 60000,
            }
        ),
        encoding="utf-8",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "- dialect: unknown" in text
    assert "- analysis_support: unsupported" in text
    assert "- primary_bottleneck_policy: unsupported" in text
    assert "- label: unknown" in text
    assert "profile_dialect_not_supported_for_primary" in text
    assert (
        "Profile dialect is unknown; profile-derived primary bottleneck classification is disabled."
        in text
    )
    assert_no_banned_or_unsupported_claims(text)


def test_analyzer_profile_v2_reports_limited_analysis_scope(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
{
  "profile_version": 2,
  "aggregated_profile": {
    "fragments": []
  }
}
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "- dialect: experimental_profile_v2" in text
    assert "- analysis_support: limited" in text
    assert "- primary_bottleneck_policy: non_profile_only" in text
    assert "Experimental profile-v2 was detected" in text
    assert "scan-skew and backend-tail claims must not be promoted" in text
    assert_no_banned_or_unsupported_claims(text)


def test_analyzer_profile_v2_sections_fail_closed_without_raw_details(tmp_path):
    case_dir = write_case(
        tmp_path,
        json.dumps(
            {
                "profile_version": 2,
                "aggregated_profile": {
                    "sections": [
                        {
                            "name": "Query Timeline",
                            "value": "Completed admission after 45s on worker-a.example.net",
                        },
                        {
                            "name": "Admission result",
                            "value": "Queued for pool memory on worker-a.example.net",
                        },
                    ],
                    "counters": [
                        {"name": "ClientFetchWaitTimer", "value": "45s"},
                        {"name": "ScratchBytesWritten", "value": "4.0 KiB"},
                    ],
                },
            }
        ),
    )
    json_path = case_dir / "analysis.json"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "query_doctor.cli.analyze_profile",
            str(case_dir),
            "--json",
            str(json_path),
        ],
        cwd=str(REPO_DIR),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    analysis = json.loads(json_path.read_text(encoding="utf-8"))
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")

    assert analysis["profile_format"]["profile_dialect"] == "experimental_profile_v2"
    assert (
        analysis["profile_format"]["section_mappings"]["profile_counters"]["state"] == "unsupported"
    )
    assert analysis["profile_resources"]["available"] is False
    assert analysis["profile_timings"]["available"] is False
    assert analysis["client_fetch"]["evidence_tier"] == "unsupported"
    assert analysis["memory_pressure"]["evidence_tier"] == "unsupported"
    assert "profile_counters=unsupported" in text
    assert "## Client Fetch Tail Facts" not in text
    assert "## Memory Pressure Evidence" not in text
    assert "Completed admission after 45s" not in text
    assert "pool memory on" not in text
    assert "worker-a.example.net" not in text
    assert_no_banned_or_unsupported_claims(text)


def test_analyzer_renders_safe_profile_resource_facts_without_hosts(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
Summary:
  Admission result: Admitted immediately
  Per Host Number of Fragment Instances: worker-a.example.net:27000(2) worker-b.example.net:27000(5) worker-c.example.net:27000(3)
F00:
  Backend startup latencies: Count: 3, sum: 12ms, min / max: 2ms / 7ms, 25th %-ile: 2ms, 50th %-ile: 3ms, 75th %-ile: 5ms, 90th %-ile: 7ms, 95th %-ile: 7ms, 99.9th %-ile: 7ms
  Slowest backend to start up: worker-b.example.net:27000
  Per Node Peak Memory Usage: worker-a.example.net:27000(1.00 GiB) worker-b.example.net:27000(4.00 GiB) worker-c.example.net:27000(2.00 GiB)
  Per Node Bytes Read: worker-a.example.net:27000(10.00 GiB) worker-b.example.net:27000(20.00 GiB) worker-c.example.net:27000(15.00 GiB)
  Per Node User Time: worker-a.example.net:27000(20s100ms) worker-b.example.net:27000(30s200ms) worker-c.example.net:27000(25s)
  Per Node System Time: worker-a.example.net:27000(1s100ms) worker-b.example.net:27000(2s200ms) worker-c.example.net:27000(1s650ms)
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Profile Resource Facts" in text
    assert "- admission_result: admitted_immediately" in text
    assert (
        "- backend_startup_latencies: count=3, sum=12ms, min=2ms, max=7ms, p50=3ms, p95=7ms" in text
    )
    assert (
        "- fragment_instances_per_host: hosts=3, total=10, min=2, max=5, max_min_ratio=2.50x"
        in text
    )
    assert (
        "- per_node_peak_memory: hosts=3, min=1.00 GiB, max=4.00 GiB, max_min_ratio=4.00x" in text
    )
    assert (
        "- per_node_bytes_read: hosts=3, min=10.00 GiB, max=20.00 GiB, max_min_ratio=2.00x" in text
    )
    assert "- per_node_user_time: hosts=3, min=20.1s, max=30.2s, max_min_ratio=1.50x" in text
    assert "- per_node_system_time: hosts=3, min=1.1s, max=2.2s, max_min_ratio=2.00x" in text
    assert "### Profile resource balance" in text
    assert "- status: context_only" in text
    assert "Profile resource facts were available, but admission, startup latency" in text
    assert "Profile Resource Facts: backend_startup_max=7ms." in text
    assert "Profile Resource Facts: per_node_bytes_read hosts=3, max_min_ratio=2.00x." in text
    assert "worker-a.example.net" not in text
    assert "worker-b.example.net" not in text
    assert "worker-c.example.net" not in text
    assert_no_banned_or_unsupported_claims(text)


def test_analyzer_renders_resource_trace_context_without_hosts(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
Summary:
  Query State: FINISHED
  Query Status: OK
    Per Node Profiles:
      worker-a.example.net:27000:
         - HostCpuIoWaitPercentage (50.000ms): 0, 25, 50
         - HostCpuSysPercentage (50.000ms): 2, 4
         - HostCpuUserPercentage (50.000ms): 10, 20
         - HostDiskReadThroughput (50.000ms): 1.00 MiB/sec, 3.00 MiB/sec
         - HostDiskWriteThroughput (50.000ms): 512.00 KiB/sec, 1.00 MiB/sec
         - HostNetworkRx (50.000ms): 2.00 MiB/sec, 4.00 MiB/sec
         - HostNetworkTx (50.000ms): 1.00 MiB/sec, 2.00 MiB/sec
      worker-b.example.net:27000:
         - HostCpuUserPercentage (50.000ms): 30
""",
    )
    json_path = case_dir / "analysis.json"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "query_doctor.cli.analyze_profile",
            str(case_dir),
            "--json",
            str(json_path),
        ],
        cwd=str(REPO_DIR),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    analysis = json.loads(json_path.read_text(encoding="utf-8"))
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")

    assert analysis["resource_trace"]["status"] == "available"
    assert analysis["resource_trace"]["evidence_tier"] == "context_only"
    assert analysis["resource_trace"]["primary_supported"] is False
    assert analysis["resource_trace"]["selected_query_mapping"] == "unproven"
    assert analysis["resource_trace"]["metrics"]["cpu_io_wait_percentage"]["sample_count"] == 3
    assert analysis["resource_trace"]["metrics"]["cpu_io_wait_percentage"]["max"] == 50
    assert analysis["resource_trace"]["metrics"]["cpu_user_percentage"]["sample_count"] == 3
    assert "## Resource Trace Facts" in text
    assert "- evidence_tier: context_only" in text
    assert "- primary_supported: no" in text
    assert "- selected_query_mapping: unproven" in text
    assert (
        "- cpu_io_wait_percentage: samples=3, min=0.00%, max=50.00%, avg=25.00%, "
        "max_min_ratio=2.00x" in text
    )
    assert (
        "- cpu_user_percentage: samples=3, min=10.00%, max=30.00%, avg=20.00%, "
        "max_min_ratio=3.00x" in text
    )
    assert (
        "- disk_read_throughput: samples=2, min=1.00 MiB/s, max=3.00 MiB/s, "
        "avg=2.00 MiB/s, max_min_ratio=3.00x" in text
    )
    assert (
        "- network_receive_throughput: samples=2, min=2.00 MiB/s, max=4.00 MiB/s, "
        "avg=3.00 MiB/s, max_min_ratio=2.00x" in text
    )
    assert "Resource trace samples are safe aggregate host context only" in text
    assert "worker-a.example.net" not in text
    assert "worker-b.example.net" not in text
    assert_no_banned_or_unsupported_claims(text)


def test_runtime_diagnosis_treats_profile_queued_admission_as_follow_up(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
Summary:
  Admission result: Queued
  Per Host Number of Fragment Instances: worker-a.example.net:27000(2) worker-b.example.net:27000(2)
F00:
  Backend startup latencies: Count: 2, sum: 20s, min / max: 7s / 13s, 50th %-ile: 10s, 95th %-ile: 13s
  Per Node Peak Memory Usage: worker-a.example.net:27000(2.00 GiB) worker-b.example.net:27000(2.50 GiB)
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Runtime Diagnosis" in text
    assert (
        "- summary: Profile resource balance is the strongest plausible follow-up hypothesis from deterministic facts."
        in text
    )
    assert "### Profile resource balance" in text
    assert "- status: plausible_follow_up" in text
    assert "Backend startup latency is large enough to be a plausible follow-up hypothesis." in text
    assert (
        "Runtime Admission Evidence: admission result is context-only without material selected-query wait"
        in text
    )
    assert "Profile Resource Facts: admission_result=queued." in text
    assert "Profile Resource Facts: backend_startup_max=13s." in text
    assert "worker-a.example.net" not in text
    assert "worker-b.example.net" not in text
    assert_no_banned_or_unsupported_claims(text)


def test_analyzer_promotes_profile_admission_wait_to_primary(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
Summary:
  Admission result: Admitted (queued)
  Initial admission queue reason: waited 45s, reason: pool memory on worker-a.example.net:27000
  Per Host Number of Fragment Instances: worker-a.example.net:27000(2) worker-b.example.net:27000(2)
Query Timeline: 2m
  - Query submitted: 0ms
  - Planning finished: 1s (1s)
  - Submit for admission: 1s
  - Completed admission: 46s (45s)
  - Ready to start 2 backends: 47s
  - All 2 execution backends started: 48s (1s)
  - Unregister query: 2m (1s)
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Primary Bottleneck" in text
    assert "- label: runtime_admission" in text
    assert "- confidence: high" in text
    assert "admission_wait_share_37pct" in text
    assert "admission_wait_source_profile_resource_facts" in text
    assert "## Runtime Admission Evidence" in text
    assert "- evidence_tier: strong" in text
    assert "- primary_supported: yes" in text
    assert "- selected_wait: 45s (source=profile_resource_facts, share=37%)" in text
    assert "## Profile Resource Facts" in text
    assert "- admission_result: queued" in text
    assert "- admission_wait: 45s" in text
    assert "- admission_queue_reason_category: pool_memory" in text
    assert "### Card 1: Admission wait or rejection dominated the case" in text
    assert "worker-a.example.net" not in text
    assert "pool memory on" not in text
    assert_no_banned_or_unsupported_claims(text)


def test_analyzer_uses_profile_total_time_as_wall_clock_fallback(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
01:SCAN HDFS  1  1s000ms  1s000ms  10  10  1.00 MB  1.00 MB
```

## Metric lines

```text
- TotalTime: 20s
```
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Query Wall Clock" in text
    assert "- duration: 20s" in text
    assert "- source: profile TotalTime" in text
    assert "- confidence: medium" in text


def test_analyzer_uses_query_timeline_before_profile_total_time_fallback(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

Query Timeline:
  - Query submitted: 0ns (0)
  - Planning finished: 2s (2s)
  - Rows available: 1.50m (1.50m)

## ExecSummary

```text
01:SCAN HDFS  1  1s000ms  1s000ms  10  10  1.00 MB  1.00 MB
```

## Metric lines

```text
- TotalTime: 20s
```
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Query Wall Clock" in text
    assert "- duration: 1.50m" in text
    assert "- source: profile Query Timeline" in text
    assert "- confidence: medium" in text
    assert "## Profile Timing Facts" in text
    assert "- query_timeline: duration=1.50m, events=3" in text
    assert (
        "- query_timeline_phases: planning=2s, admission=n/a, backend_start=n/a, "
        "rows_available=1.50m, fetch=n/a, unregister=n/a"
    ) in text


def test_analyzer_renders_safe_profile_timing_facts(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

Query Timeline: 1.00m (60000000000)
  - Query submitted: 10us (10us)
  - Planning finished: 2s (2s)
  - Submit for admission: 2s100ms (100ms)
  - Completed admission: 5s (2s900ms)
  - Ready to start on 2 backends: 5s100ms (100ms)
  - All 2 execution backends (4 fragment instances) started: 8s100ms (3s)
  - Rows available: 40s (31s900ms)
  - First row fetched: 42s (2s)
  - Last row fetched: 50s (8s)
  - Unregister query: 1m (10s)

F00:
  HDFS_SCAN_NODE (id=00)
    - RowsProduced: 10 (10)
    - TotalTime: 1s (1000000000)
  Fragment Instance Lifecycle Event Timeline: 40s
    - Prepare Finished: 1ms (1ms)
    - Open Finished: 10s (10s)
    - First Batch Produced: 30s (20s)
    - ExecInternal Finished: 40s (10s)
  Fragment Instance Lifecycle Event Timeline: 20s
    - Prepare Finished: 2ms (2ms)
    - Open Finished: 5s (5s)
    - First Batch Produced: 10s (5s)
    - ExecInternal Finished: 20s (10s)
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Profile Timing Facts" in text
    assert "- query_timeline: duration=1.00m, events=10" in text
    assert (
        "- query_timeline_phases: planning=2s, admission=2.9s, backend_start=3s, "
        "rows_available=31.9s, fetch=8s, unregister=10s"
    ) in text
    assert "- fragment_lifecycle: instances=2, timeline_max=40s" in text
    assert "- fragment_lifecycle_prepare_finished: count=2, min=1ms, max=2ms" in text
    assert "- fragment_lifecycle_open_finished: count=2, min=5s, max=10s" in text
    assert "- fragment_lifecycle_first_batch_produced: count=2, min=5s, max=20s" in text
    assert "- fragment_lifecycle_exec_internal_finished: count=2, min=10s, max=10s" in text
    assert "### Profile timing phases" in text
    assert "- status: plausible_follow_up" in text
    assert (
        "Investigate rows_available, fragment_open, fragment_first_batch, fragment_exec_internal "
        "with comparable query profiles"
    ) in text
    assert (
        "Profile Timing Facts: query_timeline_phases planning=2s, admission=2.9s, "
        "backend_start=3s, rows_available=31.9s, fetch=8s, unregister=10s."
    ) in text
    assert (
        "Profile Timing Facts: fragment_lifecycle instances=2, open_max=10s, "
        "first_batch_max=20s, exec_internal_max=10s."
    ) in text
    assert "All 2 execution backends" not in text
    assert "ExecInternal Finished:" not in text
    assert_no_banned_or_unsupported_claims(text)


def test_analyzer_detects_client_fetch_tail_from_query_specific_counter(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

Query Timeline: 100s (100000000000)
  - Query submitted: 0ns (0)
  - Rows available: 50s (50s)
  - First row fetched: 55s (5s)
  - Last row fetched: 100s (45s)

## ExecSummary

```text
01:SCAN HDFS  1  1s000ms  1s000ms  10  10  1.00 MB  1.00 MB
```

## Metric lines

```text
- TotalTime: 100s
- ClientFetchWaitTimer: 45s
```
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Client Fetch Tail Facts" in text
    assert "- evidence_tier: strong" in text
    assert "- finding_supported: yes" in text
    assert (
        "- client_fetch_wait: 45s (counter=ClientFetchWaitTimer, share=45%, query_duration=1.67m)"
    ) in text
    assert "### Client fetch tail [medium]" in text
    assert "- label: client_fetch_tail" in text
    assert "- confidence: medium" in text
    assert "client_fetch_wait_share_45pct" in text
    assert "not proof of an external client, Hue, BI tool, or network root cause" in text
    assert_no_banned_or_unsupported_claims(text)


def test_analyzer_treats_timeline_fetch_without_counter_as_context_only(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

Query Timeline: 100s (100000000000)
  - Query submitted: 0ns (0)
  - Rows available: 10s (10s)
  - First row fetched: 20s (10s)
  - Last row fetched: 100s (80s)

## ExecSummary

```text
01:SCAN HDFS  1  1s000ms  1s000ms  10  10  1.00 MB  1.00 MB
```

## Metric lines

```text
- TotalTime: 100s
```
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Client Fetch Tail Facts" in text
    assert "- evidence_tier: context_only" in text
    assert "- finding_supported: no" in text
    assert "### Client fetch tail" not in text
    assert "- label: client_fetch_tail" not in text
    assert "Query Timeline fetch phase is context only" in text


def test_analyzer_treats_profile_serialization_counter_as_context_only(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

Query Timeline: 100s (100000000000)
  - Query submitted: 0ns (0)
  - Rows available: 50s (50s)

## ExecSummary

```text
01:SCAN HDFS  1  1s000ms  1s000ms  10  10  1.00 MB  1.00 MB
```

## Metric lines

```text
- TotalTime: 100s
- GetInFlightProfileTimeStats: max=30s
```
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Client Fetch Tail Facts" in text
    assert "- evidence_tier: context_only" in text
    assert "- finding_supported: no" in text
    assert "- profile_serialization_context: 30s (counter=GetInFlightProfileTimeStats)" in text
    assert "### Client fetch tail" not in text
    assert "not client fetch wait evidence by itself" in text


def test_analyzer_uses_query_timeline_when_profile_total_time_is_zero(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

Query Timeline: 2.00m (120000000000)
  - Query submitted: 0ns (0)
  - Unregister query: 2.00m (120000000000)

## ExecSummary

```text
01:SCAN HDFS  1  1s000ms  1s000ms  10  10  1.00 MB  1.00 MB
```

## Metric lines

```text
- TotalTime: 0ns
```
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "- duration: 2.00m" in text
    assert "- source: profile Query Timeline" in text


def test_analyzer_prefers_cm_duration_over_query_timeline(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

Query Timeline:
  - Unregister query: 2.00m (120000000000)

## ExecSummary

```text
01:SCAN HDFS  1  1s000ms  1s000ms  10  10  1.00 MB  1.00 MB
```
""",
    )
    (case_dir / "cm_metadata.json").write_text(
        json.dumps({"duration_ms": 180000}),
        encoding="utf-8",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "- duration: 3.00m" in text
    assert "- source: CM Query Context" in text
    assert "- confidence: high" in text


def test_analyzer_uses_cm_duration_when_profile_total_time_is_zero_for_codegen_share(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
01:SCAN HDFS  1  1s000ms  1s000ms  10  10  1.00 MB  1.00 MB
```

## Metric lines

```text
- TotalTime: 0ns
- CodegenTotalWallClockTime: 1s
```
""",
    )
    (case_dir / "cm_metadata.json").write_text(
        json.dumps({"duration_ms": 100000}),
        encoding="utf-8",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "- duration: 1.67m" in text
    assert "- source: CM Query Context" in text
    assert "Codegen candidate signal" not in text
    assert "No codegen/LLVM candidate signal was parsed." in text


def test_analyzer_uses_cm_duration_when_profile_total_time_is_zero_for_storage_share(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
01:HDFS SCAN                        1  20s000ms 20s000ms   900.00K     900.00K   128.00 MiB  128.00 MiB  synthetic.table
```

## Metric lines

```text
- TotalTime: 0ns
- TotalBytesRead: 20.0 GiB
```
""",
    )
    (case_dir / "cm_metadata.json").write_text(
        json.dumps({"duration_ms": 500000}),
        encoding="utf-8",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "- duration: 8.33m" in text
    assert "- source: CM Query Context" in text
    assert "### Storage/HDFS candidate signal" not in text
    assert "Large TotalBytesRead is an I/O footprint, not proof" in text


def test_raw_node_operator_time_ignores_nested_cumulative_counters(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## Metric lines

```text
- TotalTime: 30s
```

## Runtime profile

```text
Averaged Fragment F00
  HDFS_SCAN_NODE (id=3)
    - RowsRead: 1000 (1000)
    - RowsReturned: 1000 (1000)
    ScannerThreads
      - ScannerThreadsTotalWallClockTime: 5m (300000000000)
      - TotalTime: 5m (300000000000)
    CodeGen
      - CodegenTotalWallClockTime: 4m (240000000000)
      - TotalTime: 4m (240000000000)
    - PeakMemoryUsage: 128.0 MiB (134217728)
    - TotalStorageWaitTime: 3s (3000000000)
    - TotalTime: 500ms (500000000)
      - ExecTime: 400ms (400000000)
```
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "| 03:HDFS SCAN | 500ms | 1.00K | n/a |" in text
    assert "| 03:HDFS SCAN | 5.00m |" not in text
    assert "| 03:HDFS SCAN | 4.00m |" not in text
    assert "## Runtime Counter Context" in text
    assert "Runtime thread/codegen/wait/CPU counters are context only" in text
    assert "- codegen: counters=1, max=4.00m, max_counter=CodegenTotalWallClockTime" in text
    assert (
        "- thread wall-clock: counters=1, max=5.00m, max_counter=ScannerThreadsTotalWallClockTime"
        in text
    )
    assert "- wait: counters=1, max=3s, max_counter=TotalStorageWaitTime" in text


def test_raw_node_direct_counter_indent_ignores_child_only_counters():
    module = load_analyzer_module()
    section_lines = [
        "  HDFS_SCAN_NODE (id=3)",
        "    CodeGen",
        "      - CodegenTotalWallClockTime: 4m (240000000000)",
        "      - TotalTime: 4m (240000000000)",
    ]

    assert module.raw_node_direct_counter_indent(section_lines, 2) is None


def test_analyzer_evidence_quality_high_with_profile_runtime_metrics_and_metadata(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
01:SCAN HDFS  1  1s000ms  1s000ms  100  100  1.00 MB  1.00 MB quality.table
```

## Backend counters

```text
Backend 1 host=worker-a fragment=F00:000
  - ScanBytesAssigned: 10.0 GiB
  - BytesRead: 10.0 GiB
  - RowsProduced: 100,000
  - ExecutionTime: 40s
Backend 2 host=worker-b fragment=F00:001
  - ScanBytesAssigned: 10.1 GiB
  - BytesRead: 10.0 GiB
  - RowsProduced: 101,000
  - ExecutionTime: 42s
Backend 3 host=worker-c fragment=F00:002
  - ScanBytesAssigned: 10.0 GiB
  - BytesRead: 10.2 GiB
  - RowsProduced: 99,000
  - ExecutionTime: 41s
```
""",
    )
    (case_dir / "cm_metadata.json").write_text(
        json.dumps({"duration_ms": 90000}),
        encoding="utf-8",
    )
    write_cm_timeseries_context(case_dir)
    (case_dir / "impala_context.json").write_text(
        json.dumps(
            {
                "tables": ["quality.table"],
                "read_only_statements_only": True,
                "results": [
                    {
                        "table": "quality.table",
                        "statement": "SHOW TABLE STATS",
                        "status": "ok",
                        "stdout": "| #Rows | Size |\n| 123 | 1MB |\n",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Evidence Quality" in text
    assert "- score: 90/100" in text
    assert "- level: high" in text
    assert "- profile operators parsed: 1" in text
    assert "- query wall-clock available from CM Query Context" in text
    assert "- comparable backend groups: 1" in text
    assert "- runtime metrics coverage: 4/4 metrics ok, 40 points" in text
    assert "- table metadata facts supported for 1 requested tables" in text


def test_analyzer_evidence_quality_low_when_core_context_is_missing(tmp_path):
    case_dir = write_case(tmp_path, "# Synthetic digest\n")

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Evidence Quality" in text
    assert "- score: 0/100" in text
    assert "- level: low" in text
    assert "- no profile operators were parsed" in text
    assert "- query wall-clock duration is unknown" in text
    assert "- backend per-host facts are unavailable" in text
    assert "- runtime metrics context is unavailable" in text
    assert "- table metadata context is unavailable" in text


def test_analyzer_includes_safe_cm_timeseries_context(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
01:SCAN HDFS  1  1s000ms  1s000ms  10  10  1.00 MB  1.00 MB
```
""",
    )
    (case_dir / "cm_timeseries_context.json").write_text(
        json.dumps(
            {
                "available": True,
                "metrics_profile": "cm6",
                "limits": {
                    "max_response_bytes": 12345,
                    "max_points_per_query": 10,
                },
                "window": {
                    "from": "2026-05-04T09:59:00Z",
                    "to": "2026-05-04T10:06:00Z",
                    "padding_sec": 60,
                },
                "queries": [
                    {
                        "id": "impala_daemon_cpu",
                        "label": "Impala daemon CPU pressure",
                        "status": "ok",
                        "point_count": 2,
                        "min": 10,
                        "max": 30,
                        "avg": 20,
                        "latest": 30,
                    }
                ],
                "warnings": ["impala_daemon_memory: unavailable"],
            }
        ),
        encoding="utf-8",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## CM Time-Series Context" in text
    assert "- available: yes" in text
    assert "- metrics_profile: cm6" in text
    assert "- window: 2026-05-04T09:59:00Z to 2026-05-04T10:06:00Z" in text
    assert "### Impala daemon CPU pressure" in text
    assert "- point_count: 2" in text
    assert "- max: 30.00" in text
    assert "timestamp" not in text


def test_analyzer_prefers_canonical_runtime_metrics_context_for_cm(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
01:SCAN HDFS  1  1s000ms  1s000ms  10  10  1.00 MB  1.00 MB
```
""",
    )
    canonical_context = {
        "available": True,
        "source": "cm_timeseries",
        "source_label": "Cloudera Manager time-series metrics",
        "metrics_profile": "cm-canonical",
        "limits": {
            "max_response_bytes": 12345,
            "max_points_per_query": 10,
        },
        "window": {
            "from": "2026-05-04T09:59:00Z",
            "to": "2026-05-04T10:06:00Z",
            "padding_sec": 60,
        },
        "queries": [
            {
                "id": "impala_daemon_cpu",
                "label": "Canonical CM CPU pressure",
                "status": "ok",
                "point_count": 2,
                "min": 10,
                "max": 30,
                "avg": 20,
                "latest": 30,
            }
        ],
    }
    legacy_context = {
        **canonical_context,
        "metrics_profile": "cm-legacy",
        "queries": [
            {
                "id": "impala_daemon_cpu",
                "label": "Legacy CM CPU pressure",
                "status": "ok",
                "point_count": 2,
                "min": 10,
                "max": 40,
                "avg": 25,
                "latest": 40,
            }
        ],
    }
    (case_dir / "runtime_metrics_context.json").write_text(
        json.dumps(canonical_context), encoding="utf-8"
    )
    (case_dir / "cm_timeseries_context.json").write_text(
        json.dumps(legacy_context), encoding="utf-8"
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "- metrics_profile: cm-canonical" in text
    assert "Canonical CM CPU pressure" in text
    assert "cm-legacy" not in text
    assert "Legacy CM CPU pressure" not in text


def test_analyzer_accepts_prometheus_runtime_metrics_context(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
01:SCAN HDFS  1  1s000ms  1s000ms  10  10  1.00 MB  1.00 MB
```
""",
    )
    (case_dir / "runtime_metrics_context.json").write_text(
        json.dumps(
            {
                "available": True,
                "source": "prometheus",
                "source_label": "Prometheus runtime metrics",
                "metrics_profile": "ambari-hadoop",
                "limits": {
                    "max_response_bytes": 12345,
                    "max_points_per_query": 10,
                },
                "window": {
                    "from": "2026-05-04T09:59:00Z",
                    "to": "2026-05-04T10:06:00Z",
                    "padding_sec": 60,
                },
                "queries": [
                    {
                        "id": "host_cpu_user",
                        "label": "Host CPU user rate",
                        "status": "ok",
                        "point_count": 3,
                        "min": 90,
                        "max": 95,
                        "avg": 92,
                        "latest": 95,
                    },
                    {
                        "id": "host_cpu_system",
                        "label": "Host CPU system rate",
                        "status": "no_data",
                        "point_count": 0,
                    },
                ],
                "warnings": ["raw hostname host-a.example.net should not render"],
            }
        ),
        encoding="utf-8",
    )

    json_path = case_dir / "analysis.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "query_doctor.cli.analyze_profile",
            str(case_dir),
            "--json",
            str(json_path),
        ],
        cwd=str(REPO_DIR),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    analysis = json.loads(json_path.read_text(encoding="utf-8"))
    assert analysis["metrics_facts"] == analysis["cm_metrics_facts"]
    assert analysis["metrics_facts"]["source"] == "prometheus"
    assert analysis["metrics_facts"]["host_cpu_pressure"]["status"] == "observed"
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## CM Time-Series Context" in text
    assert "- source: prometheus" in text
    assert "- source_label: Prometheus runtime metrics" in text
    assert "- metrics_profile: ambari-hadoop" in text
    assert "## Runtime Metrics Facts" in text
    assert "## CM Metrics Facts" not in text
    assert "## CM Metrics Correlation" not in text
    assert "## Source Provenance" in text
    assert (
        "- metrics: partial; source=Prometheus runtime metrics; coverage=1/2 metric queries ok"
        in text
    )
    assert "- host_cpu_pressure: observed" in text
    assert (
        "Prometheus metrics collection limits: max_points_per_query=10, max_response_bytes=12345."
        in text
    )
    assert (
        "Prometheus host-level metrics can cover multiple Impala deployments on the same hosts"
        in text
    )
    assert "Prometheus metrics returned no_data for: host_cpu_system." in text
    assert "host-a.example.net" not in text


def test_analyzer_derives_conservative_cm_metrics_facts(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
01:SCAN HDFS  1  1s000ms  1s000ms  10  10  1.00 MB  1.00 MB
```
""",
    )
    (case_dir / "cm_timeseries_context.json").write_text(
        json.dumps(
            {
                "available": True,
                "metrics_profile": "cm6",
                "limits": {
                    "max_response_bytes": 12345,
                    "max_points_per_query": 10,
                },
                "window": {
                    "from": "2026-05-04T09:59:00Z",
                    "to": "2026-05-04T10:06:00Z",
                    "padding_sec": 60,
                },
                "queries": [
                    {
                        "id": "impala_daemon_memory",
                        "label": "Impala daemon memory",
                        "status": "ok",
                        "point_count": 10,
                        "min": 10 * 1024 * 1024 * 1024,
                        "max": 23 * 1024 * 1024 * 1024,
                        "avg": 16 * 1024 * 1024 * 1024,
                        "latest": 23 * 1024 * 1024 * 1024,
                        "series_count": 2,
                        "top_series": [
                            {
                                "series": "series_01",
                                "point_count": 5,
                                "min": 12 * 1024 * 1024 * 1024,
                                "max": 23 * 1024 * 1024 * 1024,
                                "avg": 18 * 1024 * 1024 * 1024,
                                "latest": 23 * 1024 * 1024 * 1024,
                            },
                            {
                                "series": "series_02",
                                "point_count": 5,
                                "min": 10 * 1024 * 1024 * 1024,
                                "max": 11 * 1024 * 1024 * 1024,
                                "avg": 10.5 * 1024 * 1024 * 1024,
                                "latest": 11 * 1024 * 1024 * 1024,
                            },
                        ],
                    },
                    {
                        "id": "host_cpu_user",
                        "label": "Host CPU user",
                        "status": "ok",
                        "point_count": 10,
                        "min": 1,
                        "max": 22,
                        "avg": 5,
                        "latest": 4,
                    },
                    {
                        "id": "host_cpu_system",
                        "label": "Host CPU system",
                        "status": "ok",
                        "point_count": 10,
                        "min": 0,
                        "max": 3,
                        "avg": 1,
                        "latest": 1,
                    },
                    {
                        "id": "host_network_io",
                        "label": "Host network I/O",
                        "status": "ok",
                        "point_count": 10,
                        "truncated": True,
                        "min": 1 * 1024 * 1024,
                        "max": 200 * 1024 * 1024,
                        "avg": 20 * 1024 * 1024,
                        "latest": 8 * 1024 * 1024,
                        "series_count": 2,
                        "top_series": [
                            {
                                "series": "series_01",
                                "point_count": 5,
                                "min": 10 * 1024 * 1024,
                                "max": 200 * 1024 * 1024,
                                "avg": 50 * 1024 * 1024,
                                "latest": 8 * 1024 * 1024,
                            },
                            {
                                "series": "series_02",
                                "point_count": 5,
                                "min": 1 * 1024 * 1024,
                                "max": 50 * 1024 * 1024,
                                "avg": 10 * 1024 * 1024,
                                "latest": 5 * 1024 * 1024,
                            },
                        ],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Runtime Metrics Facts" in text
    assert "## CM Metrics Facts" not in text
    assert "- status: available" in text
    assert "- metrics_profile: cm6" in text
    assert "- coverage: 4/4 metrics ok, 40 points" in text
    assert "- availability: 4 ok, 0 no_data, 0 unavailable" in text
    assert "- unavailable_metrics: none" in text
    assert "- max_response_bytes: 12345" in text
    assert "- max_points_per_query: 10" in text
    assert "- host_cpu_pressure: not_observed" in text
    assert "- daemon_memory_growth: observed" in text
    assert "series_count: 2" in text
    assert "top_series_by_max" in text
    assert "top series max/peer max=2.09x" in text
    assert "- daemon_memory_pressure: unknown" in text
    assert "- network_io_spike: observed" in text
    assert "top series max/peer max=4.00x" in text
    assert "## Runtime Metrics Correlation" in text
    assert "## CM Metrics Correlation" not in text
    assert "- correlated_signals: 0" in text
    assert "- context_only_signals: 2" in text
    assert "- daemon_memory_growth: context_only (metric=observed, strength=weak)" in text
    assert "- network_io_spike: context_only (metric=observed, strength=weak)" in text
    assert "## Cluster Runtime Context" in text
    assert "- collection_status: collected" in text
    assert "- window_scope: bounded query runtime window with 60s padding" in text
    assert "- limit_summary: max_points_per_query=10, max_response_bytes=12345" in text
    assert "- observed_signals: Daemon memory growth, Network I/O spike" in text
    assert "- context_only_signals: Daemon memory growth, Network I/O spike" in text
    assert (
        "- scoring_contribution: none; only correlated runtime metric signals can add bounded runtime triage score"
        in text
    )
    assert "standalone proof of cause" in text
    assert (
        "CM metrics collection limits: max_points_per_query=10, max_response_bytes=12345." in text
    )
    assert "CM metrics were truncated for: host_network_io." in text
    assert "timestamp" not in text


def test_analyzer_explains_partial_cm_metrics_coverage(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
01:SCAN HDFS  1  1s000ms  1s000ms  10  10  1.00 MB  1.00 MB
```
""",
    )
    (case_dir / "cm_timeseries_context.json").write_text(
        json.dumps(
            {
                "available": True,
                "metrics_profile": "cm6",
                "queries": [
                    {
                        "id": "host_cpu_user",
                        "label": "Host CPU user",
                        "status": "ok",
                        "point_count": 10,
                        "min": 1,
                        "max": 22,
                        "avg": 5,
                    },
                    {
                        "id": "host_network_receive_rate",
                        "label": "Host network receive rate",
                        "status": "unavailable",
                        "point_count": 0,
                    },
                    {
                        "id": "impala_daemon_memory",
                        "label": "Impala daemon memory",
                        "status": "no_data",
                        "point_count": 0,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Runtime Metrics Facts" in text
    assert "- status: partial" in text
    assert "- metrics_profile: cm6" in text
    assert "- coverage: 1/3 metrics ok, 10 points" in text
    assert "- availability: 1 ok, 1 no_data, 1 unavailable" in text
    assert "- unavailable_metrics: host_network_receive_rate" in text
    assert "- no_data_metrics: impala_daemon_memory" in text
    assert "host network I/O metric is missing or has insufficient points; availability:" in text
    assert "host_network_receive_rate=unavailable" in text
    assert "host_network_transmit_rate=missing" in text
    assert "CM metrics unavailable for: host_network_receive_rate." in text
    assert "profile/version metric-name mismatch" in text
    assert "CM metrics returned no_data for: impala_daemon_memory." in text
    assert "## Cluster Runtime Context" in text
    assert "- status: partial" in text
    assert "- collection_status: collected" in text
    assert "- coverage: 1/3 metrics ok, 10 points" in text
    assert "- unknown_signals:" in text
    assert (
        "- scoring_contribution: none; only correlated runtime metric signals can add bounded runtime triage score"
        in text
    )
    assert "- runtime metrics coverage is partial" in text


def test_analyzer_correlates_cm_metrics_with_profile_evidence(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
01:HASH JOIN                        1  2s000ms  2s000ms    5.00M      10.00K   20.00 GB        1.00 GB  INNER JOIN, PARTITIONED
02:EXCHANGE                         1  3s000ms  3s000ms    5.00M      5.00M    20.00 GB       20.00 GB  HASH
```

## Metric lines

```text
- TotalBytesSent: 44.0 GiB (47244640256)
```
""",
    )
    write_cm_timeseries_context(case_dir, cpu_user_max=91, cpu_user_avg=73)

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Runtime Metrics Correlation" in text
    assert "## Memory Pressure Evidence" in text
    assert "- evidence_tier: context_only" in text
    assert "- runtime_metric_correlation_supported: no" in text
    assert "- memory_estimate_anomaly_count: 1" in text
    assert "- correlated_signals: 2" in text
    assert "- host_cpu_pressure: correlated (metric=observed, strength=moderate)" in text
    assert "- daemon_memory_growth: context_only (metric=observed, strength=weak)" in text
    assert "- network_io_spike: correlated (metric=observed, strength=moderate)" in text
    assert "Runtime metrics correlation: Daemon memory growth is correlated" not in text
    assert "Runtime metrics correlation: Network I/O spike is correlated" in text
    assert "Runtime metrics correlation: Host CPU pressure is correlated" in text
    assert (
        "Use runtime metrics only as correlated runtime context, not as standalone root-cause proof."
        in text
    )
    assert "## Cluster Runtime Context" in text
    assert "- correlated_signals: Host CPU pressure, Network I/O spike" in text
    assert (
        "- scoring_contribution: +4 triage score points from 2 correlated runtime metric signal(s), capped at +6"
        in text
    )
    assert "## Runtime Diagnosis" in text
    assert (
        "- summary: Network/exchange pressure is the strongest plausible follow-up hypothesis from deterministic facts."
        in text
    )
    assert "### Network/exchange pressure" in text
    assert "- status: plausible_follow_up" in text
    assert "Profile finding: Large intermediate or exchange traffic." in text
    assert "not standalone proof of external network instability" in text


def test_network_metric_without_mapped_exchange_context_stays_context_only(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
01:HASH JOIN                        1  2s000ms  2s000ms    5.00M      10.00K   20.00 GB        1.00 GB  INNER JOIN, PARTITIONED
```

## Metric lines

```text
- TotalBytesSent: 44.0 GiB (47244640256)
```
""",
    )
    write_cm_timeseries_context(case_dir, cpu_user_max=22, cpu_user_avg=5)

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "- network_io_spike: context_only (metric=observed, strength=weak)" in text
    assert "large data movement is context-only without mapped EXCHANGE operator evidence" in text
    assert "Network/exchange pressure is the strongest plausible follow-up" not in text
    assert_no_banned_or_unsupported_claims(text)


def test_nonzero_spill_supports_memory_metric_correlation(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
01:HASH JOIN                        1  2s000ms  2s000ms    5.00M      10.00K   20.00 GB        1.00 GB  INNER JOIN, PARTITIONED
```

## Metric lines

```text
- TotalTime: 40s
- SpilledBytes: 2.0 GiB
```
""",
    )
    write_cm_timeseries_context(case_dir, memory_min_gib=10, memory_max_gib=23)

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Memory Pressure Evidence" in text
    assert "- status: supported" in text
    assert "- evidence_tier: strong" in text
    assert "- finding_supported: yes" in text
    assert "- runtime_metric_correlation_supported: yes" in text
    assert "- spill_or_scratch_evidence_count: 1" in text
    assert "- daemon_memory_growth: correlated (metric=observed, strength=moderate)" in text
    assert "Runtime metrics correlation: Daemon memory growth is correlated" in text
    assert "### Memory pressure" in text
    assert "- status: plausible_follow_up" in text
    assert (
        "Memory pressure is a plausible follow-up hypothesis because selected-query non-zero spill/scratch evidence was parsed."
        in text
    )
    assert_no_banned_or_unsupported_claims(text)


def test_analyzer_generates_action_card_for_severe_cardinality_anomaly(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
01:HASH JOIN                        1  2s000ms  2s000ms    5.00M      10.00K   20.00 GB        1.00 GB  INNER JOIN, PARTITIONED
```

## Metric lines

```text
- TotalBytesRead: 12.0 GiB (12884901888)
- TotalBytesSent: 44.0 GiB (47244640256)
```
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout

    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Action Cards" in text
    assert "### Card 1: Severe cardinality underestimation before high-cost operator" in text
    assert "actual rows: 5.00M" in text
    assert "estimated rows: 10.00K" in text
    assert "actual/estimated ratio: 500x" in text
    assert "Check per-host RowsProduced for this operator." in text
    assert "Skew is suspected but not proven." in text


def test_cancelled_exec_node_downgrades_row_count_conclusions(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

Summary:
  Query State: FINISHED

## ExecSummary

```text
01:HASH JOIN                        1  2s000ms  2s000ms    5.00M      10.00K   20.00 GB        1.00 GB  INNER JOIN, PARTITIONED
02:HASH JOIN                        1  1s000ms  1s000ms  200.00K      10.00K    1.00 GB      512.00 MB  INNER JOIN
```

Averaged Fragment F00
  HASH_JOIN_NODE (id=1)
    - Cancelled: true
    - RowsProduced: 5,000,000 (5000000)
    - TotalTime: 2s000ms (2000000000)
  HASH_JOIN_NODE (id=2)
    - RowsProduced: 200,000 (200000)
    - TotalTime: 1s000ms (1000000000)
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Exec Node Completeness" in text
    assert "- row_count_conclusions: limited" in text
    assert "- affected_operator_count: 1" in text
    assert "01:HASH JOIN: state=cancelled" in text
    assert "Cardinality anomalies: 1" in text
    assert "### Card 1: Severe cardinality underestimation before high-cost operator" not in text
    assert "Zero rows on affected nodes must not be interpreted as an empty table" in text
    assert "runtime filters filtering everything" in text


def test_cancelled_query_state_blocks_cardinality_and_zero_row_claims(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

Summary:
  Query State: CANCELLED

## ExecSummary

```text
01:HASH JOIN                        1  2s000ms  2s000ms    5.00M      10.00K   20.00 GB        1.00 GB  INNER JOIN, PARTITIONED
02:HDFS SCAN                        1  1s000ms  1s000ms          0          0   64.00 MB       64.00 MB
```
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "- profile_wide_state: cancelled" in text
    assert "- row_count_conclusions: limited" in text
    assert "- affected_operator_count: 2" in text
    assert "Cardinality anomalies: 0" in text
    assert "Zero/unknown row estimate gaps: 0" in text
    assert "actual rows: 5.00M" not in text
    assert "runtime filters filtering everything" in text


def test_runtime_filter_context_renders_safe_aggregate_facts(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
02:HASH JOIN                        1  3s000ms  3s000ms    2.00M       1.00K   16.00 GiB     512.00 MiB  INNER JOIN, PARTITIONED
03:HDFS SCAN                        1  1s000ms  1s000ms    2.00M       1.00K  512.00 MiB     512.00 MiB
```

F01:PLAN FRAGMENT
|  02:HASH JOIN
|  |  runtime filters: RF001[bloom] <- sensitive_join_column
|  03:HDFS SCAN
|     runtime filters: RF001[bloom] -> sensitive_scan_column

Averaged Fragment F01
  HDFS_SCAN_NODE (id=3)
    Runtime filters: Not all filters arrived (arrived: [], missing [0]), waited for 803ms
    - BloomFilterBytes: 1.0 MiB (1048576)
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Runtime Filter Evidence" in text
    assert "- status: context_only" in text
    assert "- evidence_tier: context_only" in text
    assert "- finding_supported: no" in text
    assert "- primary_supported: no" in text
    assert "- runtime_filter_lines: 3" in text
    assert "- plan_filter_lines: 2" in text
    assert "- runtime_filter_id_count: 1" in text
    assert "- plan_producer_lines: 1" in text
    assert "- plan_consumer_lines: 1" in text
    assert "- plan_filter_id_count: 1" in text
    assert "- producer_filter_id_count: 1" in text
    assert "- consumer_filter_id_count: 1" in text
    assert "- paired_filter_id_count: 1" in text
    assert "- producer_consumer_mapping_status: mapped" in text
    assert "- target_scan_consumer_lines: 1" in text
    assert "- target_scan_filter_id_count: 1" in text
    assert "- paired_target_scan_filter_id_count: 1" in text
    assert "- target_scan_mapping_status: mapped" in text
    assert "- target_scan_family_counts: hdfs=1" in text
    assert "- routing_table_status: not_observed" in text
    assert "- routing_filter_count: 0" in text
    assert "- final_filter_count: 0" in text
    assert "- arrival_status: missing_observed" in text
    assert "- max_arrival_wait: 803ms" in text
    assert "sensitive_join_column" not in text
    assert "sensitive_scan_column" not in text


def test_analyzer_action_card_merges_cardinality_and_memory_evidence(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
02:HASH JOIN                        1  3s000ms  3s000ms    2.00M       1.00K   16.00 GiB     512.00 MiB  INNER JOIN, PARTITIONED
```
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout

    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "### Card 1: Severe cardinality underestimation before high-cost operator" in text
    assert "peak memory: 16.00 GiB" in text
    assert "estimated peak memory: 512.00 MiB" in text
    assert "peak/estimated memory ratio: 32.0x" in text
    assert "### Card 2:" not in text


def test_analyzer_action_cards_avoid_banned_vague_advice(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
03:SORT                             1  1s000ms  1s000ms    3.00M       1.00K    2.00 GB      128.00 MB
```
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout

    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8").lower()
    assert "reduce skew" not in text
    assert "optimize joins" not in text
    assert "improve query" not in text


def test_analyzer_works_when_no_action_cards_are_triggered(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
01:SCAN HDFS                        1  1ms  1ms      10          10    1.00 MB        1.00 MB  example_db1.table_a
```
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout

    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Action Cards" in text
    assert "No deterministic action cards were triggered from the parsed evidence." in text


def test_analyzer_includes_generated_impala_context(tmp_path):
    case_dir = copy_minimal_case(tmp_path)
    context_dir = case_dir / "impala_context"
    tables_dir = context_dir / "tables"
    tables_dir.mkdir(parents=True)
    (context_dir / "impala_context.md").write_text(
        "\n".join(
            [
                "# Impala Context",
                "",
                "## Warnings",
                "- SQL contains FROM/JOIN subqueries; table extraction is best-effort.",
                "",
                "## Metadata Commands",
                "- `SHOW COLUMN STATS example_db1.table_b`: failed rc=1; `impala_context/tables/example_db1.table_b.column_stats.txt`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (context_dir / "original_query.sql").write_text(
        "select * from example_db1.table_a\n", encoding="utf-8"
    )
    (context_dir / "referenced_tables.txt").write_text(
        "example_db1.table_a\nexample_db1.table_b\n\n# Warnings\n# ignored comment\n",
        encoding="utf-8",
    )
    (context_dir / "explain.txt").write_text("PLAN\n", encoding="utf-8")
    (tables_dir / "example_db1.table_a.show_create.sql").write_text(
        "CREATE TABLE example_db1.table_a\n", encoding="utf-8"
    )
    (tables_dir / "example_db1.table_a.table_stats.txt").write_text("stats\n", encoding="utf-8")
    (tables_dir / "example_db1.table_a.column_stats.txt").write_text("stats\n", encoding="utf-8")
    (tables_dir / "example_db1.table_a.describe_formatted.txt").write_text(
        "desc\n", encoding="utf-8"
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout

    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Impala Context" in text
    assert "### Original SQL" in text
    assert "- present: yes" in text
    assert "- path: `impala_context/original_query.sql`" in text
    assert "- `example_db1.table_a`" in text
    assert "- `example_db1.table_b`" in text
    assert "- EXPLAIN: available (`impala_context/explain.txt`)" in text
    assert (
        "SHOW CREATE TABLE: available (`impala_context/tables/example_db1.table_a.show_create.sql`)"
        in text
    )
    assert (
        "SHOW TABLE STATS: missing (`impala_context/tables/example_db1.table_b.table_stats.txt`)"
        in text
    )
    assert "SHOW COLUMN STATS example_db1.table_b" in text
    assert (
        "Run SHOW TABLE STATS for referenced tables involved in this query: `example_db1.table_a`, `example_db1.table_b`."
        in text
    )
    assert "select * from example_db1.table_a" not in text


def test_analyzer_reads_impala_context_json_table_metadata(tmp_path):
    case_dir = copy_minimal_case(tmp_path)
    (case_dir / "impala_context.json").write_text(
        json.dumps(
            {
                "tables": ["example_db1.table_a", "example_db2.table_b"],
                "read_only_statements_only": True,
                "results": [
                    {
                        "table": "example_db1.table_a",
                        "statement": "SHOW CREATE TABLE",
                        "status": "ok",
                        "stdout": (
                            "CREATE TABLE example_db1.table_a (id BIGINT, amount DOUBLE)\n"
                            "PARTITIONED BY (ds STRING)\n"
                            "STORED AS PARQUET\n"
                            "LOCATION 'hdfs://host_01:8020/warehouse/example_db1.table_a'\n"
                        ),
                    },
                    {
                        "table": "example_db1.table_a",
                        "statement": "SHOW TABLE STATS",
                        "status": "ok",
                        "stdout": "| #Rows | Size |\n| 123456 | 1.2 GiB |\n",
                    },
                    {
                        "table": "example_db1.table_a",
                        "statement": "SHOW COLUMN STATS",
                        "status": "ok",
                        "stdout": (
                            "| Column | Type | NDV | #Nulls |\n"
                            "| id | BIGINT | 123456 | 0 |\n"
                            "| amount | DOUBLE | -1 | NULL |\n"
                        ),
                    },
                    {
                        "table": "example_db2.table_b",
                        "statement": "SHOW CREATE TABLE",
                        "status": "timeout",
                        "error": "statement timed out after 30s",
                    },
                    {
                        "table": "example_db2.table_b",
                        "statement": "SHOW TABLE STATS",
                        "status": "too_large",
                        "error": "captured output exceeded max-output-bytes",
                    },
                    {
                        "table": "example_db2.table_b",
                        "statement": "SHOW COLUMN STATS",
                        "status": "error",
                        "stderr": "Authorization: Bearer <redacted>",
                    },
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Table Metadata Context" in text
    assert "- context file: present" in text
    assert "- context path: `impala_context.json`" in text
    assert "- table metadata facts: supported" in text
    assert "- tables requested: 2" in text
    assert "- read-only statements only: yes" in text
    assert "### Table: example_db1.table_a" in text
    assert "- SHOW CREATE TABLE status: ok" in text
    assert "- SHOW TABLE STATS status: ok" in text
    assert "- SHOW COLUMN STATS status: ok" in text
    assert "- table stats rows: 123456" in text
    assert "- table stats row-count completeness: available" in text
    assert "- table stats size: 1.2 GiB" in text
    assert "table stats state: supported" not in text
    assert "- column stats columns observed: 2" in text
    assert "- column stats missing/unknown markers: 2" in text
    assert "- column stats completeness: incomplete/unknown" in text
    assert "- column stats columns: `id`, `amount`" in text
    assert "- file format: PARQUET" in text
    assert "- storage family: hdfs" in text
    assert "- storage scheme: hdfs" in text
    assert "- partition columns: `ds`" in text
    assert "### Table: example_db2.table_b" in text
    assert "- SHOW CREATE TABLE status: timeout" in text
    assert "- SHOW TABLE STATS status: too_large" in text
    assert "- SHOW COLUMN STATS status: error" in text
    assert "- table stats row-count completeness: not_available" in text
    assert "- column stats completeness: not_available" in text
    assert "## Source Provenance" in text
    assert "- metadata: available; source=Impala metadata context; coverage=tables=2/2" in text
    assert "## Storage Context" in text
    assert "- storage_family: hdfs" in text
    assert "- storage_semantics: hdfs_locality_applicable" in text
    assert "- view_table_count: 0" in text
    assert "- hdfs_locality_applicable: yes" in text
    assert "- remote_reads_expected: no" in text
    assert "CREATE TABLE example_db1.table_a" not in text
    assert "LOCATION" not in text
    assert "hdfs://host_01" not in text
    assert "Authorization" not in text
    assert "COMPUTE STATS" not in text


def test_analyzer_distinguishes_metadata_status_from_stats_completeness(tmp_path):
    case_dir = copy_minimal_case(tmp_path)
    (case_dir / "impala_context.json").write_text(
        json.dumps(
            {
                "tables": ["scratch_db.query_doctor_meta_probe"],
                "read_only_statements_only": True,
                "results": [
                    {
                        "table": "scratch_db.query_doctor_meta_probe",
                        "statement": "SHOW TABLE STATS",
                        "status": "ok",
                        "stdout": "| #Rows | Size |\n| -1 | 34B |\n",
                    },
                    {
                        "table": "scratch_db.query_doctor_meta_probe",
                        "statement": "SHOW COLUMN STATS",
                        "status": "ok",
                        "stdout": (
                            "| Column | Type | NDV | #Nulls | Max Size | Avg Size |\n"
                            "| id | BIGINT | -1 | NULL | -1 | 8 |\n"
                            "| name | STRING | -1 | -1 | NULL | 10 |\n"
                            "| amount | DOUBLE | 10 | 0 | -1 | unknown |\n"
                        ),
                    },
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "- SHOW TABLE STATS status: ok" in text
    assert "- SHOW COLUMN STATS status: ok" in text
    assert "- table stats rows: unknown" in text
    assert "- table stats row-count completeness: missing/unknown" in text
    assert "- table stats size: 34B" in text
    assert "- column stats columns observed: 3" in text
    assert "- column stats missing/unknown markers: 8" in text
    assert "- column stats completeness: incomplete/unknown" in text
    assert "table stats state: supported" not in text


def test_analyzer_renders_partition_row_count_coverage_without_partition_values(tmp_path):
    case_dir = copy_minimal_case(tmp_path)
    (case_dir / "impala_context.json").write_text(
        json.dumps(
            {
                "tables": ["scratch_db.partitioned_probe"],
                "read_only_statements_only": True,
                "results": [
                    {
                        "table": "scratch_db.partitioned_probe",
                        "statement": "SHOW CREATE TABLE",
                        "status": "ok",
                        "stdout": (
                            "CREATE TABLE scratch_db.partitioned_probe (id BIGINT)\n"
                            "PARTITIONED BY (ds STRING)\n"
                            "STORED AS PARQUET\n"
                        ),
                    },
                    {
                        "table": "scratch_db.partitioned_probe",
                        "statement": "SHOW TABLE STATS",
                        "status": "ok",
                        "stdout": (
                            "| ds | #Rows | Size |\n"
                            "| 2026-05-01 | 10 | 1 MiB |\n"
                            "| 2026-05-02 | -1 | 1 MiB |\n"
                            "| 2026-05-03 | 0 | 0B |\n"
                            "| Total | -1 | 2 MiB |\n"
                        ),
                    },
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "- table stats rows: unknown" in text
    assert "- table stats row-count completeness: missing/unknown" in text
    assert "- table stats size: 2 MiB" in text
    assert "- partition count: 3" in text
    assert "- partitions with known row count: 2" in text
    assert "- partitions with unknown row count: 1" in text
    assert "- partitions with zero row count: 1" in text
    assert "- partition_coverage: partial" in text
    assert "- partition_count: 3" in text
    assert "- partitions_with_known_row_count: 2" in text
    assert "- partitions_with_unknown_row_count: 1" in text
    assert "- partitions_with_zero_row_count: 1" in text
    assert "2026-05-01" not in text
    assert "2026-05-02" not in text
    assert "2026-05-03" not in text


def test_analyzer_totals_only_partition_stats_keep_partition_coverage_unknown(tmp_path):
    case_dir = copy_minimal_case(tmp_path)
    (case_dir / "impala_context.json").write_text(
        json.dumps(
            {
                "tables": ["scratch_db.partitioned_probe"],
                "read_only_statements_only": True,
                "results": [
                    {
                        "table": "scratch_db.partitioned_probe",
                        "statement": "SHOW CREATE TABLE",
                        "status": "ok",
                        "stdout": (
                            "CREATE TABLE scratch_db.partitioned_probe (id BIGINT)\n"
                            "PARTITIONED BY (ds STRING)\n"
                        ),
                    },
                    {
                        "table": "scratch_db.partitioned_probe",
                        "statement": "SHOW TABLE STATS",
                        "status": "ok",
                        "stdout": "| ds | #Rows | Size |\n| Total | 10 | 1 MiB |\n",
                    },
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "- table stats rows: 10" in text
    assert "- partition count: 0" not in text
    assert "- partition_coverage: unknown" in text


def test_analyzer_renders_view_stats_as_not_applicable(tmp_path):
    case_dir = copy_minimal_case(tmp_path)
    (case_dir / "impala_context.json").write_text(
        json.dumps(
            {
                "tables": ["example_db1.view_a"],
                "read_only_statements_only": True,
                "results": [
                    {
                        "table": "example_db1.view_a",
                        "statement": "SHOW CREATE TABLE",
                        "status": "ok",
                        "stdout": "CREATE VIEW example_db1.view_a AS SELECT id FROM example_db1.table_a\n",
                    },
                    {
                        "table": "example_db1.view_a",
                        "statement": "SHOW TABLE STATS",
                        "status": "not_applicable",
                        "error": "object is a view",
                    },
                    {
                        "table": "example_db1.view_a",
                        "statement": "SHOW COLUMN STATS",
                        "status": "not_applicable",
                        "error": "object is a view",
                    },
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "### Table: example_db1.view_a" in text
    assert "- object type: view" in text
    assert "- SHOW CREATE TABLE status: ok" in text
    assert "- SHOW TABLE STATS status: not_applicable" in text
    assert "- SHOW COLUMN STATS status: not_applicable" in text
    assert "- table stats row-count completeness: not_available" in text
    assert "- column stats columns observed: 0" in text
    assert "- column stats missing/unknown markers: 0" in text
    assert "- column stats completeness: not_available" in text
    assert "incomplete/unknown" not in text
    assert "COMPUTE STATS" not in text


def test_analyzer_handles_malformed_impala_context_json_safely(tmp_path):
    case_dir = copy_minimal_case(tmp_path)
    (case_dir / "impala_context.json").write_text("{not-json\n", encoding="utf-8")

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Table Metadata Context" in text
    assert "- context file: error" in text
    assert "- context path: `impala_context.json`" in text
    assert "- table metadata facts: unknown" in text
    assert "- error: failed to parse impala_context.json" in text
    assert "{not-json" not in text


def test_analyzer_handles_missing_optional_impala_context_files(tmp_path):
    case_dir = copy_minimal_case(tmp_path)
    context_dir = case_dir / "impala_context"
    context_dir.mkdir()
    (context_dir / "impala_context.md").write_text("# Impala Context\n", encoding="utf-8")

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout

    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Impala Context" in text
    assert "- present: no" in text
    assert "- path: `impala_context/original_query.sql`" in text
    assert "- EXPLAIN: missing (`impala_context/explain.txt`)" in text
    assert "- none parsed" in text


def assert_no_banned_or_unsupported_claims(text: str) -> None:
    lower = text.lower()
    for phrase in [
        "reduce skew",
        "optimize joins",
        "improve query",
        "skew is proven",
        "stats are stale",
        "hot keys exist",
    ]:
        assert phrase not in lower


def test_fixture_matrix_no_action_cards_case(tmp_path):
    case_dir = copy_fixture_case(tmp_path, "no_action_cards_case")

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Action Cards" in text
    assert "No deterministic action cards were triggered from the parsed evidence." in text
    assert "Severe deterministic evidence was detected" not in text
    assert_no_banned_or_unsupported_claims(text)


def test_fixture_matrix_memory_only_case_generates_memory_card(tmp_path):
    case_dir = copy_fixture_case(tmp_path, "memory_only_case")

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Action Cards" in text
    assert "Severe memory underestimation at high-memory operator" in text
    assert "operator: 07:SORT" in text
    assert "peak memory: 20.00 GiB" in text
    assert "estimated peak memory: 512.00 MiB" in text
    assert "peak/estimated memory ratio: 40.0x" in text
    assert "actual/estimated ratio: 1.00x" in text
    assert "Severe cardinality underestimation before high-cost operator" not in text
    assert_no_banned_or_unsupported_claims(text)


def test_fixture_matrix_missing_estimates_does_not_invent_ratios(tmp_path):
    case_dir = copy_fixture_case(tmp_path, "missing_estimates_case")

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Action Cards" in text
    assert "inf" not in text.lower()
    assert "actual/estimated ratio:" not in text
    assert "Cardinality anomalies: 0" in text
    assert "Memory anomalies: 0" in text
    assert "Zero/unknown row estimate gaps: 1" in text
    assert "Zero/unknown memory estimate gaps: 1" in text
    assert "## Zero/unknown row estimate gaps" in text
    assert "## Zero/unknown memory estimate gaps" in text
    assert "positive actual rows with an explicit zero/non-positive row estimate" in text
    assert "positive peak memory with an explicit zero/non-positive estimated peak memory" in text
    assert_no_banned_or_unsupported_claims(text)


def test_zero_estimate_gaps_require_positive_actual_or_peak(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
01:HASH JOIN                        1  2s000ms  2s000ms          0          0       0 B       0 B  INNER JOIN
```
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "Cardinality anomalies: 0" in text
    assert "Memory anomalies: 0" in text
    assert "Zero/unknown row estimate gaps: 0" in text
    assert "Zero/unknown memory estimate gaps: 0" in text
    assert "positive actual rows with an explicit zero/non-positive row estimate" not in text
    assert (
        "positive peak memory with an explicit zero/non-positive estimated peak memory" not in text
    )


def test_missing_estimates_remain_unknown_not_zero_gap(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
13:EXCHANGE                         1  1s000ms  1s000ms    2.00M        n/a    32.00 MiB  n/a  UNPARTITIONED
```
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "Cardinality anomalies: 0" in text
    assert "Memory anomalies: 0" in text
    assert "Zero/unknown row estimate gaps: 0" in text
    assert "Zero/unknown memory estimate gaps: 0" in text


def test_scientific_notation_rows_and_memory_are_parsed(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
04:HASH JOIN                        1  2s000ms  2s000ms    1.23E6      4.50e3   1.00E1 GiB  5.00e2 MiB  INNER JOIN
```
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "Cardinality anomalies: 1" in text
    assert "Memory anomalies: 1" in text
    assert "actual rows: 1.23M" in text
    assert "estimated rows: 4.50K" in text
    assert "actual/estimated ratio: 273x" in text
    assert "peak memory: 10.00 GiB" in text
    assert "estimated peak memory: 500.00 MiB" in text
    assert_no_banned_or_unsupported_claims(text)


def test_large_cardinality_overestimation_is_not_underestimation(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
01:SCAN HDFS                        1  1s000ms  1s000ms    1.00K       5.00M   128.00 MiB  128.00 MiB  synthetic.table
```
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "Cardinality anomalies: 0" in text
    assert "Severe cardinality underestimation" not in text
    assert "Cardinality estimate errors" not in text
    assert "actual rows | estimated rows" in text
    assert "1.00K" in text
    assert "5.00M" in text
    assert_no_banned_or_unsupported_claims(text)


def test_malformed_split_operator_snippets_do_not_create_fake_anomalies(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
01:HASH JOIN
- Actual rows: 4.00M
- Peak Mem: 2.00 GiB

02:SORT
- Estimated rows: 1.00K
- Est Peak Mem: 128.00 MiB

03:HDFS SCAN
| RowsRead line was truncated before values
| Peak Memory line was split
```
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "Parsed operators: 3" in text
    assert "Cardinality anomalies: 0" in text
    assert "Memory anomalies: 0" in text
    assert "Zero/unknown row estimate gaps: 0" in text
    assert "Zero/unknown memory estimate gaps: 0" in text
    assert "actual/estimated ratio:" not in text
    assert "Traceback" not in result.stderr
    assert_no_banned_or_unsupported_claims(text)


def test_repeated_operator_cardinality_uses_paired_worst_ratio(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
06:HASH JOIN                        1  1s000ms  1s000ms        100         10    1.00 GB     1.00 GB  INNER JOIN
06:HASH JOIN                        1  2s000ms  2s000ms      1.00K      1.00K    2.00 GB     2.00 GB  INNER JOIN
```
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "Cardinality anomalies: 1" in text
    assert "100 actual vs 10 estimated" in text
    assert "rows=100 vs est 10 (10.0x)" in text
    assert "1.00K actual rows vs 1.00K estimated rows" not in text


def test_repeated_operator_does_not_create_synthetic_cardinality_ratio(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
06:HASH JOIN                        1  1s000ms  1s000ms      1.00K      1.00K    1.00 GB     1.00 GB  INNER JOIN
06:HASH JOIN                        1  1s000ms  1s000ms        100         20    1.00 GB     1.00 GB  INNER JOIN
```
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "Cardinality anomalies: 0" in text
    assert "actual/estimated ratio:" not in text


def test_repeated_operator_zero_row_estimate_gap_uses_paired_observation(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
06:HASH JOIN                        1  1s000ms  1s000ms      1.00K      1.00K    1.00 GB     1.00 GB  INNER JOIN
06:HASH JOIN                        1  1s000ms  1s000ms        100          0    1.00 GB     1.00 GB  INNER JOIN
```
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "Cardinality anomalies: 0" in text
    assert "Zero/unknown row estimate gaps: 1" in text
    assert "100 actual rows vs 0 estimated rows" in text
    assert "1.00K actual rows vs 1.00K estimated rows" not in text


def test_repeated_operator_memory_uses_paired_worst_ratio(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
07:SORT                             1  1s000ms  1s000ms        100        100   20.00 GiB     1.00 GiB
07:SORT                             1  2s000ms  2s000ms        100        100   40.00 GiB    40.00 GiB
```
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "Memory anomalies: 1" in text
    assert "peak memory: 20.00 GiB" in text
    assert "estimated peak memory: 1.00 GiB" in text
    assert "peak/estimated memory ratio: 20.0x" in text
    assert "40.00 GiB peak memory vs 40.00 GiB estimated peak memory" not in text


def test_repeated_operator_memory_does_not_create_synthetic_ratio(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
07:SORT                             1  1s000ms  1s000ms        100        100   40.00 GiB    40.00 GiB
07:SORT                             1  1s000ms  1s000ms        100        100    1.00 GiB   512.00 MiB
```
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "Memory anomalies: 0" in text
    assert "peak/estimated memory ratio:" not in text
    assert "80.0x" not in text
    assert_no_banned_or_unsupported_claims(text)


def test_fixture_matrix_cte_context_uses_referenced_tables_only(tmp_path):
    case_dir = copy_fixture_case(tmp_path, "cte_context_case")

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Impala Context" in text
    assert "- `example_warehouse.orders`" in text
    assert "- `example_warehouse.customers`" in text
    assert "`recent_orders`" not in text
    assert "`ranked_customers`" not in text
    assert "join/filter columns once join/filter columns are identified" not in text
    assert "No deterministic action cards were triggered from the parsed evidence." in text
    assert_no_banned_or_unsupported_claims(text)


def test_fixture_matrix_scan_or_exchange_heavy_avoids_fake_join_claims(tmp_path):
    case_dir = copy_fixture_case(tmp_path, "scan_or_exchange_heavy_case")

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "Large intermediate or exchange traffic" in text
    assert "TotalBytesSent: 15.0 GiB" in text
    assert "Join bottleneck" not in text
    assert "Skew is suspected but not proven." not in text
    assert "No deterministic action cards were triggered from the parsed evidence." in text
    assert_no_banned_or_unsupported_claims(text)


def test_fixture_matrix_stats_present_exchange_case_is_not_stats_primary(tmp_path):
    fixture_dir = REPO_DIR / "tests" / "fixtures" / "stats_present_exchange_case"
    fixture_text = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(fixture_dir.glob("*")) if path.is_file()
    )
    for forbidden in [
        "SELECT ",
        "Query (id=",
        ".example.",
        "/tmp/",
        "/Users/",
        "hdfs://",
        "RAW_",
        "Authorization",
    ]:
        assert forbidden not in fixture_text

    case_dir = copy_fixture_case(tmp_path, "stats_present_exchange_case")

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Summary" in text
    assert "- Parsed operators: 3" in text
    assert "## Query Wall Clock" in text
    assert "- duration: 2.00m" in text
    assert "## Primary Bottleneck" in text
    assert "- label: runtime_data_movement" in text
    assert "- confidence: medium" in text
    assert "- reasons: large_intermediate_or_exchange_top_finding" in text
    assert "## Data Movement Evidence" in text
    assert "- status: supported" in text
    assert "- evidence_tier: strong" in text
    assert "- finding_supported: yes" in text
    assert "- primary_supported: yes" in text
    assert "- exchange_elapsed_share: " in text
    assert "Large intermediate or exchange traffic [high]" in text
    assert "- TotalBytesSent: 42.0 GiB (42.00 GiB)" in text
    assert "## Table Metadata Context" in text
    assert "- table metadata facts: supported" in text
    assert "- read-only statements only: yes" in text
    assert "## Stats Metadata Quality" in text
    assert "- status: available" in text
    assert "- table_stats: available" in text
    assert "- column_stats: complete" in text
    assert "- row_estimate_evidence: not_observed" in text
    assert "- non_stats_bottleneck_categories: exchange_or_data_movement" in text
    assert "- stats_primary_bottleneck: not_supported" in text
    assert "- stats_context: stats_available_no_row_estimate_evidence" in text
    assert "Stats quality is follow-up evidence, not a standalone root cause." in text
    assert (
        "- summary: No single runtime environment hypothesis is supported as likely by the deterministic facts."
        in text
    )
    assert "stats_candidate_supported" not in text
    assert "stats are stale" not in text.lower()
    assert "duration is the root cause" not in text.lower()
    assert "runtime context is the root cause" not in text.lower()
    assert "SELECT " not in text
    assert "profile_digest.md" not in text
    assert str(case_dir) not in text
    assert_no_banned_or_unsupported_claims(text)


def test_fixture_matrix_mixed_stats_runtime_case_keeps_both_signals(tmp_path):
    fixture_dir = REPO_DIR / "tests" / "fixtures" / "mixed_stats_runtime_case"
    fixture_text = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(fixture_dir.glob("*")) if path.is_file()
    )
    for forbidden in [
        "SELECT ",
        "Query (id=",
        ".example.",
        "/tmp/",
        "/Users/",
        "hdfs://",
        "RAW_",
        "Authorization",
    ]:
        assert forbidden not in fixture_text

    case_dir = copy_fixture_case(tmp_path, "mixed_stats_runtime_case")

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Summary" in text
    assert "- Parsed operators: 2" in text
    assert "- Cardinality anomalies: 1" in text
    assert "## Query Wall Clock" in text
    assert "- duration: 1.50m" in text
    assert "## Primary Bottleneck" in text
    assert "- label: mixed" in text
    assert "- confidence: medium" in text
    assert "- reasons: competing_stats, competing_runtime_skew" in text
    assert "## Stats Metadata Quality" in text
    assert "- status: limited" in text
    assert "- table_stats: incomplete_or_unknown" in text
    assert "- column_stats: incomplete_or_unknown" in text
    assert "- row_estimate_evidence: observed" in text
    assert "- row_estimate_issue_count: 1" in text
    assert "- non_stats_bottleneck_categories: backend_data_skew" in text
    assert "- stats_primary_bottleneck: mixed_candidate" in text
    assert "- stats_context: stats_gap_with_row_estimate_evidence" in text
    assert "competing non-stats bottleneck signals are also present" in text
    assert "## Backend / Host Tail Evidence" in text
    assert "- backend rows parsed: 3" in text
    assert "- data skew: yes (F02: bytes read max/min ratio is 6.00x)" in text
    assert "- execution skew: unknown" in text
    assert "Host-specific execution tail suspected" not in text
    assert "stats_candidate_supported" not in text
    assert "stats are stale" not in text.lower()
    assert "hot keys exist" not in text.lower()
    assert "duration is the root cause" not in text.lower()
    assert "runtime context is the root cause" not in text.lower()
    assert "SELECT " not in text
    assert "profile_digest.md" not in text
    assert str(case_dir) not in text
    assert_no_banned_or_unsupported_claims(text)


def test_tiny_total_bytes_sent_does_not_trigger_large_exchange_finding(tmp_path):
    case_dir = copy_fixture_case(tmp_path, "tiny_exchange_case")

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "TotalBytesSent: 288.4 KiB" in text
    assert "Large intermediate or exchange traffic" not in text
    assert "TotalBytesSent is large" not in text
    assert "below the large data-movement threshold" in text
    assert "No deterministic action cards were triggered from the parsed evidence." in text
    assert_no_banned_or_unsupported_claims(text)


def test_large_total_bytes_sent_still_triggers_data_movement_finding(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
01:HDFS SCAN                        1  1s000ms  1s000ms    900.00K     900.00K   128.00 MiB  128.00 MiB  example_logs.raw_events
02:EXCHANGE                         1  2s000ms  2s000ms    900.00K     900.00K    16.00 MiB   16.00 MiB  UNPARTITIONED
```

## Metric lines

```text
- TotalBytesSent: 66.0 GiB
```
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "Large intermediate or exchange traffic [high]" in text
    assert "TotalBytesSent: 66.0 GiB" in text
    assert_no_banned_or_unsupported_claims(text)


def test_large_total_bytes_sent_with_tiny_exchange_share_is_not_primary(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
01:HDFS SCAN                        1  90s000ms  90s000ms    900.00K     900.00K   128.00 MiB  128.00 MiB
02:EXCHANGE                         1   2s000ms   2s000ms    900.00K     900.00K    16.00 MiB   16.00 MiB  UNPARTITIONED
```

## Metric lines

```text
- TotalTime: 2m
- TotalBytesSent: 66.0 GiB
```
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "Large intermediate or exchange traffic [high]" in text
    assert "TotalBytesSent: 66.0 GiB" in text
    assert "## Primary Bottleneck" in text
    assert "- label: unknown" in text
    assert "- label: runtime_data_movement" not in text
    assert "## Data Movement Evidence" in text
    assert "- evidence_tier: medium" in text
    assert "- primary_supported: no" in text
    assert "too small a share" in text
    assert_no_banned_or_unsupported_claims(text)


def test_storage_finding_uses_candidate_signal_title(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
01:HDFS SCAN                        1  30s000ms  30s000ms    900.00K     900.00K   128.00 MiB  128.00 MiB  example_logs.raw_events
02:EXCHANGE                         1  1s000ms  1s000ms     900.00K     900.00K    16.00 MiB   16.00 MiB  UNPARTITIONED
```

## Metric lines

```text
- TotalTime: 2m
- TotalBytesRead: 42.0 GiB (45097156608)
```
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "Storage/HDFS candidate signal [medium]" in text
    assert "scan/storage operator evidence among top time operators" in text
    assert "HDFS or storage bottleneck" not in text
    assert "root-cause claim" in text
    assert_no_banned_or_unsupported_claims(text)


def test_analyzer_builds_runtime_diagnosis_before_primary_classification(tmp_path, monkeypatch):
    from query_doctor.analyzer.case_bottleneck import CasePrimaryBottleneck
    from query_doctor.cli import analyze_profile

    case_dir = copy_minimal_case(tmp_path)
    runtime_seen_by_classifier = []

    def fake_classify(analysis):
        runtime_seen_by_classifier.append("runtime_diagnosis" in analysis)
        return CasePrimaryBottleneck("unknown", "low", ("test_classifier_order",))

    monkeypatch.setattr(analyze_profile, "classify_case_primary_bottleneck", fake_classify)

    result = analyze_profile.main([str(case_dir)])

    assert result == 0
    assert runtime_seen_by_classifier == [True]


def test_host_disk_io_pressure_correlates_with_storage_evidence(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
01:HDFS SCAN                        1  30s000ms  30s000ms    900.00K     900.00K   128.00 MiB  128.00 MiB  example_logs.raw_events
02:EXCHANGE                         1  1s000ms  1s000ms     900.00K     900.00K    16.00 MiB   16.00 MiB  UNPARTITIONED
```

## Metric lines

```text
- TotalTime: 2m
- TotalBytesRead: 80.0 GiB
```
""",
    )
    write_cm_timeseries_context(
        case_dir,
        memory_min_gib=10,
        memory_max_gib=11,
        network_max_mib=20,
        network_avg_mib=10,
        disk_max_mib=500,
        disk_avg_mib=100,
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "- host_disk_io_pressure: observed" in text
    assert "host disk I/O max=500.00 MiB/s avg=100.00 MiB/s ratio=5.00x" in text
    assert "- host_disk_io_pressure: correlated (metric=observed, strength=moderate)" in text
    assert "Host disk I/O pressure is correlated with parsed scan/storage evidence" in text
    assert "Storage/local disk path is a plausible follow-up hypothesis" in text
    assert_no_banned_or_unsupported_claims(text)


def test_hdfs_datanode_io_pressure_correlates_with_storage_evidence(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
01:HDFS SCAN                        1  45s000ms  45s000ms    900.00K     900.00K   128.00 MiB  128.00 MiB  example_logs.raw_events
02:EXCHANGE                         1  1s000ms  1s000ms     900.00K     900.00K    16.00 MiB   16.00 MiB  UNPARTITIONED
```

## Metric lines

```text
- TotalTime: 2m
- TotalBytesRead: 120.0 GiB
```
""",
    )
    write_cm_timeseries_context(
        case_dir,
        memory_min_gib=10,
        memory_max_gib=11,
        network_max_mib=20,
        network_avg_mib=10,
        disk_max_mib=20,
        disk_avg_mib=10,
        hdfs_read_max_mib=600,
        hdfs_read_avg_mib=120,
        hdfs_local_reads_max=100,
        hdfs_remote_reads_max=260,
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "- hdfs_datanode_io_pressure: observed" in text
    assert "HDFS DataNode read max=600.00 MiB/s avg=120.00 MiB/s" in text
    assert "remote/local reads ratio=2.60x" in text
    assert "- hdfs_datanode_io_pressure: correlated (metric=observed, strength=moderate)" in text
    assert "HDFS/DataNode read path is a plausible follow-up hypothesis" in text
    assert_no_banned_or_unsupported_claims(text)


def test_object_store_context_does_not_promote_hdfs_locality(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
01:HDFS SCAN                        1  45s000ms  45s000ms    900.00K     900.00K   128.00 MiB  128.00 MiB  example_logs.raw_events
02:EXCHANGE                         1  1s000ms  1s000ms     900.00K     900.00K    16.00 MiB   16.00 MiB  UNPARTITIONED
```

## Metric lines

```text
- TotalTime: 2m
- TotalBytesRead: 120.0 GiB
```
""",
    )
    (case_dir / "impala_context.json").write_text(
        json.dumps(
            {
                "tables": ["example_db1.table_a"],
                "read_only_statements_only": True,
                "results": [
                    {
                        "table": "example_db1.table_a",
                        "statement": "SHOW CREATE TABLE",
                        "status": "ok",
                        "stdout": (
                            "CREATE TABLE example_db1.table_a (id BIGINT)\n"
                            "STORED AS PARQUET\n"
                            "LOCATION 's3a://raw-lake-prod/warehouse/example_db1.table_a'\n"
                        ),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    write_cm_timeseries_context(
        case_dir,
        memory_min_gib=10,
        memory_max_gib=11,
        network_max_mib=20,
        network_avg_mib=10,
        disk_max_mib=20,
        disk_avg_mib=10,
        hdfs_read_max_mib=600,
        hdfs_read_avg_mib=120,
        hdfs_local_reads_max=100,
        hdfs_remote_reads_max=260,
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Storage Context" in text
    assert "- storage_family: s3" in text
    assert "- storage_semantics: object_store_remote_reads_expected" in text
    assert "- view_table_count: 0" in text
    assert "- hdfs_locality_applicable: no" in text
    assert "- remote_reads_expected: yes" in text
    assert "- hdfs_datanode_io_pressure: context_only (metric=observed, strength=weak)" in text
    assert "Do not use it as HDFS locality evidence." in text
    assert "### Object-store scan path" in text
    assert "Remote reads can be expected for this storage context" in text
    assert "HDFS/DataNode read path is a plausible follow-up hypothesis" not in text
    assert "HDFS DataNode metrics are not used as object-store locality evidence" in text
    assert "s3a://raw-lake-prod" not in text
    assert "warehouse/example_db1.table_a" not in text
    assert "LOCATION" not in text
    assert_no_banned_or_unsupported_claims(text)


def test_admission_pool_pressure_correlates_with_query_admission_wait(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
01:SCAN HDFS  1  1s000ms  1s000ms  10  10  1.00 MB  1.00 MB
```
""",
    )
    (case_dir / "cm_metadata.json").write_text(
        json.dumps(
            {
                "query_id": "abc:def",
                "status": "succeeded",
                "query_state": "FINISHED",
                "query_type": "QUERY",
                "pool": "etl",
                "duration_ms": 90000,
                "admission_result": "admitted",
                "admission_wait_ms": 32000,
            }
        ),
        encoding="utf-8",
    )
    write_cm_timeseries_context(
        case_dir,
        memory_min_gib=10,
        memory_max_gib=11,
        network_max_mib=20,
        network_avg_mib=10,
        admission_queued_max=2.5,
        admission_queued_avg=0.4,
        admission_rejected_max=0.0,
        admission_timed_out_max=0.0,
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "- admission_wait: 32s" in text
    assert "- admission_pool_pressure: observed" in text
    assert "admission queued max=2.50/s avg=0.40/s" in text
    assert "- admission_pool_pressure: correlated (metric=observed, strength=moderate)" in text
    assert "Admission/pool pressure is a plausible follow-up hypothesis" in text
    assert_no_banned_or_unsupported_claims(text)


def test_storage_candidate_signal_absent_without_slow_scan_evidence(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
01:HDFS SCAN                        1  1s000ms  1s000ms    900.00K     900.00K   128.00 MiB  128.00 MiB  synthetic.table
02:EXCHANGE                         1  2s000ms  2s000ms    900.00K     900.00K    16.00 MiB   16.00 MiB  UNPARTITIONED
```

## Metric lines

```text
- TotalTime: 20s
- TotalBytesRead: 20.0 GiB
```
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "### Storage/HDFS candidate signal" not in text
    assert "HDFS or storage bottleneck" not in text
    assert "Large TotalBytesRead is an I/O footprint, not proof" in text
    assert_no_banned_or_unsupported_claims(text)


def test_storage_candidate_signal_requires_bytes_and_scan_context(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
01:HDFS SCAN                        1  30s000ms  30s000ms    900.00K     900.00K   128.00 MiB  128.00 MiB  synthetic.table
```

## Metric lines

```text
- TotalTime: 2m
```
""",
    )
    write_cm_timeseries_context(case_dir, disk_max_mib=500, disk_avg_mib=100)

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "### Storage/HDFS candidate signal" not in text
    assert "- host_disk_io_pressure: context_only (metric=observed, strength=weak)" in text
    assert "requires both slow scan/storage operator context and parsed TotalBytesRead" in text
    assert "Storage/local disk path is a plausible follow-up hypothesis" not in text
    assert_no_banned_or_unsupported_claims(text)


def test_storage_candidate_signal_requires_known_query_wall_clock(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
01:HDFS SCAN                        1  30s000ms  30s000ms    900.00K     900.00K   128.00 MiB  128.00 MiB  synthetic.table
```
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "- duration: unknown" in text
    assert "Storage/HDFS candidate signal" not in text
    assert (
        "Storage/HDFS share was not evaluated because Query Wall Clock duration is unknown." in text
    )
    assert_no_banned_or_unsupported_claims(text)


def test_codegen_finding_uses_candidate_signal_title(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
01:SCAN HDFS                        1  1s000ms  1s000ms    900.00K     900.00K   128.00 MiB  128.00 MiB  example_logs.raw_events
```

## Metric lines

```text
- TotalTime: 20s
- CodegenTotalWallClockTime: 3s
```
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "Codegen candidate signal [medium]" in text
    assert "notable codegen/LLVM timing evidence" in text
    assert "Codegen bottleneck" not in text
    assert "treated as a bottleneck" not in text
    assert "root-cause claim" in text
    assert_no_banned_or_unsupported_claims(text)


def test_codegen_candidate_signal_requires_known_query_wall_clock(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
01:SCAN HDFS                        1  1s000ms  1s000ms    900.00K     900.00K   128.00 MiB  128.00 MiB  synthetic.table
```

## Metric lines

```text
- CodegenTotalWallClockTime: 3s
```
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "- duration: unknown" in text
    assert "Codegen candidate signal" not in text
    assert (
        "Codegen/LLVM share was not evaluated because Query Wall Clock duration is unknown." in text
    )
    assert "No codegen/LLVM candidate signal was parsed." in text
    assert_no_banned_or_unsupported_claims(text)


def test_codegen_candidate_signal_absent_when_timing_share_is_small(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## ExecSummary

```text
01:SCAN HDFS                        1  1s000ms  1s000ms    900.00K     900.00K   128.00 MiB  128.00 MiB  synthetic.table
```

## Metric lines

```text
- TotalTime: 100s
- CodegenTotalWallClockTime: 1s
```
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "Codegen candidate signal" not in text
    assert "Codegen bottleneck" not in text
    assert "No codegen/LLVM candidate signal was parsed." in text
    assert_no_banned_or_unsupported_claims(text)


def test_spill_detection_ignores_general_write_io_metrics(tmp_path):
    module = load_analyzer_module()
    text = "\n".join(
        [
            "- WriteIoBytes: 12.0 GiB",
            "- BytesWritten: 8.0 GiB",
            "- HDFSBytesWritten: 9.8 GiB",
        ]
    )

    assert module.find_nonzero_spill_metric_lines(text) == []

    case_dir = write_case(
        tmp_path,
        f"""
# Synthetic digest

## Metric lines

```text
{text}
```
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    facts = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "Spill or scratch I/O [medium]" not in facts
    assert "No non-zero spill/scratch I/O evidence was parsed." in facts
    assert_no_banned_or_unsupported_claims(facts)


def test_spill_detection_accepts_explicit_spill_and_scratch_metrics(tmp_path):
    module = load_analyzer_module()
    text = "\n".join(
        [
            "- SpilledBytes: 2.0 GiB",
            "- BytesSpilled: 64.0 MiB",
            "- MemorySpilled: 1.0 GiB",
            "- ScratchBytesWritten: 4.0 KiB",
            "- SpilledPartitions: 3",
        ]
    )

    lines = module.find_nonzero_spill_metric_lines(text)

    assert "- SpilledBytes: 2.0 GiB" in lines
    assert "- BytesSpilled: 64.0 MiB" in lines
    assert "- MemorySpilled: 1.0 GiB" in lines
    assert "- ScratchBytesWritten: 4.0 KiB" in lines
    assert "- SpilledPartitions: 3" in lines


def test_backend_tail_fixture_extracts_host_tail_evidence(tmp_path):
    case_dir = copy_fixture_case(tmp_path, "backend_tail_case")
    json_path = case_dir / "analysis.json"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "query_doctor.cli.analyze_profile",
            str(case_dir),
            "--json",
            str(json_path),
        ],
        cwd=str(REPO_DIR),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    analysis_json = json_path.read_text(encoding="utf-8")
    analysis = json.loads(analysis_json)
    assert "## Backend / Host Tail Evidence" in text
    assert "- backend rows parsed: 3" in text
    assert "- host tail candidates: 1" in text
    assert "- execution tail candidates: 0" in text
    assert "- read-rate tail candidates: 1" in text
    assert "- write-path tail candidates: 1" in text
    assert "### Normalized tail candidates" in text
    assert "| host_03 | unknown | read_rate | read_rate_bps |" in text
    assert "| host_03 | unknown | write_path | hdfs_write_time_ms |" in text
    assert "- data skew: no" in text
    assert "- execution skew: no" in text
    assert "- write-path anomaly: yes" in text
    assert "worker-c.example.net" not in text
    assert "worker-c.example.net" not in analysis_json
    assert "host_03" in text
    assert any(
        candidate.get("host") == "host_03"
        for candidate in analysis["backend_tail"]["write_path_candidates"]
    )
    assert "Host-specific execution tail suspected" not in text
    assert "Execution skew is not confirmed by backend execution-time tail candidates." in text
    assert "Host-specific HDFS/RPC/write path issue is suspected, not proven." in text
    assert "skew is proven" not in text.lower()
    assert "NUM_SCANNER_THREADS" not in text
    assert_no_banned_or_unsupported_claims(text)


def test_backend_tail_groups_fragment_instances_before_skew_and_tail(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic profile

Averaged Fragment F03
  Instance q:001 (host=worker-a.example.net:22000)
    - RowsProduced: 1,000,000 (1000000)
    - TotalTime: 20m (1200000000000)
  Instance q:002 (host=worker-b.example.net:22000)
    - RowsProduced: 1,010,000 (1010000)
    - TotalTime: 21m (1260000000000)
  Instance q:003 (host=worker-c.example.net:22000)
    - RowsProduced: 1,005,000 (1005000)
    - TotalTime: 45m (2700000000000)

Averaged Fragment F02
  Instance q:004 (host=worker-a.example.net:22000)
    - RowsProduced: 10,000 (10000)
    - TotalTime: 2s (2000000000)
  Instance q:005 (host=worker-b.example.net:22000)
    - RowsProduced: 11,000 (11000)
    - TotalTime: 2s (2000000000)
  Instance q:006 (host=worker-c.example.net:22000)
    - RowsProduced: 9,500 (9500)
    - TotalTime: 2s (2000000000)
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "- backend rows parsed: 6" in text
    assert "- host tail candidates: 1" in text
    assert "- execution tail candidates: 1" in text
    assert "### Normalized tail candidates" in text
    assert "| host_03 | F03 | execution | execution_time_ms |" in text
    assert "- data skew: no (F03: assigned/read work appears comparable" in text
    assert "- execution skew: yes" in text
    assert "F03 execution time" in text
    assert "worker-c.example.net" not in text
    assert "host_03" in text
    assert "Host-specific execution tail suspected [high]" in text
    assert "100x" not in text
    assert_no_banned_or_unsupported_claims(text)


def test_scan_skew_facts_support_runtime_skew_from_per_instance_bytes(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic profile

Summary:
  Query Type: QUERY

## Backend counters

Averaged Fragment F03
  Instance q:001 (host=worker-a.example.net:22000)
    - BytesRead: 100.0 MiB
    - RowsProduced: 1,000,000 (1000000)
    - TotalTime: 20m (1200000000000)
  Instance q:002 (host=worker-b.example.net:22000)
    - BytesRead: 110.0 MiB
    - RowsProduced: 1,100,000 (1100000)
    - TotalTime: 21m (1260000000000)
  Instance q:003 (host=worker-c.example.net:22000)
    - BytesRead: 800.0 MiB
    - RowsProduced: 8,000,000 (8000000)
    - TotalTime: 45m (2700000000000)
""",
    )
    (case_dir / "cm_metadata.json").write_text(
        json.dumps({"duration_ms": 120_000}),
        encoding="utf-8",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Scan Skew Evidence" in text
    assert "- status: supported" in text
    assert "- evidence_tier: strong" in text
    assert "- finding_supported: yes" in text
    assert "- primary_supported: yes" in text
    assert "- evidence_source: per_instance_backend_metrics" in text
    assert "- fragment_group: F03" in text
    assert "- skew_metric: bytes_read" in text
    assert "- skew_ratio: 8.00x" in text
    assert "- corroborating_metric_count: 2" in text
    assert "- runtime_status: long_running_imbalanced" in text
    assert "- group_max_execution_time: 45.00m" in text
    assert "- label: runtime_skew" in text
    assert "- reasons: scan_skew_bytes_read" in text
    assert_no_banned_or_unsupported_claims(text)


def test_backend_tail_keeps_instance_metrics_after_lifecycle_headers(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic profile

Averaged Fragment F03
  Instance q:001 (host=worker-a.example.net:22000):
    Fragment Instance Lifecycle Event Timeline: 20m
       - Open Finished: 10ms (10ms)
    Fragment Instance Lifecycle Timings:
    - RowsProduced: 1,000,000 (1000000)
    - TotalTime: 20m (1200000000000)
  Instance q:002 (host=worker-b.example.net:22000):
    Fragment Instance Lifecycle Event Timeline: 45m
       - Open Finished: 10ms (10ms)
    Fragment Instance Lifecycle Timings:
    - RowsProduced: 1,005,000 (1005000)
    - TotalTime: 45m (2700000000000)
  Instance q:003 (host=worker-c.example.net:22000):
    Fragment Instance Lifecycle Event Timeline: 21m
       - Open Finished: 10ms (10ms)
    Fragment Instance Lifecycle Timings:
    - RowsProduced: 1,010,000 (1010000)
    - TotalTime: 21m (1260000000000)
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "- backend rows parsed: 3" in text
    assert "- execution tail candidates: 1" in text
    assert "| host_02 | F03 | execution | execution_time_ms |" in text
    assert "- data skew: no (F03: assigned/read work appears comparable" in text
    assert "- execution skew: yes" in text
    assert "Host-specific execution tail suspected [high]" in text
    assert "worker-b.example.net" not in text
    assert_no_banned_or_unsupported_claims(text)


def test_backend_tail_detects_long_absolute_gap_below_old_ratio_threshold(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic profile

Averaged Fragment F03
  Instance q:001 (host=worker-a.example.net:22000)
    - RowsProduced: 2,955,509 (2955509)
    - TotalTime: 53.0m (3179349097125)
  Instance q:002 (host=worker-b.example.net:22000)
    - RowsProduced: 3,017,761 (3017761)
    - TotalTime: 40.8m (2446125698828)
  Instance q:003 (host=worker-c.example.net:22000)
    - RowsProduced: 2,943,789 (2943789)
    - TotalTime: 30.0m (1800478257951)
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "- backend rows parsed: 3" in text
    assert "- host tail candidates: 1" in text
    assert "- execution tail candidates: 1" in text
    assert (
        "| host_01 | F03 | execution | execution_time_ms | 53.00m | 30.00m | 23.00m | 1.77x |"
        in text
    )
    assert "- data skew: no (F03: assigned/read work appears comparable" in text
    assert "- execution skew: yes" in text
    assert "Host-specific execution tail suspected [high]" in text
    assert "worker-a.example.net" not in text
    assert_no_banned_or_unsupported_claims(text)


def test_backend_tail_ignores_nested_cumulative_total_time_for_execution_tail(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic profile

Averaged Fragment F03
  Instance q:001 (host=worker-a.example.net:22000)
    - RowsProduced: 1,000,000 (1000000)
    ScannerThreads
      - ScannerThreadsTotalWallClockTime: 20m (1200000000000)
      - TotalTime: 20m (1200000000000)
    - TotalTime: 20m (1200000000000)
  Instance q:002 (host=worker-b.example.net:22000)
    - RowsProduced: 1,010,000 (1010000)
    ScannerThreads
      - ScannerThreadsTotalWallClockTime: 20m (1200000000000)
      - TotalTime: 20m (1200000000000)
    - TotalTime: 20m (1200000000000)
  Instance q:003 (host=worker-c.example.net:22000)
    - RowsProduced: 1,005,000 (1005000)
    ScannerThreads
      - ScannerThreadsTotalWallClockTime: 90m (5400000000000)
      - TotalTime: 90m (5400000000000)
    - TotalTime: 20m (1200000000000)
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "- backend rows parsed: 3" in text
    assert "- execution tail candidates: 0" in text
    assert "- execution skew: no" in text
    assert "| worker-c.example.net:22000 | F03 | execution | execution_time_ms |" not in text
    assert "Host-specific execution tail suspected" not in text
    assert (
        "- thread wall-clock: counters=3, max=1.50h, max_counter=ScannerThreadsTotalWallClockTime"
        in text
    )
    assert_no_banned_or_unsupported_claims(text)


def test_backend_tail_writer_fixture_does_not_claim_execution_skew(tmp_path):
    src_fixture = REPO_DIR / "tests" / "fixtures" / "writer_tail_case" / "profile_digest.md"
    fixture_text = src_fixture.read_text(encoding="utf-8")
    for forbidden in [
        "SELECT ",
        ".example.",
        "Query (id=",
        "/tmp/",
        "/Users/",
        "worker-a.example.net",
    ]:
        assert forbidden not in fixture_text

    case_dir = copy_fixture_case(tmp_path, "writer_tail_case")

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "- host tail candidates: 1" in text
    assert "- execution tail candidates: 0" in text
    assert "- write-path tail candidates: 1" in text
    assert "| host_03 | unknown | write_path | write_rate_bps |" in text
    assert "- execution skew: no" in text
    assert "- write-path anomaly: yes" in text
    assert "Host-specific execution tail suspected" not in text
    assert "Backend write-path anomaly [high]" in text
    assert (
        "Treat this as write-path evidence, not execution skew and not scan-storage proof." in text
    )
    assert "Storage/HDFS candidate signal" not in text
    assert "write rate" in text
    assert "synth-writer-c" not in text
    assert "host_03" in text
    assert ".example." not in text
    assert "SELECT " not in text
    assert str(case_dir) not in text
    assert_no_banned_or_unsupported_claims(text)


def test_backend_tail_long_writer_fixture_keeps_duration_as_context(tmp_path):
    src_fixture = REPO_DIR / "tests" / "fixtures" / "long_writer_tail_case" / "profile_digest.md"
    fixture_text = src_fixture.read_text(encoding="utf-8")
    for forbidden in [
        "SELECT ",
        ".example.",
        "Query (id=",
        "/tmp/",
        "/Users/",
        "hdfs://",
        "RAW_",
        "Authorization",
    ]:
        assert forbidden not in fixture_text

    case_dir = copy_fixture_case(tmp_path, "long_writer_tail_case")

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Query Wall Clock" in text
    assert "- duration: 55.00m" in text
    assert "- source: profile TotalTime" in text
    assert "## Primary Bottleneck" in text
    assert "- label: unknown" in text
    assert "- reasons: wall_clock_not_explained_by_mapped_operators" in text
    assert "## Backend / Host Tail Evidence" in text
    assert "- backend rows parsed: 3" in text
    assert "- host tail candidates: 1" in text
    assert "- execution tail candidates: 0" in text
    assert "- write-path tail candidates: 1" in text
    assert "- data skew: no (F07: assigned/read work appears comparable" in text
    assert "- execution skew: no" in text
    assert "- write-path anomaly: yes" in text
    assert "| host_03 | F07 | write_path | write_rate_bps |" in text
    assert "| host_03 | F07 | write_path | hdfs_write_time_ms |" in text
    assert "52.00m" in text
    assert "Backend write-path anomaly [high]" in text
    assert (
        "Treat this as write-path evidence, not execution skew and not scan-storage proof." in text
    )
    assert "Execution skew is not confirmed by backend execution-time tail candidates." in text
    assert "Host-specific HDFS/RPC/write path issue is suspected, not proven." in text
    assert "Host-specific execution tail suspected" not in text
    assert "Storage/HDFS candidate signal" not in text
    assert "duration is the root cause" not in text.lower()
    assert "writer duration is the root cause" not in text.lower()
    assert "SELECT " not in text
    assert "profile_digest.md" not in text
    assert "synth-long-writer-c" not in text
    assert str(case_dir) not in text
    assert_no_banned_or_unsupported_claims(text)


def test_backend_tail_parser_tolerates_missing_metrics(tmp_path):
    case_dir = write_case(
        tmp_path,
        """
# Synthetic digest

## Backend counters

```text
Backend 1 host=worker-a fragment=F00:000
  - ScanBytesAssigned: 10.0 GiB
Backend 2 host=worker-b fragment=F00:001
  - RowsProduced: 10,000
Backend 3 host=worker-c fragment=F00:002
  - ExecutionTime: 30s
```
""",
    )

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "## Backend / Host Tail Evidence" in text
    assert "- backend rows parsed: 3" in text
    assert "- execution skew: unknown" in text
    assert "Traceback" not in result.stderr
    assert_no_banned_or_unsupported_claims(text)


def test_fixture_matrix_raw_cm_profile_json_extracts_operator_evidence(tmp_path):
    case_dir = copy_fixture_case(tmp_path, "raw_cm_profile_case")

    result = run_analyzer(case_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    assert "Parsed operators: 3" in text
    assert "01:HASH JOIN (INNER JOIN, PARTITIONED)" in text
    assert "02:EXCHANGE" in text
    assert "03:HDFS SCAN" in text
    assert "actual rows: 2.00M" in text
    assert "estimated rows: 10.00K" in text
    assert "actual/estimated ratio: 200x" in text
    assert "4.00 GiB" in text
    assert "500ms" in text
    assert "Memory anomalies: 0" in text
    assert_no_banned_or_unsupported_claims(text)
