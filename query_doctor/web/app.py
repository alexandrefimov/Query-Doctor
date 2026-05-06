"""HTTP handler factory for the local Query Doctor web UI."""

from __future__ import annotations

import re
import subprocess
import sys
from http.server import BaseHTTPRequestHandler
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
from query_doctor.web.models import WebError, WebSettings
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
    render_page,
    render_query_page,
    render_readme_page,
)
from query_doctor.web.ui.running import render_running_queries_page


MAX_WEB_POST_BODY_BYTES = 320 * 1024
AnalysisFunc = Callable[[str, str, bool, WebSettings], object]


def make_handler(
    settings: WebSettings,
    analysis_func: AnalysisFunc = run_query_id_analysis,
    job_store: WebJobStore | None = None,
    runner: Runner = subprocess.run,
) -> type[BaseHTTPRequestHandler]:
    store = job_store or WebJobStore()

    class QueryDoctorWebHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in {"/", "/index.html", "/batch"}:
                query = parse_qs(parsed.query, keep_blank_values=True)
                self.write_html(
                    200,
                    render_batch_page(
                        batch_page_settings(settings, store),
                        query_group=first_form_value(query, "query_group"),
                        only_with_spills=form_flag_enabled(query, "only_with_spills"),
                    ),
                )
                return
            match = re.fullmatch(r"/batch/case/(?P<case_id>[^/]+)/report", parsed.path)
            if match:
                case_id = match.group("case_id")
                effective_settings, case = resolve_case_detail_settings(settings, store, case_id)
                if case is None:
                    self.write_html(404, render_batch_case_not_found_page(effective_settings, case_id))
                    return
                report_text = load_validated_batch_case_report(effective_settings, case)
                if report_text is None:
                    self.write_html(404, render_batch_case_detail_for_request(effective_settings, case_id, case, store))
                    return
                self.write_html(200, render_batch_case_report_page(effective_settings, case_id, case, report_text))
                return
            match = re.fullmatch(r"/batch/case/(?P<case_id>[^/]+)/optimized-query", parsed.path)
            if match:
                case_id = match.group("case_id")
                effective_settings, case = resolve_case_detail_settings(settings, store, case_id)
                if case is None:
                    self.write_html(404, render_batch_case_not_found_page(effective_settings, case_id))
                    return
                self.write_html(200, render_batch_case_detail_for_request(effective_settings, case_id, case, store))
                return
            match = re.fullmatch(r"/batch/case/(?P<case_id>[^/]+)", parsed.path)
            if match:
                case_id = match.group("case_id")
                effective_settings, case = resolve_case_detail_settings(settings, store, case_id)
                if case is None:
                    self.write_html(404, render_batch_case_not_found_page(effective_settings, case_id))
                    return
                self.write_html(200, render_batch_case_detail_for_request(effective_settings, case_id, case, store))
                return
            match = re.fullmatch(r"/running/case/(?P<case_id>[^/]+)/report", parsed.path)
            if match:
                case_id = match.group("case_id")
                effective_settings, case = resolve_running_case_detail_settings(settings, store, case_id)
                if case is None:
                    self.write_html(404, render_batch_case_not_found_page(effective_settings, case_id))
                    return
                report_text = load_validated_batch_case_report(effective_settings, case)
                if report_text is None:
                    self.write_html(404, render_batch_case_detail_for_request(effective_settings, case_id, case, store, **running_detail_kwargs()))
                    return
                self.write_html(200, render_batch_case_report_page(effective_settings, case_id, case, report_text))
                return
            match = re.fullmatch(r"/running/case/(?P<case_id>[^/]+)/optimized-query", parsed.path)
            if match:
                case_id = match.group("case_id")
                effective_settings, case = resolve_running_case_detail_settings(settings, store, case_id)
                if case is None:
                    self.write_html(404, render_batch_case_not_found_page(effective_settings, case_id))
                    return
                self.write_html(200, render_batch_case_detail_for_request(effective_settings, case_id, case, store, **running_detail_kwargs()))
                return
            match = re.fullmatch(r"/running/case/(?P<case_id>[^/]+)", parsed.path)
            if match:
                case_id = match.group("case_id")
                effective_settings, case = resolve_running_case_detail_settings(settings, store, case_id)
                if case is None:
                    self.write_html(404, render_batch_case_not_found_page(effective_settings, case_id))
                    return
                self.write_html(200, render_batch_case_detail_for_request(effective_settings, case_id, case, store, **running_detail_kwargs()))
                return
            match = re.fullmatch(r"/query/details/(?P<query_id>[^/]+)/report", parsed.path)
            if match:
                status, body = render_specific_query_report_for_request(settings, unquote(match.group("query_id")))
                self.write_html(status, body)
                return
            match = re.fullmatch(r"/query/details/(?P<query_id>[^/]+)/optimized-query", parsed.path)
            if match:
                status, body = render_specific_query_detail_for_request(settings, unquote(match.group("query_id")), store)
                self.write_html(status, body)
                return
            match = re.fullmatch(r"/query/details/(?P<query_id>[^/]+)", parsed.path)
            if match:
                status, body = render_specific_query_detail_for_request(settings, unquote(match.group("query_id")), store)
                self.write_html(status, body)
                return
            if parsed.path in {"/query", "/run"}:
                self.write_html(200, render_query_page(settings))
                return
            if parsed.path in {"/optimizer", "/query-optimizer"}:
                self.write_html(200, render_optimizer_page(settings))
                return
            if parsed.path in {"/running", "/running-queries"}:
                query = parse_qs(parsed.query, keep_blank_values=True)
                self.write_html(
                    200,
                    render_running_queries_page(
                        running_page_settings(settings, store),
                        query_group=first_form_value(query, "query_group"),
                        only_with_spills=form_flag_enabled(query, "only_with_spills"),
                    ),
                )
                return
            if parsed.path == "/help":
                self.write_html(200, render_help_page(settings))
                return
            if parsed.path in {"/demo", "/demo-guide"}:
                self.write_html(200, render_demo_guide_page(settings))
                return
            if parsed.path == "/readme":
                self.write_html(200, render_readme_page(settings))
                return
            match = re.fullmatch(r"/jobs/(?P<job_id>[0-9a-f]{32})", parsed.path)
            if match:
                job = store.get(match.group("job_id"))
                if job is None:
                    self.write_html(
                        404,
                        render_batch_page(
                            batch_page_settings(settings, store),
                            error="Analysis job was not found.",
                        ),
                    )
                    return
                if job.kind == "batch":
                    query = parse_qs(parsed.query, keep_blank_values=True)
                    self.write_html(
                        200,
                        render_batch_page(
                            batch_page_settings(settings, store),
                            job=job,
                            query_group=first_form_value(query, "query_group"),
                            only_with_spills=form_flag_enabled(query, "only_with_spills"),
                        ),
                    )
                elif job.kind == "running":
                    query = parse_qs(parsed.query, keep_blank_values=True)
                    self.write_html(
                        200,
                        render_running_queries_page(
                            running_page_settings(settings, store),
                            job=job,
                            query_group=first_form_value(query, "query_group"),
                            only_with_spills=form_flag_enabled(query, "only_with_spills"),
                        ),
                    )
                elif job.kind in {"batch_report", "batch_llm_actions"}:
                    case_id = job.batch_case_id or job.query_id
                    if job.batch_source == "running":
                        effective_settings, case = resolve_running_case_detail_settings(settings, store, case_id)
                        detail_kwargs = running_detail_kwargs()
                    else:
                        effective_settings, case = resolve_case_detail_settings(settings, store, case_id)
                        detail_kwargs = {}
                    if case is None:
                        self.write_html(404, render_batch_case_not_found_page(effective_settings, case_id))
                        return
                    self.write_html(200, render_batch_case_detail_for_request(effective_settings, case_id, case, store, job=job, **detail_kwargs))
                elif job.kind in {"query_report", "query_llm_actions"}:
                    status, body = render_specific_query_detail_for_request(settings, job.query_id, store, job=job)
                    self.write_html(status, body)
                elif job.kind == "batch_optimized_query":
                    case_id = job.batch_case_id or job.query_id
                    if job.batch_source == "running":
                        effective_settings, case = resolve_running_case_detail_settings(settings, store, case_id)
                        detail_kwargs = running_detail_kwargs()
                    else:
                        effective_settings, case = resolve_case_detail_settings(settings, store, case_id)
                        detail_kwargs = {}
                    if case is None:
                        self.write_html(404, render_batch_case_not_found_page(effective_settings, case_id))
                        return
                    self.write_html(200, render_batch_case_detail_for_request(effective_settings, case_id, case, store, job=job, **detail_kwargs))
                elif job.kind == "query_optimized_query":
                    status, body = render_specific_query_detail_for_request(settings, job.query_id, store, job=job)
                    self.write_html(status, body)
                else:
                    self.write_html(200, render_query_page(settings, report_mode=job.report_mode, job=job))
                return
            match = re.fullmatch(r"/jobs/(?P<job_id>[0-9a-f]{32})/status", parsed.path)
            if match:
                job = store.get(match.group("job_id"))
                if job is None:
                    self.write_json(404, render_job_status_json(None))
                    return
                self.write_json(200, render_job_status_json(job))
                return
            self.send_error(404)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            report_match = re.fullmatch(r"/batch/case/(?P<case_id>[^/]+)/report", parsed.path)
            optimized_query_match = re.fullmatch(r"/batch/case/(?P<case_id>[^/]+)/optimized-query", parsed.path)
            validate_rewrite_match = re.fullmatch(r"/batch/case/(?P<case_id>[^/]+)/validate-rewrite", parsed.path)
            llm_actions_match = re.fullmatch(r"/batch/case/(?P<case_id>[^/]+)/llm-actions", parsed.path)
            running_report_match = re.fullmatch(r"/running/case/(?P<case_id>[^/]+)/report", parsed.path)
            running_optimized_query_match = re.fullmatch(r"/running/case/(?P<case_id>[^/]+)/optimized-query", parsed.path)
            running_validate_rewrite_match = re.fullmatch(r"/running/case/(?P<case_id>[^/]+)/validate-rewrite", parsed.path)
            running_llm_actions_match = re.fullmatch(r"/running/case/(?P<case_id>[^/]+)/llm-actions", parsed.path)
            query_report_match = re.fullmatch(r"/query/details/(?P<query_id>[^/]+)/report", parsed.path)
            query_optimized_query_match = re.fullmatch(r"/query/details/(?P<query_id>[^/]+)/optimized-query", parsed.path)
            query_validate_rewrite_match = re.fullmatch(r"/query/details/(?P<query_id>[^/]+)/validate-rewrite", parsed.path)
            query_llm_actions_match = re.fullmatch(r"/query/details/(?P<query_id>[^/]+)/llm-actions", parsed.path)
            if (
                parsed.path not in {"/analyze", "/batch/run", "/running/run", "/optimizer", "/query-optimizer"}
                and report_match is None
                and optimized_query_match is None
                and validate_rewrite_match is None
                and llm_actions_match is None
                and running_report_match is None
                and running_optimized_query_match is None
                and running_validate_rewrite_match is None
                and running_llm_actions_match is None
                and query_report_match is None
                and query_optimized_query_match is None
                and query_validate_rewrite_match is None
                and query_llm_actions_match is None
            ):
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw_body = self.rfile.read(min(length, MAX_WEB_POST_BODY_BYTES + 1)).decode("utf-8", errors="replace")
            if length > MAX_WEB_POST_BODY_BYTES:
                self.write_html(413, render_page(settings, active_nav="batch", error=WebError("Submitted form exceeds the bounded web input limit.")))
                return
            form = parse_qs(raw_body, keep_blank_values=True)
            if report_match is not None:
                status, body = start_batch_case_report_job(report_match.group("case_id"), settings, store, runner=runner)
            elif optimized_query_match is not None:
                status, body = start_batch_case_optimized_query_job(optimized_query_match.group("case_id"), settings, store, runner=runner)
            elif validate_rewrite_match is not None:
                status, body = handle_batch_case_external_rewrite_validation(
                    validate_rewrite_match.group("case_id"),
                    settings,
                    store,
                    form,
                )
            elif llm_actions_match is not None:
                status, body = start_batch_case_llm_actions_job(llm_actions_match.group("case_id"), settings, store, runner=runner)
            elif running_report_match is not None:
                status, body = start_batch_case_report_job(
                    running_report_match.group("case_id"),
                    settings,
                    store,
                    runner=runner,
                    source="running",
                )
            elif running_optimized_query_match is not None:
                status, body = start_batch_case_optimized_query_job(
                    running_optimized_query_match.group("case_id"),
                    settings,
                    store,
                    runner=runner,
                    source="running",
                )
            elif running_validate_rewrite_match is not None:
                status, body = handle_batch_case_external_rewrite_validation(
                    running_validate_rewrite_match.group("case_id"),
                    settings,
                    store,
                    form,
                    source="running",
                )
            elif running_llm_actions_match is not None:
                status, body = start_batch_case_llm_actions_job(
                    running_llm_actions_match.group("case_id"),
                    settings,
                    store,
                    runner=runner,
                    source="running",
                )
            elif query_report_match is not None:
                status, body = start_specific_query_report_job(
                    unquote(query_report_match.group("query_id")),
                    settings,
                    store,
                    runner=runner,
                )
            elif query_optimized_query_match is not None:
                status, body = start_specific_query_optimized_query_job(
                    unquote(query_optimized_query_match.group("query_id")),
                    settings,
                    store,
                    runner=runner,
                )
            elif query_validate_rewrite_match is not None:
                status, body = handle_specific_query_external_rewrite_validation(
                    unquote(query_validate_rewrite_match.group("query_id")),
                    settings,
                    store,
                    form,
                )
            elif query_llm_actions_match is not None:
                status, body = start_specific_query_llm_actions_job(
                    unquote(query_llm_actions_match.group("query_id")),
                    settings,
                    store,
                    runner=runner,
                )
            elif parsed.path == "/batch/run":
                status, body = start_batch_job(form, settings, store, runner=runner)
            elif parsed.path == "/running/run":
                status, body = start_running_job(form, settings, store, runner=runner)
            elif parsed.path in {"/optimizer", "/query-optimizer"}:
                status, body = handle_optimizer_request(form, settings, runner=runner)
            else:
                status, body = start_analyze_job(form, settings, store, analysis_func=analysis_func)
            if status == 303:
                self.send_response(303)
                self.send_header("Location", body)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            self.write_html(status, body)

        def write_html(self, status: int, body: str) -> None:
            payload = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def write_json(self, status: int, body: str) -> None:
            payload = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, fmt: str, *args: object) -> None:
            print(f"[Query Doctor web] {self.address_string()} {fmt % args}", file=sys.stderr)

    return QueryDoctorWebHandler
