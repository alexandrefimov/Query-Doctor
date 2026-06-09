# Query Doctor

Last reviewed: 2026-06-06

Language: English | [Russian](README.ru.md)

[![Safety CI](https://github.com/alexandrefimov/Query-Doctor/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/alexandrefimov/Query-Doctor/actions/workflows/ci.yml)
[![Package CI](https://github.com/alexandrefimov/Query-Doctor/actions/workflows/package.yml/badge.svg?branch=main)](https://github.com/alexandrefimov/Query-Doctor/actions/workflows/package.yml)
[![Docs CI](https://github.com/alexandrefimov/Query-Doctor/actions/workflows/docs.yml/badge.svg?branch=main)](https://github.com/alexandrefimov/Query-Doctor/actions/workflows/docs.yml)
[![CodeQL](https://github.com/alexandrefimov/Query-Doctor/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/alexandrefimov/Query-Doctor/actions/workflows/codeql.yml)
[![PyPI](https://img.shields.io/pypi/v/query-doctor.svg?cacheSeconds=300)](https://pypi.org/project/query-doctor/)

Query Doctor is a local-first Big Data query diagnostic tool focused today on
Apache Impala production triage. It helps operators rank suspicious Recent
queries, collect bounded profile context, derive deterministic evidence, and
generate validated reports without exposing raw SQL or raw profiles in trusted
browser/report surfaces.

Core rule:

```text
Python owns facts. LLM owns wording only.
```

Recent scan is the flagship workflow. Query ID diagnosis is secondary for one
known Impala query. Query Optimizer is separate, read-only, and does not execute
or echo submitted SQL.

## What It Is / Is Not

Query Doctor is:

- a local-first Impala production triage workbench;
- a deterministic evidence extractor;
- a Recent-query ranking workflow for operators and administrators;
- a safe report generator using validated facts;
- a practical tool for deciding what to inspect, change, and verify next;
- a Big Data SQL/lakehouse diagnostics wedge whose production triage engine is
  Apache Impala today, with a bounded Trino offline evidence import path.

Query Doctor is not:

- a generic AI chatbot over raw profiles;
- a replacement for the Impala Web UI;
- a tool that executes user SQL or optimizer draft SQL;
- a tool that sends raw SQL/profile data to remote services by default;
- a root-cause oracle;
- a live multi-engine query collector today.

## What It Does

- Scans completed Recent queries as the primary workflow, with Running queries
  and one explicit Known Query ID as focused secondary modes for Apache Impala.
- Works with Cloudera Manager when available, or with direct Impala daemon
  profile/query-list endpoints for vanilla, Ambari-style, or otherwise
  non-Cloudera-Manager clusters.
- Direct Impala profile collection keeps text endpoints as the default
  compatibility path; JSON profile probing is opt-in and falls back to text for
  older Impala versions. Analyzer facts record only safe capability summaries
  such as the selected endpoint format and probe status.
- Direct Impala can also opt in to a bounded `/profile_docs/?json`
  counter-stability probe with `/profile_docs` HTML fallback. Query Doctor
  stores only a safe allowlisted registry context, not raw counter
  documentation.
- Direct Impala can opt in to bounded `/admission?json` aggregate context.
  Missing older endpoints are non-fatal, and the analyzer treats the result as
  context-only unless selected-query admission wait/result evidence exists.
- Optionally collects bounded Prometheus runtime metric summaries for direct
  Impala workflows and bounded read-only Impala metadata through `impala-shell`.
- Ranks suspicious cases and action candidates from deterministic analyzer
  facts, not LLM scoring.
- Generates trusted reports only after deterministic normalization,
  sanitization, and validation.
- Provides a separate read-only Query Optimizer workflow for pasted SQL review,
  plus an explicit details-page optimizer action for server-owned analyzed
  cases.
- Imports already-sanitized Trino evidence packages through
  `query-doctor-trino-import`, compact sanitized local event-store records
  through `query-doctor-trino-event-store-import`, compact sanitized operator
  HTTP event archives through
  `query-doctor-trino-http-event-archive-import`, one explicit compact
  sanitized operator HTTP query-detail archive through
  `query-doctor-trino-http-query-detail-archive-import`, and one explicit
  compact sanitized local query-detail JSON through
  `query-doctor-trino-query-detail-import`, plus one explicit compact sanitized
  local query-list aggregate JSON through
  `query-doctor-trino-query-list-import`, plus one explicit compact sanitized
  local statement-stats JSON through
  `query-doctor-trino-statement-stats-import`, plus one explicit compact
  sanitized local pruned QueryInfo JSON through
  `query-doctor-trino-query-info-pruned-import`, plus one explicit compact
  sanitized local metadata summary JSON through
  `query-doctor-trino-metadata-summary-import`, then emits only safe summaries
  or normalized raw-free fact boundaries.
- Validates future Trino event-source contracts through
  `query-doctor-trino-event-source-contract-check`, checking only source type,
  auth-reference label, schema version, bounds, and redaction rules without
  contacting Trino or reading event records.
- Validates a future one-query Trino coordinator query-info target through
  `query-doctor-trino-coordinator-query-info-target-check`, checking a compact
  source contract, safe auth-reference label, one Query ID bound, coordinator
  base-URL shape, limits, and redaction rules without contacting Trino,
  fetching query-info, or echoing the URL or Query ID.
- Validates future Trino metadata allowlist source contracts through
  `query-doctor-trino-metadata-source-contract-check`, checking only safe source
  references, explicit relation/column allowlist shape, bounds, and redaction
  rules without contacting Trino, reading metadata, submitting SQL, or echoing
  object identifiers.
- Imports one compact sanitized local Trino metadata summary through
  `query-doctor-trino-metadata-summary-import`, after an accepted
  `metadata_allowlist` source contract, mapping only aggregate relation/column
  coverage and stats-completeness counts into a raw-free normalized fact
  boundary. It performs no network read, does not execute metadata SQL, and
  rejects raw identifiers or metadata values before mapping.
- Probes one Trino coordinator pruned query-info endpoint through
  `query-doctor-trino-coordinator-query-info-pruned-probe`, issuing only a
  bounded `GET /v1/query/{queryId}?pruned=true` after the same source-contract
  gate. An optional local `--auth-header-file` can provide one operator-managed
  `Authorization` header line for that bounded read; the file path and header
  value are never printed. The command does not follow HTTP redirects and emits
  a safe summary without URL, Query ID, raw QueryInfo, normalized facts,
  browser/report output, or live Query ID diagnosis.
- Imports one Trino coordinator pruned QueryInfo response through
  `query-doctor-trino-coordinator-query-info-pruned-import`, after the same
  source-contract gate, mapping only allowlisted lifecycle, timing,
  row/byte, memory/spill, blocked, and task-count fields into a raw-free
  normalized fact boundary. It supports the same optional local
  `--auth-header-file` for one operator-managed `Authorization` header and does
  not follow HTTP redirects, store or print raw QueryInfo, URL, Query ID, query
  text, session fields, endpoint URLs, object names, stage/task detail, auth
  header paths or values, browser/report output, or live Query ID diagnosis.
  Maintainers can add
  `--boundary-out <raw-free-trino-boundary.json>` to write the direct
  `engine_fact_boundary_v1` payload for strict local readiness auditing without
  echoing the output path.
- Imports one compact sanitized local pruned QueryInfo JSON through
  `query-doctor-trino-query-info-pruned-import`, after an accepted
  `coordinator_query_info` source contract, mapping only allowlisted lifecycle
  and `queryStats` fields into a raw-free normalized fact boundary. It performs
  no network read and rejects raw QueryInfo fields such as Query IDs, query
  text, session fields, endpoint URLs, object names, and stage/task detail.
- Builds deterministic Trino compact diagnosis JSON through
  `query-doctor-diagnose-trino-compact` from an already raw-free
  `engine_fact_boundary_v1` payload, from one sample selected out of a Trino
  package boundary export with `--sample-index`, or directly from accepted
  single-boundary Trino imports through `--diagnosis-out`. The local
  `/trino/compact-diagnosis` page can render the same deterministic diagnosis
  from already raw-free direct boundary JSON, or from a selected package-export
  sample boundary. Metadata summary boundaries are rejected because they are
  aggregate coverage evidence, not compact diagnosis inputs. Both paths emit
  a raw-free diagnostic-lane summary, attention areas including
  planning-heavy timing and high peak memory, change directions, verification
  prompts, and limitations without root-cause claims, raw input echo,
  Details/trusted report output, optimizer behavior, live Recent scans, or Trino
  SQL execution.
- Keeps raw SQL, raw profiles, raw metadata, local paths, secrets, subprocess
  output, model/runtime internals, and raw artifact filenames out of browser and
  trusted report surfaces.

## Supported Scope

| Area | Supported today | Not current support |
| --- | --- | --- |
| Query engine | Apache Impala production triage; Trino sanitized offline evidence package, bounded local event-store, bounded HTTP event archive, bounded HTTP query-detail archive, bounded local query-detail, bounded local query-list aggregate, bounded local statement-stats import, bounded local pruned QueryInfo import, bounded local metadata summary import, source-contract/target checks, metadata source-contract check, one-query pruned coordinator probe, one-query pruned coordinator fact import, local compact diagnosis from raw-free boundary JSON excluding metadata summary boundaries, and isolated `/trino/compact-diagnosis` page | Trino live collection, live Trino Recent scans, live Trino Query ID diagnosis, Trino metadata collection, Trino Details/trusted report output, Trino optimizer behavior, or Query Doctor-generated Trino SQL. |
| Trino offline/local import | `query-doctor-trino-import` validates already-sanitized compact packages; `query-doctor-trino-event-store-import` validates compact sanitized local event records; `query-doctor-trino-query-detail-import` validates one explicit compact sanitized local query-detail JSON; `query-doctor-trino-query-list-import` validates one explicit compact sanitized local query-list aggregate JSON; `query-doctor-trino-statement-stats-import` validates one explicit compact sanitized local statement-stats JSON; `query-doctor-trino-query-info-pruned-import` validates one explicit compact sanitized local pruned QueryInfo JSON after a source contract; `query-doctor-trino-metadata-summary-import` validates one explicit compact sanitized local metadata summary JSON after a metadata source contract; all can emit raw-free normalized fact boundaries | Direct Trino coordinator collection, raw event/query-info ingestion, live query-list crawling, `/v1/statement` collection, arbitrary package contents, raw query IDs, raw SQL, stack traces, object names, stage/task detail, raw metadata, raw identifiers, or connector internals. |
| Trino compact diagnosis | `query-doctor-diagnose-trino-compact` reads one already raw-free `engine_fact_boundary_v1` payload excluding local metadata summary boundaries, or one selected sample boundary from a package boundary export using `--sample-index`, and writes a raw-free `diagnostic_lane` summary, deterministic attention areas, including planning-heavy timing and high peak memory, plus change directions, verification prompts, and limitations; `/trino/compact-diagnosis` renders the same diagnosis locally for accepted direct boundaries or selected package samples without echoing submitted JSON | Raw Trino payload ingestion, metadata summary diagnosis, root-cause claims, Details/trusted report output, optimizer behavior, live Recent scans, live Query ID diagnosis, Query Doctor-generated SQL, or accepting arbitrary compact JSON. |
| Trino HTTP event archive import | `query-doctor-trino-http-event-archive-import` validates one explicit `http_event_listener_archive` source contract, fetches one explicit operator HTTP(S) archive URL, enforces contract bounds, and emits safe summaries or raw-free normalized fact boundaries | Default network discovery, Trino coordinator query-history reading, URL echoing, credentials in URLs, endpoint/topic/database config ingestion, raw event records, SQL submission, browser/report output, or live Recent scans. |
| Trino HTTP query-detail archive import | `query-doctor-trino-http-query-detail-archive-import` validates one explicit `http_query_detail_archive` source contract, fetches one explicit operator HTTP(S) archive URL, enforces contract bounds, and emits a safe summary or raw-free normalized fact boundary for one compact sanitized query-detail record | Default network discovery, Trino coordinator query-info fetching, URL echoing, credentials in URLs, endpoint config ingestion, raw query-detail records, raw query IDs, SQL submission, browser/report output, or live Query ID diagnosis. |
| Trino source-contract gate | `query-doctor-trino-event-source-contract-check` validates one explicit compact event-source contract JSON, including source type, safe auth-reference label, accepted event schema, bounds, and redaction/storage policy | Endpoint/topic/database config ingestion, credentials, raw event records, query-history collection, browser/report output, or live support claims. |
| Trino coordinator query-info target gate | `query-doctor-trino-coordinator-query-info-target-check` validates one compact future query-info source contract plus one explicit coordinator base URL and Query ID shape, then emits only a URL-free and Query-ID-free safe summary | Network reads, query-info fetching, broad query-history collection, URL or Query ID echoing, credentials in URLs, raw QueryInfo JSON, SQL submission, browser/report output, live Query ID diagnosis, or support claims. |
| Trino metadata source-contract gate | `query-doctor-trino-metadata-source-contract-check` validates one compact future metadata allowlist contract with safe source references, explicit relation/column allowlist shape, bounds, and redaction rules, then emits only a path-free and identifier-free safe summary | Metadata reads, metadata SQL execution, broad object crawling, raw identifier output, raw metadata storage, browser/report output, Details/trusted reports, optimizer behavior, or support claims. |
| Trino local metadata summary import | `query-doctor-trino-metadata-summary-import` validates one explicit compact sanitized aggregate metadata summary against a `metadata_allowlist` source contract and maps only relation/column coverage and stats-completeness counts into raw-free normalized facts | Network reads, metadata SQL execution, raw metadata, raw catalog/schema/table/column identifiers, metadata values, object crawling, browser/report output, Details/trusted reports, optimizer behavior, live metadata collection, or support claims. |
| Trino coordinator pruned query-info probe | `query-doctor-trino-coordinator-query-info-pruned-probe` performs one bounded `GET /v1/query/{queryId}?pruned=true` only after an accepted `coordinator_query_info` contract with operator-managed auth reference, can use one local `--auth-header-file` containing an `Authorization` header, validates the response as a bounded JSON object, and emits only a safe probe summary | Mapping raw QueryInfo to facts, storing or printing raw QueryInfo, URL or Query ID echoing, auth header paths or values, credentials in URLs, broad query-history collection, SQL submission, browser/report output, live Query ID diagnosis, or support claims. |
| Trino coordinator pruned query-info import | `query-doctor-trino-coordinator-query-info-pruned-import` performs the same one bounded pruned query-info read, can use the same local `--auth-header-file`, then maps only allowlisted `queryStats` and lifecycle fields into raw-free normalized facts and boundary JSON; `--boundary-out` can write the direct raw-free `engine_fact_boundary_v1` payload for local readiness auditing. The dev-only `scripts/trino_one_query_live_handoff.py` wrapper uses the same one-query read plus readiness/product-surface gates; for real-cluster handoff runs, prefer `--query-id-file <operator-query-id-file>` so the explicit Query ID stays out of shell history and process args. | Raw QueryInfo storage/output, URL or Query ID echoing, auth header paths or values, credentials in URLs, query text/session/object/stage/task detail, connector internals, broad query-history collection, SQL submission, browser/report output, live Query ID diagnosis, or support claims. |
| Trino local pruned query-info import | `query-doctor-trino-query-info-pruned-import` validates one explicit compact sanitized local pruned QueryInfo JSON against a `coordinator_query_info` source contract and maps only allowlisted `state` and `queryStats` fields into raw-free normalized facts | Network reads, raw QueryInfo fields, Query ID echoing, query text/session/object/stage/task detail, connector internals, broad query-history collection, SQL submission, browser/report output, live Query ID diagnosis, or support claims. |
| Spark compact support surfaces | Registered bounded compact Spark History Server summary collection for one explicit application, Spark compact evidence-package build/validation/fixture export, plus local compact-diagnosis CLI/direct web page for raw-free contract shaping | Production Spark triage support, live Recent scans, Details/trusted report output, optimizer behavior, raw event logs, raw SQL/plans, environment/log dumps, Spark job execution, or any public claim beyond the bounded compact surfaces; no public Spark engine support. |
| Cloudera Manager | Full Recent discovery/profile/metrics/events context for Impala workflows | Generic cluster diagnosis beyond the Query Doctor flow. |
| Direct Impala | Bounded Recent scans, Running scans, and one Known Query ID through impalad daemon endpoints | Cloudera Manager events, broad log scraping, or SQL execution. |
| Runtime metrics | Optional bounded Prometheus summaries for configured direct Impala workflows | Raw time-series output or arbitrary PromQL from users. |
| Metadata | Read-only allowlisted metadata statements through `impala-shell` | User SQL execution or unbounded metadata crawling. |
| Reports and optimizer | Python-owned facts, validation, and explicit selected-case actions | LLM output as trusted evidence or automatic batch LLM jobs. |

Future Big Data SQL/lakehouse live collectors, broader providers, prepared
event/log sources, and Cluster Doctor workflows remain roadmap seams, not
current support. Trino support is limited to sanitized offline package import,
bounded local event-store import, bounded HTTP event archive import, bounded
HTTP query-detail archive import, bounded local query-detail import, and
bounded local query-list aggregate import, plus bounded local statement-stats
import, bounded local metadata summary import, event-source contract checking,
dry-run coordinator query-info target checking, and metadata source-contract
checking, plus one-query pruned coordinator probe and one-query pruned
coordinator fact import and local compact diagnosis from raw-free boundary JSON;
see
[docs/engines/trino-evidence-package-templates.md](docs/engines/trino-evidence-package-templates.md).

Apache Impala also has upstream work around native AI query profile analysis.
Query Doctor aligns with that direction by staying focused on local-first
production triage across many queries, deterministic evidence, safe enrichment,
and validated raw-free reports. See
[docs/upstream-impala-ai-analyzer.md](docs/upstream-impala-ai-analyzer.md).

## Install

Install the current public package from PyPI:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install query-doctor
```

For local development from a checkout:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
pre-commit install
```

Local JSON configuration is documented in [docs/configuration.md](docs/configuration.md).
The preferred workstation path is `~/.qdcreds/query-doctor-config.json`;
secrets stay in environment variables or local env files.

## Run The Demo

The synthetic demo is the fastest way to see the product. It is deterministic,
local-only, and contains no real SQL, profiles, metadata, hostnames, users, or
credentials.

```bash
query-doctor-demo-preflight
DEMO_PACK="${TMPDIR:-/tmp}/query-doctor-demo-pack"
query-doctor-demo --out "$DEMO_PACK" --overwrite
QUERY_DOCTOR_ACTION_OUTCOMES_PATH="$DEMO_PACK/action_outcomes.jsonl" \
  query-doctor-web --host 127.0.0.1 --port 8766 --batch-summary "$DEMO_PACK/batch_summary.json"
```

For a read-only click-through demo that matches the public synthetic UI, use
the one-command mode documented in [docs/demo-mode.md](docs/demo-mode.md):
`query-doctor-web --public-demo`. It generates the synthetic demo pack in a
dedicated temp directory, forces Python-only mode, ignores default local config,
and blocks all POST actions.

Open the localhost URL printed by `query-doctor-web`. Start with
`/?query_group=workloads#workload-action-queue` to show the workload action
queue and local synthetic action outcomes before opening workload Details.
When a Recent summary has repeated safe row-level workload fingerprints but no
materialized group payload, the UI derives bounded repeated groups from the
sanitized rows; those groups have no baseline or regression claim until local
history evidence is available.

The local web UI starts with a bounded search form and renders synthetic
Finished Queries results for review:

![Synthetic Query Doctor demo search form](docs/assets/demo_search.png)

![Synthetic Query Doctor finished queries results](docs/assets/demo_finished_queries.png)

The `0.5.0` synthetic demo pack contains eleven sanitized cases covering
Workloads/Action Queue, trusted optimizer recommendations, stats maintenance,
storage/HDFS follow-up, frequent-short workloads, mixed signals, unknown but
useful limited evidence, and direct-Impala compatibility. See
[docs/demo-cases.md](docs/demo-cases.md) for the full scenario list and talk
track.

## Product Scope

| Surface | Current status |
| --- | --- |
| Query engine | Apache Impala is the only production engine support. |
| Cloudera Manager | Full Recent discovery/profile/metrics/events context for Impala workflows. |
| Direct Impala | Bounded Recent scans, Running scans, and one Known Query ID through impalad daemon endpoints; no Cloudera Manager events and no SQL execution. |
| Runtime metrics | Optional bounded Prometheus summaries for configured direct Impala workflows; no arbitrary PromQL from users. |
| Metadata | Read-only allowlisted Impala metadata statements through `impala-shell`; no user SQL execution or unbounded metadata crawl. |
| Reports and optimizer | Python-owned facts, validation, and explicit selected-case actions; no automatic batch LLM jobs. |
| Trino private preview | Closed test-cluster smoke and sanitized evidence-package artifacts for maintainers only; no public Trino engine support, live collection, browser/report output, optimizer behavior, or Query Doctor-generated SQL. |
| Spark compact support surfaces | Registered bounded compact Spark History Server summary intake and compact evidence-package build/validation/fixture export for raw-free contract shaping only; no public Spark engine support, Recent scans, Details/trusted report output, optimizer behavior, raw event logs, raw SQL/plans, environment/log dumps, or Spark job execution. |

Future Big Data SQL/lakehouse engines, broader providers, prepared event/log
sources, and Cluster Doctor workflows remain roadmap seams, not current
support. Use [docs/engine-support-gap-matrix.md](docs/engine-support-gap-matrix.md)
for the current engine support, fixture-only, and research boundary.

## Main Workflows

- `query-doctor-web --help`: local browser UI for Recent scan, Running now, one
  Known Query ID, Details pages, explicit report actions, and explicit
  details-page optimizer actions.
- `query-doctor-batch-recent --help`: headless Recent scan workflow for bounded
  local collection and ranking.
- `query-doctor-analyze --help`: deterministic analyzer over collected local
  case files.
- `query-doctor-report --help`: validated report generation from Python-owned
  facts.
- `query-doctor-optimize-query --help`: read-only pasted-SQL optimizer review.

Every packaged console script accepts `--help`. Root-level compatibility
launchers have been removed; use `query-doctor-*` commands or
`python -m query_doctor.cli.<command_module>` from an uninstalled checkout.

Query Doctor is supported as a single-user, local-first tool run by an operator
with their own local Cloudera Manager, Kerberos, Impala, Prometheus, and LLM
credentials. Use localhost or a tightly controlled local bind for the web UI.
Do not deploy ordinary local mode as a shared service without a separate design
for authentication, authorization, tenant/job isolation, audit logging,
TLS/reverse-proxy trust, and resource limits. Shared public demos should use
the read-only `query-doctor-web --public-demo` mode.

## Safety Model

- Python/analyzer-owned facts are the only trusted diagnostic evidence.
- Raw LLM output is untrusted unless normalized, sanitized, and validated.
- Browser-visible UI and trusted reports must not expose raw SQL, raw profiles,
  raw metadata, local paths, secrets, subprocess output, model/runtime internals,
  or raw artifact filenames.
- External collection must be explicit, bounded, read-only, redacted, and safe
  by default.
- Local config `privacy_mode` defaults to `true`; disabling it can relax local
  artifact identifier/host masking, but browser-visible UI and trusted reports
  still do not show raw SQL, profiles, or metadata.
- Local config `no_llm=true` keeps report and optimizer actions on deterministic
  Python-owned output.
- Query Optimizer accepts only a single safe read-only statement and never
  executes pasted SQL.

See [docs/safety-contract.md](docs/safety-contract.md) for the full trust and
redaction contract. For a reviewer-oriented overview, see
[docs/security-model.md](docs/security-model.md).

## Documentation

Start with [docs/README.md](docs/README.md). It separates current user docs,
operations guides, architecture contracts, audit docs, and supporting
references.

High-value next reads:

- [docs/demo-mode.md](docs/demo-mode.md): synthetic demo pack generation and
  README screenshot refresh path.
- [docs/DEMO.md](docs/DEMO.md): localhost UI demo runbook and talk track.
- [docs/local-smoke.md](docs/local-smoke.md): local validation and smoke checks.
- [docs/credentials.md](docs/credentials.md): local credentials layout.
- [docs/roadmap.md](docs/roadmap.md): implemented scope and planned seams.
- [docs/security-model.md](docs/security-model.md): public security, privacy,
  and demo-sharing overview.
- [docs/query-optimizer-contract.md](docs/query-optimizer-contract.md):
  optimizer trust boundary.
- [docs/release-checklist.md](docs/release-checklist.md): final tag,
  package-index, and visibility-change checklist.

The canonical documentation language is English. The main Russian companion
README is [README.ru.md](README.ru.md); additional Russian companion pages live
under [docs/i18n/ru/](docs/i18n/ru/) where useful.

## Development Checks

For ordinary changes, run focused tests for the touched area and always run:

```bash
git diff --check
```

Use [docs/agent-quickstart.md](docs/agent-quickstart.md) and
[docs/test-matrix.md](docs/test-matrix.md) to choose focused validation. Before
release cleanup or public-sharing work, broaden to:

```bash
pre-commit run --all-files
scripts/local_gate.sh
query-doctor-demo-preflight --public-release
```

Stage only explicit files. Do not commit generated cases, reports, local
configs, credentials, raw profiles, raw metadata, or temporary outputs.

## Public Status

This repository is public. Public source releases start at `v0.4.2`; `v0.6.0`
continues that public source release line. Older package-index releases remain
visible on
[query-doctor on PyPI](https://pypi.org/project/query-doctor/) where needed for
installed-artifact history. The public license is Apache-2.0.

PyPI publishing uses GitHub OIDC Trusted Publishing. The repository-side
`testpypi` and `pypi` environments require maintainer approval and do not use
stored package-index API tokens.

## Licensing

Query Doctor is licensed under the Apache License, Version 2.0
(`Apache-2.0`). See [LICENSE](LICENSE).

Apache, Apache Impala, and Impala are trademarks of The Apache Software
Foundation. Query Doctor is an independent project and is not endorsed by The
Apache Software Foundation or the Apache Impala project.
