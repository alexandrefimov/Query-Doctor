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


def project_version(pyproject_path: Path = Path("pyproject.toml")) -> str:
    in_project = False
    for line in pyproject_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped == "[project]":
            in_project = True
            continue
        if in_project and stripped.startswith("["):
            break
        if in_project and stripped.startswith("version = "):
            return stripped.split("=", 1)[1].strip().strip('"')
    raise RuntimeError("pyproject.toml project version is missing")


CONSOLE_SCRIPTS = project_scripts()
VERSION = project_version()


setup(
    name="query-doctor",
    version=VERSION,
    description="Local-first Big Data query diagnostics focused today on Apache Impala.",
    author="Aleksandr Efimov",
    maintainer="Aleksandr Efimov",
    url="https://github.com/alexandrefimov/Query-Doctor",
    project_urls={
        "Homepage": "https://github.com/alexandrefimov/Query-Doctor",
        "Repository": "https://github.com/alexandrefimov/Query-Doctor",
        "Issues": "https://github.com/alexandrefimov/Query-Doctor/issues",
        "Documentation": "https://github.com/alexandrefimov/Query-Doctor/blob/main/docs/README.md",
    },
    license="Apache-2.0",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Console",
        "Environment :: Web Environment",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Database",
        "Topic :: System :: Monitoring",
    ],
    keywords=[
        "apache-impala",
        "cloudera-manager",
        "diagnostics",
        "query-analysis",
        "sql",
    ],
    long_description=Path("README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    python_requires=">=3.9",
    packages=find_packages(include=["query_doctor*"]),
    package_data={"query_doctor.web.static": ["*.css", "*.js"]},
    entry_points={"console_scripts": CONSOLE_SCRIPTS},
)
