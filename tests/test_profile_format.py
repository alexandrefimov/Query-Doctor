from query_doctor.analyzer.profile_format import (
    build_profile_format_facts,
    detect_profile_dialect,
)
from query_doctor.analyzer.profile_text import normalize_profile_text


def test_detects_classic_text_profile():
    profile = """
Summary:
  Impala Version: impalad version 5.0.0 RELEASE
ExecSummary:
F00:
  HDFS_SCAN_NODE (id=00)
    - RowsProduced: 10 (10)
"""

    detection = detect_profile_dialect(profile)
    facts = build_profile_format_facts(profile)

    assert detection.dialect.value == "classic_text_profile"
    assert facts["profile_dialect"] == "classic_text_profile"
    assert facts["analysis_support"] == "supported"
    assert facts["primary_bottleneck_policy"] == "supported"


def test_detects_classic_json_profile_without_claiming_full_parser_support():
    profile = """
{
  "profile_version": 1,
  "runtime_profile": {
    "name": "Query",
    "children": [{"name": "Fragment"}],
    "counters": []
  }
}
"""

    facts = build_profile_format_facts(profile)

    assert facts["profile_dialect"] == "classic_json_profile"
    assert facts["analysis_support"] == "limited"
    assert facts["primary_bottleneck_policy"] == "unsupported"
    assert any(item["id"] == "profile_dialect_partially_mapped" for item in facts["limitations"])


def test_classic_json_profile_maps_allowlisted_counters_without_primary_support():
    raw_profile = """
{
  "profile_version": 1,
  "runtime_profile": {
    "name": "Query",
    "counters": [
      {"name": "TotalTime", "value": "100s"},
      {"name": "ClientFetchWaitTimer", "value": "45s"},
      {"name": "ScratchBytesWritten", "value": "4.0 KiB"},
      {"name": "SensitiveFutureCounter", "value": "do not expose"}
    ]
  }
}
"""

    normalized = normalize_profile_text(raw_profile)
    facts = build_profile_format_facts(normalized, raw_text=raw_profile)

    assert normalized.startswith("# JSON mapped profile counters")
    assert "- TotalTime: 100s" in normalized
    assert "- ClientFetchWaitTimer: 45s" in normalized
    assert "- ScratchBytesWritten: 4.0 KiB" in normalized
    assert "SensitiveFutureCounter" not in normalized
    assert facts["profile_dialect"] == "classic_json_profile"
    assert facts["layout"] == "json_mapped_counters"
    assert facts["features"]["json_mapped_counter_count"] == 3
    assert facts["analysis_support"] == "limited"
    assert facts["primary_bottleneck_policy"] == "unsupported"


def test_classic_json_profile_maps_numeric_counter_units():
    raw_profile = """
{
  "profile_version": 1,
  "runtime_profile": {
    "counters": [
      {"name": "TotalTime", "value": 1000000000, "unit": "TIME_NS"},
      {"name": "ScratchBytesWritten", "value": 4096, "unit": "BYTES"}
    ]
  }
}
"""

    normalized = normalize_profile_text(raw_profile)

    assert "- TotalTime: 1s" in normalized
    assert "- ScratchBytesWritten: 4.00 KiB" in normalized


def test_detects_json_wrapped_classic_text_as_effective_text_profile():
    raw_profile = """
{
  "details": "Summary:\\nExecSummary:\\nF00:\\n  HDFS_SCAN_NODE (id=00)\\n"
}
"""
    normalized_profile = "Summary:\nExecSummary:\nF00:\n  HDFS_SCAN_NODE (id=00)\n"

    facts = build_profile_format_facts(normalized_profile, raw_text=raw_profile)

    assert facts["profile_dialect"] == "classic_text_profile"
    assert facts["dialect_reasons"] == ["json_wrapped_classic_text_profile"]
    assert facts["analysis_support"] == "supported"


def test_detects_experimental_profile_v2_as_limited():
    profile = """
{
  "profile_version": 2,
  "aggregated_profile": {
    "fragments": []
  }
}
"""

    facts = build_profile_format_facts(profile)

    assert facts["profile_dialect"] == "experimental_profile_v2"
    assert facts["analysis_support"] == "limited"
    assert facts["primary_bottleneck_policy"] == "non_profile_only"
    assert facts["per_instance_evidence"] == "unknown"
    assert any(item["id"] == "profile_v2_limited" for item in facts["limitations"])


def test_detects_classic_thrift_profile_as_limited():
    profile = "TQueryProfile(profile=TRuntimeProfileTree(nodes=[]))"

    facts = build_profile_format_facts(profile)

    assert facts["profile_dialect"] == "classic_thrift_profile"
    assert facts["analysis_support"] == "limited"
    assert facts["primary_bottleneck_policy"] == "unsupported"


def test_unknown_profile_fails_closed():
    facts = build_profile_format_facts("not a recognized runtime profile")

    assert facts["profile_dialect"] == "unknown"
    assert facts["profile_family"] == "unknown"
    assert facts["analysis_support"] == "unsupported"
    assert facts["primary_bottleneck_policy"] == "unsupported"
    assert any(item["id"] == "profile_dialect_unknown" for item in facts["limitations"])
