#!/usr/bin/env python3
"""Smoke-check local web static assets, CSP, and security headers."""

from __future__ import annotations

import argparse
import http.client
import sys
from dataclasses import dataclass
from urllib.parse import urlsplit


SECURITY_HEADERS = {
    "cache-control": "no-store",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
}
STATIC_ASSETS = {
    "/static/app.css": ("text/css; charset=utf-8", "color-scheme:light"),
    "/static/app.js": ("application/javascript; charset=utf-8", "query-doctor-design"),
    "/static/theme-bootstrap.js": (
        "application/javascript; charset=utf-8",
        "query-doctor-theme",
    ),
}
STATIC_DENYLIST = (
    "/static/missing.css",
    "/static/../app.py",
    "/static/..%2fapp.py",
    "/static/./app.css",
    "/static/app.css/",
)
FORBIDDEN_STATIC_LEAKS = (
    "HTTP handler factory",
    "make_handler",
    "SECURITY_HEADERS",
)


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: bytes

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


def normalize_base_url(raw_url: str) -> tuple[str, int, str]:
    parsed = urlsplit(raw_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("URL must use http or https")
    if not parsed.hostname:
        raise ValueError("URL must include a host")
    if parsed.username or parsed.password:
        raise ValueError("URL must not include credentials")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    base_path = parsed.path.rstrip("/")
    return parsed.hostname, port, base_path


def fetch(host: str, port: int, path: str, *, timeout: float = 5.0) -> HttpResponse:
    connection = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        connection.request("GET", path, headers={"Host": f"{host}:{port}"})
        response = connection.getresponse()
        body = response.read()
        headers = {name.lower(): value for name, value in response.getheaders()}
        return HttpResponse(status=response.status, headers=headers, body=body)
    finally:
        connection.close()


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def header_value(response: HttpResponse, name: str) -> str:
    return response.headers.get(name.lower(), "")


def check_common_security_headers(
    response: HttpResponse,
    label: str,
    failures: list[str],
) -> None:
    for name, expected in SECURITY_HEADERS.items():
        actual = header_value(response, name)
        require(actual == expected, f"{label}: expected {name}: {expected!r}, got {actual!r}", failures)
    csp = header_value(response, "content-security-policy")
    require(csp, f"{label}: missing Content-Security-Policy", failures)
    require("'unsafe-inline'" not in csp, f"{label}: CSP must not contain 'unsafe-inline'", failures)
    for directive in (
        "default-src 'self'",
        "img-src 'self' data:",
        "style-src 'self'",
        "script-src 'self'",
        "connect-src 'self'",
        "base-uri 'none'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ):
        require(directive in csp, f"{label}: CSP missing {directive!r}", failures)


def check_content_length(response: HttpResponse, label: str, failures: list[str]) -> None:
    raw_length = header_value(response, "content-length")
    require(raw_length.isdigit(), f"{label}: missing numeric Content-Length", failures)
    if raw_length.isdigit():
        require(
            int(raw_length) == len(response.body),
            f"{label}: Content-Length {raw_length} does not match {len(response.body)} bytes",
            failures,
        )


def check_home(response: HttpResponse, failures: list[str]) -> None:
    label = "GET /"
    require(response.status == 200, f"{label}: expected 200, got {response.status}", failures)
    require(
        header_value(response, "content-type") == "text/html; charset=utf-8",
        f"{label}: unexpected Content-Type {header_value(response, 'content-type')!r}",
        failures,
    )
    check_common_security_headers(response, label, failures)
    check_content_length(response, label, failures)
    body = response.text
    require('<link rel="stylesheet" href="/static/app.css">' in body, f"{label}: missing app.css link", failures)
    require('<script src="/static/theme-bootstrap.js"></script>' in body, f"{label}: missing theme bootstrap script", failures)
    require('<script src="/static/app.js"></script>' in body, f"{label}: missing app.js script", failures)
    require("<style>" not in body, f"{label}: unexpected inline <style>", failures)
    require("color-scheme:light" not in body, f"{label}: product CSS leaked inline", failures)


def check_static_asset(
    response: HttpResponse,
    path: str,
    content_type: str,
    marker: str,
    failures: list[str],
) -> None:
    label = f"GET {path}"
    require(response.status == 200, f"{label}: expected 200, got {response.status}", failures)
    require(
        header_value(response, "content-type") == content_type,
        f"{label}: unexpected Content-Type {header_value(response, 'content-type')!r}",
        failures,
    )
    check_common_security_headers(response, label, failures)
    check_content_length(response, label, failures)
    require(marker in response.text, f"{label}: missing expected marker {marker!r}", failures)


def check_static_rejection(response: HttpResponse, path: str, failures: list[str]) -> None:
    label = f"GET {path}"
    require(response.status in {400, 404}, f"{label}: expected 400/404, got {response.status}", failures)
    for forbidden in FORBIDDEN_STATIC_LEAKS:
        require(forbidden not in response.text, f"{label}: response leaked {forbidden!r}", failures)


def run_smoke(base_url: str) -> list[str]:
    host, port, base_path = normalize_base_url(base_url)
    failures: list[str] = []
    home_path = f"{base_path}/" if base_path else "/"
    check_home(fetch(host, port, home_path), failures)
    for path, (content_type, marker) in STATIC_ASSETS.items():
        check_static_asset(fetch(host, port, path), path, content_type, marker, failures)
    for path in STATIC_DENYLIST:
        check_static_rejection(fetch(host, port, path), path, failures)
    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8766",
        help="Base URL for a running Query Doctor web UI.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        failures = run_smoke(args.url)
    except Exception as exc:  # noqa: BLE001 - CLI should report connection/setup failures plainly.
        print(f"web static smoke failed to run: {exc}", file=sys.stderr)
        return 2
    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    print(f"Web static smoke passed for {args.url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
