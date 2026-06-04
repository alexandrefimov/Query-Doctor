import importlib
from pathlib import Path

import pytest

from query_doctor.cli import (
    build_spark_evidence_package,
    collect_spark_history,
    diagnose_spark_compact,
    validate_spark_evidence_package,
)
from query_doctor.cli.commands import (
    COMMAND_BACKENDS,
    COMMAND_BACKEND_ENV,
    COMMAND_SPECS,
    DEFAULT_COMMAND_BACKEND,
    command_prefix,
    command_spec,
    console_script_name,
    module_name,
    resolve_command_backend,
)

FORBIDDEN_SQL_EXECUTION_FLAGS = (
    "--execute-sql",
    "--run-sql",
    "--apply-sql",
    "--execute-query",
    "--allow-sql-execution",
)
TRINO_COMMAND_ROLES = tuple(
    role for role in COMMAND_SPECS if role.startswith("trino_") or role == "diagnose_trino_compact"
)


REPO_DIR = Path(__file__).resolve().parents[1]


def project_scripts() -> dict[str, str]:
    scripts: dict[str, str] = {}
    in_scripts = False
    for line in (REPO_DIR / "pyproject.toml").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped == "[project.scripts]":
            in_scripts = True
            continue
        if in_scripts and stripped.startswith("["):
            break
        if not in_scripts or not stripped or stripped.startswith("#"):
            continue
        name, value = stripped.split("=", 1)
        scripts[name.strip()] = value.strip().strip('"')
    return scripts


def test_command_specs_cover_module_and_console_backends():
    assert COMMAND_BACKENDS == ("module", "console")
    assert command_spec("pipeline") == COMMAND_SPECS["pipeline"]
    assert module_name("pipeline") == "query_doctor.cli.pipeline"
    assert console_script_name("pipeline") == "query-doctor-pipeline"


@pytest.mark.parametrize(
    ("role", "module", "script"),
    (
        (
            "collect_spark_history",
            "query_doctor.cli.collect_spark_history",
            "query-doctor-collect-spark-history",
        ),
        (
            "diagnose_spark_compact",
            "query_doctor.cli.diagnose_spark_compact",
            "query-doctor-diagnose-spark-compact",
        ),
        (
            "build_spark_evidence_package",
            "query_doctor.cli.build_spark_evidence_package",
            "query-doctor-build-spark-evidence-package",
        ),
        (
            "validate_spark_evidence_package",
            "query_doctor.cli.validate_spark_evidence_package",
            "query-doctor-validate-spark-evidence-package",
        ),
        (
            "trino_query_info_pruned_import",
            "query_doctor.cli.trino_query_info_pruned_import",
            "query-doctor-trino-query-info-pruned-import",
        ),
    ),
)
def test_compact_cli_roles_cover_module_and_console_backends(role, module, script):
    assert module_name(role) == module
    assert console_script_name(role) == script
    assert command_prefix(Path("/repo"), role, backend="module", python_executable="/py") == [
        "/py",
        "-m",
        module,
    ]
    assert command_prefix(Path("/repo"), role, backend="console", python_executable="/py") == [
        script
    ]


def test_trino_console_scripts_are_registered_command_specs():
    scripts = project_scripts()
    expected_scripts = {
        name: target
        for name, target in scripts.items()
        if name.startswith("query-doctor-trino-") or name == "query-doctor-diagnose-trino-compact"
    }
    trino_specs = {
        spec.console_script: spec.module
        for role, spec in COMMAND_SPECS.items()
        if role.startswith("trino_") or role == "diagnose_trino_compact"
    }

    assert trino_specs == {
        script: target.split(":", 1)[0] for script, target in expected_scripts.items()
    }


@pytest.mark.parametrize("role", TRINO_COMMAND_ROLES)
def test_trino_cli_help_preserves_safe_preview_boundary(role, capsys):
    module = importlib.import_module(module_name(role))

    with pytest.raises(SystemExit) as exc:
        module.main(["--help"])

    captured = capsys.readouterr()
    output = captured.out + captured.err

    assert exc.value.code == 0
    assert "Trino" in output
    assert "Traceback" not in output
    assert "No module named" not in output
    for flag in FORBIDDEN_SQL_EXECUTION_FLAGS:
        assert flag not in output, console_script_name(role)
    for local_marker in (
        str(REPO_DIR),
        "/Users/",
        "/private/tmp/",
        "/var/folders/",
    ):
        assert local_marker not in output, console_script_name(role)


def test_trino_pruned_import_help_exposes_boundary_and_diagnosis_outputs(capsys):
    module = importlib.import_module(module_name("trino_coordinator_query_info_pruned_import"))

    with pytest.raises(SystemExit) as exc:
        module.main(["--help"])

    captured = capsys.readouterr()
    output = captured.out + captured.err

    assert exc.value.code == 0
    assert "--boundary-out" in output
    assert "--diagnosis-out" in output
    assert "--auth-header-file" in output
    assert "--query-id" in output
    assert "never submits SQL" in output
    for flag in FORBIDDEN_SQL_EXECUTION_FLAGS:
        assert flag not in output


@pytest.mark.parametrize(
    "module",
    (
        build_spark_evidence_package,
        collect_spark_history,
        diagnose_spark_compact,
        validate_spark_evidence_package,
    ),
)
def test_spark_cli_help_preserves_no_support_boundary(module, capsys):
    help_func = getattr(module, "parse_args", None)
    with pytest.raises(SystemExit) as exc:
        if help_func is None:
            module.build_parser().parse_args(["--help"])
        else:
            help_func(["--help"])

    captured = capsys.readouterr()
    output = captured.out + captured.err
    normalized_output = " ".join(output.split())

    assert exc.value.code == 0
    assert "does not claim Spark product support" in normalized_output
    assert "Traceback" not in output
    for flag in FORBIDDEN_SQL_EXECUTION_FLAGS:
        assert flag not in output
    for local_marker in (
        "/Users/",
        "/private/tmp/",
        "/var/folders/",
    ):
        assert local_marker not in output


def test_spark_history_cli_help_documents_local_target_opt_in(capsys):
    with pytest.raises(SystemExit) as exc:
        collect_spark_history.parse_args(["--help"])

    output = capsys.readouterr().out

    assert exc.value.code == 0
    assert "--allow-local-history-server-target" in output
    assert "--max-task-summaries" in output
    assert (
        "Metadata, link-local, reserved, documentation, multicast, and unspecified targets remain blocked"
        in (" ".join(output.split()))
    )
    assert "--allow-sql-execution" not in output


def test_command_prefix_defaults_to_module_backend():
    repo_dir = Path("/repo")

    assert command_prefix(repo_dir, "pipeline", env={}, python_executable="/py") == [
        "/py",
        "-m",
        "query_doctor.cli.pipeline",
    ]
    assert resolve_command_backend(env={}) == DEFAULT_COMMAND_BACKEND == "module"


def test_command_backend_can_be_selected_from_environment():
    repo_dir = Path("/repo")

    assert resolve_command_backend(env={COMMAND_BACKEND_ENV: "module"}) == "module"
    assert command_prefix(
        repo_dir,
        "pipeline",
        env={COMMAND_BACKEND_ENV: "module"},
        python_executable="/py",
    ) == [
        "/py",
        "-m",
        "query_doctor.cli.pipeline",
    ]


def test_command_prefix_can_build_module_backend():
    repo_dir = Path("/repo")

    assert command_prefix(repo_dir, "pipeline", backend="module", python_executable="/py") == [
        "/py",
        "-m",
        "query_doctor.cli.pipeline",
    ]


def test_command_prefix_can_build_console_backend():
    repo_dir = Path("/repo")

    assert command_prefix(repo_dir, "pipeline", backend="console", python_executable="/py") == [
        "query-doctor-pipeline"
    ]


def test_unknown_command_role_is_rejected():
    with pytest.raises(ValueError, match="Unknown Query Doctor CLI role 'unknown'"):
        command_spec("unknown")


def test_unknown_command_backend_is_rejected():
    with pytest.raises(ValueError, match="Unsupported Query Doctor command backend 'bad'"):
        command_prefix(Path("/repo"), "pipeline", backend="bad")
