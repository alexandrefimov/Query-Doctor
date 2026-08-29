import importlib.util
import subprocess
from pathlib import Path


REPO_DIR = Path(__file__).resolve().parents[1]


def load_module():
    path = REPO_DIR / "scripts" / "check_declared_extras_resolve.py"
    spec = importlib.util.spec_from_file_location("check_declared_extras_resolve", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def completed(returncode: int, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout="", stderr=stderr)


def test_declared_extras_reads_every_name_in_the_section():
    module = load_module()

    extras = module.declared_extras((REPO_DIR / "pyproject.toml").read_text(encoding="utf-8"))

    assert extras == ["dev", "e2e", "impala", "postgres"]


def test_declared_extras_stops_at_the_next_section():
    module = load_module()
    text = (
        "[project]\n"
        'name = "example"\n\n'
        "[project.optional-dependencies]\n"
        'first = [\n    "a>=1",\n]\n'
        'second-one = [\n    "b[extra]>=2",\n]\n\n'
        "[project.scripts]\n"
        'later = "not.an:extra"\n'
    )

    assert module.declared_extras(text) == ["first", "second-one"]


def test_declared_extras_is_empty_without_the_section():
    module = load_module()

    assert module.declared_extras('[project]\nname = "example"\n') == []


def test_unresolvable_extras_reports_only_the_failing_ones(tmp_path):
    module = load_module()
    asked: list[str] = []

    def runner(extra, root):
        asked.append(extra)
        return completed(1, "No matching distribution") if extra == "postgres" else completed(0)

    failures = module.unresolvable_extras(["dev", "e2e", "postgres"], tmp_path, runner=runner)

    assert asked == ["dev", "e2e", "postgres"]
    assert [extra for extra, _ in failures] == ["postgres"]
    assert "No matching distribution" in failures[0][1]


def test_ci_resolves_declared_extras_on_every_matrix_interpreter():
    workflow = (REPO_DIR / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "python scripts/check_declared_extras_resolve.py" in workflow
