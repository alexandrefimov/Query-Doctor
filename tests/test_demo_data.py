import json
from pathlib import Path

from query_doctor.web.action_outcomes import (
    load_action_outcomes,
    summarize_workload_action_outcomes,
)
from query_doctor.web.command_builders import PYTHON_REPORT_NAME, REPORT_VARIANT_PYTHON
from query_doctor.web.details_facts import load_case_analysis_query_context_facts
from query_doctor.web.models import WebSettings
from query_doctor.web.presenters.recent_scan import present_recent_scan_case_detail
from query_doctor.web.trusted_artifacts import (
    batch_case_validated_report_exists,
    load_validated_optimizer_recommendations,
    optimized_query_validated_exists,
    resolve_batch_case_report_dir,
)
from query_doctor.web.ui.action_candidates import render_action_candidate_findings
from query_doctor.web.ui.recent_scan_details import render_recent_scan_case_detail_view
from query_doctor.web.ui.recent_scan_results import render_batch_summary
from query_doctor.web.ui.trino_demo import render_trino_demo_sections


REPO_DIR = Path(__file__).resolve().parents[1]


def load_demo_module():
    from query_doctor.cli import demo_data

    return demo_data


def test_package_entrypoint_exposes_demo_generator_api():
    from query_doctor.cli import demo_data

    assert demo_data.REPO_DIR == REPO_DIR
    assert demo_data.SUMMARY_NAME == "batch_summary.json"
    assert demo_data.TRINO_DEMO_NAME == "trino_demo.json"


def test_generates_synthetic_demo_pack_with_trusted_artifacts(tmp_path):
    module = load_demo_module()
    out_dir = tmp_path / "query-doctor-demo-pack"

    result = module.main(["--out", str(out_dir)])

    assert result == 0
    summary_path = out_dir / "batch_summary.json"
    assert summary_path.is_file()
    trino_demo_path = out_dir / "trino_demo.json"
    assert trino_demo_path.is_file()
    assert (out_dir / "README.md").is_file()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    trino_demo = json.loads(trino_demo_path.read_text(encoding="utf-8"))
    cases = summary["cases"]
    assert summary["demo_mode"] is True
    assert [case["query_id"] for case in cases] == [
        "demo-optimizer-0001",
        "demo-stats-0002",
        "demo-validator-0003",
        "demo-admission-0004",
        "demo-admission-0005",
        "demo-storage-0006",
        "demo-short-0007",
        "demo-short-0008",
        "demo-mixed-0009",
        "demo-client-fetch-0010",
        "demo-direct-0011",
    ]
    assert summary["selected_count"] == 11
    workload_groups = summary["workload_groups"]["groups"]
    assert [group["fingerprint"] for group in workload_groups] == [
        "wf_adadadadadadadadadadadad",
        "wf_cdcdcdcdcdcdcdcdcdcdcdcd",
    ]
    assert workload_groups[0]["baseline"]["regression"] == "strong"
    assert workload_groups[1]["baseline"]["regression"] == "none"
    assert trino_demo["schema_version"] == "query_doctor_trino_demo_v1"
    assert [case["query_id"] for case in trino_demo["cases"]] == [
        "20260603_120102_00001_demoa",
        "20260603_120212_00002_demob",
    ]
    assert trino_demo["recent"]["records_diagnosed"] == 2

    settings = WebSettings(config=Path(".query-doctor-cm.local.json"), batch_summary=summary_path)
    optimizer_case = cases[0]
    assert optimizer_case["query_optimization_candidate"]["confidence"] == "medium"
    assert (
        "metadata was not collected, so stats-vs-query-shape split is unconfirmed"
        in optimizer_case["query_optimization_candidate"]["counter_signals"]
    )
    optimizer_dir = resolve_batch_case_report_dir(settings, optimizer_case)
    assert optimizer_dir == out_dir / "cases" / "case-001"
    assert batch_case_validated_report_exists(
        optimizer_dir, optimizer_case, report_variant=REPORT_VARIANT_PYTHON
    )
    report_text = (optimizer_dir / PYTHON_REPORT_NAME).read_text(encoding="utf-8")
    assert "## Short Summary" in report_text
    assert "## Practical Recommendations" in report_text
    assert "## Detailed Analysis" in report_text
    assert not any("А" <= ch <= "я" or ch == "ё" or ch == "Ё" for ch in report_text)
    assert optimized_query_validated_exists(optimizer_dir)
    recommendations = load_validated_optimizer_recommendations(optimizer_dir)
    assert recommendations is not None
    assert "candidate, not a proven root cause" in recommendations

    stats_case_dir = Path(cases[1]["case_dir"])
    assert {
        "metadata_table_stats",
        "plan_cardinality_anomaly",
    } == {locator["id"] for locator in cases[1]["source_locators"]["stats_refresh"]}
    assert "Table Metadata Context" in (stats_case_dir / "analysis_facts.md").read_text(
        encoding="utf-8"
    )
    rejected_case = cases[2]
    assert (
        rejected_case["optimizer_rewrite_support"]["rewriteability_bucket"] == "human_review_only"
    )
    assert rejected_case["case_primary_bottleneck"]["label"] == "runtime_data_movement"
    assert (Path(rejected_case["case_dir"]) / "optimized_query.partial.txt").is_file()
    admission_case = cases[3]
    assert admission_case["case_primary_bottleneck"]["label"] == "runtime_admission"
    assert admission_case["workload_group_member_count"] == 2
    assert admission_case["workload_regression"] == "strong"
    storage_case = cases[5]
    assert storage_case["case_primary_bottleneck"]["label"] == "runtime_storage"
    mixed_case = cases[8]
    assert mixed_case["case_primary_bottleneck"]["label"] == "mixed"
    assert mixed_case["query_optimization_candidate"]["tier"] == "medium"
    assert mixed_case["stats_optimization_candidate"]["tier"] == "medium"
    client_fetch_case = cases[9]
    assert client_fetch_case["case_primary_bottleneck"]["label"] == "client_fetch_tail"
    assert client_fetch_case["case_primary_bottleneck"]["confidence"] == "high"
    assert client_fetch_case["query_optimization_candidate"] is None
    assert client_fetch_case["stats_optimization_candidate"] is None
    assert "client fetch wait" in client_fetch_case["score_reasons"][0]
    direct_case = cases[10]
    assert direct_case["case_primary_bottleneck"]["label"] == "runtime_admission"
    assert "direct Impala profile resource facts" in direct_case["score_reasons"][0]

    outcome_path = out_dir / "action_outcomes.jsonl"
    records = load_action_outcomes(path=outcome_path)
    assert len(records) == 8
    assert {record.recommendation_id for record in records} == {
        "query_optimization_review.v1",
        "stats_refresh_review.v1",
        "runtime_admission_check.v1",
    }
    assert all(record.note_redacted == "synthetic demo outcome" for record in records)


def test_generated_demo_renders_read_only_trino_beta_cases(tmp_path):
    module = load_demo_module()
    out_dir = tmp_path / "query-doctor-demo-pack"
    module.main(["--out", str(out_dir)])
    settings = WebSettings(
        config=Path(".query-doctor-cm.local.json"),
        batch_summary=out_dir / "batch_summary.json",
    )

    html = render_trino_demo_sections(settings)

    assert "Trino Beta demo cases" in html
    assert "20260603_120102_00001_demoa" in html
    assert "20260603_120212_00002_demob" in html
    assert "Trino spill observed" in html
    assert "Trino queue or blocked" in html
    assert "Trino SQL execution" in html
    assert "not_performed" in html
    assert 'href="#trino-demo-001"' in html
    assert 'action="/analyze"' not in html
    assert 'href="/batch/case/' not in html
    assert 'href="/query/' not in html
    assert 'href="/optimizer"' not in html
    assert "SELECT" not in html
    assert str(out_dir) not in html


def test_generated_demo_optimizer_case_renders_safe_review_locations(tmp_path):
    module = load_demo_module()
    out_dir = tmp_path / "query-doctor-demo-pack"
    module.main(["--out", str(out_dir)])
    summary = json.loads((out_dir / "batch_summary.json").read_text(encoding="utf-8"))

    view = present_recent_scan_case_detail("case-001", summary["cases"][0])
    html = render_action_candidate_findings(view)

    assert "Where to inspect" in html
    assert "SQL: final SELECT filter (line 9): predicate near final SELECT" in html
    assert "Plan: estimate-mismatch operator: node 03 HASH JOIN (inner join, partitioned)" in html
    assert "What to change" in html
    assert "Try to reduce rows earlier: move the final SELECT filter closer" in html
    assert str(out_dir) not in html
    assert "original_query.sql" not in html
    assert "SELECT segment" not in html


def test_generated_demo_details_renders_safe_query_context(tmp_path):
    module = load_demo_module()
    out_dir = tmp_path / "query-doctor-demo-pack"
    module.main(["--out", str(out_dir)])
    summary = json.loads((out_dir / "batch_summary.json").read_text(encoding="utf-8"))
    case = summary["cases"][0]

    query_context_facts = load_case_analysis_query_context_facts(Path(case["case_dir"]))
    view = present_recent_scan_case_detail(
        "case-001",
        case,
        query_context_facts=query_context_facts,
    )
    html = render_recent_scan_case_detail_view(view)

    assert query_context_facts is not None
    assert query_context_facts["summary"]["available"] == "yes"
    assert query_context_facts["summary"]["start_time"] == "2026-05-21T09:04:00Z"
    assert query_context_facts["summary"]["admission_wait"] == "4.20s"
    assert query_context_facts["summary"]["bytes_read"] == "148.00 GiB"
    assert query_context_facts["summary"]["memory_aggregate_peak"] == "36.00 GiB"
    assert "query window" in html
    assert "2026-05-21T09:04:00Z to 2026-05-21T09:09:15Z" in html
    assert "admission wait" in html
    assert "4.20s" in html
    assert "resource footprint" in html
    assert "read 148.00 GiB; peak memory 36.00 GiB" in html
    assert "When and how much?" in html
    assert "Queue or cluster?" in html
    assert "Coverage checks" in html
    assert "coverage, limitations, and supporting context" in html
    assert str(out_dir) not in html
    assert "original_query.sql" not in html
    assert "SELECT segment" not in html


def test_generated_demo_runtime_and_workload_cases_render_safely(tmp_path):
    module = load_demo_module()
    out_dir = tmp_path / "query-doctor-demo-pack"
    module.main(["--out", str(out_dir)])
    summary = json.loads((out_dir / "batch_summary.json").read_text(encoding="utf-8"))

    admission_case = summary["cases"][3]
    query_context_facts = load_case_analysis_query_context_facts(Path(admission_case["case_dir"]))
    admission_view = present_recent_scan_case_detail(
        "case-004",
        admission_case,
        query_context_facts=query_context_facts,
    )
    admission_html = render_recent_scan_case_detail_view(admission_view)
    action_html = render_action_candidate_findings(admission_view)

    assert "Admission/runtime" in admission_html
    assert "88.00s" in admission_html
    assert "Similar queries in this scan: 2 · p95 128.0s" in admission_html
    assert "Admission/runtime follow-up" in action_html
    assert "Runtime: admission and pool timeline" in action_html
    assert str(out_dir) not in admission_html
    assert str(out_dir) not in action_html
    assert "original_query.sql" not in admission_html
    assert "SELECT queue_bucket" not in admission_html

    storage_view = present_recent_scan_case_detail("case-006", summary["cases"][5])
    storage_html = render_recent_scan_case_detail_view(storage_view)
    assert "Storage/HDFS" in storage_html
    assert "storage/HDFS evidence is the strongest runtime follow-up" in storage_html
    assert str(out_dir) not in storage_html

    mixed_view = present_recent_scan_case_detail("case-009", summary["cases"][8])
    mixed_html = render_recent_scan_case_detail_view(mixed_view)
    mixed_action_html = render_action_candidate_findings(mixed_view)
    assert "Multiple supported signals need review" in mixed_html
    assert "Query-shape recommendation" in mixed_action_html
    assert "Stats maintenance recommendation" in mixed_action_html
    assert str(out_dir) not in mixed_html
    assert "SELECT c.channel" not in mixed_html

    client_fetch_view = present_recent_scan_case_detail("case-010", summary["cases"][9])
    client_fetch_html = render_recent_scan_case_detail_view(client_fetch_view)
    client_fetch_action_html = render_action_candidate_findings(client_fetch_view)
    assert "Client fetch wait may be stretching the tail" in client_fetch_html
    assert "client fetch wait share 63%" in client_fetch_html
    assert "Diagnostic follow-up" in client_fetch_action_html
    assert "Client fetch wait evidence" in client_fetch_action_html
    assert "comparable rerun" in client_fetch_action_html
    assert str(out_dir) not in client_fetch_html

    direct_case = summary["cases"][10]
    direct_query_context = load_case_analysis_query_context_facts(Path(direct_case["case_dir"]))
    direct_view = present_recent_scan_case_detail(
        "case-011",
        direct_case,
        query_context_facts=direct_query_context,
    )
    direct_html = render_recent_scan_case_detail_view(direct_view)
    direct_action_html = render_action_candidate_findings(direct_view)
    assert direct_query_context is not None
    assert direct_query_context["summary"]["source"] == "Direct Impala daemon"
    assert "Direct Impala daemon" in direct_html
    assert "Admission/runtime" in direct_html
    assert "profile resource and timing facts both show admission wait" in direct_action_html
    assert str(out_dir) not in direct_html
    assert "SELECT queue_name" not in direct_html


def test_demo_pack_launch_instructions_use_console_script(tmp_path, capsys):
    module = load_demo_module()
    out_dir = tmp_path / "query-doctor-demo-pack"

    result = module.main(["--out", str(out_dir)])

    assert result == 0
    stdout = capsys.readouterr().out
    readme_text = (out_dir / "README.md").read_text(encoding="utf-8")
    assert "QUERY_DOCTOR_ACTION_OUTCOMES_PATH" in stdout
    assert "QUERY_DOCTOR_ACTION_OUTCOMES_PATH" in readme_text
    assert "query-doctor-web --host 127.0.0.1 --port 8766 --batch-summary" in stdout
    assert "query-doctor-web --host 127.0.0.1 --port 8766 --batch-summary" in readme_text
    assert stdout.index("query_group=workloads#scan-context") < stdout.index(
        "query_group=optimization#recent-results"
    )
    assert "query_group=workloads#recent-results" in stdout
    assert "query_group=frequent_short#recent-results" in stdout
    assert "query_doctor_web_ui.py" not in stdout
    assert "query_doctor_web_ui.py" not in readme_text


def test_generated_summary_renders_demo_groups_without_paths_or_raw_files(tmp_path):
    module = load_demo_module()
    out_dir = tmp_path / "query-doctor-demo-pack"
    module.main(["--out", str(out_dir)])
    summary = json.loads((out_dir / "batch_summary.json").read_text(encoding="utf-8"))
    outcome_metrics = summarize_workload_action_outcomes(
        load_action_outcomes(path=out_dir / "action_outcomes.jsonl")
    )

    optimization_html = render_batch_summary(summary, query_group="optimization")
    stats_html = render_batch_summary(summary, query_group="stats")
    workloads_html = render_batch_summary(
        summary,
        query_group="workloads",
        action_outcomes_recorded=8,
        workload_outcome_metrics=outcome_metrics,
    )
    frequent_short_html = render_batch_summary(summary, query_group="frequent_short")

    assert "demo-optimizer-0001" in optimization_html
    assert "demo-mixed-0009" in optimization_html
    assert "demo-stats-0002" in stats_html
    assert "demo-mixed-0009" in stats_html
    assert "Workload follow-up" in workloads_html
    assert "Open Workload Details;" in workloads_html
    assert "Repeated workload details" not in workloads_html
    assert "demo-admission-0004" in workloads_html
    assert "demo-admission-0005" in workloads_html
    assert "strong; baseline p95 38.0s; n=6" not in workloads_html
    assert "Action outcomes" in workloads_html
    assert (
        "5 recorded; 5 applied; 5 comparable reruns; improved 3, no change 2; "
        "last applied action Admission/runtime check: no change; "
        "family signal Admission/runtime check: improved 3/5 comparable reruns, no change 2; "
        "feedback sample threshold met (5/5 comparable reruns); "
        "next check admission/runtime signal count and workload p95"
    ) in workloads_html
    assert "demo-short-0008" in frequent_short_html
    assert "Low-value repeat" in frequent_short_html
    assert str(out_dir) not in optimization_html
    assert str(out_dir) not in stats_html
    assert str(out_dir) not in workloads_html
    assert str(out_dir) not in frequent_short_html
    for forbidden in (
        "profile_digest.md",
        "analysis_facts.md",
        "query_metadata.json",
        "cm_metadata.json",
    ):
        assert forbidden not in optimization_html
        assert forbidden not in stats_html
        assert forbidden not in workloads_html
        assert forbidden not in frequent_short_html


def test_refuses_repo_output_path(tmp_path):
    module = load_demo_module()

    result = module.main(["--out", str(REPO_DIR / "query-doctor-demo-pack")])

    assert result == 2


def test_requires_overwrite_for_existing_non_empty_output(tmp_path):
    module = load_demo_module()
    out_dir = tmp_path / "query-doctor-demo-pack"
    out_dir.mkdir()
    (out_dir / "existing.txt").write_text("existing", encoding="utf-8")

    result = module.main(["--out", str(out_dir)])

    assert result == 2
    assert (out_dir / "existing.txt").is_file()

    result = module.main(["--out", str(out_dir), "--overwrite"])

    assert result == 0
    assert not (out_dir / "existing.txt").exists()
    assert (out_dir / "batch_summary.json").is_file()
