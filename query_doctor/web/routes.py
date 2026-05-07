"""HTTP-route response construction for the local web UI."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from typing import Callable
from urllib.parse import parse_qs, unquote, urlparse

from query_doctor.web.batch_case_actions import (
    handle_batch_case_external_rewrite_validation,
    start_batch_case_llm_actions_job,
    start_batch_case_optimized_query_job,
    start_batch_case_report_job,
)
from query_doctor.web.batch_case_pages import render_batch_case_detail_for_request
from query_doctor.web.batch_jobs import start_batch_job, start_running_job
from query_doctor.web.case_detail_context import (
    batch_page_settings,
    resolve_case_detail_settings,
    resolve_running_case_detail_settings,
    running_detail_kwargs,
    running_page_settings,
)
from query_doctor.web.form_helpers import first_form_value, form_flag_enabled
from query_doctor.web.jobs import WebJobStore, render_job_status_json
from query_doctor.web.models import WebJobSnapshot, WebSettings
from query_doctor.web.query_analysis import run_query_id_analysis
from query_doctor.web.request_handlers import handle_optimizer_request, start_analyze_job
from query_doctor.web.specific_query_actions import (
    handle_specific_query_external_rewrite_validation,
    start_specific_query_llm_actions_job,
    start_specific_query_optimized_query_job,
    start_specific_query_report_job,
)
from query_doctor.web.specific_query_pages import (
    render_specific_query_detail_for_request,
    render_specific_query_report_for_request,
)
from query_doctor.web.subprocesses import Runner
from query_doctor.web.trusted_artifacts import load_validated_batch_case_report
from query_doctor.web.ui.help import render_demo_guide_page, render_help_page
from query_doctor.web.ui.optimizer import render_optimizer_page
from query_doctor.web.ui.pages import (
    render_batch_case_not_found_page,
    render_batch_case_report_page,
    render_batch_page,
    render_query_page,
    render_readme_page,
)
from query_doctor.web.ui.running import render_running_queries_page


AnalysisFunc = Callable[[str, str, bool, WebSettings], object]

STATIC_POST_PATHS = {"/analyze", "/batch/run", "/running/run", "/optimizer", "/query-optimizer"}
BATCH_CASE_POST_RE = re.compile(
    r"/(?P<source>batch|running)/case/(?P<case_id>[^/]+)/(?P<action>report|optimized-query|validate-rewrite|llm-actions)"
)
SPECIFIC_QUERY_POST_RE = re.compile(
    r"/query/details/(?P<query_id>[^/]+)/(?P<action>report|optimized-query|validate-rewrite|llm-actions)"
)


@dataclass(frozen=True)
class WebRouteResponse:
    status: int
    body: str
    content_type: str = "text/html; charset=utf-8"
    location: str | None = None

    @classmethod
    def html(cls, status: int, body: str) -> "WebRouteResponse":
        return cls(status=status, body=body)

    @classmethod
    def json(cls, status: int, body: str) -> "WebRouteResponse":
        return cls(status=status, body=body, content_type="application/json; charset=utf-8")

    @classmethod
    def redirect(cls, location: str) -> "WebRouteResponse":
        return cls(status=303, body="", location=location)


def route_get_request(
    path: str,
    settings: WebSettings,
    store: WebJobStore,
) -> WebRouteResponse | None:
    parsed = urlparse(path)
    if parsed.path in {"/", "/index.html", "/batch"}:
        query = parse_qs(parsed.query, keep_blank_values=True)
        return WebRouteResponse.html(
            200,
            render_batch_page(
                batch_page_settings(settings, store),
                query_group=first_form_value(query, "query_group"),
                only_with_spills=form_flag_enabled(query, "only_with_spills"),
            ),
        )
    batch_detail = route_batch_detail_get(parsed.path, settings, store)
    if batch_detail is not None:
        return batch_detail
    specific_detail = route_specific_detail_get(parsed.path, settings, store)
    if specific_detail is not None:
        return specific_detail
    if parsed.path in {"/query", "/run"}:
        return WebRouteResponse.html(200, render_query_page(settings))
    if parsed.path in {"/optimizer", "/query-optimizer"}:
        return WebRouteResponse.html(200, render_optimizer_page(settings))
    if parsed.path in {"/running", "/running-queries"}:
        query = parse_qs(parsed.query, keep_blank_values=True)
        return WebRouteResponse.html(
            200,
            render_running_queries_page(
                running_page_settings(settings, store),
                query_group=first_form_value(query, "query_group"),
                only_with_spills=form_flag_enabled(query, "only_with_spills"),
            ),
        )
    if parsed.path == "/help":
        return WebRouteResponse.html(200, render_help_page(settings))
    if parsed.path in {"/demo", "/demo-guide"}:
        return WebRouteResponse.html(200, render_demo_guide_page(settings))
    if parsed.path == "/readme":
        return WebRouteResponse.html(200, render_readme_page(settings))
    job_response = route_job_get(parsed.path, parsed.query, settings, store)
    if job_response is not None:
        return job_response
    return None


def post_route_is_allowed(path: str) -> bool:
    parsed_path = urlparse(path).path
    return (
        parsed_path in STATIC_POST_PATHS
        or BATCH_CASE_POST_RE.fullmatch(parsed_path) is not None
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
        match = re.fullmatch(rf"{prefix}/case/(?P<case_id>[^/]+)(?P<suffix>/report|/optimized-query)?", path)
        if not match:
            continue
        case_id = match.group("case_id")
        effective_settings, case = resolver(settings, store, case_id)
        if case is None:
            return WebRouteResponse.html(404, render_batch_case_not_found_page(effective_settings, case_id))
        detail_kwargs = kwargs_factory()
        suffix = match.group("suffix") or ""
        if suffix == "/report":
            report_text = load_validated_batch_case_report(effective_settings, case)
            if report_text is None:
                return WebRouteResponse.html(
                    404,
                    render_batch_case_detail_for_request(effective_settings, case_id, case, store, **detail_kwargs),
                )
            return WebRouteResponse.html(
                200,
                render_batch_case_report_page(effective_settings, case_id, case, report_text),
            )
        return WebRouteResponse.html(
            200,
            render_batch_case_detail_for_request(effective_settings, case_id, case, store, **detail_kwargs),
        )
    return None


def route_specific_detail_get(
    path: str,
    settings: WebSettings,
    store: WebJobStore,
) -> WebRouteResponse | None:
    match = re.fullmatch(r"/query/details/(?P<query_id>[^/]+)(?P<suffix>/report|/optimized-query)?", path)
    if not match:
        return None
    query_id = unquote(match.group("query_id"))
    if match.group("suffix") == "/report":
        status, body = render_specific_query_report_for_request(settings, query_id)
    else:
        status, body = render_specific_query_detail_for_request(settings, query_id, store)
    return WebRouteResponse.html(status, body)


def route_job_get(
    path: str,
    query_string: str,
    settings: WebSettings,
    store: WebJobStore,
) -> WebRouteResponse | None:
    match = re.fullmatch(r"/jobs/(?P<job_id>[0-9a-f]{32})/status", path)
    if match:
        job = store.get(match.group("job_id"))
        return WebRouteResponse.json(404 if job is None else 200, render_job_status_json(job))
    match = re.fullmatch(r"/jobs/(?P<job_id>[0-9a-f]{32})", path)
    if not match:
        return None
    job = store.get(match.group("job_id"))
    if job is None:
        return WebRouteResponse.html(
            404,
            render_batch_page(
                batch_page_settings(settings, store),
                error="Analysis job was not found.",
            ),
        )
    query = parse_qs(query_string, keep_blank_values=True)
    if job.kind == "batch":
        return WebRouteResponse.html(
            200,
            render_batch_page(
                batch_page_settings(settings, store),
                job=job,
                query_group=first_form_value(query, "query_group"),
                only_with_spills=form_flag_enabled(query, "only_with_spills"),
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
            ),
        )
    if job.kind in {"batch_report", "batch_llm_actions", "batch_optimized_query"}:
        return route_batch_job_detail_get(job, settings, store)
    if job.kind in {"query_report", "query_llm_actions", "query_optimized_query"}:
        status, body = render_specific_query_detail_for_request(settings, job.query_id, store, job=job)
        return WebRouteResponse.html(status, body)
    return WebRouteResponse.html(200, render_query_page(settings, report_mode=job.report_mode, job=job))


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
        return WebRouteResponse.html(404, render_batch_case_not_found_page(effective_settings, case_id))
    return WebRouteResponse.html(
        200,
        render_batch_case_detail_for_request(effective_settings, case_id, case, store, job=job, **detail_kwargs),
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
    elif parsed.path == "/analyze":
        status, body = start_analyze_job(form, settings, store, analysis_func=analysis_func)
    else:
        return None
    return WebRouteResponse.redirect(body) if status == 303 else WebRouteResponse.html(status, body)


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
    if action == "report":
        status, body = start_batch_case_report_job(case_id, settings, store, runner=runner, source=source)
    elif action == "optimized-query":
        status, body = start_batch_case_optimized_query_job(case_id, settings, store, runner=runner, source=source)
    elif action == "validate-rewrite":
        status, body = handle_batch_case_external_rewrite_validation(case_id, settings, store, form, source=source)
    else:
        status, body = start_batch_case_llm_actions_job(case_id, settings, store, runner=runner, source=source)
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
    if action == "report":
        status, body = start_specific_query_report_job(query_id, settings, store, runner=runner)
    elif action == "optimized-query":
        status, body = start_specific_query_optimized_query_job(query_id, settings, store, runner=runner)
    elif action == "validate-rewrite":
        status, body = handle_specific_query_external_rewrite_validation(query_id, settings, store, form)
    else:
        status, body = start_specific_query_llm_actions_job(query_id, settings, store, runner=runner)
    return WebRouteResponse.redirect(body) if status == 303 else WebRouteResponse.html(status, body)
