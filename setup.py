"""Legacy editable-install shim for pip versions without PEP 660 support."""

from __future__ import annotations

from pathlib import Path

from setuptools import find_packages, setup


CONSOLE_SCRIPTS = [
    "query-doctor-analyze=query_doctor.cli.analyze_profile:main",
    "query-doctor-batch-recent=query_doctor.cli.batch_recent:main",
    "query-doctor-cleanup-generated=query_doctor.cli.cleanup_generated:main",
    "query-doctor-cm-events=query_doctor.cli.cm_events:main",
    "query-doctor-cm-sample-smoke=query_doctor.cli.cm_sample_smoke:main",
    "query-doctor-collect-cm-profiles=query_doctor.cli.collect_cm_profiles:main",
    "query-doctor-collect-impala-context=query_doctor.cli.collect_impala_context:main",
    "query-doctor-corpus-smoke=query_doctor.cli.corpus_smoke:main",
    "query-doctor-demo=query_doctor.cli.demo_data:main",
    "query-doctor-demo-preflight=query_doctor.cli.demo_preflight:main",
    "query-doctor-optimize-query=query_doctor.cli.optimize_query:main",
    "query-doctor-pipeline=query_doctor.cli.pipeline:main",
    "query-doctor-report=query_doctor.cli.report:main",
    "query-doctor-web=query_doctor.cli.web:main",
]


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
