import ast
import importlib
import inspect
import runpy
from pathlib import Path
from unittest.mock import patch


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


def project_version() -> str:
    for line in (REPO_DIR / "pyproject.toml").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("version = "):
            return stripped.split("=", 1)[1].strip().strip('"')
    raise AssertionError("pyproject.toml project version is missing")


def setup_py_metadata() -> dict[str, object]:
    captured: dict[str, object] = {}

    def fake_setup(**kwargs):
        captured.update(kwargs)

    with patch("setuptools.setup", fake_setup):
        runpy.run_path(str(REPO_DIR / "setup.py"))
    return captured


def setup_py_console_scripts() -> dict[str, str]:
    captured = setup_py_metadata()
    scripts = captured["entry_points"]["console_scripts"]
    return dict(item.split("=", 1) for item in scripts)


def setup_py_text() -> str:
    return (REPO_DIR / "setup.py").read_text(encoding="utf-8")


def test_pyproject_declares_query_doctor_package_and_console_scripts():
    text = (REPO_DIR / "pyproject.toml").read_text(encoding="utf-8")

    assert 'requires = ["setuptools>=77", "wheel"]' in text
    assert 'build-backend = "setuptools.build_meta"' in text
    assert 'name = "query-doctor"' in text
    assert 'include = ["query_doctor*"]' in text
    assert project_scripts()


def test_project_license_metadata_is_consistent():
    pyproject_text = (REPO_DIR / "pyproject.toml").read_text(encoding="utf-8")
    setup_text = setup_py_text()

    assert 'license = "AGPL-3.0-or-later"' in pyproject_text
    assert 'license="AGPL-3.0-or-later"' in setup_text


def test_public_packaging_metadata_is_present():
    pyproject_text = (REPO_DIR / "pyproject.toml").read_text(encoding="utf-8")
    setup_text = setup_py_text()

    for expected in (
        "authors = [",
        "maintainers = [",
        "keywords = [",
        "classifiers = [",
        "[project.urls]",
        'Homepage = "https://github.com/alexandrefimov/Query-Doctor"',
        'Issues = "https://github.com/alexandrefimov/Query-Doctor/issues"',
        '"Development Status :: 3 - Alpha"',
        '"Programming Language :: Python :: 3.9"',
        '"Programming Language :: Python :: 3.11"',
    ):
        assert expected in pyproject_text

    for expected in (
        'author="Aleksandr Efimov"',
        'maintainer="Aleksandr Efimov"',
        'url="https://github.com/alexandrefimov/Query-Doctor"',
        '"Homepage": "https://github.com/alexandrefimov/Query-Doctor"',
        '"Development Status :: 3 - Alpha"',
        '"Programming Language :: Python :: 3.9"',
        '"Programming Language :: Python :: 3.11"',
    ):
        assert expected in setup_text


def test_legacy_setup_py_version_matches_pyproject():
    assert setup_py_metadata()["version"] == project_version()


def test_legacy_setup_py_console_scripts_match_pyproject():
    assert setup_py_console_scripts() == project_scripts()


def test_internal_command_specs_match_pyproject_console_scripts():
    from query_doctor.cli.commands import COMMAND_SPECS

    scripts = project_scripts()
    for role, spec in COMMAND_SPECS.items():
        assert scripts.get(spec.console_script) == f"{spec.module}:main", role


def test_legacy_setup_py_reads_console_scripts_from_pyproject():
    tree = ast.parse((REPO_DIR / "setup.py").read_text(encoding="utf-8"))

    literal_script_lists = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.List)
        and any(
            isinstance(item, ast.Constant)
            and isinstance(item.value, str)
            and item.value.startswith("query-doctor-")
            for item in node.elts
        )
    ]

    assert literal_script_lists == []


def test_console_script_entrypoints_are_importable_and_callable_without_args():
    for script_name, target in project_scripts().items():
        module_name, function_name = target.split(":", 1)
        module = importlib.import_module(module_name)
        function = getattr(module, function_name)

        assert callable(function), script_name
        signature = inspect.signature(function)
        for parameter in signature.parameters.values():
            assert parameter.default is not inspect.Parameter.empty, script_name
