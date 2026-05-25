from query_doctor.analyzer.runtime_filters import build_runtime_filter_facts


CLASSIC_TEXT_FORMAT = {"dialect": "classic_text_profile"}
COMPLETE_NODES = {"runtime_filter_effectiveness": "supported"}


def test_runtime_filter_plan_arrows_are_context_only():
    facts = build_runtime_filter_facts(
        """
F01:PLAN FRAGMENT
|  02:HASH JOIN
|  |  runtime filters: RF001[bloom] <- join_key
|  03:HDFS SCAN
|     runtime filters: RF001[bloom] -> scan_key
""",
        CLASSIC_TEXT_FORMAT,
        COMPLETE_NODES,
    )

    assert facts["status"] == "context_only"
    assert facts["evidence_tier"] == "context_only"
    assert facts["finding_supported"] is False
    assert facts["primary_supported"] is False
    assert facts["runtime_filter_lines"] == 2
    assert facts["plan_filter_lines"] == 2
    assert facts["runtime_filter_id_count"] == 1
    assert facts["plan_producer_lines"] == 1
    assert facts["plan_consumer_lines"] == 1
    assert facts["filter_kind_counts"] == {"bloom": 2}
    assert facts["arrival_status"] == "not_reported"
    assert any("does not independently support" in item for item in facts["limitations"])


def test_runtime_filter_arrival_gaps_stay_context_only():
    facts = build_runtime_filter_facts(
        """
HDFS_SCAN_NODE (id=3)
  Runtime filters: Not all filters arrived (arrived: [], missing [0]), waited for 803ms
  - BloomFilterBytes: 2.0 MiB (2097152)
""",
        CLASSIC_TEXT_FORMAT,
        COMPLETE_NODES,
    )

    assert facts["status"] == "context_only"
    assert facts["runtime_filter_lines"] == 1
    assert facts["plan_filter_lines"] == 0
    assert facts["arrival_status"] == "missing_observed"
    assert facts["missing_arrival_lines"] == 1
    assert facts["max_arrival_wait_ms"] == 803
    assert facts["max_arrival_wait_human"] == "803ms"
    assert facts["bloom_filter_counter_lines"] == 1
    assert facts["bloom_filter_counter_nonzero_lines"] == 1
    assert facts["finding_supported"] is False
    assert facts["primary_supported"] is False
    assert any("keeps them as context" in item for item in facts["limitations"])


def test_runtime_filter_unknown_dialect_fails_closed():
    facts = build_runtime_filter_facts(
        "runtime filters: RF001[bloom] <- join_key\n",
        {"dialect": "classic_json_profile"},
        COMPLETE_NODES,
    )

    assert facts["status"] == "unknown"
    assert facts["evidence_tier"] == "unsupported"
    assert facts["runtime_filter_lines"] == 0
    assert facts["plan_filter_lines"] == 0
    assert facts["runtime_filter_id_count"] == 0
    assert facts["finding_supported"] is False
    assert facts["primary_supported"] is False
    assert any("not interpreted for this profile dialect" in item for item in facts["limitations"])


def test_runtime_filter_incomplete_nodes_limit_effectiveness():
    facts = build_runtime_filter_facts(
        "runtime filters: RF001[bloom] -> scan_key\n",
        CLASSIC_TEXT_FORMAT,
        {"runtime_filter_effectiveness": "limited"},
    )

    assert facts["status"] == "context_only"
    assert facts["exec_node_runtime_filter_effectiveness"] == "limited"
    assert any("Exec-node completeness limits" in item for item in facts["limitations"])


def test_runtime_filter_absence_is_not_observed():
    facts = build_runtime_filter_facts("", CLASSIC_TEXT_FORMAT, COMPLETE_NODES)

    assert facts["status"] == "not_observed"
    assert facts["evidence_tier"] == "unsupported"
    assert facts["arrival_status"] == "not_observed"
    assert facts["finding_supported"] is False
    assert facts["primary_supported"] is False
