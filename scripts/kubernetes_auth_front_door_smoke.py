#!/usr/bin/env python3
"""Raw-free live smoke for an external Kubernetes auth front door."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import http.client
import json
import os
from pathlib import Path
import socket
import ssl
import sys
from typing import Any
from urllib import parse


SMOKE_KIND = "kubernetes_auth_front_door_smoke_v1"
DEFAULT_CALLBACK_PATH = "/oauth2/callback"
DEFAULT_CODE_CHALLENGE_METHOD = "S256"
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
TOKEN_HEADER_KEYWORDS = ("authorization", "access-token", "id-token")
TOKEN_COOKIE_KEYWORDS = ("access_token", "id_token", "authorization", "bearer")


@dataclass(frozen=True)
class SmokeConfig:
    base_url: str
    expected_issuer_url: str = ""
    expected_client_id: str = ""
    expected_callback_path: str = DEFAULT_CALLBACK_PATH
    expected_code_challenge_method: str = DEFAULT_CODE_CHALLENGE_METHOD
    timeout_sec: float = 10.0
    max_redirects: int = 5


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, tuple[str, ...]]

    def first_header(self, name: str) -> str:
        values = self.headers.get(name.lower(), ())
        return values[0] if values else ""

    def header_values(self, name: str) -> tuple[str, ...]:
        return self.headers.get(name.lower(), ())


@dataclass(frozen=True)
class RedirectTrace:
    first_status: int | None
    redirect_count: int
    authorize_url: str
    cookie_count: int
    token_header_seen: bool
    token_cookie_seen: bool
    error_category: str = ""


@dataclass(frozen=True)
class SmokeCheck:
    name: str
    passed: bool
    details: dict[str, object]

    def raw_free_summary(self) -> dict[str, object]:
        return {
            "name": self.name,
            "passed": self.passed,
            **self.details,
        }


Fetch = Callable[[str, float], HttpResponse]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("QUERY_DOCTOR_K8S_AUTH_SMOKE_BASE_URL", ""),
        help="External Query Doctor URL behind the auth front door. Never printed.",
    )
    parser.add_argument(
        "--expected-issuer-url",
        default=os.environ.get("QUERY_DOCTOR_K8S_AUTH_SMOKE_EXPECTED_ISSUER_URL", ""),
        help="Expected OIDC issuer URL. Checked but never printed.",
    )
    parser.add_argument(
        "--expected-client-id",
        default=os.environ.get("QUERY_DOCTOR_K8S_AUTH_SMOKE_EXPECTED_CLIENT_ID", ""),
        help="Expected OIDC client ID. Checked but never printed.",
    )
    parser.add_argument(
        "--expected-callback-path",
        default=os.environ.get(
            "QUERY_DOCTOR_K8S_AUTH_SMOKE_EXPECTED_CALLBACK_PATH",
            DEFAULT_CALLBACK_PATH,
        ),
        help=f"Expected OAuth callback path. Default: {DEFAULT_CALLBACK_PATH}.",
    )
    parser.add_argument(
        "--expected-code-challenge-method",
        default=os.environ.get(
            "QUERY_DOCTOR_K8S_AUTH_SMOKE_EXPECTED_CODE_CHALLENGE_METHOD",
            DEFAULT_CODE_CHALLENGE_METHOD,
        ),
        help=f"Expected PKCE code challenge method. Default: {DEFAULT_CODE_CHALLENGE_METHOD}.",
    )
    parser.add_argument(
        "--timeout-sec",
        type=float,
        default=float(os.environ.get("QUERY_DOCTOR_K8S_AUTH_SMOKE_TIMEOUT_SEC", "10")),
    )
    parser.add_argument(
        "--max-redirects",
        type=int,
        default=int(os.environ.get("QUERY_DOCTOR_K8S_AUTH_SMOKE_MAX_REDIRECTS", "5")),
    )
    parser.add_argument("--summary-json", type=Path)
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Print compact JSON instead of indented JSON.",
    )
    return parser.parse_args(argv)


def status_class(status: int | None) -> str:
    if status is None:
        return "unknown"
    return f"{status // 100}xx"


def error_category(exc: BaseException) -> str:
    if isinstance(exc, TimeoutError | socket.timeout):
        return "timeout"
    if isinstance(exc, ConnectionRefusedError):
        return "connection_refused"
    if isinstance(exc, socket.gaierror):
        return "name_resolution_error"
    if isinstance(exc, ssl.SSLError):
        return "tls_error"
    if isinstance(exc, ValueError):
        return "invalid_smoke_target"
    if isinstance(exc, OSError):
        return "network_error"
    return "unexpected_error"


def normalize_http_url(url: str) -> str:
    parsed = parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("smoke target must be an http(s) URL")
    path = parsed.path or "/"
    return parse.urlunparse((parsed.scheme, parsed.netloc, path, "", parsed.query, ""))


def request_no_redirect(url: str, timeout_sec: float) -> HttpResponse:
    normalized = normalize_http_url(url)
    parsed = parse.urlparse(normalized)
    path = parse.urlunparse(("", "", parsed.path or "/", parsed.params, parsed.query, ""))
    connection_cls = (
        http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    )
    connection = connection_cls(parsed.hostname, parsed.port, timeout=timeout_sec)
    try:
        connection.request(
            "GET",
            path,
            headers={
                "User-Agent": "query-doctor-kubernetes-auth-front-door-smoke",
                "Accept": "text/html,application/json;q=0.8,*/*;q=0.1",
            },
        )
        response = connection.getresponse()
        response.read(1024)
        headers: dict[str, list[str]] = {}
        for key, value in response.getheaders():
            headers.setdefault(key.lower(), []).append(value)
        return HttpResponse(
            status=response.status,
            headers={key: tuple(values) for key, values in headers.items()},
        )
    finally:
        connection.close()


def has_token_header(headers: Mapping[str, tuple[str, ...]]) -> bool:
    for key in headers:
        normalized = key.lower()
        if any(keyword in normalized for keyword in TOKEN_HEADER_KEYWORDS):
            return True
    return False


def has_token_cookie(cookies: Sequence[str]) -> bool:
    for cookie in cookies:
        name = cookie.split("=", 1)[0].strip().lower()
        if any(keyword in name for keyword in TOKEN_COOKIE_KEYWORDS):
            return True
    return False


def looks_like_oidc_authorize(url: str) -> bool:
    parsed = parse.urlparse(url)
    params = parse.parse_qs(parsed.query)
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.hostname)
        and params.get("response_type") == ["code"]
        and bool(params.get("client_id", [""])[0])
        and bool(params.get("redirect_uri", [""])[0])
    )


def expected_authorization_endpoint(config: SmokeConfig) -> str:
    if not config.expected_issuer_url:
        return ""
    issuer = config.expected_issuer_url.rstrip("/")
    return f"{issuer}/protocol/openid-connect/auth"


def endpoint_without_query(url: str) -> str:
    parsed = parse.urlparse(url)
    return parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def collect_redirect_trace(
    config: SmokeConfig, *, fetch: Fetch = request_no_redirect
) -> RedirectTrace:
    try:
        current_url = normalize_http_url(config.base_url)
        first_status: int | None = None
        redirect_count = 0
        cookie_count = 0
        token_header_seen = False
        token_cookie_seen = False
        for _ in range(config.max_redirects):
            response = fetch(current_url, config.timeout_sec)
            if first_status is None:
                first_status = response.status
            token_header_seen = token_header_seen or has_token_header(response.headers)
            cookies = response.header_values("set-cookie")
            cookie_count += len(cookies)
            token_cookie_seen = token_cookie_seen or has_token_cookie(cookies)
            if response.status not in REDIRECT_STATUSES:
                return RedirectTrace(
                    first_status=first_status,
                    redirect_count=redirect_count,
                    authorize_url="",
                    cookie_count=cookie_count,
                    token_header_seen=token_header_seen,
                    token_cookie_seen=token_cookie_seen,
                )
            location = response.first_header("location")
            if not location:
                return RedirectTrace(
                    first_status=first_status,
                    redirect_count=redirect_count,
                    authorize_url="",
                    cookie_count=cookie_count,
                    token_header_seen=token_header_seen,
                    token_cookie_seen=token_cookie_seen,
                )
            redirect_count += 1
            next_url = parse.urljoin(current_url, location)
            if looks_like_oidc_authorize(next_url):
                return RedirectTrace(
                    first_status=first_status,
                    redirect_count=redirect_count,
                    authorize_url=next_url,
                    cookie_count=cookie_count,
                    token_header_seen=token_header_seen,
                    token_cookie_seen=token_cookie_seen,
                )
            current_url = next_url
        return RedirectTrace(
            first_status=first_status,
            redirect_count=redirect_count,
            authorize_url="",
            cookie_count=cookie_count,
            token_header_seen=token_header_seen,
            token_cookie_seen=token_cookie_seen,
        )
    except Exception as exc:  # noqa: BLE001 - only safe categories are reported.
        return RedirectTrace(
            first_status=None,
            redirect_count=0,
            authorize_url="",
            cookie_count=0,
            token_header_seen=False,
            token_cookie_seen=False,
            error_category=error_category(exc),
        )


def authorize_params(authorize_url: str) -> dict[str, str]:
    if not authorize_url:
        return {}
    parsed = parse.urlparse(authorize_url)
    params = parse.parse_qs(parsed.query)
    return {key: values[0] for key, values in params.items() if values}


def same_external_origin(left: str, right: str) -> bool:
    left_url = parse.urlparse(left)
    right_url = parse.urlparse(right)
    return (
        left_url.scheme == right_url.scheme
        and left_url.netloc == right_url.netloc
        and left_url.scheme in {"http", "https"}
        and bool(left_url.netloc)
    )


def build_checks(config: SmokeConfig, trace: RedirectTrace) -> tuple[SmokeCheck, ...]:
    params = authorize_params(trace.authorize_url)
    redirect_uri = params.get("redirect_uri", "")
    redirect_uri_path = parse.urlparse(redirect_uri).path
    expected_endpoint = expected_authorization_endpoint(config)
    checks = [
        SmokeCheck(
            "front_door_requires_auth",
            not trace.error_category
            and trace.first_status in REDIRECT_STATUSES
            and trace.redirect_count > 0,
            {
                "status_class": status_class(trace.first_status),
                "redirect_count": trace.redirect_count,
                "error_category": trace.error_category,
            },
        ),
        SmokeCheck(
            "oidc_authorize_redirect",
            bool(trace.authorize_url),
            {
                "authorize_redirect_seen": bool(trace.authorize_url),
                "cookie_count": trace.cookie_count,
            },
        ),
        SmokeCheck(
            "callback_redirect_uri",
            bool(redirect_uri)
            and redirect_uri_path == config.expected_callback_path
            and same_external_origin(config.base_url, redirect_uri),
            {
                "redirect_uri_present": bool(redirect_uri),
                "callback_path_matches": redirect_uri_path == config.expected_callback_path,
                "external_origin_matches": bool(redirect_uri)
                and same_external_origin(config.base_url, redirect_uri),
            },
        ),
        SmokeCheck(
            "pkce_code_challenge_method",
            params.get("code_challenge_method") == config.expected_code_challenge_method,
            {
                "method_matches": params.get("code_challenge_method")
                == config.expected_code_challenge_method,
            },
        ),
        SmokeCheck(
            "raw_auth_material_not_returned_to_client",
            not trace.token_header_seen and not trace.token_cookie_seen,
            {
                "token_header_seen": trace.token_header_seen,
                "token_cookie_seen": trace.token_cookie_seen,
            },
        ),
    ]
    if config.expected_client_id:
        checks.append(
            SmokeCheck(
                "expected_client_id",
                params.get("client_id") == config.expected_client_id,
                {"client_id_matches": params.get("client_id") == config.expected_client_id},
            )
        )
    if expected_endpoint:
        checks.append(
            SmokeCheck(
                "expected_issuer_authorization_endpoint",
                endpoint_without_query(trace.authorize_url) == expected_endpoint,
                {
                    "authorization_endpoint_matches": endpoint_without_query(trace.authorize_url)
                    == expected_endpoint,
                },
            )
        )
    return tuple(checks)


def run_checks(
    config: SmokeConfig, *, fetch: Fetch = request_no_redirect
) -> tuple[SmokeCheck, ...]:
    trace = collect_redirect_trace(config, fetch=fetch)
    return build_checks(config, trace)


def smoke_payload(config: SmokeConfig, checks: Sequence[SmokeCheck]) -> dict[str, object]:
    del config
    issue_codes = [f"{check.name}_failed" for check in checks if not check.passed]
    return {
        "kind": SMOKE_KIND,
        "all_passed": not issue_codes,
        "check_count": len(checks),
        "issue_codes": issue_codes,
        "raw_values_output": "no",
        "checks": [check.raw_free_summary() for check in checks],
    }


def print_payload(payload: dict[str, object], *, compact: bool) -> None:
    if compact:
        print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.base_url:
        print("--base-url or QUERY_DOCTOR_K8S_AUTH_SMOKE_BASE_URL is required", file=sys.stderr)
        return 2
    config = SmokeConfig(
        base_url=args.base_url,
        expected_issuer_url=args.expected_issuer_url,
        expected_client_id=args.expected_client_id,
        expected_callback_path=args.expected_callback_path,
        expected_code_challenge_method=args.expected_code_challenge_method,
        timeout_sec=args.timeout_sec,
        max_redirects=args.max_redirects,
    )
    checks = run_checks(config)
    payload = smoke_payload(config, checks)
    if args.summary_json is not None:
        args.summary_json.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print_payload(payload, compact=args.compact)
    return 0 if payload["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
