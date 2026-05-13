from pathlib import Path

from query_doctor.cli import batch_recent


REPO_DIR = Path(__file__).resolve().parents[1]


def test_high_volume_recent_scan_keeps_bounded_results(monkeypatch, tmp_path):
    calls: list[tuple[int, str | None]] = []

    def fake_fetch_page(client, filters, page_token):
        del client
        calls.append((filters.page_size, page_token))
        offset = int(page_token or 0)
        if offset >= 6000:
            return batch_recent.cm_profiles.CMQueryPage(items=[])
        count = min(filters.page_size, 6000 - offset)
        return batch_recent.cm_profiles.CMQueryPage(
            items=[
                batch_recent.cm_profiles.CMQuerySummary(
                    query_id=f"q{offset + index:04d}:id",
                    duration_ms=(offset + index + 1) * 1000,
                    query_type="QUERY",
                    statement="SELECT 1",
                    status="succeeded",
                )
                for index in range(count)
            ]
        )

    monkeypatch.setattr(batch_recent, "make_cm_http_client", lambda config, env: object())
    monkeypatch.setattr(batch_recent.cm_profiles, "fetch_cm_query_summary_page", fake_fetch_page)

    args = batch_recent.parse_args(
        [
            "--out",
            str(tmp_path / "query-doctor-batch"),
            "--cm-url",
            "https://cm.example.net:7183",
            "--cluster",
            "cluster",
            "--service",
            "impala",
            "--cm-inspect-limit",
            "5000",
            "--triage-profile-limit",
            "5000",
            "--from-time",
            "2026-05-13T09:00:00Z",
            "--to-time",
            "2026-05-13T10:00:00Z",
            "--min-duration-sec",
            "10",
            "--order",
            "duration-desc",
            "--query-type",
            "QUERY",
        ]
    )
    config = batch_recent.build_batch_config(
        args,
        env={"CM_PASSWORD": "secret", "CM_USERNAME": "user"},
        cwd=tmp_path,
        repo_root=REPO_DIR,
    )

    discovery = batch_recent.discover_candidates(
        config,
        env={"CM_PASSWORD": "secret", "CM_USERNAME": "user"},
    )

    selected_ids = [
        candidate.summary.query_id for candidate in discovery.candidates if candidate.selected
    ]
    excluded_ids = [
        candidate.summary.query_id for candidate in discovery.candidates if not candidate.selected
    ]

    assert calls == [
        (1000, None),
        (1000, "1000"),
        (1000, "2000"),
        (1000, "3000"),
        (1000, "4000"),
        (1000, "5000"),
        (1000, "6000"),
    ]
    assert discovery.summaries_inspected == 6000
    assert discovery.scan_too_broad is False
    assert discovery.raw_summary_scan_cap_hit is False
    assert len(discovery.candidates) == 6000
    assert len(selected_ids) == 5000
    assert "q5999:id" in selected_ids
    assert "q0000:id" in excluded_ids
    assert "selected the top 5000 by scan order" in discovery.warnings[-1]
