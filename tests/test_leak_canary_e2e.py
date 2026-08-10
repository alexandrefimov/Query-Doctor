from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import pytest

from query_doctor.cli import analyze_profile, batch_recent, report
from query_doctor.report.prompt_contract import build_prompt
from query_doctor.web.case_files import expected_case_dir_for_query
from query_doctor.web.command_builders import PYTHON_REPORT_NAME, REPORT_VARIANT_PYTHON
from query_doctor.web.job_workers import run_specific_query_report_job
from query_doctor.web.jobs import WebJobStore, render_job_status_json
from query_doctor.web.models import WebSettings
from query_doctor.web.owner_raw_source import OwnerRawSourceView
from query_doctor.web.query_analysis import run_query_id_analysis, run_uploaded_profile_analysis
from query_doctor.web.routes import route_get_request
from query_doctor.web.specific_query_pages import (
    render_specific_query_detail_for_request,
    render_specific_query_report_for_request,
)
from query_doctor.web.trusted_artifacts import write_batch_case_report_validation_marker
from query_doctor.web.ui.owner_raw_source import render_owner_raw_source_page


REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_PROFILE = REPO_ROOT / "tests" / "fixtures" / "mixed_stats_runtime_case" / "profile_digest.md"
QUERY_ID = "aaaabbbbccccdddd:1111222233334444"


CANARY_MARKERS = {
    "user": "qdleak_user_20260611_alpha",
    "pool": "qdleak_pool_20260611_alpha",
    "host": "qdleak-host-20260611-alpha.example.invalid",
    "ip": "198.51.100.77",
    "email": "qdleak.owner.20260611@example.invalid",
    "url_user": "qdleak_urluser_20260611",
    "url_password": "qdleak_urlpass_20260611",
    "auth_header": "QDLEAKBEARER20260611TOKEN",
    "cookie": "QDLEAKCOOKIE20260611VALUE",
    "password": "QDLEAK_PASSWORD_20260611_VALUE",
    "api_key": "QDLEAK_APIKEY_20260611_VALUE",
    "sql_db": "qdleak_db_20260611",
    "sql_table": "qdleak_table_20260611",
    "local_path": "qdleak_local_path_20260611",
}
PERSISTED_SINK_TIERS = frozenset({"local", "public"})
OWNER_RAW_EPHEMERAL_TIER = "owner_raw_ephemeral"
RAW_SOURCE_MARKER_IDS = frozenset({"sql_db", "sql_table"})
SECRET_MARKER_IDS = frozenset(
    {
        "url_password",
        "auth_header",
        "cookie",
        "password",
        "api_key",
    }
)
OWNER_RAW_ALLOWED_MARKER_IDS = frozenset(
    {
        "user",
        "pool",
        "host",
        "sql_db",
        "sql_table",
    }
)


@dataclass(frozen=True)
class SinkPolicy:
    tier: str
    allowed_marker_ids: frozenset[str] = frozenset()


OWNER_RAW_EPHEMERAL_RESPONSE_POLICY = SinkPolicy(
    OWNER_RAW_EPHEMERAL_TIER,
    allowed_marker_ids=OWNER_RAW_ALLOWED_MARKER_IDS,
)


CASE_SINK_POLICIES = {
    "profile_digest.md": SinkPolicy("local"),
    "query_metadata.json": SinkPolicy("local"),
    "cm_metadata.json": SinkPolicy("local"),
    "collection_warnings.txt": SinkPolicy("local"),
    "analysis_facts.md": SinkPolicy("public"),
    "analysis.json": SinkPolicy("public"),
    PYTHON_REPORT_NAME: SinkPolicy("public"),
    "diagnosis_python.validated.json": SinkPolicy("local"),
}


@dataclass(frozen=True)
class TextSink:
    label: str
    text: str
    policy: SinkPolicy


def test_full_pipeline_leak_canary_stays_out_of_public_and_local_sinks(tmp_path):
    raw_profile = write_raw_canary_profile(tmp_path)
    raw_profile_text = raw_profile.read_text(encoding="utf-8")
    assert all(marker in raw_profile_text for marker in CANARY_MARKERS.values())

    case_dir = run_manual_profile_analysis(tmp_path, raw_profile)
    report_prompt = build_report_prompt(case_dir)
    run_deterministic_report(case_dir)
    write_batch_case_report_validation_marker(case_dir, report_variant=REPORT_VARIANT_PYTHON)

    summary_case = score_case(case_dir)
    summary_path = write_batch_summary(tmp_path, summary_case)
    detail_html, report_html = render_browser_visible_pages(summary_path)

    assert_generated_case_sinks_clean(
        case_dir,
        required_paths=CASE_SINK_POLICIES.keys(),
    )
    assert_text_sinks_clean(
        [
            TextSink(
                "local batch summary",
                summary_path.read_text(encoding="utf-8"),
                SinkPolicy("local"),
            ),
            TextSink(
                "scoring summary JSON",
                json.dumps(summary_case, sort_keys=True),
                SinkPolicy("public"),
            ),
            TextSink("report prompt", report_prompt, SinkPolicy("local")),
            TextSink("browser Details HTML", detail_html, SinkPolicy("public")),
            TextSink("browser trusted report HTML", report_html, SinkPolicy("public")),
        ]
    )
    assert_browser_visible_text_is_generic_raw_free(tmp_path, detail_html + "\n" + report_html)


def test_manual_profile_inbox_known_query_details_leak_canary(tmp_path):
    raw_profile = write_raw_canary_profile(tmp_path)
    profile_dir = tmp_path / "profile-inbox"
    profile_dir.mkdir()
    profile_slug = QUERY_ID.replace(":", "_")
    inbox_profile = profile_dir / f"{profile_slug}.txt"
    inbox_profile.write_text(raw_profile.read_text(encoding="utf-8"), encoding="utf-8")
    settings = WebSettings(
        config=tmp_path / "cm-config.json",
        repo_dir=REPO_ROOT,
        corpus_dir=tmp_path / "cm-corpus",
        manual_profile_dir=profile_dir,
        no_llm=True,
        timeout_sec=90,
    )
    store = WebJobStore()
    progress_stages: list[int] = []

    result = run_query_id_analysis(
        QUERY_ID,
        "analysis",
        True,
        settings,
        progress=progress_stages.append,
    )
    case_dir = expected_case_dir_for_query(QUERY_ID, settings)
    assert result.query_id == QUERY_ID
    assert result.case["query_id"] == QUERY_ID
    assert "case_dir" not in result.case
    assert "case_index" not in result.case
    assert case_dir.is_dir()
    assert progress_stages == [0, 1, 2, 3, 4, 5]
    assert (case_dir / PYTHON_REPORT_NAME).is_file()
    assert (case_dir / "diagnosis_python.validated.json").is_file()

    analysis_job = store.create(QUERY_ID, "analysis")
    store.complete(analysis_job.job_id, result)
    analysis_status_json = render_job_status_json(store.get(analysis_job.job_id))

    detail_status, detail_html = render_specific_query_detail_for_request(
        settings,
        QUERY_ID,
        store,
        job=store.get(analysis_job.job_id),
    )
    assert detail_status == 200
    detail_route = route_get_request(
        f"/query/details/{quote(QUERY_ID, safe='')}",
        settings,
        store,
    )
    assert detail_route is not None
    assert detail_route.status == 200

    report_job = store.create_query_report(QUERY_ID, report_variant=REPORT_VARIANT_PYTHON)
    run_specific_query_report_job(
        report_job.job_id,
        QUERY_ID,
        case_dir,
        settings,
        store,
        subprocess.run,
        REPORT_VARIANT_PYTHON,
    )
    report_status_json = render_job_status_json(store.get(report_job.job_id))
    report_page_status, report_html = render_specific_query_report_for_request(
        settings,
        QUERY_ID,
        report_variant=REPORT_VARIANT_PYTHON,
    )
    assert report_page_status == 200
    detail_with_report_status, detail_with_report_html = render_specific_query_detail_for_request(
        settings,
        QUERY_ID,
        store,
        job=store.get(report_job.job_id),
    )
    assert detail_with_report_status == 200

    assert_generated_case_sinks_clean(
        case_dir,
        required_paths=CASE_SINK_POLICIES.keys(),
    )
    assert_text_sinks_clean(
        [
            TextSink("Known Query job status JSON", analysis_status_json, SinkPolicy("public")),
            TextSink(
                "Known Query report job status JSON",
                report_status_json,
                SinkPolicy("public"),
            ),
            TextSink("Known Query Details HTML", detail_html, SinkPolicy("public")),
            TextSink("Known Query Details route HTML", detail_route.body, SinkPolicy("public")),
            TextSink(
                "Known Query Details HTML with report",
                detail_with_report_html,
                SinkPolicy("public"),
            ),
            TextSink("Known Query report HTML", report_html, SinkPolicy("public")),
        ]
    )
    assert_browser_visible_text_is_generic_raw_free(
        tmp_path,
        "\n".join(
            [
                analysis_status_json,
                report_status_json,
                detail_html,
                detail_route.body,
                detail_with_report_html,
                report_html,
            ]
        ),
        extra_forbidden_fragments=(profile_slug, inbox_profile.name, raw_profile.name),
    )


def test_uploaded_profile_known_query_details_leak_canary(tmp_path):
    raw_profile = write_raw_canary_profile(tmp_path)
    raw_profile_text = raw_profile.read_text(encoding="utf-8")
    settings = WebSettings(
        config=tmp_path / "cm-config.json",
        repo_dir=REPO_ROOT,
        corpus_dir=tmp_path / "cm-corpus",
        no_llm=True,
        timeout_sec=90,
    )
    store = WebJobStore()
    progress_stages: list[int] = []

    result = run_uploaded_profile_analysis(
        QUERY_ID,
        raw_profile_text,
        settings,
        progress=progress_stages.append,
    )
    case_dir = expected_case_dir_for_query(QUERY_ID, settings)
    assert result.query_id == QUERY_ID
    assert result.case["query_id"] == QUERY_ID
    assert "case_dir" not in result.case
    assert "case_index" not in result.case
    assert case_dir.is_dir()
    assert progress_stages == [0, 1, 2, 3, 4, 5]
    assert (case_dir / PYTHON_REPORT_NAME).is_file()
    assert (case_dir / "diagnosis_python.validated.json").is_file()
    assert not any(settings.corpus_dir.glob(".profile-upload-*"))

    analysis_job = store.create(QUERY_ID, "uploaded_profile")
    store.complete(analysis_job.job_id, result)
    analysis_status_json = render_job_status_json(store.get(analysis_job.job_id))

    detail_status, detail_html = render_specific_query_detail_for_request(
        settings,
        QUERY_ID,
        store,
        job=store.get(analysis_job.job_id),
    )
    assert detail_status == 200
    detail_route = route_get_request(
        f"/query/details/{quote(QUERY_ID, safe='')}",
        settings,
        store,
    )
    assert detail_route is not None
    assert detail_route.status == 200

    assert_generated_case_sinks_clean(
        case_dir,
        required_paths=CASE_SINK_POLICIES.keys(),
    )
    assert_text_sinks_clean(
        [
            TextSink(
                "Uploaded profile job status JSON", analysis_status_json, SinkPolicy("public")
            ),
            TextSink("Uploaded profile Details HTML", detail_html, SinkPolicy("public")),
            TextSink(
                "Uploaded profile Details route HTML", detail_route.body, SinkPolicy("public")
            ),
        ]
    )
    assert_browser_visible_text_is_generic_raw_free(
        tmp_path,
        "\n".join([analysis_status_json, detail_html, detail_route.body]),
        extra_forbidden_fragments=(raw_profile.name, "uploaded-profile.txt"),
    )


def test_leak_canary_fails_closed_for_unclassified_generated_file(tmp_path):
    raw_profile = write_raw_canary_profile(tmp_path)
    case_dir = run_manual_profile_analysis(tmp_path, raw_profile)
    (case_dir / "new_unreviewed_sink.txt").write_text("safe text\n", encoding="utf-8")

    with pytest.raises(AssertionError, match="unclassified generated sink"):
        assert_generated_case_sinks_clean(case_dir)


def test_leak_canary_negative_control_catches_disabled_host_redaction(tmp_path):
    raw_profile = write_raw_canary_profile(tmp_path)
    case_dir = analyze_profile.stage_manual_profile_case(
        profile_text_path=raw_profile,
        query_id=QUERY_ID,
        out_dir=tmp_path / "unredacted-cases",
        redact_identifiers=True,
        redact_hosts=False,
    )

    with pytest.raises(AssertionError, match=r"profile_digest\.md: .*host"):
        assert_generated_case_sinks_clean(
            case_dir,
            required_paths=("profile_digest.md", "query_metadata.json", "cm_metadata.json"),
        )


def test_leak_canary_persisted_sink_policy_rejects_raw_source_allowlist():
    with pytest.raises(AssertionError, match="persisted sink policy"):
        assert_text_sinks_clean(
            [
                TextSink(
                    "bad persisted sink",
                    "",
                    SinkPolicy("local", allowed_marker_ids=RAW_SOURCE_MARKER_IDS),
                )
            ]
        )


def test_owner_raw_ephemeral_policy_allows_source_but_not_secrets():
    owner_raw_body = "\n".join(
        [
            f"Owner: {CANARY_MARKERS['user']}",
            f"Pool: {CANARY_MARKERS['pool']}",
            f"Coordinator: {CANARY_MARKERS['host']}",
            (
                "SELECT id "
                f"FROM {CANARY_MARKERS['sql_db']}.{CANARY_MARKERS['sql_table']} "
                "WHERE ds = '2026-06-11'"
            ),
        ]
    )

    assert_text_sinks_clean(
        [
            TextSink(
                "future owner-raw ephemeral response",
                owner_raw_body,
                OWNER_RAW_EPHEMERAL_RESPONSE_POLICY,
            )
        ]
    )

    disallowed_marker_ids = set(CANARY_MARKERS) - OWNER_RAW_ALLOWED_MARKER_IDS
    assert SECRET_MARKER_IDS <= disallowed_marker_ids
    for marker_id in sorted(disallowed_marker_ids):
        with pytest.raises(AssertionError, match=marker_id):
            assert_text_sinks_clean(
                [
                    TextSink(
                        f"future owner-raw ephemeral response with {marker_id}",
                        f"{owner_raw_body}\n{CANARY_MARKERS[marker_id]}\n",
                        OWNER_RAW_EPHEMERAL_RESPONSE_POLICY,
                    )
                ]
            )


def test_owner_raw_source_page_uses_ephemeral_policy_and_masks_secrets(tmp_path):
    owner_raw_body = render_owner_raw_source_page(
        WebSettings(config=tmp_path / "cm-config.json"),
        OwnerRawSourceView(
            case_id="case-001",
            query_id=QUERY_ID,
            query_user=CANARY_MARKERS["user"],
            source_sql=(
                "SELECT id "
                f"FROM {CANARY_MARKERS['sql_db']}.{CANARY_MARKERS['sql_table']} "
                "WHERE password = '<redacted>'"
            ),
            source_scope="read_only_statement",
            reason_code="viewer_matches_query_user",
            highlights=(),
            back_href="/batch/case/case-001",
        ),
    )

    assert CANARY_MARKERS["password"] not in owner_raw_body
    assert_text_sinks_clean(
        [
            TextSink(
                "owner-raw source response",
                owner_raw_body,
                OWNER_RAW_EPHEMERAL_RESPONSE_POLICY,
            )
        ]
    )


def test_owner_raw_source_markers_stay_forbidden_in_public_sinks():
    owner_raw_body = (
        "SELECT id "
        f"FROM {CANARY_MARKERS['sql_db']}.{CANARY_MARKERS['sql_table']} "
        "WHERE ds = '2026-06-11'"
    )

    with pytest.raises(AssertionError, match="sql_db"):
        assert_text_sinks_clean(
            [
                TextSink(
                    "browser Details HTML",
                    owner_raw_body,
                    SinkPolicy("public"),
                )
            ]
        )


def write_raw_canary_profile(tmp_path: Path) -> Path:
    marker = CANARY_MARKERS
    base_profile = BASE_PROFILE.read_text(encoding="utf-8")
    profile_url = (
        f"https://{marker['host']}/profile?"
        f"username={marker['url_user']}&password={marker['url_password']}"
    )
    profile_text = f"""Query Runtime Profile
Query ID: {QUERY_ID}
Query Type: QUERY
Query State: FINISHED
User: {marker["user"]}
Request Pool: {marker["pool"]}
Coordinator: {marker["host"]}:25000
Host: {marker["ip"]}
Owner Email: {marker["email"]}
Profile URL: {profile_url}
Authorization: Bearer {marker["auth_header"]}
Cookie: session={marker["cookie"]}
password={marker["password"]}
api_key={marker["api_key"]}
Scratch path: /Users/{marker["local_path"]}/query-doctor/scratch
Start Time: 2026-06-11 10:00:00.000000
End Time: 2026-06-11 10:01:30.000000
Sql Statement: SELECT id FROM {marker["sql_db"]}.{marker["sql_table"]} WHERE ds = '2026-06-11'
Plan:

{base_profile}
"""
    path = tmp_path / "raw-profile-export.txt"
    path.write_text(profile_text, encoding="utf-8")
    return path


def run_manual_profile_analysis(tmp_path: Path, raw_profile: Path) -> Path:
    out_dir = tmp_path / "cases"
    result = analyze_profile.main(
        [
            "--profile-text",
            str(raw_profile),
            "--query-id",
            QUERY_ID,
            "--out",
            str(out_dir),
            "--redact-identifiers",
            "--fail-on-empty",
        ]
    )
    assert result == 0
    case_dirs = sorted(out_dir.iterdir())
    assert len(case_dirs) == 1
    return case_dirs[0]


def build_report_prompt(case_dir: Path) -> str:
    facts_path = case_dir / "analysis_facts.md"
    facts_text = facts_path.read_text(encoding="utf-8")
    facts_sha256 = hashlib.sha256(facts_path.read_bytes()).hexdigest()
    return build_prompt(
        facts_text=facts_text,
        facts_path=facts_path,
        facts_sha256=facts_sha256,
        model="synthetic-leak-canary-model",
        language="en",
        mode="admin",
    )


def run_deterministic_report(case_dir: Path) -> None:
    result = report.main(
        [
            str(case_dir),
            "--no-llm",
            "--out",
            PYTHON_REPORT_NAME,
            "--language",
            "en",
            "--mode",
            "admin",
            "--model",
            "synthetic-leak-canary-model",
        ]
    )
    assert result == 0


def score_case(case_dir: Path) -> dict[str, object]:
    case = batch_recent.CaseResult(
        index=1,
        query_id=QUERY_ID,
        duration_sec=90.0,
        user=None,
        pool=None,
        query_type="QUERY",
        sql_verb="SELECT",
        wrapper_dir=case_dir,
        actual_case_dir=case_dir,
        collection_status="ok",
        analysis_status="ok",
        report_generated=True,
        report_validation_status="passed",
    )
    batch_recent.inspect_case_outputs(case)
    batch_recent.score_case(case)
    return batch_recent.case_to_summary(case)


def write_batch_summary(tmp_path: Path, summary_case: dict[str, object]) -> Path:
    summary = {
        "mode": "leak-canary-e2e",
        "query_profile_source": "manual-profile",
        "cases": [summary_case],
        "selected_count": 1,
    }
    summary_path = tmp_path / "batch_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary_path


def render_browser_visible_pages(summary_path: Path) -> tuple[str, str]:
    settings = WebSettings(
        config=Path(".query-doctor-cm.local.json"),
        batch_summary=summary_path,
        no_llm=True,
        model="synthetic-leak-canary-model",
    )
    store = WebJobStore()

    detail = route_get_request("/batch/case/case-001", settings, store)
    assert detail is not None
    assert detail.status == 200

    report_page = route_get_request("/batch/case/case-001/python-report", settings, store)
    assert report_page is not None
    assert report_page.status == 200
    return detail.body, report_page.body


def assert_generated_case_sinks_clean(
    case_dir: Path,
    *,
    required_paths: object = (),
) -> None:
    observed = {
        path.relative_to(case_dir).as_posix(): path
        for path in sorted(case_dir.rglob("*"))
        if path.is_file()
    }
    unclassified = sorted(set(observed) - set(CASE_SINK_POLICIES))
    assert not unclassified, f"unclassified generated sink(s): {unclassified}"

    missing = sorted(set(required_paths) - set(observed))
    assert not missing, f"missing expected generated sink(s): {missing}"

    for relative_path, path in observed.items():
        policy = CASE_SINK_POLICIES[relative_path]
        assert_persisted_policy_has_no_raw_allowlist(relative_path, policy)
        text = path.read_text(encoding="utf-8", errors="replace")
        assert_no_forbidden_markers(
            relative_path,
            text,
            allowed_marker_ids=policy.allowed_marker_ids,
        )


def assert_text_sinks_clean(sinks: list[TextSink]) -> None:
    for sink in sinks:
        assert_persisted_policy_has_no_raw_allowlist(sink.label, sink.policy)
        assert_no_forbidden_markers(
            sink.label,
            sink.text,
            allowed_marker_ids=sink.policy.allowed_marker_ids,
        )


def assert_persisted_policy_has_no_raw_allowlist(label: str, policy: SinkPolicy) -> None:
    if policy.tier not in PERSISTED_SINK_TIERS:
        return
    forbidden_allowed = policy.allowed_marker_ids & (RAW_SOURCE_MARKER_IDS | SECRET_MARKER_IDS)
    assert not forbidden_allowed, (
        f"persisted sink policy for {label} allows raw/secret marker(s): "
        + ", ".join(sorted(forbidden_allowed))
    )


def assert_no_forbidden_markers(
    label: str,
    text: str,
    *,
    allowed_marker_ids: frozenset[str] = frozenset(),
) -> None:
    hits = [
        marker_id
        for marker_id, marker in CANARY_MARKERS.items()
        if marker_id not in allowed_marker_ids and marker in text
    ]
    assert not hits, f"forbidden leak-canary marker(s) in {label}: {', '.join(hits)}"


def assert_browser_visible_text_is_generic_raw_free(
    tmp_path: Path,
    text: str,
    *,
    extra_forbidden_fragments: tuple[str, ...] = (),
) -> None:
    forbidden_fragments = (
        str(tmp_path),
        "case_dir",
        "profile_digest.md",
        "analysis_facts.md",
        PYTHON_REPORT_NAME,
        "raw stdout",
        "raw stderr",
        "qwen3-coder",
        "ollama",
        *extra_forbidden_fragments,
    )
    leaked = [fragment for fragment in forbidden_fragments if fragment in text]
    assert not leaked, f"browser-visible raw/internal fragment(s): {leaked}"
