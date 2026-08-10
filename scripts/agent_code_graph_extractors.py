"""Deterministic extractors for scripts/agent_code_graph.py."""

from __future__ import annotations

import ast
import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


PY_SUFFIXES = (".py",)
GO_SUFFIXES = (".go",)
TS_SUFFIXES = (".ts", ".tsx", ".js", ".jsx")
DOC_SUFFIXES = (".md",)
CONFIG_SUFFIXES = (".yaml", ".yml", ".json", ".toml", ".tpl")
SCRIPT_SUFFIXES = (".sh", ".bash", ".zsh")
CODE_SUFFIXES = (*PY_SUFFIXES, *GO_SUFFIXES, *TS_SUFFIXES)
SUPPORT_SUFFIXES = (*CONFIG_SUFFIXES, *SCRIPT_SUFFIXES)
SPECIAL_FILENAMES = {"Dockerfile", "Makefile"}
TS_RESOLVE_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".json")

SKIP_DIRS = {
    ".agents",
    ".claude",
    ".git",
    ".github",
    ".local-audit",
    ".local-docs",
    ".mypy_cache",
    ".pycache-agent",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "build",
    "cases",
    "dev",
    "dist",
    "graphify-out",
    "legacy",
    "node_modules",
    "site",
    "tmp",
}

MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+\.md(?:#[^)]+)?)\)")
PATH_REF_RE = re.compile(
    r"(?<![A-Za-z0-9_.@/-])"
    r"((?:\.{1,2}/)?(?:[A-Za-z0-9_.@+-]+/)+[A-Za-z0-9_.@+-]+"
    r"(?:\.[A-Za-z0-9_.@+-]+)?)"
    r"(?![A-Za-z0-9_.@/-])"
)
TS_IMPORT_RE = re.compile(
    r"(?:import|export)\s+(?:[^;]*?\s+from\s+)?[\"']([^\"']+)[\"']|"
    r"import\(\s*[\"']([^\"']+)[\"']\s*\)"
)
GO_IMPORT_BLOCK_RE = re.compile(r"import\s*\((.*?)\)", re.DOTALL)
GO_IMPORT_LINE_RE = re.compile(r"^\s*(?:[\w.]+\s+)?\"([^\"]+)\"", re.MULTILINE)
GO_SINGLE_IMPORT_RE = re.compile(r"import\s+(?:[\w.]+\s+)?\"([^\"]+)\"")
_REPO_FILES_CACHE: dict[Path, list[Path]] = {}


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    relation: str
    confidence: str
    evidence: str


@dataclass(frozen=True)
class Symbol:
    name: str
    kind: str
    path: str
    start: int
    end: int
    parent: str | None = None


def rel(repo: Path, path: Path) -> str:
    return path.resolve().relative_to(repo).as_posix()


def should_skip(repo: Path, path: Path) -> bool:
    try:
        parts = path.resolve().relative_to(repo).parts
    except ValueError:
        return True
    return any(
        part in SKIP_DIRS or part.startswith(".venv") or part.endswith(".egg-info")
        for part in parts
    )


def git_repo_files(repo: Path) -> list[Path] | None:
    if not (repo / ".git").exists():
        return None
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        return None
    paths = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        try:
            relative = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        path = repo / relative
        if path.is_file() and not should_skip(repo, path):
            paths.append(path)
    return sorted(paths)


def rglob_repo_files(repo: Path) -> list[Path]:
    paths: list[Path] = []
    for path in repo.rglob("*"):
        if should_skip(repo, path):
            continue
        if not path.is_file():
            continue
        paths.append(path)
    return sorted(paths)


def repo_files(repo: Path) -> list[Path]:
    repo = repo.resolve()
    cached = _REPO_FILES_CACHE.get(repo)
    if cached is not None:
        return cached
    paths = git_repo_files(repo)
    if paths is None:
        paths = rglob_repo_files(repo)
    _REPO_FILES_CACHE[repo] = paths
    return paths


def iter_files(repo: Path, suffixes: Sequence[str]) -> list[Path]:
    paths: list[Path] = []
    for path in repo_files(repo):
        if path.suffix in suffixes:
            paths.append(path)
        elif path.name in SPECIAL_FILENAMES and "" in suffixes:
            paths.append(path)
        elif "" in suffixes and is_extensionless_script(repo, path):
            paths.append(path)
    return sorted(paths)


def is_extensionless_script(repo: Path, path: Path) -> bool:
    try:
        relative = path.resolve().relative_to(repo)
    except ValueError:
        return False
    if path.suffix or not relative.parts or relative.parts[0] != "scripts":
        return False
    try:
        first_line = path.read_text(encoding="utf-8", errors="replace").splitlines()[0]
    except IndexError:
        return False
    return first_line.startswith("#!")


def python_module_name(repo: Path, path: Path) -> str:
    relative = path.resolve().relative_to(repo)
    if relative.name == "__init__.py":
        return ".".join(relative.parts[:-1])
    return ".".join(relative.with_suffix("").parts)


def python_package_context(repo: Path, path: Path) -> str:
    module = python_module_name(repo, path)
    if path.name == "__init__.py":
        return module
    return module.rsplit(".", 1)[0] if "." in module else ""


def longest_python_module(module: str, module_to_file: dict[str, str]) -> str | None:
    parts = module.split(".")
    for end in range(len(parts), 0, -1):
        candidate = ".".join(parts[:end])
        if candidate in module_to_file:
            return module_to_file[candidate]
    return None


def relative_import_base(repo: Path, path: Path, level: int, module: str | None) -> str:
    package = python_package_context(repo, path)
    parts = package.split(".") if package else []
    if level > 1:
        parts = parts[: -(level - 1)] if len(parts) >= level - 1 else []
    if module:
        parts.extend(module.split("."))
    return ".".join(part for part in parts if part)


def extract_python_analysis(
    repo: Path,
    paths: Sequence[Path],
    *,
    include_symbols: bool = True,
) -> tuple[list[Edge], list[Symbol]]:
    module_to_file = {python_module_name(repo, path): rel(repo, path) for path in paths}
    edges: list[Edge] = []
    symbols: list[Symbol] = []
    for path in paths:
        source = rel(repo, path)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError as exc:
            edges.append(
                Edge(source, f"parse-error:{source}", "parse_error", "EXTRACTED", str(exc))
            )
            continue
        if include_symbols:
            visitor = _PythonSymbolVisitor(source)
            visitor.visit(tree)
            symbols.extend(visitor.symbols)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target = longest_python_module(alias.name, module_to_file)
                    if target and target != source:
                        edges.append(Edge(source, target, "imports", "EXTRACTED", source))
            elif isinstance(node, ast.ImportFrom):
                base = (
                    relative_import_base(repo, path, node.level, node.module)
                    if node.level
                    else node.module or ""
                )
                for alias in node.names:
                    candidates = [f"{base}.{alias.name}" if base else alias.name, base]
                    for candidate in candidates:
                        target = longest_python_module(candidate, module_to_file)
                        if target and target != source:
                            edges.append(Edge(source, target, "imports", "EXTRACTED", source))
                            break
    return edges, sorted(symbols, key=lambda item: (item.path, item.start, item.end, item.name))


class _PythonSymbolVisitor(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path
        self.parents: list[tuple[str, str]] = []
        self.symbols: list[Symbol] = []

    def _visit_symbol(self, node: ast.AST, name: str, kind: str) -> None:
        parent = ".".join(item[1] for item in self.parents) or None
        if kind == "function" and self.parents and self.parents[-1][0] == "class":
            kind = "method"
        self.symbols.append(
            Symbol(
                name=name,
                kind=kind,
                path=self.path,
                start=int(getattr(node, "lineno", 1)),
                end=int(getattr(node, "end_lineno", getattr(node, "lineno", 1))),
                parent=parent,
            )
        )
        self.parents.append(("class" if kind == "class" else "function", name))
        self.generic_visit(node)
        self.parents.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802 - ast visitor API
        self._visit_symbol(node, node.name, "class")

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802 - ast visitor API
        self._visit_symbol(node, node.name, "function")

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802 - ast visitor API
        self._visit_symbol(node, node.name, "function")


def read_go_module(repo: Path) -> str | None:
    go_mod = repo / "go.mod"
    if not go_mod.exists():
        return None
    for line in go_mod.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip().startswith("module "):
            return line.split()[1]
    return None


def extract_go_imports(text: str) -> list[str]:
    imports: list[str] = []
    for block in GO_IMPORT_BLOCK_RE.findall(text):
        imports.extend(GO_IMPORT_LINE_RE.findall(block))
    imports.extend(GO_SINGLE_IMPORT_RE.findall(text))
    return sorted(set(imports))


def extract_go_edges(repo: Path, paths: Sequence[Path]) -> list[Edge]:
    module = read_go_module(repo)
    if not module:
        return []
    package_dirs = {rel(repo, path.parent) for path in paths}
    edges: list[Edge] = []
    for path in paths:
        source = rel(repo, path)
        for imported in extract_go_imports(path.read_text(encoding="utf-8", errors="replace")):
            if not imported.startswith(f"{module}/"):
                continue
            target_dir = imported.removeprefix(f"{module}/")
            if target_dir in package_dirs:
                edges.append(Edge(source, f"pkg:{target_dir}", "imports", "EXTRACTED", source))
    return edges


def resolve_ts_import(repo: Path, source: Path, specifier: str, all_files: set[str]) -> str | None:
    if not specifier.startswith("."):
        return None
    base = (source.parent / specifier).resolve()
    candidates = [base]
    candidates.extend(base.with_suffix(suffix) for suffix in TS_RESOLVE_SUFFIXES)
    candidates.extend(base / f"index{suffix}" for suffix in TS_RESOLVE_SUFFIXES)
    for candidate in candidates:
        try:
            candidate_rel = candidate.relative_to(repo).as_posix()
        except ValueError:
            continue
        if candidate_rel in all_files:
            return candidate_rel
    return None


def extract_ts_edges(repo: Path, paths: Sequence[Path]) -> list[Edge]:
    all_files = {rel(repo, path) for path in paths}
    edges: list[Edge] = []
    for path in paths:
        source = rel(repo, path)
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in TS_IMPORT_RE.finditer(text):
            specifier = match.group(1) or match.group(2) or ""
            target = resolve_ts_import(repo, path, specifier, all_files)
            if target and target != source:
                edges.append(Edge(source, target, "imports", "EXTRACTED", source))
    return edges


def extract_doc_edges(repo: Path, paths: Sequence[Path]) -> list[Edge]:
    edges: list[Edge] = []
    for path in paths:
        source = rel(repo, path)
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in MARKDOWN_LINK_RE.finditer(text):
            raw = match.group(1).split("#", 1)[0]
            if raw.startswith(("http://", "https://", "mailto:")):
                continue
            target_path = (path.parent / raw).resolve()
            try:
                target = target_path.relative_to(repo).as_posix()
            except ValueError:
                continue
            if target.endswith(".md"):
                edges.append(Edge(source, target, "doc_link", "EXTRACTED", source))
    return edges


def normalize_path_ref(raw: str) -> str:
    return raw.strip().strip("'\"`),]").split("#", 1)[0]


def resolve_file_ref(repo: Path, source: Path, raw: str, all_files: set[str]) -> str | None:
    ref = normalize_path_ref(raw)
    if not ref or ref.startswith(("http://", "https://", "mailto:")):
        return None
    candidates: list[Path] = []
    if ref.startswith(("./", "../")):
        candidates.append((source.parent / ref).resolve())
    else:
        candidates.append((repo / ref).resolve())
        candidates.append((source.parent / ref).resolve())
    for candidate in candidates:
        try:
            candidate_rel = candidate.relative_to(repo).as_posix()
        except ValueError:
            continue
        if candidate_rel in all_files:
            return candidate_rel
    return None


def extract_file_reference_edges(
    repo: Path, paths: Sequence[Path], graph_paths: Sequence[Path]
) -> list[Edge]:
    all_files = {rel(repo, path) for path in graph_paths}
    edges: list[Edge] = []
    for path in paths:
        source = rel(repo, path)
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in PATH_REF_RE.finditer(text):
            target = resolve_file_ref(repo, path, match.group(1), all_files)
            if not target or target == source:
                continue
            if source.endswith(".md") and target.endswith(".md"):
                continue
            edges.append(Edge(source, target, "file_ref", "EXTRACTED", source))
    return edges


def chart_root_for(path: Path) -> Path | None:
    for parent in [path.parent, *path.parents]:
        if (parent / "Chart.yaml").exists():
            return parent
    return None


def extract_chart_edges(repo: Path, paths: Sequence[Path]) -> list[Edge]:
    graph_files = {rel(repo, path) for path in paths}
    edges: list[Edge] = []
    for path in paths:
        root = chart_root_for(path)
        if root is None:
            continue
        source = rel(repo, path)
        chart = rel(repo, root / "Chart.yaml")
        values = rel(repo, root / "values.yaml")
        schema = rel(repo, root / "values.schema.json")
        if source != chart and chart in graph_files:
            edges.append(Edge(source, chart, "chart_member", "INFERRED", source))
        if (
            source != values
            and values in graph_files
            and (
                "/templates/" in source
                or "/examples/" in source
                or source.endswith("values.schema.json")
            )
        ):
            edges.append(Edge(source, values, "chart_values", "INFERRED", source))
        if source == values and schema in graph_files:
            edges.append(Edge(source, schema, "chart_schema", "INFERRED", source))
    return edges


def infer_test_edges(
    repo: Path, paths: Sequence[Path], existing_edges: Sequence[Edge]
) -> list[Edge]:
    existing = {(edge.source, edge.target) for edge in existing_edges}
    file_set = {rel(repo, path) for path in paths}
    by_stem = defaultdict(list)
    for path in paths:
        by_stem[path.stem.removeprefix("test_").removesuffix("_test")].append(rel(repo, path))

    inferred: list[Edge] = []
    for path in paths:
        source = rel(repo, path)
        candidates: list[str] = []
        if source.startswith("tests/") and path.stem.startswith("test_"):
            name = path.stem.removeprefix("test_")
            candidates.extend(by_stem.get(name, []))
            candidates.extend(
                item
                for item in (
                    f"query_doctor/{name}.py",
                    f"query_doctor/web/{name}.py",
                    f"query_doctor/cli/{name}.py",
                    f"query_doctor/analyzer/{name}.py",
                )
                if item in file_set
            )
        elif source.endswith("_test.go"):
            candidate = source.removesuffix("_test.go") + ".go"
            if candidate in file_set:
                candidates.append(candidate)
        elif ".test." in source or ".spec." in source:
            name = Path(source).name.split(".test.", 1)[0].split(".spec.", 1)[0]
            candidates.extend(by_stem.get(name, []))

        for target in sorted(set(candidates)):
            if target != source and (source, target) not in existing:
                inferred.append(Edge(source, target, "test_name_targets", "INFERRED", source))
    return inferred


def dedupe_edges(edges: Iterable[Edge]) -> list[Edge]:
    seen: set[tuple[str, str, str, str]] = set()
    result: list[Edge] = []
    for edge in edges:
        key = (edge.source, edge.target, edge.relation, edge.confidence)
        if key in seen:
            continue
        seen.add(key)
        result.append(edge)
    return sorted(
        result, key=lambda edge: (edge.source, edge.target, edge.relation, edge.confidence)
    )
