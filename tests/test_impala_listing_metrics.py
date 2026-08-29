"""The coordinator listing carries metrics; the summary has to keep them."""

import pytest

from query_doctor.impala.query_discovery import (
    parse_admission_wait_ms,
    parse_impala_query_entry,
    parse_nonnegative_count,
    parse_size_bytes,
)


GIB = 1024**3
MIB = 1024**2


# One completed query as /queries?json actually serves it, values verbatim.
COORDINATOR_ROW = {
    "query_id": "e94f2b1a3c5d6e70:8f9a0b1c00000000",
    "stmt_type": "QUERY",
    "state": "FINISHED",
    "effective_user": "job-example",
    "start_time": "2026-08-29 21:14:02.115357000",
    "end_time": "2026-08-29 21:14:04.679412000",
    "duration": "2s564ms",
    "rows_fetched": 22643,
    "bytes_read": "1000.40 MB",
    "bytes_sent": "1017.80 KB",
    "mem_usage": "16.52 GB",
    "mem_est": "30.71 GB",
    "queued_duration": "0",
    "resource_pool": "default-pool",
    "stmt": "select id from marts.orders",
}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("11.43 GB", int(11.43 * GIB)),
        ("989.45 MB", int(989.45 * MIB)),
        ("1017.80 KB", int(1017.80 * 1024)),
        ("512 B", 512),
        ("0", 0),
        (12345, 12345),
        ("", None),
        (None, None),
        (True, None),
        ("not a size", None),
    ],
)
def test_coordinator_sizes_are_read_as_binary_units(value, expected):
    # Impala prints binary units under decimal names, so GB is 1024**3. Reading
    # them as decimal would understate every suspicion threshold.
    assert parse_size_bytes(value) == expected


def test_rows_fetched_becomes_rows_produced():
    assert parse_nonnegative_count(22643) == 22643
    assert parse_nonnegative_count("1,813,050") == 1813050
    assert parse_nonnegative_count(-1) is None
    assert parse_nonnegative_count(None) is None
    assert parse_nonnegative_count(True) is None


def test_queued_duration_becomes_admission_wait():
    assert parse_admission_wait_ms({"queued_duration": "0"}) == 0
    assert parse_admission_wait_ms({"queued_duration": "1s500ms"}) == 1500
    assert parse_admission_wait_ms({"admission_wait_ms": 250}) == 250
    assert parse_admission_wait_ms({}) is None


def test_listing_metrics_reach_the_summary():
    summary = parse_impala_query_entry(COORDINATOR_ROW, default_status=None)

    assert summary is not None
    assert summary.duration_ms == 2564
    assert summary.rows_produced == 22643
    assert summary.bytes_read == int(1000.40 * MIB)
    assert summary.bytes_sent == int(1017.80 * 1024)
    # mem_usage is the sum of the per-node peaks, not the largest of them, so it
    # is the aggregate. The listing carries no per-node figure.
    assert summary.memory_aggregate_peak == int(16.52 * GIB)
    assert summary.memory_per_node_peak is None
    assert summary.admission_wait_ms == 0
    # The coordinator calls the pool resource_pool; the older keys stay accepted.
    assert summary.pool == "default-pool"


def test_a_listing_without_metrics_still_parses():
    summary = parse_impala_query_entry(
        {"query_id": "aa11bb22cc33dd44:ee55ff6600000000", "duration": "3s", "state": "FINISHED"},
        default_status=None,
    )

    assert summary is not None
    assert summary.duration_ms == 3000
    assert summary.rows_produced is None
    assert summary.bytes_read is None
    assert summary.memory_aggregate_peak is None
    assert summary.admission_wait_ms is None
