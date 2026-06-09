"""Optional browser-level smoke tests for the local web UI."""

from __future__ import annotations

import hashlib
import json
import subprocess
import threading
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

import pytest

from query_doctor.web.models import WebClusterConfig
from web_server_test_support import REPO_DIR, load_web_module


E2E_QUERY_ID = "aaaaaaaaaaaaaaaa:0000000000000001"


def select_diagnosis_workflow(page, value: str) -> None:
    option = page.locator(f'label:has(input[name="diagnosis_workflow"][value="{value}"])')
    if not option.is_visible():
        page.locator("details[data-diagnosis-target-root] > summary").click()
    option.click()


def open_recent_results(page) -> None:
    if page.locator("#recent-results").get_attribute("open") is None:
        page.locator("#recent-results > summary").click()


def ensure_query_groups_visible(page) -> None:
    assert page.locator(".batch-query-groups").is_visible()
    assert page.get_by_text("Stats to check").is_visible()


def synthetic_batch_summary(*, cases_root: Path | None = None) -> dict[str, object]:
    case_dir = str(cases_root / "case-001" / "bad-e2e") if cases_root is not None else None
    return {
        "selected_count": 4,
        "cases": [
            {
                "case_index": 1,
                "query_id": "bad:e2e",
                "user": "alice",
                "score": 31,
                "score_severity": "high",
                "duration_sec": 120,
                "score_reasons": ["spill/scratch evidence: non-zero metrics"],
                "collection_status": "ok",
                "analysis_status": "ok",
                **({"case_dir": case_dir} if case_dir is not None else {}),
            },
            {
                "case_index": 2,
                "query_id": "suspicious:e2e",
                "user": "bob",
                "score": 12,
                "score_severity": "suspicious",
                "duration_sec": 80,
                "collection_status": "ok",
                "analysis_status": "ok",
            },
            {
                "case_index": 3,
                "query_id": "stats:e2e",
                "user": "carol",
                "score": 0,
                "score_severity": "clean",
                "duration_sec": 70,
                "score_reasons": ["spill/scratch evidence: non-zero metrics"],
                "collection_status": "ok",
                "analysis_status": "ok",
                "stats_optimization_candidate": {
                    "score": 72,
                    "tier": "high",
                    "confidence": "medium",
                    "impact": "high",
                    "need_type": "table_and_column_stats",
                    "speed_benefit": "medium",
                    "reasons": ["missing table stats before expensive join"],
                    "counter_signals": [],
                    "suggested_review_areas": ["table/partition row counts"],
                    "required_confirmation": ["compare EXPLAIN before and after stats collection"],
                },
            },
            {
                "case_index": 4,
                "query_id": "optimization:e2e",
                "user": "dave",
                "score": 0,
                "score_severity": "clean",
                "duration_sec": 95,
                "collection_status": "ok",
                "analysis_status": "ok",
                "query_optimization_candidate": {
                    "score": 55,
                    "tier": "medium",
                    "confidence": "medium",
                    "impact": "medium",
                    "reasons": ["join row expansion or cardinality mismatch with join evidence"],
                    "counter_signals": [],
                    "suggested_review_areas": ["join keys and join cardinality"],
                },
                "optimizer_rewrite_support": {
                    "status": "guidance_only",
                    "label": "Guidance only",
                    "reason": "Manual review only",
                    "rewriteability_bucket": "not_rewriteable",
                    "rewriteability_label": "Not rewriteable",
                    "cte_count": 2,
                    "cte_graph_shape": "linear_chain",
                    "cte_predicate_origin_status": "final_select_filter",
                },
                "source_locators": {
                    "query_optimization": [
                        {
                            "id": "sql_final_select_filter",
                            "coordinate": "line 18",
                            "detail": "predicate near final SELECT",
                        },
                        {
                            "id": "plan_cardinality_anomaly",
                            "detail": "node 02 HASH JOIN (inner join, partitioned)",
                        },
                    ]
                },
            },
        ],
    }


def write_summary(path: Path) -> Path:
    path.write_text(json.dumps(synthetic_batch_summary()), encoding="utf-8")
    return path


def write_action_summary(path: Path) -> tuple[Path, Path]:
    cases_root = path.parent / "cases"
    case_dir = cases_root / "case-001" / "bad-e2e"
    case_dir.mkdir(parents=True)
    (case_dir / "profile_digest.md").write_text("PROFILE\n", encoding="utf-8")
    (case_dir / "analysis_facts.md").write_text("FACTS\n", encoding="utf-8")
    (case_dir / "cm_metadata.json").write_text(
        json.dumps({"statement": "SELECT a FROM db.source_table WHERE ds = 20260504"}),
        encoding="utf-8",
    )
    path.write_text(json.dumps(synthetic_batch_summary(cases_root=cases_root)), encoding="utf-8")
    return path, case_dir


def e2e_settings(
    tmp_path: Path,
    *,
    batch_summary: Path | None = None,
    no_llm: bool = False,
):
    module = load_web_module()
    config = tmp_path / "query-doctor-e2e-config.json"
    config.write_text("{}", encoding="utf-8")
    return module.WebSettings(
        config=config,
        repo_dir=REPO_DIR,
        corpus_dir=tmp_path / "query-corpus",
        batch_summary=batch_summary,
        clusters=(
            WebClusterConfig(
                key="cm",
                label="CM prod",
                cm_url="https://cm.example.invalid",
                cm_cluster="prod",
                cm_service="impala",
            ),
            WebClusterConfig(
                key="ambari",
                label="Ambari prod",
                query_profile_source="impala",
                impala_profile_hosts=("impalad.example.invalid",),
            ),
        ),
        active_cluster_key="cm",
        no_llm=no_llm,
    )


def write_known_query_case(module, settings, query_id: str) -> Path:
    case_dir = module.expected_case_dir_for_query(query_id, settings)
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "profile_digest.md").write_text(
        "User: e2e-user\nPool: e2e-pool\n", encoding="utf-8"
    )
    (case_dir / "analysis_facts.md").write_text(
        "- Parsed operators: 4\n- Cardinality anomalies: 0\n- Memory anomalies: 2\n",
        encoding="utf-8",
    )
    (case_dir / "cm_metadata.json").write_text(
        json.dumps(
            {
                "duration_sec": 42.0,
                "user": "e2e-user",
                "pool": "e2e-pool",
                "statement": "SELECT a FROM db.source_table WHERE ds = 20260504",
            }
        ),
        encoding="utf-8",
    )
    (case_dir / "collection_warnings.txt").write_text("", encoding="utf-8")
    return case_dir


def fake_batch_runner(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
    out_dir = Path(cmd[cmd.index("--out") + 1])
    progress_path = Path(cmd[cmd.index("--progress-jsonl") + 1])
    out_dir.mkdir(parents=True, exist_ok=True)
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    progress_path.write_text(
        json.dumps({"stage": "discovery", "status": "done", "candidates_selected": 4}) + "\n",
        encoding="utf-8",
    )
    (out_dir / "batch_summary.json").write_text(
        json.dumps(synthetic_batch_summary()),
        encoding="utf-8",
    )
    return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")


def fake_failing_batch_runner(
    cmd: list[str], **_kwargs: object
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        cmd,
        2,
        stdout="SELECT secret_col FROM example_hidden.table WHERE token = 'raw-secret';",
        stderr="LEAKED_PROFILE_BODY with /private/tmp/query-doctor-sensitive-case",
    )


def fake_detail_action_runner(
    cmd: list[str], **_kwargs: object
) -> subprocess.CompletedProcess[str]:
    module = load_web_module()
    case_dir = next(
        (
            Path(value)
            for value in cmd
            if Path(value).is_dir() and (Path(value) / "analysis_facts.md").is_file()
        ),
        None,
    )
    if case_dir is None:
        return fake_batch_runner(cmd)

    if any("optimize_query" in value for value in cmd):
        source_sql = "SELECT a FROM db.source_table WHERE ds = 20260504"
        facts_text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
        recommendations_text = "- Collect table and column statistics.\n"
        recommendations_path = case_dir / "optimized_query_recommendations.md"
        recommendations_path.write_text(recommendations_text, encoding="utf-8")
        (case_dir / "optimized_query.validated.json").write_text(
            json.dumps(
                {
                    "facts_sha256": hashlib.sha256(facts_text.encode("utf-8")).hexdigest(),
                    "output_kind": "recommendations_only",
                    "recommendations": "optimized_query_recommendations.md",
                    "recommendations_sha256": module.file_sha256(recommendations_path),
                    "risk_mode": "recommendations_only",
                    "risk_reasons": ["too_many_ctes_for_safe_rewrite"],
                    "schema_version": module.OPTIMIZED_QUERY_MARKER_SCHEMA_VERSION,
                    "source": "query_doctor_optimize_query",
                    "source_scope": "read_only_statement",
                    "source_sql_sha256": hashlib.sha256(source_sql.encode("utf-8")).hexdigest(),
                    "validated": True,
                    "validation_mode": module.OPTIMIZED_QUERY_VALIDATION_MODE,
                }
            ),
            encoding="utf-8",
        )
    else:
        report_name = cmd[cmd.index("--out") + 1] if "--out" in cmd else module.PYTHON_REPORT_NAME
        report_variant = (
            module.REPORT_VARIANT_LLM
            if report_name == module.LLM_REPORT_NAME
            else module.REPORT_VARIANT_PYTHON
        )
        (case_dir / report_name).write_text(
            "# Validated report\n\nSafe E2E report body.\n", encoding="utf-8"
        )
        module.write_batch_case_report_validation_marker(case_dir, report_variant=report_variant)

    return subprocess.CompletedProcess(
        cmd, 0, stdout="raw stdout hidden", stderr="raw stderr hidden"
    )


@contextmanager
def run_test_server(
    settings: object, *, runner=fake_batch_runner, analysis_func=None
) -> Iterator[str]:
    module = load_web_module()
    handler_kwargs = {"runner": runner}
    if analysis_func is not None:
        handler_kwargs["analysis_func"] = analysis_func
    handler = module.make_handler(settings, **handler_kwargs)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()


@pytest.fixture()
def page():
    sync_api = pytest.importorskip(
        "playwright.sync_api",
        reason=(
            "Install the optional E2E extra and Chromium browser: "
            "python -m pip install -e '.[e2e]' && python -m playwright install chromium"
        ),
    )
    try:
        with sync_api.sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch()
            except Exception as exc:  # noqa: BLE001 - optional local browser dependency.
                pytest.skip(f"Playwright Chromium is not available: {exc}")
            try:
                browser_page = browser.new_page()
                yield browser_page
            finally:
                browser.close()
    except RuntimeError as exc:
        pytest.skip(f"Playwright runtime is not available: {exc}")


def test_e2e_diagnose_controls_preserve_cluster_and_scan_target(tmp_path, page):
    with run_test_server(e2e_settings(tmp_path)) as base_url:
        page.goto(base_url)

        assert page.locator("#diagnosis_cluster_key").is_visible()
        page.locator("#diagnosis_cluster_key").select_option("ambari")
        batch_cluster = page.locator('#batch-form input[name="cluster_key"]')
        query_cluster = page.locator('#analyze-form input[name="cluster_key"]')
        assert batch_cluster.get_attribute("value") == "ambari"
        assert query_cluster.get_attribute("value") == "ambari"

        select_diagnosis_workflow(page, "query")
        assert page.locator("#analyze-form").is_visible()
        assert not page.locator("#batch-form").is_visible()
        assert query_cluster.get_attribute("value") == "ambari"

        select_diagnosis_workflow(page, "running")
        assert page.locator("#batch-form").get_attribute("action") == "/running/run"
        assert not page.locator("#scan_date").is_visible()
        assert not page.locator("#scan_hour").is_visible()
        assert page.locator(".batch-note--simple-running").count() == 0
        assert page.locator("summary", has_text="Advanced settings").count() == 0

        select_diagnosis_workflow(page, "finished")
        assert page.locator("#batch-form").get_attribute("action") == "/batch/run"
        assert page.locator("#scan_date").is_visible()
        assert page.locator("#scan_hour").is_visible()


def test_e2e_optimizer_scope_guidance_is_secondary(tmp_path, page):
    with run_test_server(e2e_settings(tmp_path)) as base_url:
        page.goto(f"{base_url}/optimizer")

        assert page.locator("#optimizer_sql").is_visible()
        assert page.locator(".optimizer-panel .scope-line").count() == 0
        scope_details = page.locator(".optimizer-scope-details")
        metadata_scope = scope_details.locator("li", has_text="Metadata:")
        assert scope_details.is_visible()
        assert not metadata_scope.is_visible()

        scope_details.locator("summary").click()
        assert metadata_scope.is_visible()


def test_e2e_help_page_shortcuts_and_topics_are_interactive(tmp_path, page):
    with run_test_server(e2e_settings(tmp_path)) as base_url:
        page.goto(f"{base_url}/help")

        assert page.locator(".help-card-grid .help-card").count() == 5
        assert page.get_by_role("link", name="Trino compact").is_visible()
        assert page.locator("#workflows[open]").count() == 1
        assert page.locator("#safety .help-topic-body").is_visible() is False

        page.locator("#safety > summary").click()

        assert page.locator("#safety .help-topic-body").is_visible()
        assert page.get_by_text("Browser UI intentionally hides").is_visible()


def test_e2e_result_filters_preserve_group_and_open_details(tmp_path, page):
    summary_path = write_summary(tmp_path / "batch_summary.json")
    with run_test_server(e2e_settings(tmp_path, batch_summary=summary_path)) as base_url:
        page.goto(base_url)

        select_diagnosis_workflow(page, "query")
        assert page.locator("#recent-results .batch-head h1").inner_text() == (
            "Previous Recent Results"
        )
        assert page.locator("#recent-results").get_attribute("open") is None
        assert not page.locator("#recent-results .batch-table-wrap").is_visible()

        select_diagnosis_workflow(page, "finished")
        assert page.locator("#recent-results .batch-head h1").inner_text() == "Finished Queries"
        assert page.locator("#recent-results").get_attribute("open") == ""

        select_diagnosis_workflow(page, "running")
        assert page.locator("#recent-results .batch-head h1").inner_text() == (
            "Previous Finished Queries"
        )
        select_diagnosis_workflow(page, "finished")
        assert page.locator("#recent-results .batch-head h1").inner_text() == "Finished Queries"

        open_recent_results(page)
        ensure_query_groups_visible(page)
        page.locator('a.batch-filter-link[href="?query_group=stats#recent-results"]').click()
        page.wait_for_url("**/?query_group=stats#recent-results")
        active_filter = page.locator(
            ".batch-filter-link--active",
            has_text="Stats to check",
        )
        assert active_filter.is_visible()
        assert page.locator("tr", has_text="stats:e2e").is_visible()

        page.locator("a.batch-spill-toggle").click()
        page.wait_for_url("**/?query_group=stats&only_with_spills=on#recent-results")
        assert page.locator(".batch-spill-toggle--active").is_visible()
        assert active_filter.is_visible()
        assert page.locator("tr", has_text="stats:e2e").is_visible()
        assert not page.locator("tr", has_text="bad:e2e").is_visible()

        page.locator('tr[data-href="/batch/case/case-003"]').click()
        page.wait_for_url("**/batch/case/case-003")
        assert page.url.endswith("/batch/case/case-003")


def test_e2e_batch_detail_renders_owner_coordinate_action_card(tmp_path, page):
    summary_path = write_summary(tmp_path / "batch_summary.json")
    with run_test_server(e2e_settings(tmp_path, batch_summary=summary_path)) as base_url:
        page.goto(f"{base_url}/batch/case/case-004")

        action_plan = page.locator("#action-plan")
        assert action_plan.get_by_role("heading", name="Recommended change").is_visible()
        assert action_plan.get_by_text("Where to inspect").is_visible()
        safe_review_locations = action_plan.locator('[aria-label="Safe review locations"]')
        assert safe_review_locations.get_by_text(
            "SQL: final SELECT filter (line 18): predicate near final SELECT", exact=True
        ).is_visible()
        assert safe_review_locations.get_by_text(
            "Plan: estimate-mismatch operator: node 02 HASH JOIN (inner join, partitioned)",
            exact=True,
        ).is_visible()
        assert action_plan.get_by_text(
            "Try to reduce rows earlier: move the final SELECT filter closer"
        ).is_visible()
        assert action_plan.get_by_text("Compare EXPLAIN before and after the change").is_visible()
        assert not action_plan.get_by_text("Review first:").is_visible()
        assert not action_plan.get_by_text("optimization:e2e").is_visible()


def test_e2e_running_scan_submit_renders_synthetic_job_result(tmp_path, page):
    with run_test_server(e2e_settings(tmp_path)) as base_url:
        page.goto(base_url)

        assert page.locator("#diagnosis_cluster_key").is_visible()
        page.locator("#diagnosis_cluster_key").select_option("ambari")
        select_diagnosis_workflow(page, "running")
        page.locator("#batch-form button[type='submit']").click()

        page.wait_for_url("**/jobs/*")
        page.wait_for_selector("#recent-results", timeout=5000)
        assert (
            page.locator("#job-result-slot")
            .get_by_role("heading", name="Running Queries")
            .is_visible()
        )
        assert page.locator("#job-result-slot").locator("tr", has_text="bad:e2e").is_visible()


def test_e2e_recent_scan_failure_hides_subprocess_output(tmp_path, page):
    with run_test_server(e2e_settings(tmp_path), runner=fake_failing_batch_runner) as base_url:
        page.goto(base_url)

        page.locator("#batch-form button[type='submit']").click()

        page.wait_for_url("**/jobs/*")
        error_slot = page.locator("#job-error-slot")
        page.wait_for_selector(
            "#job-error-slot >> text=Query Doctor recent scan failed", timeout=5000
        )

        assert error_slot.get_by_text("exit code 2").is_visible()
        assert error_slot.get_by_text("Captured subprocess output is not shown").is_visible()
        body = page.locator("body")
        assert not body.get_by_text("SELECT secret_col").is_visible()
        assert not body.get_by_text("raw-secret").is_visible()
        assert not body.get_by_text("LEAKED_PROFILE_BODY").is_visible()
        assert not body.get_by_text("/private/tmp/query-doctor-sensitive-case").is_visible()


def test_e2e_known_query_preserves_selected_cluster_after_submit(tmp_path, page):
    module = load_web_module()
    query_id = E2E_QUERY_ID
    calls = []

    def fake_analysis(query_id_arg, report_mode, redact_identifiers, settings):
        write_known_query_case(module, settings, query_id_arg)
        calls.append(
            {
                "query_id": query_id_arg,
                "report_mode": report_mode,
                "redact_identifiers": redact_identifiers,
                "active_cluster_key": settings.active_cluster_key,
                "query_profile_source": settings.query_profile_source,
                "impala_profile_hosts": settings.impala_profile_hosts,
            }
        )
        return module.WebQueryAnalysisResult(
            query_id=query_id_arg,
            case={
                "query_id": query_id_arg,
                "score": 9,
                "score_severity": "suspicious",
                "duration_sec": 42.0,
                "collection_status": "ok",
                "analysis_status": "ok",
                "metadata_status": "skipped",
                "table_stats_status": "not_checked",
                "score_reasons": ["memory estimate anomalies: 2"],
                "memory_anomaly_count": 2,
            },
        )

    with run_test_server(e2e_settings(tmp_path), analysis_func=fake_analysis) as base_url:
        page.goto(base_url)

        assert page.locator("#diagnosis_cluster_key").is_visible()
        page.locator("#diagnosis_cluster_key").select_option("ambari")
        select_diagnosis_workflow(page, "query")
        page.locator("#query_id").fill(query_id)
        page.locator("#analyze-form button[type='submit']").click()

        page.wait_for_url("**/jobs/*")
        result_slot = page.locator("#job-result-slot")
        page.wait_for_selector("#job-result-slot >> text=Known Query ID analysis", timeout=5000)

        assert page.locator("#diagnosis_cluster_key").input_value() == "ambari"
        assert (
            page.locator('#analyze-form input[name="cluster_key"]').get_attribute("value")
            == "ambari"
        )
        assert page.locator("#query_id").input_value() == ""
        assert result_slot.get_by_role("heading", name="Known Query ID analysis").is_visible()
        assert result_slot.locator("tr", has_text=query_id).is_visible()
        assert result_slot.get_by_text("memory 2").is_visible()
        assert not page.locator("body").get_by_text("raw stdout hidden").is_visible()
        assert not page.locator("body").get_by_text("case_dir").is_visible()

    assert calls == [
        {
            "query_id": query_id,
            "report_mode": "analysis",
            "redact_identifiers": True,
            "active_cluster_key": "ambari",
            "query_profile_source": "impala",
            "impala_profile_hosts": ("impalad.example.invalid",),
        }
    ]


def test_e2e_known_query_result_opens_details_without_auto_llm_actions(tmp_path, page):
    module = load_web_module()
    query_id = E2E_QUERY_ID

    def fake_analysis(query_id_arg, _report_mode, _redact_identifiers, settings):
        write_known_query_case(module, settings, query_id_arg)
        return module.WebQueryAnalysisResult(
            query_id=query_id_arg,
            case={
                "query_id": query_id_arg,
                "score": 9,
                "score_severity": "suspicious",
                "duration_sec": 42.0,
                "collection_status": "ok",
                "analysis_status": "ok",
                "metadata_status": "skipped",
                "table_stats_status": "not_checked",
                "score_reasons": ["memory estimate anomalies: 2"],
                "memory_anomaly_count": 2,
            },
        )

    with run_test_server(e2e_settings(tmp_path), analysis_func=fake_analysis) as base_url:
        page.goto(base_url)

        assert page.locator("#diagnosis_cluster_key").is_visible()
        page.locator("#diagnosis_cluster_key").select_option("ambari")
        select_diagnosis_workflow(page, "query")
        page.locator("#query_id").fill(query_id)
        page.locator("#analyze-form button[type='submit']").click()

        page.wait_for_selector("#job-result-slot >> text=Known Query ID analysis", timeout=5000)
        page.locator("#job-result-slot").locator("tr", has_text=query_id).click()
        page.wait_for_url("**/query/details/*")
        detail_page = page
        detail_page.wait_for_load_state("domcontentloaded")

        assert "/query/details/" in detail_page.url
        assert detail_page.get_by_role("heading", name="Known Query ID details").is_visible()
        actions = detail_page.locator("#case-actions")
        assert actions.get_by_role("heading", name="Reports and optimizer").is_visible()
        assert actions.get_by_role("button", name="Generate Python report", exact=True).is_visible()
        assert actions.get_by_role("button", name="Generate LLM narrative").is_visible()
        assert actions.get_by_role("button", name="Run Query LLM optimizer").is_visible()
        assert actions.get_by_role("button", name="Generate Python report + optimizer").is_visible()
        assert not actions.locator(".report-progress").is_visible()
        assert not actions.get_by_text("Open full report").is_visible()
        assert not actions.get_by_text("Open Query LLM optimizer").is_visible()
        assert not detail_page.locator("body").get_by_text("case_dir").is_visible()
        assert not detail_page.locator("body").get_by_text(str(tmp_path)).is_visible()
        detail_page.close()


def test_e2e_detail_report_action_renders_trusted_result(tmp_path, page):
    summary_path, case_dir = write_action_summary(tmp_path / "batch_summary.json")
    settings = e2e_settings(tmp_path, batch_summary=summary_path)
    with run_test_server(settings, runner=fake_detail_action_runner) as base_url:
        page.goto(f"{base_url}/batch/case/case-001")

        actions = page.locator("#case-actions")
        assert actions.locator("strong", has_text="Python Report").is_visible()
        assert actions.locator("strong", has_text="LLM narrative").is_visible()
        actions.get_by_role("button", name="Generate Python report", exact=True).click()
        page.wait_for_url("**/jobs/*#case-actions")
        page.wait_for_selector("text=Open full report", timeout=5000)

        body = page.locator("body")
        body.locator("summary", has_text="Python Report body").click()
        assert body.get_by_text("Safe E2E report body.").is_visible()
        assert body.locator('[aria-label="Python report result"]').is_visible()
        assert not body.get_by_text("raw stdout hidden").is_visible()
        assert not body.get_by_text(str(case_dir)).is_visible()


def test_e2e_detail_optimizer_action_renders_trusted_recommendations(tmp_path, page):
    summary_path, case_dir = write_action_summary(tmp_path / "batch_summary.json")
    settings = e2e_settings(tmp_path, batch_summary=summary_path)
    with run_test_server(settings, runner=fake_detail_action_runner) as base_url:
        page.goto(f"{base_url}/batch/case/case-001")

        page.locator("#case-actions").get_by_role("button", name="Run Query LLM optimizer").click()
        page.wait_for_url("**/jobs/*#case-actions")
        open_link = page.get_by_role("link", name="Open Query LLM optimizer recommendations")
        open_link.wait_for(timeout=5000)
        assert open_link.get_attribute("href") == "#query-optimizer-result"
        open_link.click()
        page.wait_for_url("**/jobs/*#query-optimizer-result")

        body = page.locator("body")
        assert body.locator("summary", has_text="Query LLM optimizer recommendations").is_visible()
        body.locator("summary", has_text="Query LLM optimizer recommendations").click()
        assert body.get_by_text("Collect table and column statistics.").is_visible()
        assert body.locator("strong", has_text="Recommendations only").is_visible()
        assert not body.get_by_text("SELECT a FROM db.source_table").is_visible()
        assert not body.get_by_text("raw stderr hidden").is_visible()
        assert not body.get_by_text(str(case_dir)).is_visible()


def test_e2e_no_llm_detail_actions_use_case_actions_and_python_labels(tmp_path, page):
    summary_path, case_dir = write_action_summary(tmp_path / "batch_summary.json")
    settings = e2e_settings(tmp_path, batch_summary=summary_path, no_llm=True)
    calls: list[list[str]] = []

    def tracking_runner(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return fake_detail_action_runner(cmd, **kwargs)

    with run_test_server(settings, runner=tracking_runner) as base_url:
        page.goto(f"{base_url}/batch/case/case-001")

        actions = page.locator("#case-actions")
        assert actions.get_by_role("heading", name="Reports and optimizer").is_visible()
        assert actions.locator("strong", has_text="Python Report").is_visible()
        assert actions.locator("strong", has_text="Query optimizer").is_visible()
        assert actions.get_by_role("button", name="Generate Python report", exact=True).is_visible()
        assert actions.get_by_role("button", name="Run Query optimizer").is_visible()
        assert actions.get_by_role("button", name="Generate Python report + optimizer").is_visible()
        assert not page.locator("#llm-actions").is_visible()
        assert not page.locator("body").get_by_text("Generate LLM narrative").is_visible()
        assert not page.locator("body").get_by_text("Query LLM optimizer").is_visible()

        actions.get_by_role("button", name="Generate Python report", exact=True).click()
        page.wait_for_url("**/jobs/*#case-actions")
        page.wait_for_selector("text=Open full report", timeout=5000)

        body = page.locator("body")
        body.locator("summary", has_text="Python Report body").click()
        assert body.get_by_text("Safe E2E report body.").is_visible()
        assert body.locator('[aria-label="Python report result"]').is_visible()
        assert not body.get_by_text("raw stdout hidden").is_visible()
        assert not body.get_by_text("raw stderr hidden").is_visible()
        assert not body.get_by_text(str(case_dir)).is_visible()

    assert calls
    assert "--no-llm" in calls[0]


def test_e2e_no_llm_combined_action_renders_report_and_optimizer(tmp_path, page):
    summary_path, case_dir = write_action_summary(tmp_path / "batch_summary.json")
    settings = e2e_settings(tmp_path, batch_summary=summary_path, no_llm=True)
    calls: list[list[str]] = []

    def tracking_runner(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return fake_detail_action_runner(cmd, **kwargs)

    with run_test_server(settings, runner=tracking_runner) as base_url:
        page.goto(f"{base_url}/batch/case/case-001")

        page.locator("#case-actions").get_by_role(
            "button", name="Generate Python report + optimizer"
        ).click()
        page.wait_for_url("**/jobs/*#case-actions")
        page.wait_for_selector("text=Open full report", timeout=5000)
        open_link = page.get_by_role("link", name="Open Query optimizer recommendations")
        open_link.wait_for(timeout=5000)
        assert open_link.get_attribute("href") == "#query-optimizer-result"
        open_link.click()
        page.wait_for_url("**/jobs/*#query-optimizer-result")

        body = page.locator("body")
        body.locator("summary", has_text="Python Report body").click()
        assert body.get_by_text("Safe E2E report body.").is_visible()
        assert body.locator('[aria-label="Python report result"]').is_visible()
        assert body.locator("summary", has_text="Query optimizer recommendations").is_visible()
        body.locator("summary", has_text="Query optimizer recommendations").click()
        assert body.get_by_text("Collect table and column statistics.").is_visible()
        assert body.locator("strong", has_text="Recommendations only").is_visible()
        assert not body.get_by_text("SELECT a FROM db.source_table").is_visible()
        assert not body.get_by_text("raw stdout hidden").is_visible()
        assert not body.get_by_text("raw stderr hidden").is_visible()
        assert not body.get_by_text(str(case_dir)).is_visible()
        assert not page.locator("#llm-actions").is_visible()

    assert len(calls) == 2
    assert all("--no-llm" in call for call in calls)


def test_e2e_known_query_no_llm_combined_action_renders_python_outputs(tmp_path, page):
    module = load_web_module()
    query_id = E2E_QUERY_ID
    settings = e2e_settings(tmp_path, no_llm=True)
    calls: list[list[str]] = []

    def fake_analysis(query_id_arg, _report_mode, _redact_identifiers, analysis_settings):
        write_known_query_case(module, analysis_settings, query_id_arg)
        return module.WebQueryAnalysisResult(
            query_id=query_id_arg,
            case={
                "query_id": query_id_arg,
                "score": 9,
                "score_severity": "suspicious",
                "duration_sec": 42.0,
                "collection_status": "ok",
                "analysis_status": "ok",
                "metadata_status": "skipped",
                "table_stats_status": "not_checked",
                "score_reasons": ["memory estimate anomalies: 2"],
                "memory_anomaly_count": 2,
            },
        )

    def tracking_runner(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return fake_detail_action_runner(cmd, **kwargs)

    with run_test_server(
        settings,
        runner=tracking_runner,
        analysis_func=fake_analysis,
    ) as base_url:
        page.goto(base_url)

        select_diagnosis_workflow(page, "query")
        page.locator("#query_id").fill(query_id)
        page.locator("#analyze-form button[type='submit']").click()

        page.wait_for_selector("#job-result-slot >> text=Known Query ID analysis", timeout=5000)
        page.locator("#job-result-slot").locator("tr", has_text=query_id).click()
        page.wait_for_url("**/query/details/*")
        detail_page = page
        detail_page.wait_for_load_state("domcontentloaded")

        actions = detail_page.locator("#case-actions")
        assert actions.get_by_role("heading", name="Reports and optimizer").is_visible()
        assert actions.get_by_role("button", name="Generate Python report + optimizer").is_visible()
        assert not detail_page.locator("#llm-actions").is_visible()
        assert not detail_page.locator("body").get_by_text("Query LLM optimizer").is_visible()

        actions.get_by_role("button", name="Generate Python report + optimizer").click()
        detail_page.wait_for_url("**/jobs/*#case-actions")
        detail_page.wait_for_selector("text=Open full report", timeout=5000)
        open_link = detail_page.get_by_role("link", name="Open Query optimizer recommendations")
        open_link.wait_for(timeout=5000)
        assert open_link.get_attribute("href") == "#query-optimizer-result"
        open_link.click()
        detail_page.wait_for_url("**/jobs/*#query-optimizer-result")

        body = detail_page.locator("body")
        body.locator("summary", has_text="Python Report body").click()
        assert body.get_by_text("Safe E2E report body.").is_visible()
        assert body.locator('[aria-label="Python report result"]').is_visible()
        assert body.locator("summary", has_text="Query optimizer recommendations").is_visible()
        body.locator("summary", has_text="Query optimizer recommendations").click()
        assert body.get_by_text("Collect table and column statistics.").is_visible()
        assert not body.get_by_text("SELECT a FROM db.source_table").is_visible()
        assert not body.get_by_text("raw stdout hidden").is_visible()
        assert not body.get_by_text("raw stderr hidden").is_visible()
        assert not body.get_by_text(str(tmp_path)).is_visible()
        assert not detail_page.locator("#llm-actions").is_visible()
        detail_page.close()

    assert len(calls) == 2
    assert all("--no-llm" in call for call in calls)
