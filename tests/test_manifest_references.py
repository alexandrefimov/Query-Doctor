from __future__ import annotations

import pytest

from query_doctor.safety.manifest_references import is_safe_relative_json_reference


@pytest.mark.parametrize(
    "value",
    (
        "boundary.json",
        ".json",
        "suite/boundary.json",
        "suite/./boundary.json",
        "nested/safe_name_1.json",
    ),
)
def test_safe_relative_json_reference_accepts_relative_json_paths(value: str) -> None:
    assert is_safe_relative_json_reference(value) is True


@pytest.mark.parametrize(
    "value",
    (
        "",
        "/tmp/boundary.json",
        "../boundary.json",
        "suite/../boundary.json",
        "boundary.txt",
        "boundary.json.bak",
        "suite\\boundary.json",
        123,
        None,
    ),
)
def test_safe_relative_json_reference_rejects_unsafe_values(value: object) -> None:
    assert is_safe_relative_json_reference(value) is False
