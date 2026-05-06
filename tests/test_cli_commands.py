from pathlib import Path

import pytest

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


def test_command_specs_cover_module_and_console_backends():
    assert COMMAND_BACKENDS == ("module", "console")
    assert command_spec("pipeline") == COMMAND_SPECS["pipeline"]
    assert module_name("pipeline") == "query_doctor.cli.pipeline"
    assert console_script_name("pipeline") == "query-doctor-pipeline"


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
