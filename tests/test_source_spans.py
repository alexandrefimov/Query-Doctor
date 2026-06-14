import pytest

from query_doctor.source_spans import (
    SOURCE_LINE_SPAN_SOURCE_LEGACY_COORDINATE,
    SOURCE_LINE_SPAN_SOURCE_SQL_PARSER,
    SourceLineSpan,
    format_source_line_span,
    parse_source_coordinate,
    safe_source_line_span_source,
    source_line_span_from_payload,
    source_line_span_payload,
)


def test_source_line_span_formats_single_line_and_range():
    assert format_source_line_span(SourceLineSpan(3, 3)) == "line 3"
    assert format_source_line_span(SourceLineSpan(3, 8)) == "lines 3-8"
    assert source_line_span_payload(SourceLineSpan(3, 8)) == {
        "start_line": 3,
        "end_line": 8,
    }


def test_source_line_span_rejects_invalid_ranges():
    with pytest.raises(ValueError):
        SourceLineSpan(0, 1)
    with pytest.raises(ValueError):
        SourceLineSpan(5, 4)
    with pytest.raises(ValueError):
        SourceLineSpan(1, 1_000_000)
    with pytest.raises(ValueError):
        SourceLineSpan(True, 1)


def test_parse_source_coordinate_accepts_only_safe_coordinate_shapes():
    assert parse_source_coordinate("line 12") == SourceLineSpan(12, 12)
    assert parse_source_coordinate("lines 12-14") == SourceLineSpan(12, 14)
    assert parse_source_coordinate("SELECT secret FROM table") is None
    assert parse_source_coordinate("line 000012") is None
    assert parse_source_coordinate("lines 14-12") is None
    assert parse_source_coordinate("line 1000000") is None


def test_source_line_span_payload_parser_rejects_unsafe_values():
    assert source_line_span_from_payload({"start_line": 7, "end_line": 9}) == SourceLineSpan(7, 9)
    assert source_line_span_from_payload({"start_line": True, "end_line": 9}) is None
    assert source_line_span_from_payload({"start_line": 7, "end_line": "9"}) is None
    assert source_line_span_from_payload({"start_line": 10, "end_line": 9}) is None
    assert source_line_span_from_payload("lines 7-9") is None


def test_source_line_span_source_is_allowlisted_and_safe():
    assert (
        safe_source_line_span_source(SOURCE_LINE_SPAN_SOURCE_SQL_PARSER)
        == SOURCE_LINE_SPAN_SOURCE_SQL_PARSER
    )
    assert (
        safe_source_line_span_source(
            "SELECT secret_col FROM table",
            fallback=SOURCE_LINE_SPAN_SOURCE_LEGACY_COORDINATE,
        )
        == SOURCE_LINE_SPAN_SOURCE_LEGACY_COORDINATE
    )
    assert safe_source_line_span_source("SELECT secret_col FROM table") == ""
