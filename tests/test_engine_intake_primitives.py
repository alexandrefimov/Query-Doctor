from __future__ import annotations

import pytest

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.analyzer.engine_intake_primitives import (
    json_size,
    max_json_depth,
    non_negative_int,
    safe_label_list,
)


def test_engine_intake_json_size_keeps_compact_and_default_modes_distinct() -> None:
    payload = {"b": [1, 2], "a": {"nested": "value"}}

    compact_size = json_size(payload, payload_label="payload", compact=True)
    default_size = json_size(payload, payload_label="payload", compact=False)

    assert compact_size == len(b'{"a":{"nested":"value"},"b":[1,2]}')
    assert default_size == len(b'{"a": {"nested": "value"}, "b": [1, 2]}')
    assert default_size > compact_size


def test_engine_intake_json_size_rejects_non_finite_payload_without_echo() -> None:
    with pytest.raises(EngineFactContractError, match="payload must be finite JSON"):
        json_size(
            {"value": float("nan")},
            payload_label="payload",
            error_message="payload must be finite JSON",
            compact=False,
        )


def test_engine_intake_max_json_depth_supports_trino_and_spark_modes() -> None:
    payload = {"outer": [{"inner": 1}]}

    assert max_json_depth(payload, count_scalar=False, sequence_types=(list,)) == 3
    assert max_json_depth(payload, count_scalar=True, sequence_types=(list,)) == 4


def test_engine_intake_safe_label_list_rejects_unsafe_values() -> None:
    with pytest.raises(EngineFactContractError, match="unsafe"):
        safe_label_list(
            {"labels": ["safe_label", "https://example.invalid/raw"]},
            "labels",
            missing_message="missing",
            unsafe_message="unsafe",
            empty_message="empty",
            allow_empty=False,
        )


def test_engine_intake_non_negative_int_rejects_bool() -> None:
    with pytest.raises(EngineFactContractError, match="invalid"):
        non_negative_int({"count": True}, "count", invalid_message="invalid")
