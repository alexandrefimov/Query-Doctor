"""Curated static Help page for the local Query Doctor web UI."""

from __future__ import annotations

from typing import Any

from query_doctor.web.ui.pages import render_page


def render_help_page(settings: Any) -> str:
    return render_page(
        settings,
        active_nav="help",
        show_run_panel=False,
        extra_sections=[render_help_content()],
    )


def render_demo_guide_page(settings: Any) -> str:
    """Legacy /demo alias.

    Demo talk-track content lives in repository docs. The product UI keeps one
    maintained static guide so navigation does not drift from Details behavior.
    """

    return render_help_page(settings)


def render_help_content() -> str:
    return """
<section class="panel docs-panel" aria-label="Query Doctor help">
<h1>Help</h1>
<div class="report-body">
<p>Query Doctor is a local-first Big Data Query Diagnostic Tool for Apache Impala workloads. It combines deterministic profile analysis, bounded metadata checks, optional bounded Cloudera Manager metric context, and validated report generation. The implemented engine is Apache Impala only.</p>

<h2>On this page</h2>
<ul>
<li><a href="#quick-start">Quick start</a></li>
<li><a href="#workflows">Workflows</a></li>
<li><a href="#results-table">Results table</a></li>
<li><a href="#details-actions">Details and LLM actions</a></li>
<li><a href="#metadata">Metadata</a></li>
<li><a href="#safety">Safety boundary</a></li>
<li><a href="#github-docs">GitHub documentation</a></li>
<li><a href="#common-questions">Common questions</a></li>
</ul>

<h2 id="quick-start">Quick start</h2>
<ul>
<li><a href="/">Open Diagnose</a> and keep <strong>Recent queries</strong> selected when you want batch triage.</li>
<li>Inside Recent queries, choose <strong>Finished queries</strong> for completed profiles or <strong>Running now</strong> for a lower-confidence live snapshot.</li>
<li>Switch to <strong>Known Query ID</strong> when you already have one query ID. Recent-query filters are intentionally hidden in that mode.</li>
<li>Open a result row and review <strong>Findings</strong> first. Expand <strong>Evidence details</strong> only when you need supporting analyzer facts.</li>
<li>Run <strong>LLM Report</strong> or <strong>Query LLM optimizer</strong> only from a selected Details page.</li>
</ul>

<h2 id="workflows">Workflows</h2>
<p>Most demos and investigations start from <strong>Recent queries</strong>. Use <strong>Known Query ID</strong> only when you already have one query ID and want to skip batch discovery.</p>

<details>
<summary>Recent queries</summary>
<p>Recent queries is the primary administrator workflow. It reads query summaries from Cloudera Manager, applies filters, collects bounded profiles for selected queries, runs deterministic analysis, and shows action-oriented groups. Web scans do not auto-run LLM reports or optimizer drafts.</p>
<ul>
<li><strong>Scan target</strong> switches between completed-query evidence and a live running-query snapshot.</li>
<li><strong>Scan date</strong> and <strong>Scan Hour</strong> appear only for Finished queries and select one Cloudera Manager summary hour from today or the previous two days.</li>
<li><strong>Minimum duration</strong>, <strong>Username</strong>, and <strong>Resource pool</strong> narrow the summary set before profile collection.</li>
<li><strong>Parallelism</strong> controls profile fetch and local analysis. <strong>Metadata parallelism</strong> separately bounds read-only metadata collection.</li>
<li><strong>Collect CM events</strong> gathers one bounded Cloudera Manager Events context for the scan window. Events do not affect candidate selection and are not standalone proof for a query.</li>
<li>Results are grouped as <strong>Bad queries</strong>, <strong>Suspicious queries</strong>, <strong>Optimization candidates</strong>, and <strong>Stats refresh candidates</strong>.</li>
<li><strong>Optimization candidates</strong> are deterministic query-shape review opportunities. They do not promise speedup and do not execute SQL.</li>
<li><strong>Stats refresh candidates</strong> require metadata evidence, estimate mismatch, and planning-sensitive runtime symptoms. They still require EXPLAIN comparison and a comparable rerun.</li>
<li><strong>Only queries with spills</strong> is a display filter over analyzed results; it does not change scan parameters.</li>
<li><strong>Collect CM metrics</strong> enables bounded Cloudera Manager time-series summaries for the top ranked analyzed cases. The default budget is 10 cases.</li>
</ul>
</details>

<details>
<summary>Running now</summary>
<p>Running now uses the same result and details shape as Finished queries, but scans only queries that are running at scan time. It has no Scan date or Scan Hour filter. Profiles can be incomplete until a query finishes, so findings can be lower-confidence than completed-query analysis. CM events and runtime metrics are enabled by default as bounded runtime context.</p>
</details>

<details>
<summary>Known Query ID</summary>
<p>Known Query ID is for one explicit query ID. The mode has only a Query ID field and a Run button. It collects and analyzes one query without automatic LLM execution, clears the input after submit, and appends the result to the Known Query ID analysis table.</p>
</details>

<h2 id="results-table">Results table</h2>
<p>The table is a triage surface. Open a row for Details before making production changes.</p>

<details>
<summary>Columns and groups</summary>
<ul>
<li><strong>Rank</strong> is ordering within the current group, not a root-cause verdict.</li>
<li><strong>Query ID</strong> opens the details page for the selected case.</li>
<li><strong>User</strong> shows the sanitized Cloudera Manager query user.</li>
<li><strong>Score</strong> is a deterministic triage priority from analyzer facts.</li>
<li><strong>Duration</strong> comes from Cloudera Manager summary data when available.</li>
<li><strong>STATS</strong> summarizes table statistics availability.</li>
<li><strong>META</strong> summarizes metadata collection status.</li>
<li><strong>Optimization candidates</strong> use Candidate, Impact, Confidence, Next action, and Review scope columns.</li>
<li><strong>Stats refresh candidates</strong> use Candidate, Need, Speed benefit, Confidence, and Next action columns.</li>
<li>Cases without triage severity and without Medium/High optimization or stats-refresh candidacy are intentionally hidden from separate result groups.</li>
<li><strong>Summary</strong> explains deterministic signals without raw evidence.</li>
</ul>
</details>

<h2 id="details-actions">Details and LLM actions</h2>
<p>Details shows a browser-safe summary for one analyzed query. <strong>Findings</strong> are open by default. <strong>Evidence details</strong> keep runtime, metadata, runtime metrics, and technical signals available without turning the first screen into a low-level evidence dump.</p>
<p><strong>LLM actions</strong> contains explicit buttons for LLM Report, Query LLM optimizer, and combined report + optimizer execution. Outputs are rendered only after deterministic validation. If validation rejects generated output, partial content stays untrusted and hidden.</p>

<details>
<summary>Validated reports</summary>
<p>Analyzer facts are the source of truth. The LLM owns wording only. Trusted reports default to English, Russian remains available through the same language-specific prompt, normalizer, and validator boundary, and raw LLM output is never trusted until validation passes.</p>
<p>The report writer reads deterministic facts, Python-owned report contract digest, case differentiators, and Python-owned recommendation candidates. It must not infer from raw profile text or raw SQL.</p>
</details>

<details>
<summary>Details-page Query LLM optimizer</summary>
<p>The details-page optimizer uses server-owned source scope from the analyzed case. Python classifies risk, selects a mode or recipe, may execute a narrow deterministic recipe patch, otherwise asks the LLM to assemble a draft, and then validates read-only scope, table set, filters, joins, projection shape, result shape, and recipe-specific invariants before any SQL draft is trusted.</p>
<p>If validation fails, Query Doctor can show trusted recommendations-only or no-rewrite guidance instead of an unsafe draft.</p>
</details>

<h2 id="metadata">Metadata</h2>
<p>Metadata collection is explicit, bounded, read-only, and allowlisted. Metadata can be unavailable or partial; that is a normal degraded state.</p>

<details>
<summary>Metadata allowlist</summary>
<ul>
<li>SHOW CREATE TABLE</li>
<li>SHOW TABLE STATS</li>
<li>SHOW COLUMN STATS</li>
</ul>
<p>Query Doctor does not run SELECT, COMPUTE, REFRESH, INVALIDATE, MSCK, SHOW PARTITIONS, DESCRIBE, DDL, or DML for metadata collection.</p>
</details>

<h2 id="safety">Safety boundary</h2>
<p>Browser UI intentionally hides raw query text, raw profile text, raw metadata output, filesystem locations, case directory details, process output, secrets, environment secret values, runtime internals, and raw evidence links. This is a product boundary, not a missing feature.</p>
<p>Safe browser output means summarized deterministic facts, statuses, validated reports, trusted optimizer outcomes, and bounded limitations.</p>

<h2 id="github-docs">GitHub documentation</h2>
<p>This page stays short and task-oriented. Full documentation lives in the repository on GitHub:</p>
<ul>
<li><a href="https://github.com/alexandrefimov/Query-Doctor/blob/main/README.md" target="_blank" rel="noopener noreferrer">Project README</a> - install, commands, workflow overview, and current public status.</li>
<li><a href="https://github.com/alexandrefimov/Query-Doctor/blob/main/docs/README.md" target="_blank" rel="noopener noreferrer">Documentation index</a> - the maintained map of current docs.</li>
<li><a href="https://github.com/alexandrefimov/Query-Doctor/blob/main/docs/safety-contract.md" target="_blank" rel="noopener noreferrer">Safety contract</a> - browser/report trust and redaction rules.</li>
<li><a href="https://github.com/alexandrefimov/Query-Doctor/blob/main/docs/roadmap.md" target="_blank" rel="noopener noreferrer">Roadmap</a> - implemented scope, near-term work, and future seams.</li>
<li><a href="https://github.com/alexandrefimov/Query-Doctor/blob/main/docs/DEMO.md" target="_blank" rel="noopener noreferrer">Synthetic demo docs</a> - maintained demo talk track outside the product UI.</li>
</ul>

<h2 id="common-questions">Common questions</h2>
<details>
<summary>Why can I not see the query SQL?</summary>
<p>Raw query text can contain sensitive business logic, table names, and literals. Query Doctor shows safe summaries and deterministic findings instead.</p>
</details>
<details>
<summary>Why can I not see the full profile?</summary>
<p>Full profiles can be large and sensitive. The UI shows analyzer-owned facts and bounded status summaries.</p>
</details>
<details>
<summary>Why is metadata partial or skipped?</summary>
<p>Metadata collection is bounded. It can be disabled, unavailable, limited to top cases, or stopped by safety limits. Profile-based findings still remain usable.</p>
</details>
<details>
<summary>Why does Recent queries not generate reports automatically?</summary>
<p>To avoid mass LLM execution and trusted-looking output without a selected case. Report generation remains an explicit user action.</p>
</details>
<details>
<summary>Can Query Doctor execute optimized SQL?</summary>
<p>No. Details-page optimizer actions can produce trusted drafts or recommendations, but Query Doctor never executes generated SQL. Benchmarks must be separate explicit read-only checks outside the UI workflow.</p>
</details>
<details>
<summary>Does a stats gap mean stats caused the slowdown?</summary>
<p>No. Treat it as a stats refresh candidate only when metadata gaps, estimate mismatch, and planning-sensitive runtime symptoms line up. Confirmation requires EXPLAIN comparison and a comparable rerun.</p>
</details>
<details>
<summary>Does runtime metrics context prove root cause?</summary>
<p>Usually no. Runtime metrics are bounded context. They become stronger only when correlated with deterministic profile evidence.</p>
</details>

<details>
<summary>Future scope</summary>
<h3>Can Query Doctor support Trino, Spark SQL, StarRocks, Doris, ClickHouse, Dremio, or another Big Data SQL engine?</h3>
<p>Not yet. Future engine work is scoped to actively developed Big Data SQL, MPP analytical, and lakehouse runtimes, not generic OLTP databases. Each engine needs a safe read-only collection contract, metadata allowlist, parser/profile support, browser safety tests, and report validator coverage before it becomes supported behavior.</p>
<h3>Does the storage backend matter?</h3>
<p>Yes, but it is a separate dimension from the query engine. Future storage context for HDFS, S3-compatible object storage, Iceberg, Hudi, Delta, Kudu, or engine-internal analytical storage must be collected as bounded analyzer-owned facts. Storage context can support candidates such as small-file risk or planning pressure, but it cannot prove root cause by itself.</p>
</details>
</div>
</section>
""".strip()
