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
<li><a href="#workflows">Workflows</a></li>
<li><a href="#results-table">Results table</a></li>
<li><a href="#details-actions">Details and LLM actions</a></li>
<li><a href="#metadata">Metadata</a></li>
<li><a href="#safety">Safety boundary</a></li>
<li><a href="#faq">FAQ</a></li>
</ul>

<h2 id="workflows">Workflows</h2>
<ul>
<li>Use <strong>Finished Queries</strong> first when you want to scan completed queries in a selected Cloudera Manager hour.</li>
<li>Use <strong>Running Queries</strong> when you want to inspect queries that are running now.</li>
<li>Use <strong>Specific Query</strong> when you already know one Query ID and want a focused diagnosis.</li>
<li>Use <strong>Query Optimizer</strong> for safe read-only review of a pasted SELECT/WITH statement before runtime profile evidence exists.</li>
<li><strong>LLM Report</strong> and <strong>Query LLM optimizer</strong> run only after an explicit action on a selected details page.</li>
</ul>

<details open>
<summary>Finished Queries</summary>
<p>Finished Queries is the primary administrator workflow. It reads query summaries from Cloudera Manager, applies filters, collects bounded profiles for selected completed queries, runs deterministic analysis, and shows action-oriented groups. Web scans do not auto-run LLM reports or optimizer drafts.</p>
<ul>
<li><strong>Scan date</strong> and <strong>Scan Hour</strong> select one Cloudera Manager summary hour from today or the previous two days.</li>
<li><strong>Minimum duration</strong>, <strong>Username</strong>, and <strong>Resource pool</strong> narrow the summary set before profile collection.</li>
<li><strong>Parallelism</strong> controls profile fetch and local analysis. <strong>Metadata parallelism</strong> separately bounds read-only metadata collection.</li>
<li><strong>Collect CM events</strong> gathers one bounded Cloudera Manager Events context for the scan window. Events are cluster context, not standalone proof for a query.</li>
<li>Results are grouped as <strong>Bad queries</strong>, <strong>Suspicious queries</strong>, <strong>Optimization candidates</strong>, and <strong>Stats refresh candidates</strong>.</li>
<li><strong>Optimization candidates</strong> are deterministic query-shape review opportunities. They do not promise speedup and do not execute SQL.</li>
<li><strong>Stats refresh candidates</strong> require metadata evidence, estimate mismatch, and planning-sensitive runtime symptoms. They still require EXPLAIN comparison and a comparable rerun.</li>
<li><strong>Only queries with spills</strong> is a display filter over analyzed results; it does not change scan parameters.</li>
<li><strong>Collect CM metrics</strong> enables bounded Cloudera Manager time-series summaries for the top ranked analyzed cases. The default budget is 10 cases.</li>
</ul>
</details>

<details>
<summary>Running Queries</summary>
<p>Running Queries uses the same result and details shape as Finished Queries, but scans only queries that are running at scan time. It has no Scan date or Scan Hour filter. CM events and CM metrics are enabled by default as bounded runtime context.</p>
</details>

<details>
<summary>Specific Query</summary>
<p>Specific Query is for one known Query ID. The page has only a Query ID field and a Run button. It collects and analyzes one query without automatic LLM execution, clears the input after submit, and appends the result to the Specific Query analysis table.</p>
</details>

<details>
<summary>Query Optimizer</summary>
<p>Query Optimizer accepts exactly one safe SELECT/WITH statement, validates it before table extraction and metadata collection, does not execute pasted SQL, and does not echo pasted SQL back into the browser after submit. It is not an LLM chat surface and not an automatic rewrite engine.</p>
</details>

<h2 id="results-table">Results table</h2>
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

<h2 id="details-actions">Details and LLM actions</h2>
<p>Details shows a browser-safe summary for one analyzed query. <strong>Findings</strong> are open by default. <strong>Evidence details</strong> keep runtime, metadata, CM metrics, and technical signals available without turning the first screen into a low-level evidence dump.</p>
<p><strong>LLM actions</strong> contains explicit buttons for LLM Report, Query LLM optimizer, and combined report + optimizer execution. Outputs are rendered only after deterministic validation. If validation rejects generated output, partial content stays untrusted and hidden.</p>

<details>
<summary>Validated reports</summary>
<p>Analyzer facts are the source of truth. The LLM owns wording only. Trusted reports default to English, Russian remains available through the same language-specific prompt, normalizer, and validator boundary, and raw LLM output is never trusted until validation passes.</p>
<p>The report writer reads deterministic facts, Python-owned report contract digest, case differentiators, and Python-owned recommendation candidates. It must not infer from raw profile text or raw SQL.</p>
</details>

<details>
<summary>Details-page Query LLM optimizer</summary>
<p>The details-page optimizer uses server-owned source scope from the analyzed case. Python classifies risk, selects a mode or recipe, the LLM assembles a draft, and Python validates read-only scope, table set, filters, joins, projection shape, result shape, and recipe-specific invariants before any SQL draft is trusted.</p>
<p>If validation fails, Query Doctor can show trusted recommendations-only or no-rewrite guidance instead of an unsafe draft.</p>
</details>

<h2 id="metadata">Metadata</h2>
<p>Metadata collection is explicit, bounded, read-only, and allowlisted. The allowlist is:</p>
<ul>
<li>SHOW CREATE TABLE</li>
<li>SHOW TABLE STATS</li>
<li>SHOW COLUMN STATS</li>
</ul>
<p>Query Doctor does not run SELECT, COMPUTE, REFRESH, INVALIDATE, MSCK, SHOW PARTITIONS, DESCRIBE, DDL, or DML for metadata collection. Metadata can be unavailable or partial; that is a normal degraded state.</p>

<h2 id="safety">Safety boundary</h2>
<p>Browser UI intentionally hides raw query text, raw profile text, raw metadata output, filesystem locations, case directory details, process output, secrets, environment secret values, runtime internals, and raw evidence links. This is a product boundary, not a missing feature.</p>
<p>Safe browser output means summarized deterministic facts, statuses, validated reports, trusted optimizer outcomes, and bounded limitations.</p>

<h2 id="faq">FAQ</h2>
<h3>Why can I not see the query SQL?</h3>
<p>Raw query text can contain sensitive business logic, table names, and literals. Query Doctor shows safe summaries and deterministic findings instead.</p>
<h3>Why can I not see the full profile?</h3>
<p>Full profiles can be large and sensitive. The UI shows analyzer-owned facts and bounded status summaries.</p>
<h3>Why is metadata partial or skipped?</h3>
<p>Metadata collection is bounded. It can be disabled, unavailable, limited to top cases, or stopped by safety limits. Profile-based findings still remain usable.</p>
<h3>Why does Finished Queries not generate reports automatically?</h3>
<p>To avoid mass LLM execution and trusted-looking output without a selected case. Report generation remains an explicit user action.</p>
<h3>Why does Query Optimizer clear the field after submit?</h3>
<p>To avoid echoing pasted SQL back into the browser. Results are built from safe extracted facts and limitations.</p>
<h3>Can Query Doctor execute optimized SQL?</h3>
<p>No. Query Optimizer is parse/analyze only. Benchmarks must be separate explicit read-only checks outside the UI workflow.</p>
<h3>Does a stats gap mean stats caused the slowdown?</h3>
<p>No. Treat it as a stats refresh candidate only when metadata gaps, estimate mismatch, and planning-sensitive runtime symptoms line up. Confirmation requires EXPLAIN comparison and a comparable rerun.</p>
<h3>Does CM metrics context prove root cause?</h3>
<p>Usually no. CM metrics are bounded runtime context. They become stronger only when correlated with deterministic profile evidence.</p>
<h3>Can Query Doctor support Trino, Spark SQL, StarRocks, Doris, ClickHouse, Dremio, or another Big Data SQL engine?</h3>
<p>Not yet. Future engine work is scoped to actively developed Big Data SQL, MPP analytical, and lakehouse runtimes, not generic OLTP databases. Each engine needs a safe read-only collection contract, metadata allowlist, parser/profile support, browser safety tests, and report validator coverage before it becomes supported behavior.</p>
<h3>Does the storage backend matter?</h3>
<p>Yes, but it is a separate dimension from the query engine. Future storage context for HDFS, S3-compatible object storage, Iceberg, Hudi, Delta, Kudu, or engine-internal analytical storage must be collected as bounded analyzer-owned facts. Storage context can support candidates such as small-file risk or planning pressure, but it cannot prove root cause by itself.</p>
</div>
</section>
""".strip()
