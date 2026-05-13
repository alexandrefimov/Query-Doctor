"""Shared web server models and defaults."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from query_doctor.cli.collect_cm_profiles import DEFAULT_CM_METRICS_PROFILE
from query_doctor.optimizer.defaults import DEFAULT_OPTIMIZER_MODEL
from query_doctor.prometheus.timeseries import (
    DEFAULT_PROMETHEUS_METRICS_PROFILE,
    DEFAULT_PROMETHEUS_STEP_SEC,
    DEFAULT_PROMETHEUS_TIMESERIES_PADDING_SEC,
)


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_TIMEOUT_SEC = 1800
DEFAULT_MODEL = "qwen3-coder:30b-a3b-q8_0"
DEFAULT_CORPUS_DIR = Path("cases/cm-corpus")
DEFAULT_QUERY_PROFILE_SOURCE = "cm"
DEFAULT_IMPALA_PROFILE_PORT = 25000
DEFAULT_IMPALA_PROFILE_SCHEME = "http"
DEFAULT_IMPALA_PROFILE_TIMEOUT_SEC = 15
DEFAULT_METADATA_AUTH = "kerberos"
DEFAULT_METADATA_PROTOCOL = "beeswax"
DEFAULT_METADATA_TIMEOUT_SEC = 30
BATCH_CM_INSPECT_LIMIT_MAX = 5000
WEB_BATCH_METADATA_TOP_LIMIT_DEFAULT = 70
WEB_CM_TIMESERIES_TOP_LIMIT_DEFAULT = 10
WEB_CM_EVENTS_MAX_EVENTS_DEFAULT = 50

_REPO_ROOT = Path(__file__).resolve().parents[2]


def batch_output_dir(job_id: str) -> Path:
    return Path("/tmp") / f"query-doctor-web-batch-{job_id}"


def batch_progress_path(job_id: str) -> Path:
    return batch_output_dir(job_id) / "progress.jsonl"


class WebError(RuntimeError):
    """User-facing web error that must not contain secrets or raw profiles."""


@dataclass(frozen=True)
class WebClusterConfig:
    key: str
    label: str
    cm_url: str | None = None
    cm_cluster: str | None = None
    cm_service: str | None = None
    cm_username: str | None = None
    ca_bundle: str | None = None
    insecure_skip_verify: bool = False
    cm_metrics_profile: str = DEFAULT_CM_METRICS_PROFILE
    query_profile_source: str = DEFAULT_QUERY_PROFILE_SOURCE
    impala_profile_hosts: tuple[str, ...] = ()
    impala_profile_port: int = DEFAULT_IMPALA_PROFILE_PORT
    impala_profile_scheme: str = DEFAULT_IMPALA_PROFILE_SCHEME
    impala_profile_timeout_sec: int = DEFAULT_IMPALA_PROFILE_TIMEOUT_SEC
    collect_prometheus_timeseries: bool = False
    prometheus_url: str | None = None
    prometheus_metrics_profile: str = DEFAULT_PROMETHEUS_METRICS_PROFILE
    prometheus_step_sec: int = DEFAULT_PROMETHEUS_STEP_SEC
    prometheus_timeseries_padding_sec: int = DEFAULT_PROMETHEUS_TIMESERIES_PADDING_SEC
    metadata_coordinator: str | None = None
    metadata_impala_shell: str | None = None
    metadata_auth: str = DEFAULT_METADATA_AUTH
    metadata_protocol: str = DEFAULT_METADATA_PROTOCOL
    metadata_kerberos_service_name: str | None = None
    metadata_ssl: bool = False
    metadata_ca_cert: str | None = None
    metadata_timeout_sec: int = DEFAULT_METADATA_TIMEOUT_SEC
    metadata_max_tables: int | None = None
    metadata_max_output_bytes: int | None = None
    metadata_redact: bool = True
    privacy_mode: bool = True
    redact_identifiers: bool = True
    redact_hosts: bool = True
    krb5ccname: str | None = None


@dataclass(frozen=True)
class WebSettings:
    config: Path
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    allow_nonlocal_web_bind: bool = False
    cm_url: str | None = None
    cm_cluster: str | None = None
    cm_service: str | None = None
    cm_username: str | None = None
    ca_bundle: str | None = None
    insecure_skip_verify: bool = False
    cm_metrics_profile: str = DEFAULT_CM_METRICS_PROFILE
    clusters: tuple[WebClusterConfig, ...] = ()
    active_cluster_key: str | None = None
    max_profile_bytes: int | None = None
    model: str = DEFAULT_MODEL
    optimizer_model: str | None = DEFAULT_OPTIMIZER_MODEL
    no_llm: bool = False
    privacy_mode: bool = True
    redact_identifiers: bool = True
    redact_hosts: bool = True
    timeout_sec: int = DEFAULT_TIMEOUT_SEC
    repo_dir: Path = _REPO_ROOT
    corpus_dir: Path = DEFAULT_CORPUS_DIR
    batch_summary: Path | None = None
    query_profile_source: str = DEFAULT_QUERY_PROFILE_SOURCE
    impala_profile_hosts: tuple[str, ...] = ()
    impala_profile_port: int = DEFAULT_IMPALA_PROFILE_PORT
    impala_profile_scheme: str = DEFAULT_IMPALA_PROFILE_SCHEME
    impala_profile_timeout_sec: int = DEFAULT_IMPALA_PROFILE_TIMEOUT_SEC
    collect_prometheus_timeseries: bool = False
    prometheus_url: str | None = None
    prometheus_metrics_profile: str = DEFAULT_PROMETHEUS_METRICS_PROFILE
    prometheus_step_sec: int = DEFAULT_PROMETHEUS_STEP_SEC
    prometheus_timeseries_padding_sec: int = DEFAULT_PROMETHEUS_TIMESERIES_PADDING_SEC
    metadata_coordinator: str | None = None
    metadata_impala_shell: str | None = None
    metadata_auth: str = DEFAULT_METADATA_AUTH
    metadata_protocol: str = DEFAULT_METADATA_PROTOCOL
    metadata_kerberos_service_name: str | None = None
    metadata_ssl: bool = False
    metadata_ca_cert: str | None = None
    metadata_timeout_sec: int = DEFAULT_METADATA_TIMEOUT_SEC
    metadata_max_tables: int | None = None
    metadata_max_output_bytes: int | None = None
    metadata_redact: bool = True
    krb5ccname: str | None = None


@dataclass(frozen=True)
class WebResult:
    query_id: str
    case_dir: Path
    case_source: str
    report_mode: str
    parsed_operators: str
    cardinality_anomalies: str
    memory_anomalies: str
    report_text: str
    report_retry: bool = False


@dataclass(frozen=True)
class WebQueryAnalysisResult:
    query_id: str
    case: dict[str, object]


@dataclass(frozen=True)
class BatchRunConfig:
    recent_window_minutes: int = 30
    scan_date: str = ""
    scan_hour: int = 0
    cluster_key: str = ""
    from_time: str | None = None
    to_time: str | None = None
    cm_inspect_limit: int = BATCH_CM_INSPECT_LIMIT_MAX
    triage_profile_limit: int = BATCH_CM_INSPECT_LIMIT_MAX
    metadata_top_limit: int = WEB_BATCH_METADATA_TOP_LIMIT_DEFAULT
    min_duration_sec: float | None = None
    max_duration_sec: float | None = None
    order: str = "duration-desc"
    parallelism: int = 50
    cm_jobs: int = 50
    jobs: int = 50
    metadata_jobs: int = 5
    user: str = ""
    pool: str = ""
    query_type: str = ""
    include_failed: bool = True
    include_running: bool = False
    only_running: bool = False
    collect_cm_events: bool = True
    cm_events_max_events: int = WEB_CM_EVENTS_MAX_EVENTS_DEFAULT
    collect_cm_timeseries: bool = True
    cm_metrics_profile: str = DEFAULT_CM_METRICS_PROFILE
    cm_timeseries_top_limit: int = WEB_CM_TIMESERIES_TOP_LIMIT_DEFAULT


@dataclass(frozen=True)
class WebJobSnapshot:
    job_id: str
    query_id: str
    report_mode: str
    status: str
    stage_label: str
    progress: int
    kind: str = "query"
    result_html: str = ""
    error: str = ""
    batch_form_values: dict[str, object] | None = None
    batch_progress_path: Path | None = None
    batch_case_id: str | None = None
    batch_source: str = "batch"
    cancel_requested: bool = False


@dataclass
class WebJob:
    job_id: str
    query_id: str
    report_mode: str
    status: str
    stage_label: str
    progress: int
    kind: str = "query"
    result_html: str = ""
    error: str = ""
    batch_form_values: dict[str, object] | None = None
    batch_progress_path: Path | None = None
    batch_case_id: str | None = None
    batch_source: str = "batch"
    cancel_requested: bool = False
    created_at: float = 0.0
    updated_at: float = 0.0

    def snapshot(self) -> WebJobSnapshot:
        return WebJobSnapshot(
            job_id=self.job_id,
            query_id=self.query_id,
            report_mode=self.report_mode,
            status=self.status,
            stage_label=self.stage_label,
            progress=self.progress,
            kind=self.kind,
            result_html=self.result_html,
            error=self.error,
            batch_form_values=dict(self.batch_form_values)
            if self.batch_form_values is not None
            else None,
            batch_progress_path=self.batch_progress_path,
            batch_case_id=self.batch_case_id,
            batch_source=self.batch_source,
            cancel_requested=self.cancel_requested,
        )
