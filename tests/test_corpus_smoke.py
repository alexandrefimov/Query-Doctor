import json
from pathlib import Path
from typing import Optional

from command_test_support import command_args, command_uses_role


REPO_DIR = Path(__file__).resolve().parents[1]


def load_smoke_module():
    from query_doctor.cli import corpus_smoke

    return corpus_smoke


def test_package_entrypoint_keeps_repo_root_and_analyzer_command():
    from query_doctor.cli import corpus_smoke

    assert corpus_smoke.REPO_DIR == REPO_DIR
    cmd = corpus_smoke.analyzer_command(Path("/case"))
    assert command_uses_role(cmd, "analyze")
    assert command_args(cmd, "analyze") == ["/case"]


def make_case(root: Path, name: str) -> Path:
    case_dir = root / name
    case_dir.mkdir(parents=True)
    for filename in [
        "profile_digest.md",
        "cm_metadata.json",
        "collection_warnings.txt",
        "report_user.md",
    ]:
        (case_dir / filename).write_text(f"{filename}\n", encoding="utf-8")
    return case_dir


def facts_text(
    *,
    operators: int = 3,
    cardinality: int = 0,
    memory: int = 1,
    action_cards: bool = True,
    severe_action_card: bool = False,
    findings: bool = True,
    extra: str = "",
) -> str:
    if action_cards and severe_action_card:
        action_cards_text = (
            "### Card 1: Severe deterministic evidence\n\n"
            "Finding:\n"
            "- Severe deterministic evidence was detected.\n"
        )
    elif action_cards:
        action_cards_text = "### Card 1: Evidence-backed finding\n\n- confirmed\n"
    else:
        action_cards_text = (
            "No deterministic action cards were triggered from the parsed evidence.\n"
        )
    findings_text = (
        "### Heavy operator [medium]\n\n- found\n"
        if findings
        else "No deterministic findings were produced from the digest.\n"
    )
    return "\n".join(
        [
            "# Query Doctor deterministic analysis facts",
            "",
            "## Summary",
            "",
            f"- Parsed operators: {operators}",
            f"- Cardinality anomalies: {cardinality}",
            f"- Memory anomalies: {memory}",
            "",
            "## Action Cards",
            "",
            action_cards_text,
            "## Findings",
            "",
            findings_text,
            extra,
        ]
    )


def fake_runner_factory(module, facts_by_case: dict[str, str], failures: Optional[set[str]] = None):
    calls: list[Path] = []
    failures = failures or set()

    def runner(case_dir: Path):
        calls.append(case_dir)
        if case_dir.name in failures:
            return module.AnalyzerResult(7, "", "synthetic failure")
        text = facts_by_case.get(case_dir.name, facts_text())
        (case_dir / "analysis_facts.md").write_text(text, encoding="utf-8")
        return module.AnalyzerResult(0, "Wrote analysis_facts.md\n", "")

    return runner, calls


def test_scans_multiple_case_dirs_and_skips_dirs_without_profile(tmp_path, capsys):
    module = load_smoke_module()
    root = tmp_path / "cm-corpus"
    make_case(root, "case-b")
    make_case(root, "case-a")
    (root / "not-a-case").mkdir()
    runner, calls = fake_runner_factory(
        module,
        {
            "case-a": facts_text(operators=2, cardinality=1, memory=0),
            "case-b": facts_text(operators=5, cardinality=0, memory=3),
        },
    )

    result = module.main([str(root)], analyzer_runner=runner)

    output = capsys.readouterr().out
    assert result == 0
    assert [item.name for item in calls] == ["case-a", "case-b"]
    assert "case-a" in output
    assert "case-b" in output
    assert "Cases scanned: 2" in output
    assert "Analyzer passed: 2" in output
    assert "PROBLEM cases: 2" in output
    assert "2" in output
    assert "5" in output


def test_classifies_ok_case_with_zero_anomalies_and_no_signals(tmp_path, capsys):
    module = load_smoke_module()
    root = tmp_path / "cm-corpus"
    make_case(root, "case-a")
    runner, _calls = fake_runner_factory(
        module,
        {"case-a": facts_text(memory=0, action_cards=False, findings=False)},
    )

    result = module.main([str(root)], analyzer_runner=runner)

    output = capsys.readouterr().out
    assert result == 0
    assert "OK" in output
    assert "OK cases: 1" in output
    assert "WARN cases: 0" in output
    assert "PROBLEM cases: 0" in output
    assert "FAIL cases: 0" in output


def test_classifies_warn_case_with_low_signal_findings(tmp_path, capsys):
    module = load_smoke_module()
    root = tmp_path / "cm-corpus"
    make_case(root, "case-a")
    runner, _calls = fake_runner_factory(
        module,
        {"case-a": facts_text(memory=0, action_cards=False, findings=True)},
    )

    result = module.main([str(root)], analyzer_runner=runner)

    output = capsys.readouterr().out
    assert result == 0
    assert "WARN" in output
    assert "OK cases: 0" in output
    assert "WARN cases: 1" in output
    assert "PROBLEM cases: 0" in output


def test_classifies_problem_case_with_memory_anomalies(tmp_path, capsys):
    module = load_smoke_module()
    root = tmp_path / "cm-corpus"
    make_case(root, "case-a")
    runner, _calls = fake_runner_factory(
        module,
        {"case-a": facts_text(cardinality=0, memory=2, action_cards=False, findings=False)},
    )

    result = module.main([str(root)], analyzer_runner=runner)

    output = capsys.readouterr().out
    assert result == 0
    assert "PROBLEM" in output
    assert "PROBLEM cases: 1" in output


def test_classifies_problem_case_with_cardinality_anomalies(tmp_path, capsys):
    module = load_smoke_module()
    root = tmp_path / "cm-corpus"
    make_case(root, "case-a")
    runner, _calls = fake_runner_factory(
        module,
        {"case-a": facts_text(cardinality=3, memory=0, action_cards=False, findings=False)},
    )

    result = module.main([str(root)], analyzer_runner=runner)

    output = capsys.readouterr().out
    assert result == 0
    assert "PROBLEM" in output
    assert "PROBLEM cases: 1" in output


def test_classifies_problem_case_with_severe_action_card(tmp_path, capsys):
    module = load_smoke_module()
    root = tmp_path / "cm-corpus"
    make_case(root, "case-a")
    runner, _calls = fake_runner_factory(
        module,
        {
            "case-a": facts_text(
                memory=0, action_cards=True, severe_action_card=True, findings=False
            )
        },
    )

    result = module.main([str(root)], analyzer_runner=runner)

    output = capsys.readouterr().out
    assert result == 0
    assert "PROBLEM" in output
    assert "PROBLEM cases: 1" in output


def test_removes_analysis_facts_by_default(tmp_path):
    module = load_smoke_module()
    root = tmp_path / "cm-corpus"
    case_dir = make_case(root, "case-a")
    runner, _calls = fake_runner_factory(module, {"case-a": facts_text()})

    result = module.main([str(root)], analyzer_runner=runner)

    assert result == 0
    assert not (case_dir / "analysis_facts.md").exists()


def test_keeps_analysis_facts_with_keep_generated(tmp_path):
    module = load_smoke_module()
    root = tmp_path / "cm-corpus"
    case_dir = make_case(root, "case-a")
    runner, _calls = fake_runner_factory(module, {"case-a": facts_text(operators=4)})

    result = module.main([str(root), "--keep-generated"], analyzer_runner=runner)

    assert result == 0
    assert "Parsed operators: 4" in (case_dir / "analysis_facts.md").read_text(encoding="utf-8")


def test_detects_banned_phrases_and_can_fail(tmp_path, capsys):
    module = load_smoke_module()
    root = tmp_path / "cm-corpus"
    make_case(root, "case-a")
    runner, _calls = fake_runner_factory(
        module,
        {
            "case-a": facts_text(
                extra="This does not prove hot keys exist or that stats are stale.\n"
            )
        },
    )

    result = module.main([str(root), "--fail-on-banned-phrases"], analyzer_runner=runner)

    output = capsys.readouterr().out
    assert result == 1
    assert "banned_phrases" in output
    assert "Banned phrase hits: 2" in output


def test_handles_analyzer_failure_and_can_fail(tmp_path, capsys):
    module = load_smoke_module()
    root = tmp_path / "cm-corpus"
    make_case(root, "case-a")
    make_case(root, "case-b")
    runner, _calls = fake_runner_factory(module, {"case-a": facts_text()}, failures={"case-b"})

    result = module.main([str(root), "--fail-on-analyzer-error"], analyzer_runner=runner)

    output = capsys.readouterr().out
    assert result == 1
    assert "analyzer_error" in output
    assert "FAIL" in output
    assert "Analyzer passed: 1" in output
    assert "Analyzer failed: 1" in output
    assert "FAIL cases: 1" in output


def test_analyzer_failure_does_not_remove_existing_analysis_facts(tmp_path):
    module = load_smoke_module()
    root = tmp_path / "cm-corpus"
    case_dir = make_case(root, "case-a")
    (case_dir / "analysis_facts.md").write_text("existing facts\n", encoding="utf-8")
    runner, _calls = fake_runner_factory(module, {}, failures={"case-a"})

    result = module.main([str(root)], analyzer_runner=runner)

    assert result == 0
    assert (case_dir / "analysis_facts.md").read_text(encoding="utf-8") == "existing facts\n"


def test_preserves_profile_metadata_and_report_files(tmp_path):
    module = load_smoke_module()
    root = tmp_path / "cm-corpus"
    case_dir = make_case(root, "case-a")
    runner, _calls = fake_runner_factory(module, {"case-a": facts_text()})

    result = module.main([str(root)], analyzer_runner=runner)

    assert result == 0
    for filename in [
        "profile_digest.md",
        "cm_metadata.json",
        "collection_warnings.txt",
        "report_user.md",
    ]:
        assert (case_dir / filename).exists()


def test_writes_deterministic_json_summary(tmp_path):
    module = load_smoke_module()
    root = tmp_path / "cm-corpus"
    make_case(root, "case-a")
    json_path = tmp_path / "summary.json"
    runner, _calls = fake_runner_factory(
        module,
        {
            "case-a": facts_text(
                operators=9, cardinality=2, memory=1, action_cards=False, findings=False
            )
        },
    )

    result = module.main([str(root), "--json-out", str(json_path)], analyzer_runner=runner)

    assert result == 0
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["totals"]["cases_scanned"] == 1
    assert payload["cases"][0]["parsed_operators"] == 9
    assert payload["cases"][0]["cardinality_anomalies"] == 2
    assert payload["cases"][0]["classification"] == "PROBLEM"
    assert payload["cases"][0]["memory_anomalies"] == 1
    assert payload["cases"][0]["action_cards_present"] is False
    assert payload["cases"][0]["findings_present"] is False


def test_symlink_case_directory_is_not_followed(tmp_path):
    module = load_smoke_module()
    root = tmp_path / "cm-corpus"
    real_case = make_case(tmp_path, "real-case")
    root.mkdir()
    (root / "linked-case").symlink_to(real_case, target_is_directory=True)
    runner, calls = fake_runner_factory(module, {"linked-case": facts_text()})

    result = module.main([str(root)], analyzer_runner=runner)

    assert result == 0
    assert calls == []


def test_rejects_symlink_root(tmp_path, capsys):
    module = load_smoke_module()
    real_root = tmp_path / "real-root"
    real_root.mkdir()
    link = tmp_path / "linked-root"
    link.symlink_to(real_root, target_is_directory=True)

    result = module.main([str(link)])

    captured = capsys.readouterr()
    assert result == 2
    assert "Refusing symlink corpus root" in captured.err
