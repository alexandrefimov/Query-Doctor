import urllib.request

import pytest

from query_doctor.cm.client import CMHttpClient, DEFAULT_MAX_CM_RESPONSE_BYTES
from query_doctor.cm.models import CMHttpConfig
from query_doctor.impala.admission_context import fetch_impala_admission_context
from query_doctor.impala.daemon_identity import fetch_impala_daemon_identity
from query_doctor.impala.profile_docs import fetch_impala_profile_docs_context
from query_doctor.impala.profile_source import fetch_impala_profile_text
from query_doctor.impala.query_discovery import fetch_impala_query_summaries
from query_doctor.prometheus.timeseries import PrometheusClient, PrometheusConfig
from query_doctor.report import llm_client
from query_doctor.safety.http_egress import (
    CONFIGURED_DIAGNOSTIC_HTTP_POLICY,
    PUBLIC_HTTP_POLICY,
    NoRedirectHandler,
    UnsafeHttpTargetError,
    configured_diagnostic_urlopen,
    make_safe_urlopen,
    public_urlopen_no_redirect,
    validate_http_url_target,
)
from query_doctor.spark.history_server import (
    SparkHistoryNoRedirectHandler,
    collect_spark_history_server_compact_summary,
    spark_history_urlopen_no_redirect,
)


def public_resolver(_host: str, _port: int):
    return ("93.184.216.34",)


@pytest.mark.parametrize(
    "url",
    (
        "http://0.0.0.0/",
        "http://169.254.169.254/",
        "http://192.0.2.10/",
        "http://198.51.100.10/",
        "http://203.0.113.10/",
        "http://224.0.0.1/",
        "http://[fe80::1]/",
        "http://[2001:db8::1]/",
        "http://metadata/",
        "http://" + ".".join(("metadata", "google", "internal")) + "/",
        "http://compute." + ".".join(("metadata", "google", "internal")) + "/",
    ),
)
def test_http_egress_rejects_unsafe_targets_even_for_configured_policy(url):
    with pytest.raises(UnsafeHttpTargetError):
        validate_http_url_target(
            url,
            policy=CONFIGURED_DIAGNOSTIC_HTTP_POLICY,
            resolver=public_resolver,
        )


@pytest.mark.parametrize(
    "url",
    (
        "http://127.0.0.1:7180/",
        "http://localhost:11434/",
        "http://10.10.0.5:7180/",
        "http://172.16.0.5:25000/",
        "http://192.168.1.10:9090/",
        "http://[fc00::1]:25000/",
    ),
)
def test_http_egress_requires_opt_in_for_loopback_or_private_targets(url):
    with pytest.raises(UnsafeHttpTargetError):
        validate_http_url_target(url, policy=PUBLIC_HTTP_POLICY, resolver=public_resolver)

    validate_http_url_target(
        url,
        policy=CONFIGURED_DIAGNOSTIC_HTTP_POLICY,
        resolver=public_resolver,
    )


@pytest.mark.parametrize(
    ("resolved_address", "policy", "allowed"),
    (
        ("93.184.216.34", PUBLIC_HTTP_POLICY, True),
        ("10.0.0.5", PUBLIC_HTTP_POLICY, False),
        ("10.0.0.5", CONFIGURED_DIAGNOSTIC_HTTP_POLICY, True),
        ("127.0.0.1", PUBLIC_HTTP_POLICY, False),
        ("127.0.0.1", CONFIGURED_DIAGNOSTIC_HTTP_POLICY, True),
        ("169.254.169.254", CONFIGURED_DIAGNOSTIC_HTTP_POLICY, False),
    ),
)
def test_http_egress_validates_dns_resolved_addresses(resolved_address, policy, allowed):
    def resolver(_host: str, _port: int):
        return (resolved_address,)

    if allowed:
        validate_http_url_target(
            "https://service.example.com/api", policy=policy, resolver=resolver
        )
    else:
        with pytest.raises(UnsafeHttpTargetError):
            validate_http_url_target(
                "https://service.example.com/api",
                policy=policy,
                resolver=resolver,
            )


def test_http_egress_blocks_integer_ip_aliases_after_resolution():
    def resolver(_host: str, _port: int):
        return ("127.0.0.1",)

    with pytest.raises(UnsafeHttpTargetError):
        validate_http_url_target("http://2130706433/", policy=PUBLIC_HTTP_POLICY, resolver=resolver)


def test_safe_urlopen_blocks_unsafe_target_before_transport(monkeypatch):
    called = False

    def fake_build_opener(*_handlers):
        nonlocal called
        called = True
        raise AssertionError("transport opener must not be built for blocked targets")

    monkeypatch.setattr(urllib.request, "build_opener", fake_build_opener)
    opener = make_safe_urlopen(CONFIGURED_DIAGNOSTIC_HTTP_POLICY, resolver=public_resolver)
    request = urllib.request.Request("http://169.254.169.254/latest/meta-data")

    with pytest.raises(UnsafeHttpTargetError):
        opener(request, timeout=1)

    assert called is False


def test_no_redirect_handlers_disable_redirects():
    assert NoRedirectHandler().redirect_request(None, None, None, None) is None
    assert SparkHistoryNoRedirectHandler().redirect_request(None, None, None, None) is None


def test_http_clients_use_safe_default_openers():
    cm_client = CMHttpClient(CMHttpConfig(cm_url="https://cm.example.com:7183"))
    prometheus_client = PrometheusClient(PrometheusConfig("https://prom.example.com"))

    assert cm_client.opener is configured_diagnostic_urlopen
    assert prometheus_client.opener is configured_diagnostic_urlopen
    assert collect_spark_history_server_compact_summary.__kwdefaults__["opener"] is (
        spark_history_urlopen_no_redirect
    )
    assert fetch_impala_profile_text.__kwdefaults__["opener"] is configured_diagnostic_urlopen
    assert fetch_impala_daemon_identity.__kwdefaults__["opener"] is configured_diagnostic_urlopen
    assert fetch_impala_profile_docs_context.__kwdefaults__["opener"] is (
        configured_diagnostic_urlopen
    )
    assert fetch_impala_admission_context.__kwdefaults__["opener"] is (
        configured_diagnostic_urlopen
    )
    assert fetch_impala_query_summaries.__kwdefaults__["opener"] is configured_diagnostic_urlopen
    assert llm_client.configured_diagnostic_urlopen is configured_diagnostic_urlopen
    assert spark_history_urlopen_no_redirect is not public_urlopen_no_redirect


def test_cm_get_json_uses_default_parent_side_response_cap():
    seen_sizes: list[int] = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self, size=-1):
            seen_sizes.append(size)
            return b'{"ok": true}'

    def fake_opener(request, timeout=None, context=None):
        return FakeResponse()

    client = CMHttpClient(
        CMHttpConfig(cm_url="https://cm.example.com:7183"),
        opener=fake_opener,
    )

    assert client.get_json("/api/v1/test") == {"ok": True}
    assert seen_sizes == [DEFAULT_MAX_CM_RESPONSE_BYTES + 1]
