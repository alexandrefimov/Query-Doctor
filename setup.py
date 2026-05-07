"""Legacy editable-install shim for pip versions without PEP 660 support."""

from __future__ import annotations

from pathlib import Path

from setuptools import find_packages, setup


def project_scripts(pyproject_path: Path = Path("pyproject.toml")) -> list[str]:
    scripts: list[str] = []
    in_scripts = False
    for line in pyproject_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped == "[project.scripts]":
            in_scripts = True
            continue
        if in_scripts and stripped.startswith("["):
            break
        if not in_scripts or not stripped or stripped.startswith("#"):
            continue
        name, value = stripped.split("=", 1)
        target = value.strip().strip('"')
        scripts.append(f"{name.strip()}={target}")
    return scripts


CONSOLE_SCRIPTS = project_scripts()


setup(
    name="query-doctor",
    version="0.1.0",
    description="Local-first Apache Impala query diagnostic tool.",
    license="AGPL-3.0-or-later",
    long_description=Path("README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    python_requires=">=3.9",
    packages=find_packages(include=["query_doctor*"]),
    entry_points={"console_scripts": CONSOLE_SCRIPTS},
)
