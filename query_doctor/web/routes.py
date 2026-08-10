"""HTTP-route response construction for the local web UI."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from importlib.resources import files
from typing import Callable
from urllib.parse import parse_qs, unquote, urlparse

from query_doctor.web.batch_case_actions import (
    handle_batch_case_external_rewrite_validation,
    start_batch_case_llm_actions_job,
    start_batch_case_optimized_query_job,
    start_batch_case_report_job,
)
from query_doctor.web.audit import WebAuditEvent
from query_doctor.web.command_builders import REPORT_VARIANT_LLM, REPORT_VARIANT_PYTHON
from query_doctor.web.batch_case_pages import render_batch_case_detail_for_request
from query_doctor.web.batch_jobs import start_batch_job, start_running_job
from query_doctor.web.action_outcomes import (
    action_outcome_record_from_case,
    append_action_outcome,
)
from query_doctor.web.case_detail_context import (
    batch_page_settings,
    resolve_case_detail_settings,
    resolve_running_case_detail_settings,
    running_detail_kwargs,
    running_page_settings,
)
from query_doctor.web.case_files import expected_case_dir_for_query
from query_doctor.web.deployment_readiness import deployment_readiness_json
from query_doctor.web.form_helpers import first_form_value, form_flag_enabled
from query_doctor.web.jobs import WebJobStore, render_job_status_json
from query_doctor.web.job_ids import WEB_JOB_ID_PATTERN
from query_doctor.web.models import WebError, WebJobSnapshot, WebSettings
from query_doctor.web.owner_raw_source import (
    OWNER_RAW_SOURCE_REASON_CASE_NOT_FOUND,
    OwnerRawSourceDecision,
    build_owner_raw_source_view,
    owner_raw_source_audit_event,
    owner_raw_source_detail_href,
    owner_raw_source_path_match,
    unquote_case_id,
)
from query_doctor.web.query_analysis import run_query_id_analysis, validate_query_id
from query_doctor.web.request_handlers import (
    handle_optimizer_request,
    start_analyze_job,
    start_profile_upload_job,
)
from query_doctor.web.trino_details import render_trino_detail_for_request
from query_doctor.web.trino_guidance import (
    load_trino_optimizer_guidance,
    render_trino_optimizer_guidance_error_page,
    render_trino_optimizer_guidance_for_request,
)
from query_doctor.web.trino_report import (
    load_trino_python_report,
    render_trino_python_report_error_page,
    render_trino_python_report_for_request,
)
from query_doctor.web.specific_query_actions import (
    handle_specific_query_external_rewrite_validation,
    start_specific_query_llm_actions_job,
    start_specific_query_optimized_query_job,
    start_specific_query_report_job,
)
from query_doctor.web.specific_query_pages import (
    render_specific_query_detail_for_request,
    render_specific_query_report_for_request,
    specific_query_report_unavailable_error,
)
from query_doctor.web.subprocesses import Runner
from query_doctor.web.preview_surfaces import (
    PREVIEW_WEB_POST_PATHS,
    preview_surface_for_get_path,
    preview_surface_for_post_path,
)
from query_doctor.web.trusted_artifacts import (
    load_batch_case_trusted_report_artifact,
    load_specific_query_trusted_report_artifact,
    resolve_batch_case_report_dir,
    trusted_report_download_filename,
)
from query_doctor.web.workload_pages import render_workload_detail_for_request
from query_doctor.web.ui.help import render_demo_guide_page, render_help_page
from query_doctor.web.ui.deployment import render_deployment_readiness_page
from query_doctor.web.ui.optimizer import render_optimizer_page
from query_doctor.web.ui.outcomes import render_action_outcomes_page
from query_doctor.web.ui.owner_raw_source import (
    render_owner_raw_source_page,
    render_owner_raw_source_unavailable_page,
)
from query_doctor.web.ui.pages import (
    render_batch_case_not_found_page,
    render_batch_case_report_page,
    render_batch_page,
    render_page,
    render_query_page,
    render_readme_page,
)
from query_doctor.web.ui.query_inbox import query_inbox_scope_filters_from_mapping
from query_doctor.web.ui.recent_scan_result_filters import (
    recent_scan_result_filters_from_mapping,
)
from query_doctor.web.ui.running import render_running_queries_page


AnalysisFunc = Callable[[str, str, bool, WebSettings], object]

STATIC_POST_PATHS = {
    "/analyze",
    "/batch/run",
    "/running/run",
    "/optimizer",
    "/query-optimizer",
    "/profile/upload",
}
STATIC_ASSETS = {
    "/static/app.css": ("app.css", "text/css; charset=utf-8"),
    "/static/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/static/theme-bootstrap.js": ("theme-bootstrap.js", "application/javascript; charset=utf-8"),
}
REPORT_DOWNLOAD_CONTENT_TYPE = "text/markdown; charset=utf-8"
JOB_CANCEL_POST_RE = re.compile(rf"/jobs/(?P<job_id>{WEB_JOB_ID_PATTERN})/cancel")
BATCH_CASE_POST_RE = re.compile(
    r"/(?P<source>batch|running)/case/(?P<case_id>[^/]+)/(?P<action>report|python-report|llm-report|optimized-query|validate-rewrite|llm-actions|case-actions)"
)
ACTION_OUTCOME_POST_RE = re.compile(
    r"/(?P<source>batch|running)/case/(?P<case_id>[^/]+)/outcome/(?P<recommendation_id>[A-Za-z0-9_.-]+)"
)
SPECIFIC_QUERY_POST_RE = re.compile(
    r"/query/details/(?P<query_id>[^/]+)/(?P<action>report|python-report|llm-report|optimized-query|validate-rewrite|llm-actions|case-actions)"
)
HEALTH_PATHS = {"/healthz", "/readyz"}


@dataclass(frozen=True)
class WebRouteResponse:
    status: int
    body: str
    content_type: str = "text/html; charset=utf-8"
    location: str | None = None
    download_filename: str | None = None
    audit_event: WebAuditEvent | None = None

    @classmethod
    def html(
        cls,
        status: int,
        body: str,
        *,
        audit_event: WebAuditEvent | None = None,
    ) -> "WebRouteResponse":
        return cls(status=status, body=body, audit_event=audit_event)

    @classmethod
    def json(cls, status: int, body: str) -> "WebRouteResponse":
        return cls(status=status, body=body, content_type="application/json; charset=utf-8")

    @classmethod
    def markdown_download(cls, filename: str, body: str) -> "WebRouteResponse":
        return cls(
            status=200,
            body=body,
            content_type=REPORT_DOWNLOAD_CONTENT_TYPE,
            download_filename=filename,
        )

    @classmethod
    def redirect(cls, location: str) -> "WebRouteResponse":
        return cls(status=303, body="", location=location)


def report_download_filename(source_id: str) -> str:
    return trusted_report_download_filename(source_id)


def route_get_request(
    path: str,
    settings: WebSettings,
    store: WebJobStore,
) -> WebRouteResponse | None:
    parsed = urlparse(path)
    if parsed.path in HEALTH_PATHS:
        return route_health_get(parsed.path)
    if parsed.path == "/deployment/readiness.json":
        return WebRouteResponse.json(200, deployment_readiness_json(settings))
    if parsed.path in {"/deployment", "/deployment/readiness"}:
        return WebRouteResponse.html(200, render_deployment_readiness_page(settings))
    if parsed.path in {"/", "/index.html", "/batch"}:
        query = parse_qs(parsed.query, keep_blank_values=True)
        effective_settings = batch_page_settings(settings, store)
        return WebRouteResponse.html(
            200,
            render_batch_page(
                effective_settings,
                query_group=first_form_value(query, "query_group")
                or default_batch_query_group(effective_settings),
                only_with_spills=form_flag_enabled(query, "only_with_spills"),
                result_sort=first_form_value(query, "result_sort"),
                results_page=first_form_value(query, "results_page"),
                workload_admin_scope=first_form_value(query, "workload_admin_scope"),
                workload_admin_signal=first_form_value(query, "workload_admin_signal"),
                workload_group_scope=first_form_value(query, "workload_group_scope"),
                workload_group_name=first_form_value(query, "workload_group_name"),
                workload_group_signal=first_form_value(query, "workload_group_signal"),
                inbox_scope_filters=query_inbox_scope_filters_from_mapping(query),
                result_filters=recent_scan_result_filters_from_mapping(query),
            ),
        )
    static_response = route_static_asset_get(parsed.path)
    if static_response is not None:
        return static_response
    owner_raw_source = route_owner_raw_source_get(parsed.path, settings, store)
    if owner_raw_source is not None:
        return owner_raw_source
    batch_detail = route_batch_detail_get(parsed.path, settings, store)
    if batch_detail is not None:
        return batch_detail
    workload_detail = route_workload_detail_get(parsed.path, settings, store)
    if workload_detail is not None:
        return workload_detail
    specific_detail = route_specific_detail_get(parsed.path, settings, store)
    if specific_detail is not None:
        return specific_detail
    trino_detail = route_trino_detail_get(parsed.path, parsed.query, settings)
    if trino_detail is not None:
        return trino_detail
    if parsed.path in {"/query", "/run"}:
        return WebRouteResponse.html(200, render_query_page(settings))
    if parsed.path in {"/optimizer", "/query-optimizer"}:
        return WebRouteResponse.html(200, render_optimizer_page(settings))
    preview_surface = preview_surface_for_get_path(parsed.path)
    if preview_surface is not None:
        return WebRouteResponse.html(200, preview_surface.render_get(settings))
    if parsed.path in {"/running", "/running-queries"}:
        query = parse_qs(parsed.query, keep_blank_values=True)
        return WebRouteResponse.html(
            200,
            render_running_queries_page(
                running_page_settings(settings, store),
                query_group=first_form_value(query, "query_group"),
                only_with_spills=form_flag_enabled(query, "only_with_spills"),
                result_sort=first_form_value(query, "result_sort"),
                results_page=first_form_value(query, "results_page"),
                workload_admin_scope=first_form_value(query, "workload_admin_scope"),
                workload_admin_signal=first_form_value(query, "workload_admin_signal"),
                workload_group_scope=first_form_value(query, "workload_group_scope"),
                workload_group_name=first_form_value(query, "workload_group_name"),
                workload_group_signal=first_form_value(query, "workload_group_signal"),
                inbox_scope_filters=query_inbox_scope_filters_from_mapping(query),
                result_filters=recent_scan_result_filters_from_mapping(query),
            ),
        )
    if parsed.path == "/help":
        return WebRouteResponse.html(200, render_help_page(settings))
    if parsed.path == "/outcomes":
        return WebRouteResponse.html(
            200,
            render_page(
                settings,
                active_nav="batch",
                show_run_panel=False,
                extra_sections=[render_action_outcomes_page()],
            ),
        )
    if parsed.path in {"/demo", "/demo-guide"}:
        return WebRouteResponse.html(200, render_demo_guide_page(settings))
    if parsed.path == "/readme":
        return WebRouteResponse.html(200, render_readme_page(settings))
    job_response = route_job_get(parsed.path, parsed.query, settings, store)
    if job_response is not None:
        return job_response
    return None


def route_health_get(path: str) -> WebRouteResponse:
    probe = "readiness" if path == "/readyz" else "liveness"
    return WebRouteResponse.json(
        200,
        json.dumps(
            {
                "status": "ok",
                "service": "query-doctor",
                "probe": probe,
                "raw_output": False,
                "sql_execution": False,
            },
            sort_keys=True,
        )
        + "\n",
    )


def default_batch_query_group(settings: WebSettings) -> str:
    if settings.corpus_summary is not None:
        return "all"
    return "bad"


def route_static_asset_get(path: str) -> WebRouteResponse | None:
    asset = STATIC_ASSETS.get(path)
    if asset is None:
        return None
    filename, content_type = asset
    body = files("query_doctor.web.static").joinpath(filename).read_text(encoding="utf-8")
    return WebRouteResponse(status=200, body=body, content_type=content_type)


def route_owner_raw_source_get(
    path: str,
    settings: WebSettings,
    store: WebJobStore,
) -> WebRouteResponse | None:
    match = owner_raw_source_path_match(path)
    if not match:
        return None
    source = match.group("source")
    case_id = unquote_case_id(match.group("case_id"))
    if source == "running":
        effective_settings, case = resolve_running_case_detail_settings(settings, store, case_id)
        detail_kwargs = running_detail_kwargs()
    else:
        effective_settings, case = resolve_case_detail_settings(settings, store, case_id)
        detail_kwargs = {}
    detail_base_path = detail_kwargs.get("detail_base_path", "/batch/case")
    active_nav = detail_kwargs.get("active_nav", "batch")
    back_href = owner_raw_source_detail_href(case_id, detail_base_path=detail_base_path)
    if case is None:
        decision = OwnerRawSourceDecision(False, OWNER_RAW_SOURCE_REASON_CASE_NOT_FOUND)
        status = 404
        return WebRouteResponse.html(
            status,
            render_owner_raw_source_unavailable_page(
                effective_settings,
                case_id=case_id,
                back_href=back_href,
                decision=decision,
                active_nav=active_nav,
            ),
            audit_event=owner_raw_source_audit_event(
                effective_settings,
                decision,
                route_source=source,
                status=status,
            ),
        )
    case_dir = resolve_batch_case_report_dir(effective_settings, case)
    view_or_decision = build_owner_raw_source_view(
        effective_settings,
        case_id,
        case,
        case_dir,
        back_href=back_href,
    )
    if isinstance(view_or_decision, OwnerRawSourceDecision):
        status = 403
        return WebRouteResponse.html(
            status,
            render_owner_raw_source_unavailable_page(
                effective_settings,
                case_id=case_id,
                back_href=back_href,
                decision=view_or_decision,
                active_nav=active_nav,
            ),
            audit_event=owner_raw_source_audit_event(
                effective_settings,
                view_or_decision,
                route_source=source,
                status=status,
            ),
        )
    status = 200
    decision = OwnerRawSourceDecision(True, view_or_decision.reason_code)
    return WebRouteResponse.html(
        status,
        render_owner_raw_source_page(
            effective_settings,
            view_or_decision,
            active_nav=active_nav,
        ),
        audit_event=owner_raw_source_audit_event(
            effective_settings,
            decision,
            route_source=source,
            status=status,
        ),
    )


def post_route_is_allowed(path: str) -> bool:
    parsed_path = urlparse(path).path
    return (
        parsed_path in STATIC_POST_PATHS
        or parsed_path in PREVIEW_WEB_POST_PATHS
        or JOB_CANCEL_POST_RE.fullmatch(parsed_path) is not None
        or BATCH_CASE_POST_RE.fullmatch(parsed_path) is not None
        or ACTION_OUTCOME_POST_RE.fullmatch(parsed_path) is not None
        or SPECIFIC_QUERY_POST_RE.fullmatch(parsed_path) is not None
    )


def route_batch_detail_get(
    path: str,
    settings: WebSettings,
    store: WebJobStore,
) -> WebRouteResponse | None:
    for prefix, resolver, kwargs_factory in (
        ("/batch", resolve_case_detail_settings, dict),
        ("/running", resolve_running_case_detail_settings, running_detail_kwargs),
    ):
        match = re.fullmatch(
            rf"{prefix}/case/(?P<case_id>[^/]+)(?P<suffix>/report|/report\.md|/python-report|/python-report\.md|/llm-report|/llm-report\.md|/optimized-query)?",
            path,
        )
        if not match:
            continue
        case_id = match.group("case_id")
        effective_settings, case = resolver(settings, store, case_id)
        if case is None:
            return WebRouteResponse.html(
                404, render_batch_case_not_found_page(effective_settings, case_id)
            )
        detail_kwargs = kwargs_factory()
        suffix = match.group("suffix") or ""
        if suffix in {"/report", "/python-report", "/llm-report"}:
            report_variant = report_variant_from_suffix(suffix)
            report = load_batch_case_trusted_report_artifact(
                effective_settings, case_id, case, report_variant=report_variant
            )
            if report is None:
                return WebRouteResponse.html(
                    404,
                    render_batch_case_detail_for_request(
                        effective_settings, case_id, case, store, **detail_kwargs
                    ),
                )
            return WebRouteResponse.html(
                200,
                render_batch_case_report_page(effective_settings, case_id, case, report.text),
            )
        if suffix in {"/report.md", "/python-report.md", "/llm-report.md"}:
            report_variant = report_variant_from_suffix(suffix)
            report = load_batch_case_trusted_report_artifact(
                effective_settings, case_id, case, report_variant=report_variant
            )
            if report is None:
                return WebRouteResponse.html(
                    404,
                    render_batch_case_detail_for_request(
                        effective_settings, case_id, case, store, **detail_kwargs
                    ),
                )
            return WebRouteResponse.markdown_download(report.download_filename, report.text)
        return WebRouteResponse.html(
            200,
            render_batch_case_detail_for_request(
                effective_settings, case_id, case, store, **detail_kwargs
            ),
        )
    return None


def route_workload_detail_get(
    path: str,
    settings: WebSettings,
    store: WebJobStore,
) -> WebRouteResponse | None:
    match = re.fullmatch(r"/(?P<source>batch|running)/workload/(?P<fingerprint>[^/]+)", path)
    if not match:
        return None
    source = match.group("source")
    status, body = render_workload_detail_for_request(
        settings,
        match.group("fingerprint"),
        store,
        source="running" if source == "running" else "batch",
    )
    return WebRouteResponse.html(status, body)


def route_specific_detail_get(
    path: str,
    settings: WebSettings,
    store: WebJobStore,
) -> WebRouteResponse | None:
    match = re.fullmatch(
        r"/query/details/(?P<query_id>[^/]+)(?P<suffix>/report|/report\.md|/python-report|/python-report\.md|/llm-report|/llm-report\.md|/optimized-query)?",
        path,
    )
    if not match:
        return None
    query_id = unquote(match.group("query_id"))
    suffix = match.group("suffix") or ""
    if suffix in {"/report", "/python-report", "/llm-report"}:
        status, body = render_specific_query_report_for_request(
            settings, query_id, report_variant=report_variant_from_suffix(suffix)
        )
    elif suffix in {"/report.md", "/python-report.md", "/llm-report.md"}:
        return route_specific_query_report_markdown(
            settings, query_id, report_variant=report_variant_from_suffix(suffix)
        )
    else:
        status, body = render_specific_query_detail_for_request(settings, query_id, store)
    return WebRouteResponse.html(status, body)


def route_trino_detail_get(
    path: str,
    query_string: str,
    settings: WebSettings,
) -> WebRouteResponse | None:
    match = re.fullmatch(r"/trino/details/(?P<case_id>[^/]+)", path)
    if not match:
        return None
    case_id = unquote(match.group("case_id"))
    query = parse_qs(query_string, keep_blank_values=True)
    if first_form_value(query, "report") == "python":
        if first_form_value(query, "download") == "1":
            try:
                report = load_trino_python_report(settings, case_id)
            except WebError as exc:
                status = 404 if exc.reason_code == "trino.details_not_found" else 400
                return WebRouteResponse.html(
                    status,
                    render_trino_python_report_error_page(settings, exc),
                )
            return WebRouteResponse.markdown_download(report.download_filename, report.text)
        status, body = render_trino_python_report_for_request(settings, case_id)
        return WebRouteResponse.html(status, body)
    if first_form_value(query, "guidance") == "optimizer":
        if first_form_value(query, "download") == "1":
            try:
                guidance = load_trino_optimizer_guidance(settings, case_id)
            except WebError as exc:
                status = 404 if exc.reason_code == "trino.details_not_found" else 400
                return WebRouteResponse.html(
                    status,
                    render_trino_optimizer_guidance_error_page(settings, exc),
                )
            return WebRouteResponse.markdown_download(guidance.download_filename, guidance.text)
        status, body = render_trino_optimizer_guidance_for_request(settings, case_id)
        return WebRouteResponse.html(status, body)
    status, body = render_trino_detail_for_request(settings, case_id)
    return WebRouteResponse.html(status, body)


def report_variant_from_suffix(suffix: str) -> str:
    if suffix.startswith("/llm-report"):
        return REPORT_VARIANT_LLM
    return REPORT_VARIANT_PYTHON


def route_specific_query_report_markdown(
    settings: WebSettings, query_id: str, *, report_variant: str = REPORT_VARIANT_PYTHON
) -> WebRouteResponse:
    try:
        validated_query_id = validate_query_id(query_id)
        case_dir = expected_case_dir_for_query(validated_query_id, settings)
    except WebError as exc:
        return WebRouteResponse.html(400, render_query_page(settings, query_id=query_id, error=exc))
    report = load_specific_query_trusted_report_artifact(
        validated_query_id, case_dir, report_variant=report_variant
    )
    if report is None:
        message = specific_query_report_unavailable_error()
        return WebRouteResponse.html(
            404, render_query_page(settings, query_id=validated_query_id, error=message)
        )
    return WebRouteResponse.markdown_download(report.download_filename, report.text)


def route_job_get(
    path: str,
    query_string: str,
    settings: WebSettings,
    store: WebJobStore,
) -> WebRouteResponse | None:
    match = re.fullmatch(rf"/jobs/(?P<job_id>{WEB_JOB_ID_PATTERN})/status", path)
    if match:
        job = store.get(match.group("job_id"))
        return WebRouteResponse.json(404 if job is None else 200, render_job_status_json(job))
    match = re.fullmatch(rf"/jobs/(?P<job_id>{WEB_JOB_ID_PATTERN})", path)
    if not match:
        return None
    job = store.get(match.group("job_id"))
    if job is None:
        return WebRouteResponse.html(
            404,
            render_batch_page(
                batch_page_settings(settings, store),
                error=job_not_found_error(),
            ),
        )
    query = parse_qs(query_string, keep_blank_values=True)
    if job.kind in {"batch", "trino_recent"}:
        return WebRouteResponse.html(
            200,
            render_batch_page(
                batch_page_settings(settings, store),
                job=job,
                query_group=first_form_value(query, "query_group"),
                only_with_spills=form_flag_enabled(query, "only_with_spills"),
                result_sort=first_form_value(query, "result_sort"),
                results_page=first_form_value(query, "results_page"),
                workload_admin_scope=first_form_value(query, "workload_admin_scope"),
                workload_admin_signal=first_form_value(query, "workload_admin_signal"),
                workload_group_scope=first_form_value(query, "workload_group_scope"),
                workload_group_name=first_form_value(query, "workload_group_name"),
                workload_group_signal=first_form_value(query, "workload_group_signal"),
                inbox_scope_filters=query_inbox_scope_filters_from_mapping(query),
                result_filters=recent_scan_result_filters_from_mapping(query),
            ),
        )
    if job.kind == "running":
        return WebRouteResponse.html(
            200,
            render_running_queries_page(
                running_page_settings(settings, store),
                job=job,
                query_group=first_form_value(query, "query_group"),
                only_with_spills=form_flag_enabled(query, "only_with_spills"),
                result_sort=first_form_value(query, "result_sort"),
                results_page=first_form_value(query, "results_page"),
                workload_admin_scope=first_form_value(query, "workload_admin_scope"),
                workload_admin_signal=first_form_value(query, "workload_admin_signal"),
                workload_group_scope=first_form_value(query, "workload_group_scope"),
                workload_group_name=first_form_value(query, "workload_group_name"),
                workload_group_signal=first_form_value(query, "workload_group_signal"),
                inbox_scope_filters=query_inbox_scope_filters_from_mapping(query),
                result_filters=recent_scan_result_filters_from_mapping(query),
            ),
        )
    if job.kind in {
        "batch_report",
        "batch_llm_report",
        "batch_case_actions",
        "batch_llm_actions",
        "batch_optimized_query",
    }:
        return route_batch_job_detail_get(job, settings, store)
    if job.kind in {
        "query_report",
        "query_llm_report",
        "query_case_actions",
        "query_llm_actions",
        "query_optimized_query",
    }:
        status, body = render_specific_query_detail_for_request(
            settings, job.query_id, store, job=job
        )
        return WebRouteResponse.html(status, body)
    return WebRouteResponse.html(
        200, render_query_page(settings, report_mode=job.report_mode, job=job)
    )


def route_batch_job_detail_get(
    job: WebJobSnapshot,
    settings: WebSettings,
    store: WebJobStore,
) -> WebRouteResponse:
    case_id = job.batch_case_id or job.query_id
    if job.batch_source == "running":
        effective_settings, case = resolve_running_case_detail_settings(settings, store, case_id)
        detail_kwargs = running_detail_kwargs()
    else:
        effective_settings, case = resolve_case_detail_settings(settings, store, case_id)
        detail_kwargs = {}
    if case is None:
        return WebRouteResponse.html(
            404, render_batch_case_not_found_page(effective_settings, case_id)
        )
    return WebRouteResponse.html(
        200,
        render_batch_case_detail_for_request(
            effective_settings, case_id, case, store, job=job, **detail_kwargs
        ),
    )


def route_post_request(
    path: str,
    form: dict[str, list[str]],
    settings: WebSettings,
    store: WebJobStore,
    *,
    analysis_func: AnalysisFunc = run_query_id_analysis,
    runner: Runner = subprocess.run,
) -> WebRouteResponse | None:
    parsed = urlparse(path)
    if settings.public_demo:
        return public_demo_post_blocked_response(settings)
    cancel_match = JOB_CANCEL_POST_RE.fullmatch(parsed.path)
    if cancel_match:
        job_id = cancel_match.group("job_id")
        job = store.request_cancel(job_id)
        if job is None:
            return WebRouteResponse.html(
                404,
                render_batch_page(
                    batch_page_settings(settings, store),
                    error=job_not_found_error(),
                ),
            )
        return WebRouteResponse.redirect(f"/jobs/{job_id}")
    outcome_action = route_action_outcome_post(parsed.path, form, settings, store)
    if outcome_action is not None:
        return outcome_action
    batch_action = route_batch_case_post(parsed.path, form, settings, store, runner=runner)
    if batch_action is not None:
        return batch_action
    query_action = route_specific_query_post(parsed.path, form, settings, store, runner=runner)
    if query_action is not None:
        return query_action
    if parsed.path == "/batch/run":
        if first_form_value(form, "scan_target") == "running":
            status, body = start_running_job(form, settings, store, runner=runner)
        else:
            status, body = start_batch_job(form, settings, store, runner=runner)
    elif parsed.path == "/running/run":
        status, body = start_running_job(form, settings, store, runner=runner)
    elif parsed.path in {"/optimizer", "/query-optimizer"}:
        status, body = handle_optimizer_request(form, settings, runner=runner)
    elif (preview_surface := preview_surface_for_post_path(parsed.path)) is not None:
        status, body = preview_surface.handle_post(form, settings)
    elif parsed.path == "/profile/upload":
        status, body = start_profile_upload_job(form, settings, store, runner=runner)
    elif parsed.path == "/analyze":
        status, body = start_analyze_job(form, settings, store, analysis_func=analysis_func)
    else:
        return None
    return WebRouteResponse.redirect(body) if status == 303 else WebRouteResponse.html(status, body)


def public_demo_post_blocked_response(settings: WebSettings) -> WebRouteResponse:
    error = WebError(
        "Public demo is read-only. Collection, report generation, optimizer actions, "
        "uploads, cancellations, and feedback writes are disabled for the hosted synthetic demo.",
        title="Public demo is read-only",
        reason_code="web.public_demo_read_only",
        stage="Checking public demo request",
        next_step="Use the synthetic demo pages without submitting write actions.",
    )
    return WebRouteResponse.html(
        403,
        render_page(settings, active_nav="batch", show_run_panel=False, error=error),
    )


def job_not_found_error() -> WebError:
    return WebError(
        "Analysis job was not found.",
        title="Job was not found",
        reason_code="job.not_found",
        stage="Checking analysis job",
        next_step="Start a new analysis job from the Query Inbox page.",
    )


def route_action_outcome_post(
    path: str,
    form: dict[str, list[str]],
    settings: WebSettings,
    store: WebJobStore,
) -> WebRouteResponse | None:
    match = ACTION_OUTCOME_POST_RE.fullmatch(path)
    if not match:
        return None
    source = "running" if match.group("source") == "running" else "batch"
    case_id = match.group("case_id")
    if source == "running":
        effective_settings, case = resolve_running_case_detail_settings(settings, store, case_id)
    else:
        effective_settings, case = resolve_case_detail_settings(settings, store, case_id)
    if case is None:
        return WebRouteResponse.html(
            404, render_batch_case_not_found_page(effective_settings, case_id)
        )
    try:
        record = action_outcome_record_from_case(
            case_id=case_id,
            case=case,
            recommendation_id=match.group("recommendation_id"),
            form=form,
        )
        append_action_outcome(record)
    except (OSError, WebError) as exc:
        safe_error = (
            WebError(
                "Action outcome could not be saved.",
                title="Outcome save failed",
                reason_code="web.action_outcome_save_failed",
                stage="Saving recommendation outcome",
                next_step="Check local write permissions for the outcome store and retry.",
            )
            if isinstance(exc, OSError)
            else exc
        )
        return WebRouteResponse.html(
            400,
            render_batch_page(
                batch_page_settings(effective_settings, store),
                error=safe_error,
            ),
        )
    return WebRouteResponse.redirect(f"/{source}/case/{case_id}#findings")


def route_batch_case_post(
    path: str,
    form: dict[str, list[str]],
    settings: WebSettings,
    store: WebJobStore,
    *,
    runner: Runner = subprocess.run,
) -> WebRouteResponse | None:
    match = BATCH_CASE_POST_RE.fullmatch(path)
    if not match:
        return None
    source = "running" if match.group("source") == "running" else "batch"
    case_id = match.group("case_id")
    action = match.group("action")
    if action in {"report", "python-report"}:
        status, body = start_batch_case_report_job(
            case_id,
            settings,
            store,
            runner=runner,
            source=source,
            report_variant=REPORT_VARIANT_PYTHON,
        )
    elif action == "llm-report":
        status, body = start_batch_case_report_job(
            case_id,
            settings,
            store,
            runner=runner,
            source=source,
            report_variant=REPORT_VARIANT_LLM,
        )
    elif action == "optimized-query":
        status, body = start_batch_case_optimized_query_job(
            case_id, settings, store, runner=runner, source=source
        )
    elif action == "validate-rewrite":
        status, body = handle_batch_case_external_rewrite_validation(
            case_id, settings, store, form, source=source
        )
    else:
        status, body = start_batch_case_llm_actions_job(
            case_id, settings, store, runner=runner, source=source
        )
    return WebRouteResponse.redirect(body) if status == 303 else WebRouteResponse.html(status, body)


def route_specific_query_post(
    path: str,
    form: dict[str, list[str]],
    settings: WebSettings,
    store: WebJobStore,
    *,
    runner: Runner = subprocess.run,
) -> WebRouteResponse | None:
    match = SPECIFIC_QUERY_POST_RE.fullmatch(path)
    if not match:
        return None
    query_id = unquote(match.group("query_id"))
    action = match.group("action")
    if action in {"report", "python-report"}:
        status, body = start_specific_query_report_job(
            query_id,
            settings,
            store,
            runner=runner,
            report_variant=REPORT_VARIANT_PYTHON,
        )
    elif action == "llm-report":
        status, body = start_specific_query_report_job(
            query_id,
            settings,
            store,
            runner=runner,
            report_variant=REPORT_VARIANT_LLM,
        )
    elif action == "optimized-query":
        status, body = start_specific_query_optimized_query_job(
            query_id, settings, store, runner=runner
        )
    elif action == "validate-rewrite":
        status, body = handle_specific_query_external_rewrite_validation(
            query_id, settings, store, form
        )
    else:
        status, body = start_specific_query_llm_actions_job(
            query_id, settings, store, runner=runner
        )
    return WebRouteResponse.redirect(body) if status == 303 else WebRouteResponse.html(status, body)
