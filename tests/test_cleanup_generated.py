from pathlib import Path


REPO_DIR = Path(__file__).resolve().parents[1]


def load_cleanup_module():
    from query_doctor.cli import cleanup_generated

    return cleanup_generated


def test_package_entrypoint_keeps_repo_root_safety_anchor():
    from query_doctor.cli import cleanup_generated

    assert cleanup_generated.REPO_DIR == REPO_DIR


def write_case(case_dir: Path) -> None:
    case_dir.mkdir(parents=True)
    for name in [
        "profile_digest.md",
        "cm_metadata.json",
        "collection_warnings.txt",
        "profile.txt",
        "raw_profile.txt",
        "original_query.sql",
        "referenced_tables.txt",
        "explain.txt",
        "impala_context.md",
        "unknown.md",
    ]:
        (case_dir / name).write_text(f"{name}\n", encoding="utf-8")
    for name in [
        "analysis_facts.md",
        "report_user.md",
        "report_admin.md",
        "diagnosis.md",
        "diagnosis_report.md",
        "failed.partial",
    ]:
        (case_dir / name).write_text(f"{name}\n", encoding="utf-8")


def test_default_mode_is_dry_run(tmp_path, capsys):
    module = load_cleanup_module()
    case_dir = tmp_path / "case"
    write_case(case_dir)

    result = module.main([str(case_dir)])

    output = capsys.readouterr().out
    assert result == 0
    assert "Would remove:" in output
    assert "Dry-run only. Re-run with --apply to delete." in output
    assert (case_dir / "analysis_facts.md").exists()
    assert (case_dir / "report_user.md").exists()


def test_dry_run_does_not_remove_files(tmp_path, capsys):
    module = load_cleanup_module()
    case_dir = tmp_path / "case"
    write_case(case_dir)

    result = module.main([str(case_dir), "--dry-run"])

    output = capsys.readouterr().out
    assert result == 0
    assert "Generated files matched: 6" in output
    assert "Files removed: 0" in output
    assert (case_dir / "analysis_facts.md").exists()
    assert (case_dir / "report_admin.md").exists()
    assert (case_dir / "failed.partial").exists()


def test_apply_removes_only_known_generated_files(tmp_path, capsys):
    module = load_cleanup_module()
    case_dir = tmp_path / "case"
    write_case(case_dir)

    result = module.main([str(case_dir), "--apply"])

    output = capsys.readouterr().out
    assert result == 0
    assert "Removed:" in output
    assert "Generated files matched: 6" in output
    assert "Files removed: 6" in output
    for name in [
        "analysis_facts.md",
        "report_user.md",
        "report_admin.md",
        "diagnosis.md",
        "diagnosis_report.md",
        "failed.partial",
    ]:
        assert not (case_dir / name).exists()
    for name in [
        "profile_digest.md",
        "cm_metadata.json",
        "collection_warnings.txt",
        "profile.txt",
        "raw_profile.txt",
        "original_query.sql",
        "referenced_tables.txt",
        "explain.txt",
        "impala_context.md",
        "unknown.md",
    ]:
        assert (case_dir / name).exists()
    assert case_dir.exists()


def test_nested_generated_files_are_found_under_parent(tmp_path, capsys):
    module = load_cleanup_module()
    parent = tmp_path / "cm-corpus"
    case_one = parent / "case-one"
    case_two = parent / "nested" / "case-two"
    write_case(case_one)
    write_case(case_two)

    result = module.main([str(parent), "--dry-run"])

    output = capsys.readouterr().out
    assert result == 0
    assert "Generated files matched: 12" in output
    assert "case-one" in output
    assert "case-two" in output


def test_multiple_input_paths_work(tmp_path, capsys):
    module = load_cleanup_module()
    case_one = tmp_path / "case-one"
    case_two = tmp_path / "case-two"
    write_case(case_one)
    write_case(case_two)

    result = module.main([str(case_one), str(case_two), "--apply"])

    output = capsys.readouterr().out
    assert result == 0
    assert "Generated files matched: 12" in output
    assert "Files removed: 12" in output
    assert not (case_one / "analysis_facts.md").exists()
    assert not (case_two / "report_user.md").exists()
    assert (case_one / "profile_digest.md").exists()
    assert (case_two / "cm_metadata.json").exists()


def test_symlink_is_not_followed(tmp_path, capsys):
    module = load_cleanup_module()
    parent = tmp_path / "cm-corpus"
    real_case = tmp_path / "real-case"
    write_case(real_case)
    parent.mkdir()
    link = parent / "linked-case"
    link.symlink_to(real_case, target_is_directory=True)

    result = module.main([str(parent), "--apply"])

    output = capsys.readouterr().out
    assert result == 0
    assert "Generated files matched: 0" in output
    assert "Skipped files: 1" in output
    assert (real_case / "analysis_facts.md").exists()


def test_explicit_symlink_path_is_not_followed(tmp_path, capsys):
    module = load_cleanup_module()
    real_case = tmp_path / "real-case"
    write_case(real_case)
    link = tmp_path / "linked-case"
    link.symlink_to(real_case, target_is_directory=True)

    result = module.main([str(link), "--apply"])

    output = capsys.readouterr().out
    assert result == 0
    assert "Generated files matched: 0" in output
    assert "Skipped files: 1" in output
    assert (real_case / "analysis_facts.md").exists()


def test_dangerous_paths_are_rejected(capsys):
    module = load_cleanup_module()

    result = module.main(["/"])

    captured = capsys.readouterr()
    assert result == 2
    assert "Refusing filesystem root cleanup path" in captured.err


def test_repo_root_is_rejected(capsys):
    module = load_cleanup_module()

    result = module.main([str(REPO_DIR)])

    captured = capsys.readouterr()
    assert result == 2
    assert "Refusing repository root cleanup path" in captured.err


def test_empty_path_is_rejected(capsys):
    module = load_cleanup_module()

    result = module.main([""])

    captured = capsys.readouterr()
    assert result == 2
    assert "Refusing empty cleanup path" in captured.err
