"""Kerberos/SPNEGO fetch helpers for bounded Trino coordinator GETs."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.trino.coordinator_query_info_target import (
    TRINO_COORDINATOR_QUERY_INFO_AUTH_REJECTED_ERROR,
    TRINO_COORDINATOR_QUERY_INFO_UNAVAILABLE_ERROR,
)


HEADER_VALUE_RE = re.compile(r"[A-Za-z0-9_.@-]{1,128}\Z")
SERVICE_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")


@dataclass(frozen=True)
class TrinoKerberosSpnegoFetcher:
    kerberos_principal: str
    service_name: str = "HTTP"
    krb5_ccname: str | None = None
    krb5_config: Path | None = None
    ca_cert: Path | None = None
    insecure_tls: bool = False

    def __post_init__(self) -> None:
        if HEADER_VALUE_RE.fullmatch(self.kerberos_principal) is None:
            raise EngineFactContractError("Trino Kerberos principal is unsupported")
        if SERVICE_NAME_RE.fullmatch(self.service_name) is None:
            raise EngineFactContractError("Trino Kerberos service name is unsupported")
        if self.krb5_ccname is not None and "\x00" in self.krb5_ccname:
            raise EngineFactContractError("Trino Kerberos ticket cache is unsupported")

    def query_list(
        self,
        coordinator_url: str,
        *,
        max_bytes: int,
        timeout_seconds: int,
        auth_headers: dict[str, str] | None = None,
    ) -> str:
        if auth_headers is not None:
            raise EngineFactContractError("Trino coordinator query-list auth mode is unsupported")
        return self._fetch(
            _pruned_query_list_url(coordinator_url),
            max_bytes=max_bytes,
            timeout_seconds=timeout_seconds,
            surface="query-list",
        )

    def query_info(
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
        return self._fetch(
            _pruned_query_info_url(coordinator_url, query_id),
            max_bytes=max_bytes,
            timeout_seconds=timeout_seconds,
            surface="query-info",
        )

    def _fetch(
        self,
        endpoint: str,
        *,
        max_bytes: int,
        timeout_seconds: int,
        surface: str,
    ) -> str:
        if urlsplit(endpoint).scheme != "https":
            raise EngineFactContractError(
                f"Trino coordinator {surface} Kerberos fetch requires HTTPS"
            )
        argv = self._curl_argv(
            endpoint,
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
            raise EngineFactContractError(f"Trino coordinator {surface} could not be read") from exc
        if proc.returncode != 0:
            raise EngineFactContractError(f"Trino coordinator {surface} could not be read")
        body, http_status = _split_curl_http_status(proc.stdout or b"")
        if http_status in {401, 403}:
            raise EngineFactContractError(_auth_rejected_error(surface))
        if surface == "query-info" and http_status in {404, 410}:
            raise EngineFactContractError(TRINO_COORDINATOR_QUERY_INFO_UNAVAILABLE_ERROR)
        if http_status is not None and http_status >= 400:
            raise EngineFactContractError(f"Trino coordinator {surface} could not be read")
        if len(body) > max_bytes:
            raise EngineFactContractError(f"Trino coordinator {surface} payload is too large")
        try:
            return body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise EngineFactContractError(
                f"Trino coordinator {surface} must be UTF-8 JSON"
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
            self.service_name,
            "-u",
            f"{self.kerberos_principal}:",
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
        if self.insecure_tls:
            argv.append("--insecure")
        if self.ca_cert is not None:
            argv.extend(["--cacert", str(self.ca_cert)])
        argv.append(endpoint)
        return argv

    def _env(self) -> dict[str, str] | None:
        if not self.krb5_ccname and self.krb5_config is None:
            return None
        env = os.environ.copy()
        if self.krb5_ccname:
            env["KRB5CCNAME"] = self.krb5_ccname
        if self.krb5_config is not None:
            env["KRB5_CONFIG"] = str(self.krb5_config)
        return env


def _auth_rejected_error(surface: str) -> str:
    if surface == "query-info":
        return TRINO_COORDINATOR_QUERY_INFO_AUTH_REJECTED_ERROR
    return (
        "Trino coordinator query-list authentication was rejected; refresh the "
        "operator-managed auth reference or ticket"
    )


def _split_curl_http_status(stdout: bytes) -> tuple[bytes, int | None]:
    separator = stdout.rfind(b"\n")
    if separator == -1:
        return stdout, None
    suffix = stdout[separator + 1 :]
    if len(suffix) == 3 and suffix.isdigit():
        return stdout[:separator], int(suffix)
    return stdout, None


def _pruned_query_list_url(coordinator_url: str) -> str:
    parsed = urlsplit(coordinator_url)
    path = f"{parsed.path.rstrip('/')}/v1/query"
    return urlunsplit((parsed.scheme, parsed.netloc, path, urlencode({"pruned": "true"}), ""))


def _pruned_query_info_url(coordinator_url: str, query_id: str) -> str:
    parsed = urlsplit(coordinator_url)
    path = f"{parsed.path.rstrip('/')}/v1/query/{query_id}"
    return urlunsplit((parsed.scheme, parsed.netloc, path, urlencode({"pruned": "true"}), ""))
