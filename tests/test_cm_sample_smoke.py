import json
from pathlib import Path


REPO_DIR = Path(__file__).resolve().parents[1]


def load_sample_module():
    from query_doctor.cli import cm_sample_smoke

    return cm_sample_smoke


def test_package_entrypoint_keeps_repo_root_and_package_corpus_smoke():
    from query_doctor.cli import cm_sample_smoke, corpus_smoke

    assert cm_sample_smoke.REPO_DIR == REPO_DIR
    assert cm_sample_smoke.corpus_smoke is corpus_smoke


def write_config(tmp_path: Path) -> Path:
    path = tmp_path / "cm-config.json"
    path.write_text(
        json.dumps(
            {
                "cm_url": "https://cm.example.com:7183",
                "cluster": "CLUSTER",
                "service": "IMPALA",
            }
        ),
        encoding="utf-8",
    )
    return path


def base_args(config_path: Path, out_dir: Path) -> list[str]:
    return ["--config", str(config_path), "--out", str(out_dir)]


def summary(
    module, query_id, *, duration_ms=10_000, status="succeeded", query_type="QUERY", user="alice"
):
    return module.CMQuerySummary(
        query_id=query_id,
        duration_ms=duration_ms,
        status=status,
        query_type=query_type,
        user=user,
    )


def fake_summary_fetcher_factory(module, summaries):
    calls = []

    def fetcher(filters, page_token):
        calls.append((filters, page_token))
        return module.CMQueryPage(items=list(summaries))

    return fetcher, calls


def failing_summary_fetcher_factory(module, message):
    calls = []

    def fetcher(filters, page_token):
        calls.append((filters, page_token))
        raise module.CMClientError(message)

    return fetcher, calls


def fake_profile_fetcher_factory(profile_text="# profile\nUser: alice\nselect * from db.table\n"):
    calls = []

    def fetcher(summary_item, max_profile_bytes):
        calls.append((summary_item.query_id, max_profile_bytes))
        return profile_text

    return fetcher, calls


def fake_analyzer_factory(module, *, memory=0, cardinality=0, action_cards=False):
    calls = []

    def analyzer(case_dir: Path):
        calls.append(case_dir)
        action_cards_text = (
            "### Card 1: Severe deterministic evidence\n\n- Severe deterministic evidence was detected.\n"
            if action_cards
            else "No deterministic action cards were triggered from the parsed evidence.\n"
        )
        (case_dir / "analysis_facts.md").write_text(
            "\n".join(
                [
                    "## Summary",
                    "",
                    "- Parsed operators: 1",
                    f"- Cardinality anomalies: {cardinality}",
                    f"- Memory anomalies: {memory}",
                    "",
                    "## Action Cards",
                    "",
                    action_cards_text,
                    "## Findings",
                    "",
                    "No deterministic findings were produced from the digest.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return module.corpus_smoke.AnalyzerResult(0, "", "")

    return analyzer, calls


def fake_report_runner_factory():
    calls = []

    def runner(case_dir: Path, mode: str) -> int:
        calls.append((case_dir, mode))
        return 0

    return runner, calls


def test_default_is_dry_run_and_fetches_summaries_only(tmp_path, capsys):
    module = load_sample_module()
    config = write_config(tmp_path)
    out_dir = tmp_path / "corpus"
    fetcher, summary_calls = fake_summary_fetcher_factory(module, [summary(module, "a:b")])
    profile_fetcher, profile_calls = fake_profile_fetcher_factory()
    analyzer, analyzer_calls = fake_analyzer_factory(module)
    report_runner, report_calls = fake_report_runner_factory()

    result = module.main(
        base_args(config, out_dir),
        cwd=tmp_path,
        repo_root=REPO_DIR,
        summary_fetcher=fetcher,
        profile_fetcher=profile_fetcher,
        analyzer_runner=analyzer,
        report_runner=report_runner,
    )

    output = capsys.readouterr().out
    assert result == 0
    assert "Dry-run only" in output
    assert len(summary_calls) == 1
    assert profile_calls == []
    assert analyzer_calls == []
    assert report_calls == []
    assert not out_dir.exists()
    assert "Summary request plan:" not in output


def test_summary_fetch_http_401_warning_fails_dry_run_with_sanitized_message(tmp_path, capsys):
    module = load_sample_module()
    config = write_config(tmp_path)
    out_dir = tmp_path / "corpus"
    fetcher, summary_calls = failing_summary_fetcher_factory(
        module,
        (
            "HTTP 401 from CM: Full authentication is required to access this resource; "
            "Authorization: Bearer tokensecret password=topsecret"
        ),
    )
    profile_fetcher, profile_calls = fake_profile_fetcher_factory(
        "Runtime Profile\nselect secret_sql from example_guarded.table\n"
    )
    analyzer, analyzer_calls = fake_analyzer_factory(module)
    report_runner, report_calls = fake_report_runner_factory()

    result = module.main(
        base_args(config, out_dir) + ["--show-request-plan"],
        cwd=tmp_path,
        repo_root=REPO_DIR,
        env={
            "CM_PASSWORD": "topsecret",
            "CM_TOKEN": "tokensecret",
        },
        summary_fetcher=fetcher,
        profile_fetcher=profile_fetcher,
        analyzer_runner=analyzer,
        report_runner=report_runner,
    )

    output = capsys.readouterr().out
    assert result == 3
    assert len(summary_calls) == 1
    assert profile_calls == []
    assert analyzer_calls == []
    assert report_calls == []
    assert not out_dir.exists()
    assert "Summary warnings:" in output
    assert "- CM query summary fetch failed: HTTP 401 from CM" in output
    assert "Full authentication is required to access this resource" in output
    assert (
        "Hint: Check that CM_USERNAME/CM_PASSWORD or CM_TOKEN are set in the current shell."
        in output
    )
    assert (
        "Summary fetch failed; candidate selection was not evaluated as a normal zero-candidate result."
        in output
    )
    assert "Summary request plan:" in output
    assert "No candidates selected. Try increasing --max-duration-sec" not in output
    assert "topsecret" not in output
    assert "tokensecret" not in output
    assert "Authorization: Bearer" not in output
    assert "secret_sql" not in output
    assert "Runtime Profile" not in output
    assert '{"items"' not in output


def test_summary_fetch_tls_warning_fails_dry_run_without_tuning_hint(tmp_path, capsys):
    module = load_sample_module()
    config = write_config(tmp_path)
    out_dir = tmp_path / "corpus"
    fetcher, summary_calls = failing_summary_fetcher_factory(
        module,
        "TLS certificate verification failed",
    )
    profile_fetcher, profile_calls = fake_profile_fetcher_factory()
    analyzer, analyzer_calls = fake_analyzer_factory(module)
    report_runner, report_calls = fake_report_runner_factory()

    result = module.main(
        base_args(config, out_dir),
        cwd=tmp_path,
        repo_root=REPO_DIR,
        summary_fetcher=fetcher,
        profile_fetcher=profile_fetcher,
        analyzer_runner=analyzer,
        report_runner=report_runner,
    )

    output = capsys.readouterr().out
    assert result == 3
    assert len(summary_calls) == 1
    assert profile_calls == []
    assert analyzer_calls == []
    assert report_calls == []
    assert not out_dir.exists()
    assert "- CM query summary fetch failed: TLS certificate verification failed" in output
    assert "No candidates selected. Try increasing --max-duration-sec" not in output


def test_healthy_dry_run_with_no_selected_candidates_prints_diagnostics(tmp_path, capsys):
    module = load_sample_module()
    config = write_config(tmp_path)
    out_dir = tmp_path / "corpus"
    fetcher, summary_calls = fake_summary_fetcher_factory(
        module,
        [
            summary(module, "", duration_ms=1_000),
            summary(module, "missing:duration", duration_ms=None),
            summary(module, "too:slow", duration_ms=70_000),
            summary(module, "failed:1", duration_ms=1_000, status="failed"),
            summary(module, "ddl:1", duration_ms=1_000, query_type="DDL"),
        ],
    )
    profile_fetcher, profile_calls = fake_profile_fetcher_factory(
        "Runtime Profile\nselect secret_sql from example_guarded.table\n"
    )
    analyzer, analyzer_calls = fake_analyzer_factory(module)
    report_runner, report_calls = fake_report_runner_factory()

    result = module.main(
        base_args(config, out_dir) + ["--sample", "healthy", "--limit", "5"],
        cwd=tmp_path,
        repo_root=REPO_DIR,
        env={"CM_PASSWORD": "topsecret"},
        summary_fetcher=fetcher,
        profile_fetcher=profile_fetcher,
        analyzer_runner=analyzer,
        report_runner=report_runner,
    )

    output = capsys.readouterr().out
    assert result == 0
    assert len(summary_calls) == 1
    assert profile_calls == []
    assert analyzer_calls == []
    assert report_calls == []
    assert not out_dir.exists()
    assert "Selection diagnostics:" in output
    assert "- Summaries fetched: 5" in output
    assert "- Considered: 5" in output
    assert "- Selected: 0" in output
    assert "- Skipped missing query id: 1" in output
    assert "- Skipped missing duration: 1" in output
    assert "- Skipped duration > 60s: 1" in output
    assert "- Skipped non-success status: 1" in output
    assert "- Skipped non-QUERY type: 1" in output
    assert (
        "No candidates selected. Try increasing --max-duration-sec or --candidate-scan-limit"
        in output
    )
    assert "secret_sql" not in output
    assert "Runtime Profile" not in output
    assert "topsecret" not in output
    assert '{"items"' not in output


def test_successful_empty_summary_fetch_keeps_zero_candidate_tuning_hint(tmp_path, capsys):
    module = load_sample_module()
    config = write_config(tmp_path)
    out_dir = tmp_path / "corpus"
    fetcher, summary_calls = fake_summary_fetcher_factory(module, [])
    profile_fetcher, profile_calls = fake_profile_fetcher_factory()
    analyzer, analyzer_calls = fake_analyzer_factory(module)
    report_runner, report_calls = fake_report_runner_factory()

    result = module.main(
        base_args(config, out_dir),
        cwd=tmp_path,
        repo_root=REPO_DIR,
        summary_fetcher=fetcher,
        profile_fetcher=profile_fetcher,
        analyzer_runner=analyzer,
        report_runner=report_runner,
    )

    output = capsys.readouterr().out
    assert result == 0
    assert len(summary_calls) == 1
    assert profile_calls == []
    assert analyzer_calls == []
    assert report_calls == []
    assert not out_dir.exists()
    assert "- Summaries fetched: 0" in output
    assert "- Selected: 0" in output
    assert (
        "No candidates selected. Try increasing --max-duration-sec or --candidate-scan-limit"
        in output
    )
    assert "Summary fetch failed" not in output


def test_show_request_plan_prints_sanitized_summary_request_in_dry_run(tmp_path, capsys):
    module = load_sample_module()
    config = write_config(tmp_path)
    out_dir = tmp_path / "corpus"
    fetcher, summary_calls = fake_summary_fetcher_factory(module, [])
    profile_fetcher, profile_calls = fake_profile_fetcher_factory(
        "Runtime Profile\nselect secret_sql from example_guarded.table\n"
    )
    analyzer, analyzer_calls = fake_analyzer_factory(module)
    report_runner, report_calls = fake_report_runner_factory()

    result = module.main(
        base_args(config, out_dir) + ["--show-request-plan"],
        cwd=tmp_path,
        repo_root=REPO_DIR,
        env={
            "CM_PASSWORD": "topsecret",
            "CM_TOKEN": "tokensecret",
            "CM_USERNAME": "alice",
        },
        summary_fetcher=fetcher,
        profile_fetcher=profile_fetcher,
        analyzer_runner=analyzer,
        report_runner=report_runner,
    )

    output = capsys.readouterr().out
    assert result == 0
    assert len(summary_calls) == 1
    assert profile_calls == []
    assert analyzer_calls == []
    assert report_calls == []
    assert not out_dir.exists()
    assert "Summary request plan:" in output
    assert (
        "- Builder: query_doctor_collect_cm_profiles.build_cm_query_summary_page_request" in output
    )
    assert "- Endpoint path: /api/v32/clusters/CLUSTER/services/IMPALA/impalaQueries" in output
    assert "- Sample: healthy" in output
    assert "- Candidate scan limit: 50" in output
    assert "- Min duration seconds: <none>" in output
    assert "- Max duration seconds: 60" in output
    assert "- Page size: 50" in output
    assert "- Offset: <none>" in output
    assert "- Summary params:" in output
    assert output.index("  - from:") < output.index("  - limit:")
    assert output.index("  - limit:") < output.index("  - to:")
    assert "topsecret" not in output
    assert "tokensecret" not in output
    assert "Authorization" not in output
    assert "secret_sql" not in output
    assert "Runtime Profile" not in output
    assert '{"items"' not in output


def test_request_plan_param_sanitizer_redacts_defensive_secret_and_filter_values():
    module = load_sample_module()

    params = module.sanitized_request_params(
        {
            "authorization": "Bearer secret",
            "filter": "user = alice",
            "from": "2026-04-30T00:00:00Z",
            "limit": 50,
            "token": "tokensecret",
            "user": "alice",
        }
    )

    assert params == [
        ("authorization", "<redacted>"),
        ("filter", "<redacted-filter>"),
        ("from", "2026-04-30T00:00:00Z"),
        ("limit", "50"),
        ("token", "<redacted>"),
        ("user", "<redacted-user>"),
    ]


def test_apply_collects_at_most_limit_and_runs_analyzer(tmp_path):
    module = load_sample_module()
    config = write_config(tmp_path)
    out_dir = tmp_path / "corpus"
    fetcher, _summary_calls = fake_summary_fetcher_factory(
        module,
        [
            summary(module, "a:1", duration_ms=5_000),
            summary(module, "a:2", duration_ms=10_000),
            summary(module, "a:3", duration_ms=15_000),
        ],
    )
    profile_fetcher, profile_calls = fake_profile_fetcher_factory()
    analyzer, analyzer_calls = fake_analyzer_factory(module)

    result = module.main(
        base_args(config, out_dir) + ["--limit", "2", "--apply"],
        cwd=tmp_path,
        repo_root=REPO_DIR,
        summary_fetcher=fetcher,
        profile_fetcher=profile_fetcher,
        analyzer_runner=analyzer,
    )

    assert result == 0
    assert [item[0] for item in profile_calls] == ["a:1", "a:2"]
    assert len(analyzer_calls) == 2
    assert (out_dir / "a_1" / "profile_digest.md").exists()
    assert (out_dir / "a_2" / "profile_digest.md").exists()
    assert not (out_dir / "a_3").exists()


def test_rejects_limit_above_hard_max(tmp_path, capsys):
    module = load_sample_module()
    config = write_config(tmp_path)
    fetcher, _calls = fake_summary_fetcher_factory(module, [])

    result = module.main(
        base_args(config, tmp_path / "corpus") + ["--limit", "11"],
        cwd=tmp_path,
        repo_root=REPO_DIR,
        summary_fetcher=fetcher,
    )

    captured = capsys.readouterr()
    assert result == 2
    assert "--limit must be <= 10" in captured.err


def test_rejects_candidate_scan_limit_above_hard_max(tmp_path, capsys):
    module = load_sample_module()
    config = write_config(tmp_path)
    fetcher, _calls = fake_summary_fetcher_factory(module, [])

    result = module.main(
        base_args(config, tmp_path / "corpus") + ["--candidate-scan-limit", "201"],
        cwd=tmp_path,
        repo_root=REPO_DIR,
        summary_fetcher=fetcher,
    )

    captured = capsys.readouterr()
    assert result == 2
    assert "--candidate-scan-limit must be <= 200" in captured.err


def test_healthy_filter_selects_fast_successful_queries(tmp_path, capsys):
    module = load_sample_module()
    config = write_config(tmp_path)
    fetcher, _calls = fake_summary_fetcher_factory(
        module,
        [
            summary(module, "good:1", duration_ms=2_000, status="succeeded", query_type="QUERY"),
            summary(module, "slow:1", duration_ms=120_000, status="succeeded", query_type="QUERY"),
            summary(module, "failed:1", duration_ms=1_000, status="failed", query_type="QUERY"),
            summary(module, "ddl:1", duration_ms=1_000, status="succeeded", query_type="DDL"),
        ],
    )

    result = module.main(
        base_args(config, tmp_path / "corpus") + ["--sample", "healthy", "--limit", "5"],
        cwd=tmp_path,
        repo_root=REPO_DIR,
        summary_fetcher=fetcher,
    )

    output = capsys.readouterr().out
    assert result == 0
    assert "good:1" in output
    assert "slow:1" not in output
    assert "failed:1" not in output
    assert "ddl:1" not in output


def test_healthy_explicit_min_duration_selects_within_bounds(tmp_path, capsys):
    module = load_sample_module()
    config = write_config(tmp_path)
    out_dir = tmp_path / "corpus"
    fetcher, summary_calls = fake_summary_fetcher_factory(
        module,
        [
            summary(module, "ultra:1", duration_ms=10),
            summary(module, "short:1", duration_ms=4_000),
            summary(module, "good:1", duration_ms=5_000),
            summary(module, "good:2", duration_ms=10_000),
            summary(module, "slow:1", duration_ms=70_000),
        ],
    )
    profile_fetcher, profile_calls = fake_profile_fetcher_factory(
        "Runtime Profile\nselect secret_sql from example_guarded.table\n"
    )
    analyzer, analyzer_calls = fake_analyzer_factory(module)
    report_runner, report_calls = fake_report_runner_factory()

    result = module.main(
        base_args(config, out_dir)
        + [
            "--sample",
            "healthy",
            "--limit",
            "5",
            "--min-duration-sec",
            "5",
            "--max-duration-sec",
            "60",
            "--show-request-plan",
        ],
        cwd=tmp_path,
        repo_root=REPO_DIR,
        summary_fetcher=fetcher,
        profile_fetcher=profile_fetcher,
        analyzer_runner=analyzer,
        report_runner=report_runner,
    )

    output = capsys.readouterr().out
    assert result == 0
    assert len(summary_calls) == 1
    assert profile_calls == []
    assert analyzer_calls == []
    assert report_calls == []
    assert not out_dir.exists()
    assert "good:1" in output
    assert "good:2" in output
    assert "ultra:1" not in output
    assert "short:1" not in output
    assert "slow:1" not in output
    assert "- Skipped duration < 5s: 2" in output
    assert "- Skipped duration > 60s: 1" in output
    assert "- Min duration seconds: 5" in output
    assert "- Max duration seconds: 60" in output
    assert "secret_sql" not in output
    assert "Runtime Profile" not in output


def test_healthy_without_explicit_min_duration_can_select_ultra_fast_query(tmp_path, capsys):
    module = load_sample_module()
    config = write_config(tmp_path)
    fetcher, _calls = fake_summary_fetcher_factory(
        module,
        [
            summary(module, "ultra:1", duration_ms=10),
            summary(module, "good:1", duration_ms=5_000),
        ],
    )

    result = module.main(
        base_args(config, tmp_path / "corpus") + ["--sample", "healthy", "--limit", "1"],
        cwd=tmp_path,
        repo_root=REPO_DIR,
        summary_fetcher=fetcher,
    )

    output = capsys.readouterr().out
    assert result == 0
    assert "ultra:1" in output
    assert "good:1" not in output
    assert "Skipped duration <" not in output


def test_slow_filter_selects_long_queries(tmp_path, capsys):
    module = load_sample_module()
    config = write_config(tmp_path)
    fetcher, _calls = fake_summary_fetcher_factory(
        module,
        [
            summary(module, "fast:1", duration_ms=2_000),
            summary(module, "slow:1", duration_ms=400_000),
        ],
    )

    result = module.main(
        base_args(config, tmp_path / "corpus") + ["--sample", "slow"],
        cwd=tmp_path,
        repo_root=REPO_DIR,
        summary_fetcher=fetcher,
    )

    output = capsys.readouterr().out
    assert result == 0
    assert "slow:1" in output
    assert "fast:1" not in output


def test_slow_dry_run_reports_duration_below_min_skip(tmp_path, capsys):
    module = load_sample_module()
    config = write_config(tmp_path)
    fetcher, _calls = fake_summary_fetcher_factory(
        module,
        [
            summary(module, "fast:1", duration_ms=120_000),
        ],
    )

    result = module.main(
        base_args(config, tmp_path / "corpus") + ["--sample", "slow"],
        cwd=tmp_path,
        repo_root=REPO_DIR,
        summary_fetcher=fetcher,
    )

    output = capsys.readouterr().out
    assert result == 0
    assert "- Summaries fetched: 1" in output
    assert "- Considered: 1" in output
    assert "- Selected: 0" in output
    assert "- Skipped duration < 300s: 1" in output
    assert "No candidates selected." in output


def test_summary_pagination_stops_on_empty_page_with_next_token():
    module = load_sample_module()
    calls = []

    def fetcher(filters, page_token):
        calls.append(page_token)
        return module.CMQueryPage(items=[], next_page_token=f"next-{len(calls)}")

    filters = module.CMQueryFilters(
        cluster="CLUSTER",
        service="IMPALA",
        since_hours=24,
        limit=50,
        min_duration_sec=0,
        status="all",
    )

    summaries, warnings = module.collect_summary_candidates(filters, fetcher)

    assert summaries == []
    assert calls == [None]
    assert warnings == ["Stopped pagination because a summary page returned no items."]


def test_skips_missing_query_id_and_missing_duration_for_healthy(tmp_path, capsys):
    module = load_sample_module()
    config = write_config(tmp_path)
    fetcher, _calls = fake_summary_fetcher_factory(
        module,
        [
            summary(module, "", duration_ms=1_000),
            summary(module, "missing:duration", duration_ms=None),
            summary(module, "good:1", duration_ms=1_000),
        ],
    )

    result = module.main(
        base_args(config, tmp_path / "corpus") + ["--sample", "healthy"],
        cwd=tmp_path,
        repo_root=REPO_DIR,
        summary_fetcher=fetcher,
    )

    output = capsys.readouterr().out
    assert result == 0
    assert "good:1" in output
    assert "missing:duration" not in output


def test_apply_forces_redaction_and_passes_max_profile_bytes(tmp_path):
    module = load_sample_module()
    config = write_config(tmp_path)
    out_dir = tmp_path / "corpus"
    fetcher, _summary_calls = fake_summary_fetcher_factory(
        module, [summary(module, "a:1", user="alice")]
    )
    profile_fetcher, profile_calls = fake_profile_fetcher_factory(
        "User: alice\nemail alice@example.com\npassword=secret\nselect * from db.table\n"
    )
    analyzer, _analyzer_calls = fake_analyzer_factory(module)

    result = module.main(
        base_args(config, out_dir) + ["--apply", "--max-profile-bytes", "1234"],
        cwd=tmp_path,
        repo_root=REPO_DIR,
        summary_fetcher=fetcher,
        profile_fetcher=profile_fetcher,
        analyzer_runner=analyzer,
    )

    assert result == 0
    assert profile_calls == [("a:1", 1234)]
    digest = (out_dir / "a_1" / "profile_digest.md").read_text(encoding="utf-8")
    metadata = json.loads((out_dir / "a_1" / "cm_metadata.json").read_text(encoding="utf-8"))
    assert "alice@example.com" not in digest
    assert "password=secret" not in digest
    assert metadata["user"] == "<user>"


def test_report_generation_only_when_report_mode_explicit(tmp_path):
    module = load_sample_module()
    config = write_config(tmp_path)
    fetcher, _summary_calls = fake_summary_fetcher_factory(module, [summary(module, "a:1")])
    profile_fetcher, _profile_calls = fake_profile_fetcher_factory()
    analyzer, _analyzer_calls = fake_analyzer_factory(module)
    report_runner, report_calls = fake_report_runner_factory()

    result = module.main(
        base_args(config, tmp_path / "corpus") + ["--apply"],
        cwd=tmp_path,
        repo_root=REPO_DIR,
        summary_fetcher=fetcher,
        profile_fetcher=profile_fetcher,
        analyzer_runner=analyzer,
        report_runner=report_runner,
    )

    assert result == 0
    assert report_calls == []

    result = module.main(
        base_args(config, tmp_path / "corpus-2") + ["--apply", "--report-mode", "both"],
        cwd=tmp_path,
        repo_root=REPO_DIR,
        summary_fetcher=fetcher,
        profile_fetcher=profile_fetcher,
        analyzer_runner=analyzer,
        report_runner=report_runner,
    )

    assert result == 0
    assert [mode for _case_dir, mode in report_calls] == ["admin", "user"]


def test_output_does_not_print_raw_user_sql_profile_json_or_secret(tmp_path, capsys):
    module = load_sample_module()
    config = write_config(tmp_path)
    fetcher, _summary_calls = fake_summary_fetcher_factory(
        module,
        [summary(module, "a:1", user="alice")],
    )
    profile_fetcher, _profile_calls = fake_profile_fetcher_factory(
        "Runtime Profile\nUser: alice\nselect secret_sql from example_guarded.table\n"
    )
    analyzer, _analyzer_calls = fake_analyzer_factory(module)

    result = module.main(
        base_args(config, tmp_path / "corpus") + ["--apply"],
        cwd=tmp_path,
        repo_root=REPO_DIR,
        env={"CM_PASSWORD": "topsecret"},
        summary_fetcher=fetcher,
        profile_fetcher=profile_fetcher,
        analyzer_runner=analyzer,
    )

    output = capsys.readouterr().out
    assert result == 0
    assert "alice" not in output
    assert "secret_sql" not in output
    assert "Runtime Profile" not in output
    assert "topsecret" not in output
