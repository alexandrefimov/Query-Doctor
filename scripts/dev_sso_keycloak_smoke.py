#!/usr/bin/env python3
"""Dev-only live smoke for the local Keycloak/oauth2-proxy SSO harness."""

from __future__ import annotations

import argparse
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from html.parser import HTMLParser
import http.client
import json
from pathlib import Path
import socket
import sys
from typing import Any
from urllib import error, parse, request
from http.cookiejar import CookieJar


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


SMOKE_KIND = "dev_sso_keycloak_smoke_v1"
DEFAULT_PROXY_URL = "http://query-doctor-sso.localhost:4180/"
DEFAULT_KEYCLOAK_DISCOVERY_URL = "http://query-doctor-sso.localhost:18080/realms/query-doctor-dev/.well-known/openid-configuration"
DEFAULT_UPSTREAM_HOST = "query-doctor-sso.localhost"
DEFAULT_UPSTREAM_PORT = 8765
DEFAULT_USERNAME = "analyst_one"
DEFAULT_PASSWORD = "analyst-one-dev-login"


@dataclass(frozen=True)
class SmokeConfig:
    proxy_url: str = DEFAULT_PROXY_URL
    keycloak_discovery_url: str = DEFAULT_KEYCLOAK_DISCOVERY_URL
    upstream_host: str = DEFAULT_UPSTREAM_HOST
    upstream_port: int = DEFAULT_UPSTREAM_PORT
    username: str = DEFAULT_USERNAME
    password: str = DEFAULT_PASSWORD
    timeout_sec: float = 10.0


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


class LoginFormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.forms: list[dict[str, object]] = []
        self._form: dict[str, object] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "form":
            self._form = {
                "action": attributes.get("action") or "",
                "inputs": {},
            }
        elif self._form is not None and tag == "input":
            name = attributes.get("name")
            if name:
                inputs = self._form["inputs"]
                assert isinstance(inputs, dict)
                inputs[name] = attributes.get("value") or ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self._form is not None:
            self.forms.append(self._form)
            self._form = None


def status_class(status: int | None) -> str:
    if status is None:
        return "unknown"
    return f"{status // 100}xx"


def error_category(exc: BaseException) -> str:
    if isinstance(exc, error.HTTPError):
        return f"http_{status_class(exc.code)}"
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return "timeout"
    if isinstance(exc, ConnectionRefusedError):
        return "connection_refused"
    if isinstance(exc, socket.gaierror):
        return "name_resolution_error"
    if isinstance(exc, error.URLError):
        reason = exc.reason
        if isinstance(reason, BaseException):
            return error_category(reason)
        return "url_error"
    if isinstance(exc, StopIteration):
        return "login_form_not_found"
    if isinstance(exc, ValueError):
        return "invalid_smoke_target"
    if isinstance(exc, OSError):
        return "network_error"
    return "unexpected_error"


def normalize_url(url: str) -> str:
    parsed = parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("smoke target must be an http(s) URL")
    return parse.urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path or "/",
            "",
            parsed.query,
            "",
        )
    )


def same_normalized_url(left: str, right: str) -> bool:
    return normalize_url(left) == normalize_url(right)


def classify_redirect(location: str | None) -> str:
    if not location:
        return "none"
    if "/protocol/openid-connect/auth" in location:
        return "keycloak_oidc_auth"
    return "other"


def head_status_and_location(url: str, *, timeout_sec: float) -> tuple[int, str | None]:
    parsed = parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("smoke target must be an http(s) URL")
    path = parse.urlunparse(("", "", parsed.path or "/", parsed.params, parsed.query, ""))
    connection_cls = (
        http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    )
    connection = connection_cls(parsed.hostname, parsed.port, timeout=timeout_sec)
    try:
        connection.request("HEAD", path)
        response = connection.getresponse()
        return response.status, response.getheader("location")
    finally:
        connection.close()


def check_proxy_requires_login(config: SmokeConfig) -> SmokeCheck:
    try:
        status, location = head_status_and_location(
            config.proxy_url, timeout_sec=config.timeout_sec
        )
    except Exception as exc:  # noqa: BLE001 - safe category is the public result.
        return SmokeCheck(
            "proxy_requires_login",
            False,
            {"error_category": error_category(exc)},
        )
    redirect_target = classify_redirect(location)
    passed = status == 302 and redirect_target == "keycloak_oidc_auth"
    return SmokeCheck(
        "proxy_requires_login",
        passed,
        {
            "status_class": status_class(status),
            "redirect_target": redirect_target,
        },
    )


def check_keycloak_discovery(config: SmokeConfig) -> SmokeCheck:
    try:
        status, _location = head_status_and_location(
            config.keycloak_discovery_url,
            timeout_sec=config.timeout_sec,
        )
    except Exception as exc:  # noqa: BLE001 - safe category is the public result.
        return SmokeCheck(
            "keycloak_discovery_ok",
            False,
            {"error_category": error_category(exc)},
        )
    return SmokeCheck(
        "keycloak_discovery_ok",
        status == 200,
        {"status_class": status_class(status)},
    )


def check_query_doctor_upstream_private(config: SmokeConfig) -> SmokeCheck:
    sock = socket.socket()
    sock.settimeout(config.timeout_sec)
    try:
        sock.connect((config.upstream_host, config.upstream_port))
    except OSError as exc:
        return SmokeCheck(
            "query_doctor_upstream_private",
            True,
            {"connection": "blocked", "blocked_category": error_category(exc)},
        )
    finally:
        sock.close()
    return SmokeCheck(
        "query_doctor_upstream_private",
        False,
        {"connection": "open"},
    )


def login_form_from_html(html: str) -> dict[str, object]:
    parser = LoginFormParser()
    parser.feed(html)
    return next(
        form
        for form in parser.forms
        if "login-actions" in str(form["action"])
        or "username" in form["inputs"]
        or "password" in form["inputs"]
    )


def cookie_header(cookie_jar: CookieJar) -> str:
    return "; ".join(f"{cookie.name}={cookie.value}" for cookie in cookie_jar)


def check_synthetic_login(config: SmokeConfig) -> SmokeCheck:
    jar = CookieJar()
    opener = request.build_opener(request.HTTPCookieProcessor(jar))
    try:
        login_page = opener.open(config.proxy_url, timeout=config.timeout_sec)
        login_html = login_page.read().decode("utf-8", errors="replace")
        login_form = login_form_from_html(login_html)
        inputs = login_form["inputs"]
        assert isinstance(inputs, dict)
        form_data: dict[str, str] = {str(key): str(value) for key, value in inputs.items()}
        form_data.update({"username": config.username, "password": config.password})
        post_data = parse.urlencode(form_data).encode("utf-8")
        action = parse.urljoin(login_page.geturl(), str(login_form["action"]))
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Cookie": cookie_header(jar),
        }
        login_request = request.Request(
            action,
            data=post_data,
            headers=headers,
            method="POST",
        )
        post_response = opener.open(login_request, timeout=config.timeout_sec)
        post_response.read()
        response = opener.open(config.proxy_url, timeout=config.timeout_sec)
        body = response.read().decode("utf-8", errors="replace")
        landed_on_query_doctor = same_normalized_url(response.geturl(), config.proxy_url)
        still_on_keycloak_login = "login-actions" in body or 'id="kc-form-login"' in body
        query_doctor_visible = "Query Doctor" in body
        passed = landed_on_query_doctor and not still_on_keycloak_login and query_doctor_visible
        return SmokeCheck(
            "synthetic_oidc_login_lands_on_query_doctor",
            passed,
            {
                "status_class": status_class(response.status),
                "final_target": "query_doctor_proxy_root" if landed_on_query_doctor else "other",
                "login_form_seen": True,
                "still_on_keycloak_login": still_on_keycloak_login,
                "query_doctor_visible": query_doctor_visible,
            },
        )
    except Exception as exc:  # noqa: BLE001 - safe category is the public result.
        return SmokeCheck(
            "synthetic_oidc_login_lands_on_query_doctor",
            False,
            {
                "error_category": error_category(exc),
                "login_form_seen": False if isinstance(exc, StopIteration) else "unknown",
            },
        )


def run_checks(config: SmokeConfig) -> tuple[SmokeCheck, ...]:
    return (
        check_proxy_requires_login(config),
        check_keycloak_discovery(config),
        check_query_doctor_upstream_private(config),
        check_synthetic_login(config),
    )


def smoke_payload(
    config: SmokeConfig, checks: Sequence[SmokeCheck] | None = None
) -> dict[str, Any]:
    resolved_checks = tuple(checks if checks is not None else run_checks(config))
    return {
        "kind": SMOKE_KIND,
        "all_passed": all(check.passed for check in resolved_checks),
        "check_count": len(resolved_checks),
        "checks": [check.raw_free_summary() for check in resolved_checks],
        "raw_values_output": "no",
    }


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a dev-only live smoke for dev/sso Keycloak and oauth2-proxy. "
            "The output is raw-free and does not print cookies, tokens, code/state, "
            "URLs, usernames, login secrets, or header values."
        )
    )
    parser.add_argument("--proxy-url", default=DEFAULT_PROXY_URL)
    parser.add_argument("--keycloak-discovery-url", default=DEFAULT_KEYCLOAK_DISCOVERY_URL)
    parser.add_argument("--upstream-host", default=DEFAULT_UPSTREAM_HOST)
    parser.add_argument("--upstream-port", type=int, default=DEFAULT_UPSTREAM_PORT)
    parser.add_argument("--username", default=DEFAULT_USERNAME)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--timeout-sec", type=float, default=10.0)
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Print compact JSON instead of indented JSON.",
    )
    return parser.parse_args(argv)


def config_from_args(args: argparse.Namespace) -> SmokeConfig:
    return SmokeConfig(
        proxy_url=args.proxy_url,
        keycloak_discovery_url=args.keycloak_discovery_url,
        upstream_host=args.upstream_host,
        upstream_port=args.upstream_port,
        username=args.username,
        password=args.password,
        timeout_sec=args.timeout_sec,
    )


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    payload = smoke_payload(config_from_args(args))
    print(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":") if args.compact else None,
            indent=None if args.compact else 2,
        )
    )
    return 0 if payload["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
