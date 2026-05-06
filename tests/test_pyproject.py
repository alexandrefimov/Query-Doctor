import ast
import importlib
import inspect
from pathlib import Path


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


def setup_py_console_scripts() -> dict[str, str]:
    tree = ast.parse((REPO_DIR / "setup.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == "CONSOLE_SCRIPTS" for target in node.targets):
                values = ast.literal_eval(node.value)
                return dict(item.split("=", 1) for item in values)
    raise AssertionError("CONSOLE_SCRIPTS not found in setup.py")


def setup_py_text() -> str:
    return (REPO_DIR / "setup.py").read_text(encoding="utf-8")


def test_pyproject_declares_query_doctor_package_and_console_scripts():
    text = (REPO_DIR / "pyproject.toml").read_text(encoding="utf-8")

    assert 'requires = ["setuptools>=61", "wheel"]' in text
    assert 'build-backend = "setuptools.build_meta"' in text
    assert 'name = "query-doctor"' in text
    assert 'include = ["query_doctor*"]' in text
    assert project_scripts()


def test_project_license_metadata_is_consistent():
    pyproject_text = (REPO_DIR / "pyproject.toml").read_text(encoding="utf-8")
    setup_text = setup_py_text()

    assert 'license = { text = "AGPL-3.0-or-later" }' in pyproject_text
    assert 'license="AGPL-3.0-or-later"' in setup_text


def test_legacy_setup_py_console_scripts_match_pyproject():
    assert setup_py_console_scripts() == project_scripts()


def test_console_script_entrypoints_are_importable_and_callable_without_args():
    for script_name, target in project_scripts().items():
        module_name, function_name = target.split(":", 1)
        module = importlib.import_module(module_name)
        function = getattr(module, function_name)

        assert callable(function), script_name
        signature = inspect.signature(function)
        for parameter in signature.parameters.values():
            assert parameter.default is not inspect.Parameter.empty, script_name
