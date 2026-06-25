"""Trino one-query diagnosis for the local web UI."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Callable

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.trino.coordinator_query_info_pruned_import import (
    load_trino_coordinator_query_info_pruned_import,
    trino_coordinator_query_info_pruned_import_boundary_export,
)
from query_doctor.trino.coordinator_query_info_target import (
    TRINO_COORDINATOR_QUERY_ID_RE,
    load_trino_coordinator_query_info_auth_header_file,
    load_trino_coordinator_query_info_source_contract,
    validate_trino_coordinator_query_info_target,
)
from query_doctor.trino.coordinator_query_list_target import (
    load_trino_coordinator_query_list_source_contract,
    validate_trino_coordinator_query_list_source_contract,
)
from query_doctor.trino.diagnosis import build_trino_compact_diagnosis_from_boundary
from query_doctor.trino.kerberos_spnego import TrinoKerberosSpnegoFetcher
from query_doctor.trino.support_mode import (
    TRINO_SUPPORT_MODE_OFF,
    trino_support_mode_enabled,
    trino_support_mode_is_production,
)
from query_doctor.web.models import WebError, WebSettings, WebTrinoQueryAnalysisResult
from query_doctor.web.trino_case_artifacts import materialize_trino_web_case_artifacts


ENGINE_IMPALA = "impala"
ENGINE_TRINO = "trino"
SUPPORTED_QUERY_ENGINES = frozenset({ENGINE_IMPALA, ENGINE_TRINO})
CancelCheck = Callable[[], bool]
TRINO_QUERY_WORKFLOW = "Trino Beta Query ID diagnosis"


def normalize_query_engine(value: object) -> str:
    engine = str(value or "").strip().lower()
    return engine if engine in SUPPORTED_QUERY_ENGINES else ENGINE_IMPALA


def validate_trino_query_id(query_id: str) -> str:
    normalized = str(query_id or "").strip()
    if normalized != query_id or TRINO_COORDINATOR_QUERY_ID_RE.fullmatch(normalized) is None:
        raise WebError(
            "Trino Query ID must look like 20260603_120102_00001_abcde.",
            title="Trino Query ID rejected",
            reason_code="trino_beta.query_id_invalid",
            stage="Checking Trino Query ID",
            next_step="Paste one explicit Trino Query ID in the expected coordinator format.",
        )
    return normalized


def trino_beta_query_configured(settings: WebSettings) -> bool:
    return bool(
        trino_mode_enabled(settings)
        and settings.trino_coordinator_url
        and settings.trino_query_info_source_contract
    )


def trino_mode_enabled(settings: WebSettings) -> bool:
    mode = getattr(settings, "trino_support_mode", TRINO_SUPPORT_MODE_OFF)
    return trino_support_mode_enabled(mode) or bool(getattr(settings, "trino_beta_enabled", False))


def trino_workflow_label(settings: WebSettings, beta_label: str) -> str:
    if trino_support_mode_is_production(getattr(settings, "trino_support_mode", "")):
        return beta_label.replace("Trino Beta", "Trino")
    return beta_label


def trino_mode_display_label(settings: WebSettings) -> str:
    return (
        "Trino"
        if trino_support_mode_is_production(getattr(settings, "trino_support_mode", ""))
        else "Trino Beta"
    )


def trino_result_support_mode(settings: WebSettings) -> str:
    return (
        "production"
        if trino_support_mode_is_production(getattr(settings, "trino_support_mode", ""))
        else "beta"
    )


def validate_trino_beta_startup_config(
    *,
    source_contract: Path,
    coordinator_url: str,
    query_list_source_contract: Path | None = None,
    auth_header_file: Path | None = None,
    kerberos_principal: str | None = None,
    kerberos_service_name: str = "HTTP",
    krb5_ccname: str | None = None,
    krb5_config: Path | None = None,
    kerberos_ca_cert: Path | None = None,
    kerberos_insecure_tls: bool = False,
) -> None:
    try:
        validate_trino_auth_mode(
            auth_header_file=auth_header_file,
            kerberos_principal=kerberos_principal,
            kerberos_service_name=kerberos_service_name,
            krb5_ccname=krb5_ccname,
            krb5_config=krb5_config,
            kerberos_ca_cert=kerberos_ca_cert,
            kerberos_insecure_tls=kerberos_insecure_tls,
        )
        contract = load_trino_coordinator_query_info_source_contract(source_contract)
        validate_trino_coordinator_query_info_target(
            contract,
            coordinator_url=coordinator_url,
            query_id="20260603_120102_00001_startup",
        )
        if query_list_source_contract is not None:
            query_list_contract = load_trino_coordinator_query_list_source_contract(
                query_list_source_contract
            )
            validate_trino_coordinator_query_list_source_contract(query_list_contract)
    except (OSError, EngineFactContractError) as exc:
        raise WebError(
            "Trino local config has an invalid source contract, coordinator URL, "
            "or auth reference.",
            title="Trino local config rejected",
            reason_code="trino_beta.local_config_rejected",
            stage="Checking Trino local config",
            next_step=(
                "Fix the selected local Trino source contract, coordinator target, "
                "or auth reference before starting the web UI."
            ),
        ) from exc


def run_trino_query_id_analysis(
    query_id: str,
    settings: WebSettings,
    *,
    progress: Callable[[int], None] | None = None,
    cancel_check: CancelCheck | None = None,
    artifact_workflow: str = "query_id",
) -> WebTrinoQueryAnalysisResult:
    update_progress(progress, 0)
    validated_query_id = validate_trino_query_id(query_id)
    workflow = trino_workflow_label(settings, TRINO_QUERY_WORKFLOW)
    if not trino_mode_enabled(settings):
        raise trino_not_configured_error(workflow)
    if not trino_beta_query_configured(settings):
        raise trino_not_configured_error(workflow)
    source_contract = settings.trino_query_info_source_contract
    coordinator_url = settings.trino_coordinator_url
    if source_contract is None or coordinator_url is None:
        raise trino_not_configured_error(workflow)
    try:
        stop_if_cancelled(cancel_check)
        auth_headers = trino_auth_headers(settings)
        update_progress(progress, 1)
        stop_if_cancelled(cancel_check)
        result = load_trino_coordinator_query_info_pruned_import(
            source_contract,
            coordinator_url=coordinator_url,
            query_id=validated_query_id,
            auth_headers=auth_headers,
            fetcher=trino_query_info_fetcher(settings),
        )
        stop_if_cancelled(cancel_check)
        update_progress(progress, 2)
        boundary = trino_coordinator_query_info_pruned_import_boundary_export(result)[
            "query_info_boundary"
        ]
        update_progress(progress, 3)
        stop_if_cancelled(cancel_check)
        diagnosis = build_trino_compact_diagnosis_from_boundary(boundary)
        update_progress(progress, 4)
        stop_if_cancelled(cancel_check)
        case_artifacts = materialize_trino_web_case_artifacts(
            settings=settings,
            boundary=boundary,
            diagnosis=diagnosis,
            workflow=artifact_workflow,
            support_mode=trino_result_support_mode(settings),
        )
    except OSError as exc:
        raise trino_local_reference_error(workflow) from exc
    except EngineFactContractError as exc:
        raise trino_engine_contract_web_error(
            exc,
            workflow=workflow,
            stage="Reading bounded QueryInfo",
        ) from exc
    return WebTrinoQueryAnalysisResult(
        query_id=validated_query_id,
        diagnosis=dict(diagnosis),
        support_mode=trino_result_support_mode(settings),
        case_artifacts=case_artifacts,
    )


def trino_auth_headers(settings: WebSettings) -> Mapping[str, str] | None:
    if settings.trino_auth_header_file is None:
        return None
    return load_trino_coordinator_query_info_auth_header_file(settings.trino_auth_header_file)


def trino_query_info_fetcher(settings: WebSettings):
    fetcher = trino_kerberos_spnego_fetcher(settings)
    return None if fetcher is None else fetcher.query_info


def trino_query_list_fetcher(settings: WebSettings):
    fetcher = trino_kerberos_spnego_fetcher(settings)
    return None if fetcher is None else fetcher.query_list


def trino_kerberos_spnego_fetcher(settings: WebSettings) -> TrinoKerberosSpnegoFetcher | None:
    if settings.trino_kerberos_principal is None:
        return None
    return TrinoKerberosSpnegoFetcher(
        kerberos_principal=settings.trino_kerberos_principal,
        service_name=settings.trino_kerberos_service_name,
        krb5_ccname=settings.trino_krb5_ccname,
        krb5_config=settings.trino_krb5_config,
        ca_cert=settings.trino_kerberos_ca_cert,
        insecure_tls=settings.trino_kerberos_insecure_tls,
    )


def validate_trino_auth_mode(
    *,
    auth_header_file: Path | None,
    kerberos_principal: str | None,
    kerberos_service_name: str,
    krb5_ccname: str | None,
    krb5_config: Path | None,
    kerberos_ca_cert: Path | None,
    kerberos_insecure_tls: bool,
) -> None:
    kerberos_configured = any(
        (
            kerberos_principal,
            krb5_ccname,
            krb5_config,
            kerberos_ca_cert,
            kerberos_insecure_tls,
        )
    )
    if auth_header_file is not None and kerberos_configured:
        raise EngineFactContractError(
            "Trino auth-header and Kerberos auth modes cannot be combined"
        )
    if kerberos_configured and kerberos_principal is None:
        raise EngineFactContractError("Trino Kerberos auth requires a principal")
    if auth_header_file is not None:
        load_trino_coordinator_query_info_auth_header_file(auth_header_file)
    if krb5_config is not None and not krb5_config.is_file():
        raise EngineFactContractError("Trino Kerberos config reference is unavailable")
    if kerberos_ca_cert is not None and not kerberos_ca_cert.is_file():
        raise EngineFactContractError("Trino Kerberos CA reference is unavailable")
    if kerberos_principal is not None:
        TrinoKerberosSpnegoFetcher(
            kerberos_principal=kerberos_principal,
            service_name=kerberos_service_name,
            krb5_ccname=krb5_ccname,
            krb5_config=krb5_config,
            ca_cert=kerberos_ca_cert,
            insecure_tls=kerberos_insecure_tls,
        )


def update_progress(progress: Callable[[int], None] | None, stage_index: int) -> None:
    if progress is not None:
        progress(stage_index)


def stop_if_cancelled(cancel_check: CancelCheck | None) -> None:
    if cancel_check is not None and cancel_check():
        raise WebError(
            "Analysis was stopped by the user.",
            title="Job stopped",
            reason_code="job.cancelled",
            stage="Cancelled",
            next_step="Start a new job when you are ready to retry.",
        )


def trino_not_configured_error(workflow: str) -> WebError:
    return WebError(
        f"{workflow} is not configured for the selected source.",
        title=f"{workflow} not configured",
        reason_code="trino_beta.not_configured",
        stage="Checking Trino local config",
        next_step=(
            "Choose a Trino-ready source, or update the ignored local config with "
            "the required bounded source contracts and coordinator target."
        ),
    )


def trino_local_reference_error(workflow: str) -> WebError:
    return WebError(
        f"{workflow} could not read a local source contract or auth reference.",
        title=f"{workflow} local reference unavailable",
        reason_code="trino_beta.local_reference_unreadable",
        stage="Reading local Trino references",
        next_step=(
            "Check the selected local source contract and auth-reference files, then retry."
        ),
        details=("No local path, auth value, coordinator URL, or Query ID is shown.",),
    )


def trino_engine_contract_web_error(
    exc: EngineFactContractError,
    *,
    workflow: str,
    stage: str,
) -> WebError:
    reason_code, message, next_step, detail = classify_trino_engine_contract_error(
        str(exc),
        workflow=workflow,
    )
    return WebError(
        message,
        title=f"{workflow} failed",
        reason_code=reason_code,
        stage=stage,
        next_step=next_step,
        details=(detail, "Raw Trino payloads and local references remain hidden."),
    )


def classify_trino_engine_contract_error(
    message: str,
    *,
    workflow: str,
) -> tuple[str, str, str, str]:
    normalized = " ".join(str(message or "").casefold().split())
    if "authentication was rejected" in normalized:
        return (
            "trino_beta.auth_rejected",
            f"{workflow} could not authenticate to the coordinator.",
            "Renew the operator-managed auth reference or Kerberos ticket, then retry.",
            "The coordinator rejected authentication for the bounded read.",
        )
    if "unavailable for the selected query id" in normalized:
        return (
            "trino_beta.query_unavailable",
            "Trino coordinator QueryInfo is unavailable for the selected Query ID.",
            "Use a current or very recent Query ID that is still retained by the coordinator.",
            "The selected Query ID could not be read from coordinator retention.",
        )
    if "could not be read" in normalized:
        target = "query list" if "query-list" in normalized else "QueryInfo"
        return (
            "trino_beta.network_read_failed",
            f"{workflow} could not read the bounded coordinator {target}.",
            "Check coordinator reachability and the selected local auth mode, then retry.",
            "The bounded coordinator read failed before raw-free diagnosis could start.",
        )
    if "auth header" in normalized:
        return (
            "trino_beta.local_reference_unreadable",
            f"{workflow} rejected the local auth reference.",
            "Check the selected auth-reference file shape and size, then retry.",
            "The local auth reference did not pass safe validation.",
        )
    if "payload is too large" in normalized or "too many records" in normalized:
        return (
            "trino_beta.payload_rejected",
            f"{workflow} rejected the coordinator payload because it exceeded configured bounds.",
            "Reduce the bounded source contract limits at the source or choose a smaller retained set.",
            "The payload was rejected before browser rendering.",
        )
    if (
        "not valid json" in normalized
        or "utf-8 json" in normalized
        or "needs a json" in normalized
        or "fields are unsupported" in normalized
        or "querystats is unsupported" in normalized
    ):
        return (
            "trino_beta.payload_rejected",
            f"{workflow} rejected the coordinator payload before diagnosis.",
            "Check that the configured endpoint returns the expected pruned JSON shape.",
            "The response did not match the raw-free Trino intake contract.",
        )
    if (
        "contract" in normalized
        or "source type" in normalized
        or "query bound" in normalized
        or "redaction" in normalized
        or "browser/report output" in normalized
        or "raw payload storage" in normalized
    ):
        return (
            "trino_beta.contract_rejected",
            f"{workflow} was rejected by safe source-contract checks.",
            "Fix the selected local source contract to match the bounded Trino contract.",
            "The local source contract did not pass safe validation.",
        )
    return (
        "trino_beta.payload_rejected",
        f"{workflow} was rejected before raw-free diagnosis.",
        "Review the selected Trino source contract and retry with a bounded pruned response.",
        "The input did not pass the raw-free Trino intake contract.",
    )
