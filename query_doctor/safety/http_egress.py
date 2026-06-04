"""Shared fail-closed outbound HTTP target policy."""

from __future__ import annotations

import ipaddress
import socket
import ssl
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit


class UnsafeHttpTargetError(urllib.error.URLError):
    """Raised when outbound HTTP would target a disallowed destination."""


@dataclass(frozen=True)
class OutboundHttpPolicy:
    name: str
    allow_private_networks: bool = False
    allow_loopback: bool = False


PUBLIC_HTTP_POLICY = OutboundHttpPolicy("public http target")
CONFIGURED_DIAGNOSTIC_HTTP_POLICY = OutboundHttpPolicy(
    "configured diagnostic http target",
    allow_private_networks=True,
    allow_loopback=True,
)

Resolver = Callable[[str, int], Iterable[object]]
UrlOpener = Callable[..., Any]

BLOCKED_HOSTNAMES = frozenset({"metadata"})
BLOCKED_METADATA_SUFFIX = ".".join(("metadata", "google", "internal"))
BLOCKED_HOST_SUFFIXES = (f".{BLOCKED_METADATA_SUFFIX}",)
BLOCKED_EXACT_HOSTNAMES = frozenset({BLOCKED_METADATA_SUFFIX})
ALWAYS_BLOCKED_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in (
        "0.0.0.0/8",
        "169.254.0.0/16",
        "192.0.2.0/24",
        "198.18.0.0/15",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "224.0.0.0/4",
        "240.0.0.0/4",
        "255.255.255.255/32",
        "::/128",
        "2001:db8::/32",
        "fe80::/10",
        "ff00::/8",
    )
)
PRIVATE_OR_SHARED_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in (
        "10.0.0.0/8",
        "100.64.0.0/10",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "fc00::/7",
    )
)


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Disable redirects so every outbound target hop must pass policy."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def make_safe_urlopen(
    policy: OutboundHttpPolicy = CONFIGURED_DIAGNOSTIC_HTTP_POLICY,
    *,
    resolver: Resolver | None = None,
) -> UrlOpener:
    target_resolver = resolver or resolve_host_addresses

    def _safe_urlopen(
        request: Any,
        timeout: int | float | None = None,
        context: ssl.SSLContext | None = None,
    ) -> Any:
        validate_http_request_target(request, policy=policy, resolver=target_resolver)
        handlers: list[Any] = [NoRedirectHandler]
        if context is not None:
            handlers.append(urllib.request.HTTPSHandler(context=context))
        opener = urllib.request.build_opener(*handlers)
        return opener.open(request, timeout=timeout)

    return _safe_urlopen


def configured_diagnostic_urlopen(
    request: Any,
    timeout: int | float | None = None,
    context: ssl.SSLContext | None = None,
) -> Any:
    return _CONFIGURED_DIAGNOSTIC_URL_OPEN(request, timeout=timeout, context=context)


def public_urlopen_no_redirect(
    request: Any,
    timeout: int | float | None = None,
    context: ssl.SSLContext | None = None,
) -> Any:
    return _PUBLIC_URL_OPEN(request, timeout=timeout, context=context)


def validate_http_request_target(
    request: Any,
    *,
    policy: OutboundHttpPolicy,
    resolver: Resolver | None = None,
) -> None:
    url = getattr(request, "full_url", request)
    if not isinstance(url, str):
        raise UnsafeHttpTargetError("Outbound HTTP request target is not a URL.")
    validate_http_url_target(url, policy=policy, resolver=resolver or resolve_host_addresses)


def validate_http_url_target(
    url: str,
    *,
    policy: OutboundHttpPolicy,
    resolver: Resolver | None = None,
) -> None:
    parsed = urlsplit(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeHttpTargetError("Outbound HTTP target must be an http or https URL.")
    if parsed.username or parsed.password:
        raise UnsafeHttpTargetError("Outbound HTTP target must not include credentials.")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise UnsafeHttpTargetError("Outbound HTTP target port is invalid.") from exc

    host = parsed.hostname.rstrip(".").lower()
    validate_http_host(host, port=port, policy=policy, resolver=resolver or resolve_host_addresses)


def validate_http_host(
    host: str,
    *,
    port: int,
    policy: OutboundHttpPolicy,
    resolver: Resolver,
) -> None:
    if not host:
        raise UnsafeHttpTargetError("Outbound HTTP target host is required.")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in host):
        raise UnsafeHttpTargetError("Outbound HTTP target host contains controls.")
    if "%" in host:
        raise UnsafeHttpTargetError("Outbound HTTP target host is not allowed.")
    if (
        host in BLOCKED_HOSTNAMES
        or host in BLOCKED_EXACT_HOSTNAMES
        or any(host.endswith(suffix) for suffix in BLOCKED_HOST_SUFFIXES)
    ):
        raise UnsafeHttpTargetError("Outbound HTTP target host is not allowed.")
    if host == "localhost" or host.endswith(".localhost"):
        if not policy.allow_loopback:
            raise UnsafeHttpTargetError("Outbound HTTP loopback target requires explicit opt-in.")
        return

    literal_ip = parse_ip_address(host)
    if literal_ip is not None:
        validate_ip_address(literal_ip, policy=policy)
        return

    addresses = tuple(resolver(host, port))
    if not addresses:
        raise UnsafeHttpTargetError("Outbound HTTP target host did not resolve.")
    for address in addresses:
        parsed_address = parse_ip_address(str(address))
        if parsed_address is None:
            raise UnsafeHttpTargetError("Outbound HTTP resolver returned a non-IP address.")
        validate_ip_address(parsed_address, policy=policy)


def resolve_host_addresses(
    host: str,
    port: int,
) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise UnsafeHttpTargetError("Outbound HTTP target host could not be resolved.") from exc
    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        address = parse_ip_address(str(sockaddr[0]))
        if address is not None and address not in addresses:
            addresses.append(address)
    return tuple(addresses)


def parse_ip_address(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return None
    mapped_ipv4 = getattr(address, "ipv4_mapped", None)
    if mapped_ipv4 is not None:
        return mapped_ipv4
    return address


def validate_ip_address(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
    *,
    policy: OutboundHttpPolicy,
) -> None:
    if address.is_loopback:
        if policy.allow_loopback:
            return
        raise UnsafeHttpTargetError("Outbound HTTP loopback target requires explicit opt-in.")
    if (
        address.is_unspecified
        or address.is_link_local
        or address.is_multicast
        or ip_in_networks(address, ALWAYS_BLOCKED_NETWORKS)
    ):
        raise UnsafeHttpTargetError("Outbound HTTP target address is not allowed.")
    if address.is_reserved:
        raise UnsafeHttpTargetError("Outbound HTTP reserved target address is not allowed.")
    if ip_in_networks(address, PRIVATE_OR_SHARED_NETWORKS) or address.is_private:
        if policy.allow_private_networks:
            return
        raise UnsafeHttpTargetError("Outbound HTTP private target requires explicit opt-in.")


def ip_in_networks(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
    networks: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...],
) -> bool:
    return any(address.version == network.version and address in network for network in networks)


_CONFIGURED_DIAGNOSTIC_URL_OPEN = make_safe_urlopen(CONFIGURED_DIAGNOSTIC_HTTP_POLICY)
_PUBLIC_URL_OPEN = make_safe_urlopen(PUBLIC_HTTP_POLICY)
