#!/usr/bin/env python3
"""Run one bounded Trino coordinator QueryInfo handoff and readiness gate."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlencode, urlsplit, urlunsplit

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from query_doctor.analyzer.engine_facts import EngineFactContractError  # noqa: E402
from query_doctor.cli.trino_diagnosis_output import (  # noqa: E402
    same_path,
    write_trino_boundary_out,
    write_trino_compact_diagnosis_out,
)
from query_doctor.trino.coordinator_query_info_pruned_import import (  # noqa: E402
    format_trino_coordinator_query_info_pruned_import_summary,
    load_trino_coordinator_query_info_pruned_import,
    trino_coordinator_query_info_pruned_import_boundary_export,
)
from query_doctor.trino.coordinator_query_info_target import (  # noqa: E402
    TRINO_COORDINATOR_QUERY_INFO_AUTH_REJECTED_ERROR,
    TRINO_COORDINATOR_QUERY_INFO_CONTRACT_VERSION,
    TRINO_COORDINATOR_QUERY_INFO_UNAVAILABLE_ERROR,
    TRINO_COORDINATOR_QUERY_ID_RE,
    load_trino_coordinator_query_info_auth_header_file,
)
from scripts import audit_trino_product_surface_boundary  # noqa: E402
from scripts.audit_trino_compact_readiness import (  # noqa: E402
    TrinoCompactReadinessInputError,
    audit_boundary_payload,
    audit_result_version_family_breadth,
    load_json_object,
    print_result,
    one_query_handoff_summary_payload,
    readiness_summary_payload,
    write_readiness_summary_json,
)
from scripts.trino_kerberos_smoke import (  # noqa: E402
    TrinoSmokeError,
    validate_header_value,
    validate_service_name,
)


TRINO_ONE_QUERY_HANDOFF_SUMMARY_VERSION = "trino_one_query_handoff_summary_v1"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a dev-only one-query Trino handoff: read exactly one bounded "
            "GET /v1/query/{queryId}?pruned=true response through the existing "
            "private-preview import path, write raw-free boundary and compact "
            "diagnosis JSON, then run the strict compact readiness gate. The "
            "command never submits SQL and never prints the coordinator URL, Query ID, "
            "auth header, raw QueryInfo, artifact paths, or filenames."
        )
    )
    parser.add_argument(
        "--source-contract",
        required=True,
        type=Path,
        help="Compact sanitized Trino coordinator query-info source-contract JSON file.",
    )
    parser.add_argument(
        "--coordinator-url",
        required=True,
        help="Explicit Trino coordinator base URL. Used for the read but never echoed.",
    )
    parser.add_argument(
        "--query-id",
        help="Explicit known Trino query ID. Used for the read but never echoed.",
    )
    parser.add_argument(
        "--query-id-file",
        type=Path,
        help=(
            "Optional local file containing exactly one explicit known Trino Query ID. "
            "Use this to avoid putting the Query ID in shell history or process args. "
            "The path and value are never printed."
        ),
    )
    parser.add_argument(
        "--redaction-reviewed",
        action="store_true",
        help="Confirm the source contract and selected QueryInfo path were operator-reviewed.",
    )
    parser.add_argument(
        "--auth-header-file",
        type=Path,
        default=None,
        help=(
            "Optional local file containing one operator-managed Authorization header line. "
            "The path and value are never printed."
        ),
    )
    parser.add_argument(
        "--kerberos-principal",
        help=(
            "Optional Kerberos principal already present in the selected ticket cache. "
            "When set, the handoff fetches the pruned QueryInfo response with curl "
            "--negotiate instead of an auth-header file. The value is never printed."
        ),
    )
    parser.add_argument(
        "--kerberos-service-name",
        default="HTTP",
        help="Kerberos service name for SPNEGO when --kerberos-principal is used.",
    )
    parser.add_argument(
        "--krb5-ccname",
        help=("Optional KRB5CCNAME value for the Kerberos fetch. The value is never printed."),
    )
    parser.add_argument(
        "--krb5-config",
        type=Path,
        help="Optional KRB5_CONFIG path for the Kerberos fetch. The path is never printed.",
    )
    parser.add_argument(
        "--kerberos-ca-cert",
        type=Path,
        help="Optional CA certificate path for curl. The path is never printed.",
    )
    parser.add_argument(
        "--kerberos-insecure-tls",
        action="store_true",
        help="Disable TLS verification for the Kerberos fetch in local test-cluster runs only.",
    )
    parser.add_argument(
        "--boundary-out",
        required=True,
        type=Path,
        help="Output path for raw-free engine_fact_boundary_v1 JSON. The path is never printed.",
    )
    parser.add_argument(
        "--diagnosis-out",
        required=True,
        type=Path,
        help="Output path for raw-free Trino compact diagnosis JSON. The path is never printed.",
    )
    parser.add_argument(
        "--product-surface-summary-out",
        type=Path,
        default=None,
        help=(
            "Optional output path for the raw-free Trino product-surface audit summary JSON. "
            "The path is never printed."
        ),
    )
    parser.add_argument(
        "--readiness-summary-out",
        type=Path,
        default=None,
        help=(
            "Optional output path for the raw-free Trino compact-readiness summary JSON. "
            "The path is never printed."
        ),
    )
    parser.add_argument(
        "--handoff-summary-out",
        type=Path,
        default=None,
        help=(
            "Optional output path for the raw-free Trino one-query handoff summary JSON. "
            "The path is never printed."
        ),
    )
    parser.add_argument(
        "--smoke-summary",
        type=Path,
        default=None,
        help=("Optional dev-only trino_smoke_summary.json artifact. The path is never printed."),
    )
    parser.add_argument(
        "--require-executed-smoke",
        action="store_true",
        help="Fail unless --smoke-summary records an executed all-ok smoke.",
    )
    parser.add_argument(
        "--require-supported-attention",
        action="store_true",
        help="Fail unless the compact diagnosis contains at least one supported attention area.",
    )
    parser.add_argument(
        "--max-contract-file-bytes",
        type=int,
        default=None,
        help="Optional source-contract file byte limit override for local dry runs.",
    )
    parser.add_argument(
        "--max-contract-bytes",
        type=int,
        default=None,
        help="Optional source-contract JSON byte limit override for local dry runs.",
    )
    parser.add_argument(
        "--max-contract-depth",
        type=int,
        default=None,
        help="Optional source-contract JSON nesting-depth limit override for local dry runs.",
    )
    parser.add_argument("--limit", type=int, default=12, help="Rows to print per section.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.redaction_reviewed:
        print(
            "[trino-one-query-handoff] rejected: redaction review confirmation is required",
            file=sys.stderr,
        )
        return 1
    if args.require_executed_smoke and args.smoke_summary is None:
        print(
            "[trino-one-query-handoff] rejected: --require-executed-smoke requires --smoke-summary",
            file=sys.stderr,
        )
        return 2
    query_id_source_error = _query_id_source_error(args)
    if query_id_source_error:
        print(f"[trino-one-query-handoff] rejected: {query_id_source_error}", file=sys.stderr)
        return 2
    auth_mode_error = _auth_mode_error(args)
    if auth_mode_error:
        print(f"[trino-one-query-handoff] rejected: {auth_mode_error}", file=sys.stderr)
        return 2
    overlap_error = _output_overlap_error(args)
    if overlap_error:
        print(f"[trino-one-query-handoff] rejected: {overlap_error}", file=sys.stderr)
        return 2

    try:
        query_id = _query_id(args)
        auth_headers = _auth_headers(args)
        fetcher = _fetcher(args)
        result = load_trino_coordinator_query_info_pruned_import(
            args.source_contract,
            coordinator_url=args.coordinator_url,
            query_id=query_id,
            auth_headers=auth_headers,
            fetcher=fetcher,
            **_limit_overrides(args),
        )
        boundary_export = trino_coordinator_query_info_pruned_import_boundary_export(result)
        boundary_payload = boundary_export["query_info_boundary"]
        write_trino_boundary_out(args.boundary_out, boundary_payload)
        write_trino_compact_diagnosis_out(args.diagnosis_out, boundary_payload)
        diagnosis_payload = load_json_object(
            args.diagnosis_out, input_label="diagnosis JSON output"
        )
        smoke_summary_payload = (
            None
            if args.smoke_summary is None
            else load_json_object(args.smoke_summary, input_label="smoke summary JSON input")
        )
        readiness = audit_boundary_payload(
            boundary_payload,
            diagnosis_payload=diagnosis_payload,
            smoke_summary_payload=smoke_summary_payload,
            required_source_versions=(TRINO_COORDINATOR_QUERY_INFO_CONTRACT_VERSION,),
            require_executed_smoke=args.require_executed_smoke,
            require_supported_attention=args.require_supported_attention,
            fail_on_unknown_parser_coverage=True,
            require_one_query_boundary=True,
        )
        audit_result_version_family_breadth(
            readiness,
            require_min_trino_version_families=1,
            required_trino_version_families=(),
        )
        if args.readiness_summary_out is not None:
            write_readiness_summary_json(
                args.readiness_summary_out,
                readiness_summary_payload(
                    readiness,
                    mode="one_query_live_handoff",
                    requirements=_readiness_requirements(args),
                ),
            )
        if args.handoff_summary_out is not None:
            write_readiness_summary_json(
                args.handoff_summary_out,
                trino_one_query_handoff_summary_payload(
                    readiness=readiness,
                    requirements=_readiness_requirements(args),
                    readiness_summary_written=args.readiness_summary_out is not None,
                ),
            )
    except OSError:
        print(
            "[trino-one-query-handoff] rejected: local artifact could not be read or written",
            file=sys.stderr,
        )
        return 2
    except TrinoCompactReadinessInputError as exc:
        print(f"[trino-one-query-handoff] rejected: {exc}", file=sys.stderr)
        return 2
    except EngineFactContractError as exc:
        print(f"[trino-one-query-handoff] rejected: {exc}", file=sys.stderr)
        return 1
    except TrinoSmokeError as exc:
        print(f"[trino-one-query-handoff] rejected: {exc}", file=sys.stderr)
        return 1

    print("[trino-one-query-handoff] import")
    print(format_trino_coordinator_query_info_pruned_import_summary(result))
    print("[trino-one-query-handoff] readiness")
    print_result(readiness, limit=args.limit)
    product_surface_exit = 0
    if args.product_surface_summary_out is not None:
        print("[trino-one-query-handoff] product-surface")
        product_surface_exit = audit_trino_product_surface_boundary.main(
            [
                str(args.boundary_out),
                "--diagnosis-json",
                str(args.diagnosis_out),
                "--summary-json",
                str(args.product_surface_summary_out),
                "--limit",
                str(args.limit),
            ]
        )
    if product_surface_exit not in (0, None):
        return product_surface_exit
    return 0 if readiness.ok else 1


def _auth_headers(args: argparse.Namespace) -> dict[str, str] | None:
    if args.auth_header_file is None:
        return None
    return load_trino_coordinator_query_info_auth_header_file(args.auth_header_file)


def _query_id_source_error(args: argparse.Namespace) -> str | None:
    has_query_id = bool(args.query_id)
    has_query_id_file = args.query_id_file is not None
    if has_query_id and has_query_id_file:
        return "query-id and query-id-file cannot be combined"
    if not has_query_id and not has_query_id_file:
        return "exactly one of query-id or query-id-file is required"
    return None


def _query_id(args: argparse.Namespace) -> str:
    if args.query_id_file is None:
        return args.query_id
    query_id = _read_query_id_file(args.query_id_file)
    if not TRINO_COORDINATOR_QUERY_ID_RE.fullmatch(query_id):
        raise EngineFactContractError(
            "Trino coordinator query-info query ID file must contain one supported Query ID"
        )
    return query_id


def _read_query_id_file(path: Path, *, max_file_bytes: int = 512) -> str:
    if path.stat().st_size > max_file_bytes:
        raise EngineFactContractError("Trino coordinator query-info query ID file is too large")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise EngineFactContractError(
            "Trino coordinator query-info query ID file must be UTF-8"
        ) from exc
    if "\x00" in text:
        raise EngineFactContractError("Trino coordinator query-info query ID file is unsupported")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) != 1 or lines[0] != text.strip():
        raise EngineFactContractError(
            "Trino coordinator query-info query ID file must contain one supported Query ID"
        )
    return lines[0]


def _fetcher(args: argparse.Namespace):
    if not _kerberos_enabled(args):
        return None
    kerberos_principal = validate_header_value(
        args.kerberos_principal,
        field_name="--kerberos-principal",
    )
    service_name = validate_service_name(args.kerberos_service_name)
    return _KerberosPrunedQueryInfoFetcher(
        kerberos_principal=kerberos_principal,
        service_name=service_name,
        krb5_ccname=args.krb5_ccname,
        krb5_config=args.krb5_config,
        ca_cert=args.kerberos_ca_cert,
        insecure_tls=args.kerberos_insecure_tls,
    )


def _kerberos_enabled(args: argparse.Namespace) -> bool:
    return any(
        (
            args.kerberos_principal,
            args.krb5_ccname,
            args.krb5_config,
            args.kerberos_ca_cert,
            args.kerberos_insecure_tls,
        )
    )


def _auth_mode_error(args: argparse.Namespace) -> str | None:
    if _kerberos_enabled(args) and not args.kerberos_principal:
        return "Kerberos fetch requires --kerberos-principal"
    if _kerberos_enabled(args) and args.auth_header_file is not None:
        return "auth-header and Kerberos fetch modes cannot be combined"
    return None


def _limit_overrides(args: argparse.Namespace) -> dict[str, int]:
    overrides: dict[str, int] = {}
    if args.max_contract_file_bytes is not None:
        overrides["max_file_bytes"] = args.max_contract_file_bytes
    if args.max_contract_bytes is not None:
        overrides["max_contract_bytes"] = args.max_contract_bytes
    if args.max_contract_depth is not None:
        overrides["max_contract_depth"] = args.max_contract_depth
    return overrides


def _output_overlap_error(args: argparse.Namespace) -> str | None:
    protected_inputs = (
        args.source_contract,
        args.query_id_file,
        args.auth_header_file,
        args.smoke_summary,
        args.krb5_config,
        args.kerberos_ca_cert,
        _krb5_ccname_file(args.krb5_ccname),
    )
    for protected_input in protected_inputs:
        if protected_input is None:
            continue
        if same_path(args.boundary_out, protected_input):
            return "boundary output must differ from every input artifact"
        if same_path(args.diagnosis_out, protected_input):
            return "compact diagnosis output must differ from every input artifact"
        if args.product_surface_summary_out is not None and same_path(
            args.product_surface_summary_out,
            protected_input,
        ):
            return "product-surface summary output must differ from every input artifact"
        if args.handoff_summary_out is not None and same_path(
            args.handoff_summary_out,
            protected_input,
        ):
            return "handoff summary output must differ from every input artifact"
    if same_path(args.boundary_out, args.diagnosis_out):
        return "boundary output must differ from compact diagnosis output"
    if args.readiness_summary_out is not None:
        for protected_input in protected_inputs:
            if protected_input is not None and same_path(
                args.readiness_summary_out, protected_input
            ):
                return "readiness summary output must differ from every input artifact"
        if same_path(args.readiness_summary_out, args.boundary_out) or same_path(
            args.readiness_summary_out,
            args.diagnosis_out,
        ):
            return (
                "readiness summary output must differ from boundary and compact diagnosis outputs"
            )
        if args.product_surface_summary_out is not None and same_path(
            args.readiness_summary_out,
            args.product_surface_summary_out,
        ):
            return "readiness summary output must differ from product-surface summary output"
        if args.handoff_summary_out is not None and same_path(
            args.readiness_summary_out,
            args.handoff_summary_out,
        ):
            return "readiness summary output must differ from handoff summary output"
    if args.product_surface_summary_out is not None:
        if same_path(args.product_surface_summary_out, args.boundary_out) or same_path(
            args.product_surface_summary_out,
            args.diagnosis_out,
        ):
            return "product-surface summary output must differ from boundary and compact diagnosis outputs"
        if args.handoff_summary_out is not None and same_path(
            args.product_surface_summary_out,
            args.handoff_summary_out,
        ):
            return "product-surface summary output must differ from handoff summary output"
    if args.handoff_summary_out is not None:
        if same_path(args.handoff_summary_out, args.boundary_out) or same_path(
            args.handoff_summary_out,
            args.diagnosis_out,
        ):
            return "handoff summary output must differ from boundary and compact diagnosis outputs"
    return None


def _krb5_ccname_file(value: str | None) -> Path | None:
    if not value or not value.startswith("FILE:"):
        return None
    path_text = value.removeprefix("FILE:")
    return Path(path_text) if path_text else None


def _readiness_requirements(args: argparse.Namespace) -> dict[str, object]:
    return {
        "require_diagnosis_json": True,
        "require_executed_smoke": bool(args.require_executed_smoke),
        "require_min_inputs": 1,
        "require_min_trino_version_families": 1,
        "require_one_query_boundary": True,
        "require_source_version": True,
        "require_source_version_count": 1,
        "require_trino_version_family": False,
        "require_trino_version_family_count": 0,
        "require_supported_attention": bool(args.require_supported_attention),
        "fail_on_unknown_parser_coverage": True,
    }


def trino_one_query_handoff_summary_payload(
    *,
    readiness,
    requirements: dict[str, Any],
    readiness_summary_written: bool,
) -> dict[str, Any]:
    payload = one_query_handoff_summary_payload(
        readiness,
        requirements=requirements,
        readiness_summary_written=readiness_summary_written,
    )
    payload["schema_version"] = TRINO_ONE_QUERY_HANDOFF_SUMMARY_VERSION
    return payload


class _KerberosPrunedQueryInfoFetcher:
    def __init__(
        self,
        *,
        kerberos_principal: str,
        service_name: str,
        krb5_ccname: str | None,
        krb5_config: Path | None,
        ca_cert: Path | None,
        insecure_tls: bool,
    ) -> None:
        self._kerberos_principal = kerberos_principal
        self._service_name = service_name
        self._krb5_ccname = krb5_ccname
        self._krb5_config = krb5_config
        self._ca_cert = ca_cert
        self._insecure_tls = insecure_tls

    def __call__(
        self,
        coordinator_url: str,
        *,
        query_id: str,
        max_bytes: int,
        timeout_seconds: int,
        auth_headers: dict[str, str] | None = None,
    ) -> str:
        if auth_headers is not None:
            raise EngineFactContractError("Trino coordinator query-info auth mode is unsupported")
        if urlsplit(coordinator_url).scheme != "https":
            raise EngineFactContractError(
                "Trino coordinator query-info Kerberos fetch requires HTTPS"
            )
        argv = self._curl_argv(
            _pruned_query_info_url(coordinator_url, query_id),
            max_bytes=max_bytes,
            timeout_seconds=timeout_seconds,
        )
        try:
            proc = subprocess.run(
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=timeout_seconds + 5,
                check=False,
                env=self._env(),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise EngineFactContractError("Trino coordinator query-info could not be read") from exc
        if proc.returncode != 0:
            raise EngineFactContractError("Trino coordinator query-info could not be read")
        body, http_status = _split_curl_http_status(proc.stdout or b"")
        if http_status in {401, 403}:
            raise EngineFactContractError(TRINO_COORDINATOR_QUERY_INFO_AUTH_REJECTED_ERROR)
        if http_status in {404, 410}:
            raise EngineFactContractError(TRINO_COORDINATOR_QUERY_INFO_UNAVAILABLE_ERROR)
        if http_status is not None and http_status >= 400:
            raise EngineFactContractError("Trino coordinator query-info could not be read")
        if len(body) > max_bytes:
            raise EngineFactContractError("Trino coordinator query-info payload is too large")
        try:
            return body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise EngineFactContractError(
                "Trino coordinator query-info must be UTF-8 JSON"
            ) from exc

    def _curl_argv(
        self,
        endpoint: str,
        *,
        max_bytes: int,
        timeout_seconds: int,
    ) -> list[str]:
        argv = [
            "curl",
            "--http1.1",
            "--negotiate",
            "--service-name",
            self._service_name,
            "-u",
            f"{self._kerberos_principal}:",
            "--max-time",
            str(timeout_seconds),
            "--max-filesize",
            str(max_bytes),
            "--silent",
            "--show-error",
            "--write-out",
            "\n%{http_code}",
            "-H",
            "Accept: application/json",
        ]
        if self._insecure_tls:
            argv.append("--insecure")
        if self._ca_cert is not None:
            argv.extend(["--cacert", str(self._ca_cert)])
        argv.append(endpoint)
        return argv

    def _env(self) -> dict[str, str] | None:
        if not self._krb5_ccname and self._krb5_config is None:
            return None
        env = os.environ.copy()
        if self._krb5_ccname:
            env["KRB5CCNAME"] = self._krb5_ccname
        if self._krb5_config is not None:
            env["KRB5_CONFIG"] = str(self._krb5_config)
        return env


def _split_curl_http_status(stdout: bytes) -> tuple[bytes, int | None]:
    separator = stdout.rfind(b"\n")
    if separator == -1:
        return stdout, None
    suffix = stdout[separator + 1 :]
    if len(suffix) == 3 and suffix.isdigit():
        return stdout[:separator], int(suffix)
    return stdout, None


def _pruned_query_info_url(coordinator_url: str, query_id: str) -> str:
    parsed = urlsplit(coordinator_url)
    path = f"{parsed.path.rstrip('/')}/v1/query/{query_id}"
    return urlunsplit((parsed.scheme, parsed.netloc, path, urlencode({"pruned": "true"}), ""))


if __name__ == "__main__":
    raise SystemExit(main())
