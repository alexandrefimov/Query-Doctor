"""Running query analysis page for the local Query Doctor web UI."""

from __future__ import annotations

from typing import Any


def render_running_queries_page(settings: Any) -> str:
    from query_doctor_web_ui import render_page

    return render_page(
        settings,
        active_nav="running",
        show_run_panel=False,
        extra_sections=[render_running_queries_content()],
    )


def render_running_queries_content() -> str:
    return """
<section class="panel docs-panel" aria-label="Running query analysis">
<h1>Running Queries</h1>
<div class="report-body">
<p>Dedicated workflow for currently running Impala queries. This page is a placeholder for a separate live-query analysis flow.</p>
<ul>
<li>It will inspect currently running CM query summaries instead of historical hour buckets.</li>
<li>Finished Queries date, hour, duration, user and pool filters are intentionally not reused here.</li>
<li>All matching running queries should be analyzed as one bounded read-only workflow.</li>
<li>No LLM reports will run automatically.</li>
</ul>
</div>
</section>
""".strip()
