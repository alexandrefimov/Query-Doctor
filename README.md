# Query Doctor

Last reviewed: 2026-08-10

Language: English | [Russian](README.ru.md)

[![Safety CI](https://github.com/alexandrefimov/Query-Doctor/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/alexandrefimov/Query-Doctor/actions/workflows/ci.yml)
[![Package CI](https://github.com/alexandrefimov/Query-Doctor/actions/workflows/package.yml/badge.svg?branch=main)](https://github.com/alexandrefimov/Query-Doctor/actions/workflows/package.yml)
[![Docs CI](https://github.com/alexandrefimov/Query-Doctor/actions/workflows/docs.yml/badge.svg?branch=main)](https://github.com/alexandrefimov/Query-Doctor/actions/workflows/docs.yml)
[![CodeQL](https://github.com/alexandrefimov/Query-Doctor/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/alexandrefimov/Query-Doctor/actions/workflows/codeql.yml)
[![PyPI](https://img.shields.io/pypi/v/query-doctor.svg?cacheSeconds=300)](https://pypi.org/project/query-doctor/)

Query Doctor is a local-first Big Data query diagnostic tool focused on Apache
Impala production triage, with bounded local Trino production lanes. It helps
operators rank suspicious Recent
queries, collect bounded profile context, derive deterministic evidence, and
generate validated reports without exposing raw SQL or raw profiles in trusted
browser/report surfaces. The Query Doctor 0.11.0 release adds a
supported container image, Kubernetes manifests, a Helm chart, raw-free Online
History, and bounded parsing of one already-provided Impala EXPLAIN artifact.

Core rule:

```text
Python owns facts. LLM owns wording only.
```

Recent scan is the flagship workflow. Query ID diagnosis is secondary for one
known Impala query, with a local Trino lane for bounded retained-list Recent
diagnosis and one explicit Query ID when the required coordinator contracts are
configured. Query Optimizer is separate, read-only, and does not execute or echo
submitted SQL.

## Quickstart

```bash
python -m pip install query-doctor
query-doctor-self-test
query-doctor-analyze \
  --profile-text ./exported-impala-profile.txt \
  --out cases/cm-corpus
query-doctor-web --corpus-dir cases/cm-corpus
```

Run `query-doctor-self-test` after installation to verify the installed console
scripts, synthetic demo generation, one-profile analysis, local web rendering,
Impala Web UI filename fallback, deterministic report generation, and corpus
smoke path. It uses synthetic local data only and does not contact Cloudera
Manager, impalad, Spark, Trino, Prometheus, Ollama, or external LLM services.
Package and release CI also run a README Quickstart smoke against a clean wheel
install: `query-doctor-self-test`, `query-doctor-analyze --profile-text
./exported-impala-profile.txt --out cases/cm-corpus`, and
`query-doctor-web --corpus-dir cases/cm-corpus`.

The CLI profile-analysis path needs one exported Impala text profile and no
Cloudera Manager, Kerberos, local config, Prometheus, or LLM. A direct Impala
Web UI download named `profile_<query-id-high>_<query-id-low>` can be used
as-is. The web UI opens staged cases from `--corpus-dir` automatically, and
local/private web sessions can also upload one exported text profile from the
Query Inbox page. See [Pick A First Path](#pick-a-first-path) for the demo and
Cloudera Manager options.

## What It Is / Is Not

Query Doctor is:

- a local-first Impala production triage workbench with official bounded local
  Trino production lanes;
- a deterministic evidence extractor;
- a Recent-query ranking workflow for operators and administrators;
- a safe report generator using validated facts;
- a practical tool for deciding what to inspect, change, and verify next;
- a containerized web application that can run as a read-only public demo or a
  configured private operator service behind a trusted ingress/auth proxy;
- a Big Data SQL/lakehouse diagnostics wedge whose full production triage
  engine is Apache Impala, with bounded raw-free local Trino production lanes
  and future-engine preview seams.

Query Doctor is not:

- a generic AI chatbot over raw profiles;
- a replacement for the Impala Web UI;
- a tool that executes user SQL or optimizer draft SQL;
- a tool that sends raw SQL/profile data to remote services by default;
- a root-cause oracle;
- a broad live multi-engine query-history collector.

## What It Does

- Turns one exported Apache Impala text profile into a local deterministic
  diagnosis through CLI staging, corpus browsing, or bounded local/private web
  upload, without Cloudera Manager, Kerberos, metadata, Prometheus, or an LLM
  provider.
- Scans completed Recent queries as the flagship production workflow, with
  Running queries and one explicit Known Query ID as focused secondary modes.
- Works with Cloudera Manager when available, or with bounded direct Impala
  daemon endpoints for non-Cloudera-Manager Impala clusters.
- Opens on Query Inbox: safe materialized Recent cases are shown immediately
  when available, with an explicit empty/ready/running/partial/stale status
  strip, safe source/window/time-range/query-type scope chips,
  URL-driven source/window/time-range/workflow/query-type scope filters,
  first-screen result presets, view-only owner/pool tag and opaque owner/pool
  value filters, lifecycle, readiness, and action filters for owner-tagged
  rows, pool-tagged rows, safe owner/pool values, clean analysis, status
  follow-up, metadata availability, validated reports, optimizer guidance, and
  recorded action outcomes, and New scan as the secondary control action. If
  the selected scope filters do not
  match the current
  materialized snapshot, Query Inbox shows a safe filtered state and the New
  scan form instead of showing stale rows; that form is prefilled from the
  selected safe source/window/time-range/workflow/query-type filters when they
  map to supported scan controls. When materialized results are open, New scan
  is prefilled from safe source/window/time-range/workflow/query-type scope
  defaults so a refresh does not require re-entering the same bounded scan
  shape. Safe scope filters are preserved through New scan submit and job pages
  without echoing arbitrary query parameters; owner/pool tag and opaque
  owner/pool value filters, lifecycle/readiness/action result filters are
  preserved only in result links, spill filtering, and pagination.
  Window, UTC time-range, and query-type scope also have inline controls, so
  operators can change the bounded lookback, exact finished-query range, and
  short query type identifier directly from Query Inbox before materializing
  that scope.
- Supports bounded local Trino production lanes when explicitly configured:
  retained-list Recent, one explicit Query ID, raw-free materialized Details,
  deterministic Python Report, and optimizer guidance over the same
  server-owned case facts.
- Runs from a supported Docker image and Kubernetes manifests for read-only
  synthetic demo or configured private web deployments.
- Optionally adds bounded Prometheus runtime summaries for direct Impala
  workflows and bounded read-only Impala metadata through `impala-shell`.
- Ranks suspicious cases and action candidates from deterministic analyzer
  facts, not LLM scoring.
- Presents Details as an analyst decision page: why the query matters, where to
  inspect, what to try, how to verify a comparable rerun, and what evidence is
  missing.
- Folds validated selected-case optimizer guidance into the same Recommended
  change area when available. Report generation remains an explicit selected-case
  action, and optimizer generation is offered only when deterministic rewrite
  support marks the case safe to attempt.
- Generates trusted reports only after deterministic normalization,
  sanitization, and validation.
- Provides a separate read-only Query Optimizer workflow for pasted SQL review,
  plus explicit selected-case optimizer actions for server-owned analyzed
  cases.
- Keeps raw SQL, raw profiles, raw metadata, local paths, secrets, subprocess
  output, model/runtime internals, and raw artifact filenames out of browser and
  trusted report surfaces.

## Support Boundary

| Surface | Current status |
| --- | --- |
| Query engine | Apache Impala is the full production triage engine. Trino has bounded local production support only for the raw-free lanes named below. |
| First-value intake | One local exported Impala text profile can be uploaded from a local/private web session or staged from CLI/manual inbox, redacted, analyzed, and opened from Known Query ID. |
| Recent scan | Cloudera Manager is the full Recent discovery/profile/metrics/events provider for Impala workflows. |
| Direct Impala | Bounded Recent scans, Running scans, and one Known Query ID through impalad daemon endpoints; no Cloudera Manager events and no SQL execution. |
| Runtime metrics | Optional bounded Prometheus summaries for configured direct Impala workflows; no arbitrary PromQL from users. |
| Metadata | Read-only allowlisted Impala metadata statements through `impala-shell`; no user SQL execution or unbounded metadata crawl. |
| Reports and optimizer | Python-owned facts and validation. Known Query ID prepares the deterministic Python report in its explicit submit job; LLM narratives remain explicit selected-case actions, and optimizer actions are shown only for cases with safe-to-attempt rewrite support. |
| Trusted SSO/auth proxy deployment | Query Doctor supports deployment behind a trusted SSO/auth proxy via `viewer_identity_header` for shared/non-local `owner_raw` access only after the raw-free D3 support-readiness gate passes. The proxy or ingress owns authentication, MFA, session lifecycle, token handling, and inbound-header stripping; Query Doctor only enforces the normalized viewer owner header against `query.user`. |
| Container/Kubernetes web deployment | Supported starting point through the official container image, `/healthz` and `/readyz` probes, raw-free deployment readiness summary, a read-only `public-demo` manifest, a configured private web manifest, a synthetic self-test Job, and the `deploy/helm/query-doctor` chart with a `helm test` hook. Kubernetes support does not add native auth, RBAC, sessions, multi-tenant isolation, an operator/CRD, arbitrary command running, SQL execution, or broader engine support. Shared configured deployments still require a trusted ingress/auth proxy and the same safety gates as any shared/non-local web bind. |
| Trino local | Local web Trino mode can read one bounded retained pruned coordinator query list for Recent diagnosis, then bounded pruned coordinator QueryInfo payloads for selected rows or one explicit Query ID, render deterministic compact diagnosis, materialize server-owned raw-free case artifacts, open a raw-free Details view, and generate deterministic Python Report plus optimizer guidance from those materialized case facts. `trino_support_mode=beta` keeps the legacy beta label; `trino_support_mode=production` marks the same bounded raw-free local lanes as local production support and removes that label. No Running scans, query-history crawling, metadata collection, LLM report output, Query Optimizer jobs, generated Trino SQL, SQL execution, or broader/shared Trino production triage support. |
| Spark | Bounded compact support surfaces only. Spark is not production engine support, live Recent scans, Details/trusted report output, optimizer behavior, raw event-log handling, Spark job execution, or Query Doctor-generated SQL. |

The public GHCR release contains the Query Doctor web image.

Trino compact/dev surfaces include offline or compact raw-free imports and checks:
sanitized evidence packages, bounded local compact imports, explicit
source-contract checks, a contract-gated local metadata CLI summary builder
and dev-only round-trip smoke gate that emit aggregate metadata coverage only,
and bounded pruned QueryInfo paths
documented in the engine docs. The only local production Trino product surfaces are local web retained-list
Recent diagnosis, One Query ID diagnosis, the raw-free Details view,
deterministic Python Report, and optimizer guidance for server-owned materialized cases from those
lanes. The diagnosis lanes require
`trino_support_mode=beta` or `trino_support_mode=production`,
`trino_coordinator_url`, and `trino_query_info_source_contract` in local config;
Recent also requires `trino_query_list_source_contract`. The legacy
`trino_beta_enabled=true` key remains beta-only for existing local setups and
must not be combined with `trino_support_mode=production`. Startup validation
checks local source contracts, safe coordinator URL shape, and optional auth
reference (`trino_auth_header_file` or local Kerberos/SPNEGO settings) before
the lane is marked configured. Configured beta sources are marked as
`Trino Beta Recent + One Query ID` or `Trino Beta One Query ID`; configured
production-mode sources are marked without the beta label. The Diagnose Engine
control narrows the Source cluster selector to Impala-capable sources or
Trino-ready sources before workflow selection, and stale or forged Trino submits
still fail closed before analysis or async job creation.
Coordinator URL, auth header references, raw QueryInfo, raw SQL, and local paths
stay out of the browser. Trino web case artifacts contain only the normalized
boundary, compact diagnosis, metadata-not-collected summary, typed analysis, and
safe analyzer facts view; Details opens only after those artifacts exist.
Python Report and optimizer guidance use the same raw-free facts and hide raw payloads, query IDs,
paths, LLM report output, Query Optimizer jobs, and generated SQL. Broader/shared Trino
live collection and broader Trino production triage remain unsupported.
Spark compact support surfaces are limited to bounded compact History Server
intake, compact evidence-package build/validation, and compact diagnosis; there
is no public Spark engine support.

Future Big Data SQL/lakehouse live collectors, broader providers, prepared
event/log sources, and Cluster Doctor workflows remain roadmap seams, not
current support. For the detailed Trino and Spark preview command catalog, use
[docs/engines/README.md](docs/engines/README.md) and
[docs/engine-support-gap-matrix.md](docs/engine-support-gap-matrix.md).

Direct Impala Recent and Running scans currently see only the query history
exposed by the configured coordinator daemon query-list endpoints. Upstream
Impala keeps the coordinator query log at `--query_log_size=200` entries by
default, further bounded by `--query_log_size_in_bytes`. Operators who need
deeper direct history can increase those Impala daemon settings on each
coordinator, while watching coordinator Web UI memory and `/queries` response
latency. Future deeper-history options are deliberately separate sources:
operator-managed read-only profile-log directory ingestion, or bounded external
history sources such as Loki or OpenSearch. They require explicit source
contracts, allowlists, byte/window bounds, and raw-free browser/report output;
the current product does not read coordinator filesystems, pod filesystems, or
external log indexes for direct Recent scans.

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
query-doctor-self-test
```

`query-doctor-self-test` is the installed-package confidence check. It uses
synthetic local data to exercise packaged console scripts, one-profile analysis,
Impala Web UI filename fallback, local web rendering, deterministic reports,
and corpus smoke without contacting Cloudera Manager, impalad, Spark, Trino,
Prometheus, Ollama, or external LLM services.

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
secrets stay in environment variables or local env files. Start from
`query-doctor-config.minimal.example.json` for a Cloudera Manager Impala
workflow, then use `query-doctor-config.example.json` only when you need the
advanced direct-Impala, Prometheus, metadata, or LLM routing fields.

### Container And Kubernetes

The release workflow will publish the 0.11.0 web image on GitHub Container
Registry after the `v0.11.0` release is approved:

```text
ghcr.io/alexandrefimov/query-doctor:0.11.0
```

After publication, the image defaults to the safe synthetic public demo:

```bash
docker run --rm -p 127.0.0.1:8765:8765 ghcr.io/alexandrefimov/query-doctor:0.11.0
```

The image runs Query Doctor on supported Python 3.10 and also carries Kerberos
client tools and the isolated
`/opt/query-doctor/.venv-impala-shell/bin/impala-shell` runtime used by
configured Impala metadata collection. Metadata still requires explicit
coordinator, Kerberos cache, and redacted metadata settings in the private
deployment config.

The Helm chart can optionally initialize and continuously refresh a Kerberos
ticket cache from an existing Kubernetes Secret in configured mode. A dedicated
sidecar owns refresh for the long-lived web pod, while finite collector and
worker Jobs obtain a fresh ticket at startup. The chart references only Secret
names and keys; it does not render keytabs, principals, ticket contents, or
inline credential values, and the web container never mounts the keytab.

Configured non-local web deployments use conservative Recent defaults unless
private config explicitly overrides them: profile analysis limit `50`, overall
Recent parallelism `4`, metadata parallelism `2`, and metadata top limit `10`.
Raise those together with pod resources and a focused Kubernetes smoke.
Finished-query web Recent scans also reuse already analyzed cases from prior
local web batch outputs when the Query ID matches, the previous case completed
successfully, and the scan is still in the same safe redacted reuse contract.
The default local web cache lives under the system temp directory. Configured
Kubernetes and Helm examples set `recent_batch_root` to the dedicated
temp-backed case-PVC cache mount, so repeated finished Recent scans can reuse
analyzed profiles across pod restarts without broadening the raw-data boundary.
The Results coverage strip shows only the aggregate reused-profile count. A
second submit for the same running finished Recent scan redirects to the
existing job instead of starting duplicate collection.
For deployments that want a durable summary index, the batch CLI also accepts
`recent_history_db` / `--recent-history-db` to write raw-free Recent summary
history into a local SQLite database. That store records bounded summary
signals, selected/suspicion reason codes, profile status, and profile-budget
queue state without storing raw SQL or profile text. It also includes a
raw-free analyzed-result cache foundation keyed by Query ID, profile
fingerprint, and analyzer contract, plus raw-free profile-artifact metadata.
When `query-doctor-batch-recent --discover-only` runs with a history backend,
it also plans pending profile jobs for suspicious or selected summaries under
the existing Recent profile budget. The history database does not store raw
profile bytes, local paths, or artifact filenames. Explicit retention pruning
for old raw-free rows is opt-in through the `recent_history_*_retention_days`
config fields or matching `--recent-history-*-retention-days` CLI flags;
retention output stays aggregate-only. A separate
`query-doctor-recent-profile-remediation` maintenance CLI can dry-run or
explicitly `--apply` a bounded requeue of terminal failed profile jobs after an
operator fixes collection or materialization settings. Its output stays
aggregate-only and does not echo Query IDs, normalized error values, backend
paths, raw SQL, profile text, DSNs, or source filter values.
When the local web UI is configured with a Recent history backend, Query Inbox
can render retained raw-free summary rows as a read-only Online History view.
Those rows do not expose raw SQL or profile text and stay read-only until a
scan or profile worker materializes a safe Details snapshot. Online History
also shows the current raw-free profile worker state for retained rows, such as
pending, processing, retry-pending, analyzed, or failed, without exposing raw
profile bytes or resetting progressed states during rediscovery. The Query
Inbox status banner also summarizes retained versus shown rows, separates
profile states, rolls up normalized profile-worker error codes, and shows how
many analyzed rows have Details ready. It also shows safe Recent summary
collector freshness from the latest retained planning timestamp, so operators
can distinguish a healthy profile backlog from a stale producer without
exposing Query IDs, source keys, local paths, or raw collector payloads.
When configured with `recent_history_collector_summary_json`, the same banner
also projects the producer's last raw-free run summary as allowlisted status,
age, recorded-row, and planned-job counters. Invalid or unsafe retained
summaries degrade to blocked/unavailable status without rendering the
configured path, raw JSON, Query IDs, source keys, local paths, raw errors, or
retained free-form text. Safe next-step labels are derived from retained worker
states and aggregate counters so operators can distinguish retry, failed,
waiting, materialized backlog, and stale producer states without exposing raw
errors or trusting retained free-form text. If the web config points
`recent_history_operator_readiness_summary_json` at an already retained
`query_doctor_recent_history_operator_readiness_v1` summary, the same status
banner also shows only allowlisted operator readiness, evidence, reason-code
labels, schema, worker, worker-materialization, worker next-step,
profile-backlog health, backlog next-step, retention, and profile-remediation
counters and next-step text. It does not render the configured path, raw JSON,
raw SQL, profile text, local store paths, retained free-form remediation text,
or raw artifact names. An
analyzed row becomes an Online History Details link only when the history store
also has a ready raw-free analysis-cache payload linked through available
`fingerprint_only` profile-artifact metadata. Those Details snapshots can show
allowlisted score, recommendation, aggregate metadata coverage, and processing
timing fields, but still do not expose profile bytes, storage keys, local
paths, LLM reports, optimizer jobs, generated SQL, or SQL execution.
Configured deployments can instead set `recent_history_backend=postgres` and
provide the DSN through `QUERY_DOCTOR_RECENT_HISTORY_POSTGRES_DSN` or the
environment variable named by `recent_history_postgres_dsn_env`; the DSN value
must stay in the environment/Secret, not in Query Doctor JSON config. Container
images need the optional Postgres driver extra, for example
`QUERY_DOCTOR_INSTALL_EXTRAS=postgres scripts/build-image.sh query-doctor:dev`.
The Helm chart can reference that DSN from an existing Secret through
`recentHistory.postgres` in configured mode. It can also optionally render a
configured-mode CloudNativePG `Cluster`. When CNPG owns credential generation,
Query Doctor can consume the controller-generated application Secret through
its `uri` key; externally managed owner credentials continue to use a separate
operator-managed DSN Secret. The chart does not install CNPG or render Secret
objects.
Use `query-doctor-recent-history-postgres-readiness --json` inside the
configured image/pod environment to verify that the DSN env is present and the
history schema can initialize without printing the DSN, host, credentials,
paths, Query IDs, or raw payloads. Helm configured installs with
`recentHistory.postgres.enabled=true` run that raw-free readiness check as a
web pod initContainer by default.
Use `query-doctor-recent-history-operator-readiness` after retaining the
raw-free Postgres readiness and profile-worker summary JSON files, plus the
optional collector, retention, and profile-remediation summaries, to build one operator
handoff summary. The audit reads only those retained summaries, rejects unsafe
retained fields or values, does not print input paths, and does not contact
Postgres, Kubernetes, query engines, or profile collectors. The handoff summary
also includes accepted raw-free operation counters for schema readiness,
profile-worker jobs and materialized records, profile-backlog health, optional
collector producer status/freshness, optional retention deletes, and optional
remediation dry-run/apply counts. In Helm
configured mode,
`recentHistory.operatorReadiness.enabled=true` wires that handoff as a separate
CronJob after Postgres history, Postgres readiness, and
`recentProfileWorker.enabled=true` are enabled. The optional
`recentSummaryCollector.enabled=true` CronJob can run
`query-doctor-batch-recent --discover-only` on a schedule to write retained
summary rows and planned profile jobs to Postgres, plus a raw-free collector
run summary and progress JSONL stream to the case PVC, without collecting
profiles, running metadata SQL, LLM reports, or optimizer jobs. The chart
can pass that collector summary to operator readiness through
`recentHistory.operatorReadiness.collectorSummaryJson`. It writes the upstream
Postgres readiness, profile-worker, optional retention, and optional dry-run
profile-remediation summaries to the case PVC, then runs the
operator-readiness CronJob over only those raw-free files. The optional
`recentHistory.postgres.profileRemediation` CronJob runs only
`query-doctor-recent-profile-remediation --dry-run`; the chart does not render
an apply/requeue remediation job. That CronJob does not mount Query Doctor
config, collection credentials, Kerberos material, or source endpoint
configuration. The operator-readiness CronJob does not mount Query Doctor
config, collection credentials, the Postgres DSN Secret, Kerberos material, or
source endpoint configuration.
Use `query-doctor-recent-profile-worker` with the same batch/config flags to
claim jobs for the configured source, collect bounded profiles through the
existing Impala Recent collectors, run deterministic analysis only, and write
raw-free analysis-cache/profile-artifact metadata. The worker does not run LLM
reports, optimizer jobs, metadata SQL collection, or trusted browser raw-output
surfaces, and it cleans the worker-owned temporary `profile-worker-cases/job-*`
directory after each processed job. With `clusters[]` config and no explicit
source flags, the worker uses `active_cluster_key` or the only configured
cluster as its source. In Helm configured mode,
`recentProfileWorker.enabled=true` renders the same worker as a source-filtered
CronJob after Postgres history is enabled; it uses the configured Secret/env
DSN handoff, case PVC, and raw-free JSON output. Helm configured mode can also
render `recentHistory.postgres.retention` as a Postgres-only retention CronJob.
That job runs
`query-doctor-recent-history-retention` with only the DSN Secret env, deletes
old raw-free history rows by aggregate retention policy, and does not mount
Query Doctor config, collection credentials, Kerberos material, or case PVCs.
Profile-artifact metadata is `fingerprint_only`: storage kinds that would
retain profile bytes, local paths, object names, or external artifact
references are rejected until a bounded delete implementation exists.

For an already installed configured release with metadata enabled, run the
bounded Kubernetes metadata smoke before a release handoff:

```bash
scripts/kubernetes-configured-metadata-smoke.sh
```

The smoke uses a local port-forward, submits a one-case Recent scan with
`metadata_top_limit=1`, and requires collected or partial metadata with table
context. It prints only aggregate job, status, and table-context counters.

For a configured Kubernetes release handoff after ingress/auth is wired, set
the expected external front-door values through environment variables and run:

```bash
scripts/kubernetes-configured-release-gate.sh
```

The gate composes the configured metadata smoke, live unauthenticated auth
redirect smoke, and raw-free Kubernetes auth-front-door resource audit.

From a checkout, build and smoke the same shape locally:

```bash
scripts/build-image.sh query-doctor:dev
scripts/image-smoke.sh query-doctor:dev
```

From an arm64 workstation, build an amd64 image before testing on amd64
Kubernetes nodes:

```bash
QUERY_DOCTOR_IMAGE_PLATFORM=linux/amd64 scripts/build-image.sh query-doctor:dev-amd64
QUERY_DOCTOR_IMAGE_PLATFORM=linux/amd64 scripts/image-smoke.sh query-doctor:dev-amd64
```

Kubernetes manifests live in [deploy/kubernetes/](deploy/kubernetes/):

- `public-demo.yaml`: read-only synthetic demo with no credentials and denied
  pod egress.
- `configured-web.yaml`: private operator template with mounted config,
  externally created credentials Secret, PVC-backed case storage, and probes.
- `self-test-job.yaml`: synthetic package confidence check that runs only
  `query-doctor-self-test` without config, credentials, PVCs, live engine
  access, optimizer jobs, metadata collection, or SQL.

Web deployments expose `/healthz`, `/readyz`, and
`/deployment/readiness.json`. The companion
`query-doctor-deployment-readiness` CLI prints the same raw-free deployment
summary without starting the server. For configured or shared access, put Query
Doctor behind a trusted ingress/auth proxy; Kubernetes support does not add
native authentication, sessions, RBAC, tenant isolation, SQL execution, or
broader engine support inside Query Doctor. See
[docs/kubernetes-auth-front-door.md](docs/kubernetes-auth-front-door.md) and
`scripts/audit_kubernetes_auth_front_door.py` for the raw-free
oauth2-proxy/Keycloak-style front-door and NetworkPolicy acceptance check. Use
`scripts/kubernetes_auth_front_door_smoke.py` for a raw-free live
unauthenticated redirect smoke against the external ingress.
Configured private web pods should keep at least the packaged Recent-ready
resource baseline: `250m` CPU and `512Mi` memory requests, with `2` CPU and
`2Gi` memory limits.

The Helm chart lives in [deploy/helm/query-doctor/](deploy/helm/query-doctor/).
It renders the same safe public-demo default and configured private mode, adds
values schema coverage, includes a synthetic `helm test` hook, and supports
generic user-provided pod labels and annotations without embedding a platform
controller contract.

For disposable cluster-side checks, use `scripts/kubernetes-self-test-smoke.sh`
to install the chart in a temporary namespace, run the Helm self-test, capture
the synthetic Job logs, and clean up after the synthetic self-test.

## Pick A First Path

Use the smallest path that matches the access you have.

| Door | Use when | Starts from |
| --- | --- | --- |
| One exported profile | You can get one Impala Web UI text profile, but cannot grant live access yet. | `query-doctor-analyze --profile-text`, `query-doctor-web` upload, or `query-doctor-web` with `manual_profile_dir` |
| Synthetic demo | You want a read-only local click-through with no real data. | `query-doctor-web --public-demo` |
| Minimal CM scan | You have read-only Cloudera Manager access for an Impala service. | `query-doctor-web` or `query-doctor-batch-recent` |

### Door 1: Analyze One Exported Profile

The lowest-setup path is one exported Apache Impala text profile to one local
diagnosis. This does not contact Cloudera Manager or impalad, does not require
Kerberos, metadata collection, Prometheus, or an LLM provider.

```bash
query-doctor-analyze \
  --profile-text ./exported-impala-profile.txt \
  --out cases/cm-corpus
```

The command stages a collector-shaped local case under `cases/cm-corpus`,
redacts users, hosts, credentials, and common secret forms by default, writes
`analysis_facts.md` plus `analysis.json`, and prints the output case directory.
Use `--redact-identifiers` when the staged local artifacts may be shared. The
manual profile intake accepts exported text profiles only; JSON, Thrift, and
profile-v2 payloads remain outside this entry path. The CLI uses the Query ID
header from the exported profile, or the downloaded Impala Web UI filename when
it has the strict `profile_<query-id-high>_<query-id-low>` shape. If neither is
readable, add `--query-id <query-id>`; when multiple Query ID sources are
present, they must match before the local case is written.

To inspect staged cases in the local UI, start `query-doctor-web --corpus-dir
cases/cm-corpus` from the same workspace. The Query Inbox page opens an Exported
Profiles results table from complete manual-profile cases in that corpus
without requiring Cloudera Manager settings, credentials, or default local
config. You can still choose `One Query ID` and enter the Query ID from a staged
profile to reopen that exact case. LLM narrative and optimizer actions remain
explicit buttons.

For a local or private web session, you can also choose `One Query ID`, enter
the matching Impala Query ID in `Profile Query ID`, select one exported text
profile in `Exported profile`, and press `Upload`. The upload path is bounded by
`max_profile_bytes`, accepts exactly one multipart file, rejects JSON, Thrift,
and profile-v2 payloads in the same analyzer path, stages a server-owned case
under `corpus_dir`, and removes the temporary upload file after staging. The
public synthetic demo hides this form and blocks uploads before reading the
request body.

You can also configure a local profile inbox for the web UI. Put the exported
text profile in `manual_profile_dir` using the Query ID slug as the file name
(for example, replace the Query ID separator with `_` and save
`<query-id-slug>.txt`), start `query-doctor-web`, choose `One Query ID`, and
enter the original Query ID. The web path stages and analyzes the local file
through the same text-only, bounded, redacted analyzer path. If the file
contains an embedded Query ID for a different query, staging fails closed before
replacing any existing case. For a self-contained one-profile workspace, set
both paths in an ignored local config file and keep generated cases outside the
source tree:

```json
{
  "manual_profile_dir": "/path/to/profile-inbox",
  "corpus_dir": "/path/to/query-doctor-cases",
  "no_llm": true
}
```

Then start `query-doctor-web --config ./query-doctor-one-profile.json`.
Relative `corpus_dir` values in config resolve from the config file; the
`--corpus-dir` CLI flag resolves relative paths from the current directory.
When neither is set, the web UI stores generated Query ID cases under
`./cases/cm-corpus` from the directory where you started `query-doctor-web`.

### Troubleshooting One Exported Profile

- `Profile text does not include a Query ID`: keep the original Impala Web UI
  download name when it has the strict
  `profile_<query-id-high>_<query-id-low>` shape, or pass
  `--query-id <query-id>`. Query Doctor also accepts a `Query ID:` header inside
  the text export. If multiple Query ID sources are present, they must match.
- `Parsed operators: 0`: the case is still staged and can open in the UI, but
  that text export did not include a parseable `ExecSummary`/operator table.
  Use the preserved Impala text profile export when available; JSON, Thrift,
  and profile-v2 payloads are outside this manual profile path.
- `query-doctor-web --corpus-dir cases/cm-corpus` asks for Cloudera Manager
  settings: confirm that `query-doctor-analyze` wrote a complete case under the
  same corpus directory you pass to web, and run web from the same workspace or
  use an absolute `--corpus-dir`.

### Door 2: Run The Synthetic Demo

The synthetic demo is the fastest way to see the product. It is deterministic,
local-only, and contains no real SQL, profiles, metadata, hostnames, users, or
credentials.

```bash
query-doctor-web --public-demo
```

This one-command mode is documented in [docs/demo-mode.md](docs/demo-mode.md).
It generates the synthetic demo pack in a dedicated temp directory, forces
Python-only mode, ignores default local config, and blocks all POST actions.

If you need to inspect or reuse the generated pack manually, use the lower-level
commands:

```bash
query-doctor-demo-preflight
DEMO_PACK="${TMPDIR:-/tmp}/query-doctor-demo-pack"
query-doctor-demo --out "$DEMO_PACK" --overwrite
QUERY_DOCTOR_ACTION_OUTCOMES_PATH="$DEMO_PACK/action_outcomes.jsonl" \
  query-doctor-web --host 127.0.0.1 --port 8766 --batch-summary "$DEMO_PACK/batch_summary.json"
```

Open the localhost URL printed by `query-doctor-web`. Start with
`/?query_group=workloads#scan-context` to show the compact Scan context
workload follow-up links and local synthetic action outcomes before opening
Workload Details.
When a Recent summary has repeated safe row-level workload fingerprints but no
materialized workload payload, the UI derives bounded repeated workload details
from the sanitized rows; those details have no baseline or regression claim
until local history evidence is available.

The local web UI starts with Query Inbox status, safe
source/window/time-range/query-type scope, a compact Filters and views
disclosure for URL-driven source/window/time-range/workflow/query-type scope
filters, result presets, view-only owner/pool tag and opaque owner/pool value
filters, lifecycle, readiness, and action filters, plus synthetic Finished
Queries results when safe materialized cases are available. The
collapsed New scan form keeps safe refresh defaults from that materialized
scope without auto-running collection:

The main results table is decision-focused: attention rows show one short
deterministic classification, priority, duration, owner context, and a clear
Details path. Repeated workloads keep priority, p95, total observed impact, and
top owner in the inbox; p50, pool, bottleneck, and supporting evidence remain
available in Workload Details.

![Synthetic Query Doctor Query Inbox status](docs/assets/demo_search.png)

![Synthetic Query Doctor finished queries results](docs/assets/demo_finished_queries.png)

The synthetic demo pack contains eleven sanitized Impala cases covering
workload follow-up, repeated patterns, trusted optimizer recommendations,
stats maintenance, storage/HDFS follow-up, frequent-short workloads, mixed
signals, unknown but useful limited evidence, and direct-Impala compatibility.
It also includes two read-only raw-free Trino Beta demo cases rendered from
static compact diagnosis facts, without contacting a Trino coordinator or
enabling Details, reports, optimizer guidance, generated SQL, or SQL execution.
See
[docs/demo-cases.md](docs/demo-cases.md) for the full scenario list and talk
track.

### Door 3: Run A Minimal Cloudera Manager Scan

Use this when you have read-only Cloudera Manager access for an Impala service.
Keep secrets in the shell environment or a local env file, not in JSON config.
Create `~/.qdcreds/cm-ro.env` with `CM_USERNAME` plus `CM_PASSWORD` or
`CM_TOKEN` before sourcing it.

```bash
mkdir -p ~/.qdcreds
cp query-doctor-config.minimal.example.json ~/.qdcreds/query-doctor-config.json
# Edit ~/.qdcreds/query-doctor-config.json with CM URL, cluster, service, and CA bundle if needed.
set -a
source ~/.qdcreds/cm-ro.env
set +a
query-doctor-web \
  --config ~/.qdcreds/query-doctor-config.json \
  --host 127.0.0.1 \
  --port 8765
```

For a headless bounded Recent scan without automatic LLM reports:

```bash
query-doctor-batch-recent \
  --config ~/.qdcreds/query-doctor-config.json \
  --recent-window-minutes 60 \
  --triage-profile-limit 10 \
  --top-reports 0
```

The minimal path uses Cloudera Manager for Impala Recent discovery and profile
collection. Add metadata, CM time-series, direct Impala, Prometheus, or LLM
settings only after this basic scan path works. See
[docs/configuration.md](docs/configuration.md) and
[docs/credentials.md](docs/credentials.md).
For repeated safe local runs, `--reuse-analyzed-profiles-from <cache-root>` can
reuse completed analyzed cases from direct child `query-doctor-*` batch outputs
when the Query ID and explicit profile reuse contract match.

## Main Workflows

- `query-doctor-self-test --help`: local installed-package confidence check
  over synthetic data and core offline user paths.
- `query-doctor-deployment-readiness --help`: raw-free deployment summary for
  the same settings used by `query-doctor-web`.
- `query-doctor-web --help`: local browser UI for Recent scan, Running now, one
  Known Query ID, Details pages, explicit report actions, and explicit
  details-page optimizer actions.
- `query-doctor-batch-recent --help`: headless Recent scan workflow for bounded
  local collection and ranking.
- `query-doctor-analyze --help`: deterministic analyzer over collected local
  case files, or over one staged local exported Impala text profile.
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
the read-only `query-doctor-web --public-demo` mode. Shared `owner_raw` source
access requires authenticated per-request viewer identity through an explicit
`viewer_identity_header` supplied only by a trusted SSO/auth proxy or ingress
that strips inbound copies of the same header and sets exactly one normalized
simple owner value. Query Doctor supports that deployment pattern after the
raw-free support-readiness gate in
[docs/owner-raw-d3-deployment.md](docs/owner-raw-d3-deployment.md). A
dev-only Keycloak/oauth2-proxy smoke is available in
[docs/dev-sso-keycloak.md](docs/dev-sso-keycloak.md) to test the front-door
viewer header contract locally; `scripts/dev_sso_keycloak_smoke.py` verifies
the running local compose path with raw-free output. The dev smoke is not
production SSO support evidence and does not add native SSO to Query Doctor.

## Safety Model

- Python/analyzer-owned facts are the only trusted diagnostic evidence.
- Raw LLM output is untrusted unless normalized, sanitized, and validated.
- Trusted browser/report surfaces must not expose raw SQL, raw profiles, raw
  metadata, local paths, secrets, subprocess output, model/runtime internals, or
  raw artifact filenames. The isolated owner-only selected-case source surface is
  the narrow raw-SQL browser exception.
- External collection must be explicit, bounded, read-only, redacted, and safe
  by default.
- Local config `privacy_mode` defaults to `true`; disabling it can relax local
  artifact identifier/host masking, but trusted browser/report surfaces still do
  not show raw SQL, profiles, or metadata.
- Local config `no_llm=true` keeps report and optimizer actions on deterministic
  Python-owned output.
- SQL browser exceptions are selected-case and owner-gated: Details can show a
  validated optimizer SQL draft for an explicit safe-to-attempt optimizer action
  when `source_visibility=owner_raw`, and the isolated owner-only source view can
  show read-only original SQL for an authorized query owner. On localhost, raw
  viewer subjects come from local collectable owner users; on shared binds they
  must come from authenticated per-request viewer identity. The original source
  view can be disabled globally with `owner_raw_source_enabled=false` or
  `--disable-owner-raw-source`, and each attempt writes a reason-coded raw-free
  server audit line. The default `safe` mode shows trusted
  recommendations/no-rewrite guidance instead.
- Query Optimizer accepts only a single safe read-only statement and never
  executes pasted SQL.

See [docs/safety-contract.md](docs/safety-contract.md) for the full trust and
redaction contract, including the narrow owner-only source exception. For
shared/non-local owner-raw deployment, use
[docs/owner-raw-d3-deployment.md](docs/owner-raw-d3-deployment.md). For a
reviewer-oriented overview, see
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
- [deploy/kubernetes/README.md](deploy/kubernetes/README.md): container image,
  Kubernetes manifests, probes, and deployment boundaries.
- [deploy/helm/query-doctor/README.md](deploy/helm/query-doctor/README.md):
  Helm chart modes, validation, and deployment boundaries.
- [docs/credentials.md](docs/credentials.md): local credentials layout.
- [docs/roadmap.md](docs/roadmap.md): implemented scope and planned seams.
- [docs/security-model.md](docs/security-model.md): public security, privacy,
  and demo-sharing overview.
- [docs/query-optimizer-contract.md](docs/query-optimizer-contract.md):
  optimizer trust boundary.
- [docs/release-checklist.md](docs/release-checklist.md): final tag,
  package-index, and visibility-change checklist.

The canonical documentation language is English. The Russian layer is limited
to [README.ru.md](README.ru.md) plus practical user/operator instructions under
[docs/i18n/ru/](docs/i18n/ru/); internal, agent, research, release, and engine
deep-dive docs stay English-only.

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

This repository is public. Public source releases start at `v0.4.2`;
`v0.11.0` continues that public source release line. Older package-index
releases remain visible on
[query-doctor on PyPI](https://pypi.org/project/query-doctor/) where needed for
installed-artifact history. The public license is Apache-2.0.

PyPI publishing uses GitHub OIDC Trusted Publishing. The repository-side
`testpypi` and `pypi` environments require maintainer approval and do not use
stored package-index API tokens.

Query Doctor web container images are published to GitHub Container Registry as
`ghcr.io/alexandrefimov/query-doctor:<version>` from GitHub Releases.

## Licensing

Query Doctor is licensed under the Apache License, Version 2.0
(`Apache-2.0`). See [LICENSE](LICENSE).

Apache, Apache Impala, and Impala are trademarks of The Apache Software
Foundation. Query Doctor is an independent project and is not endorsed by The
Apache Software Foundation or the Apache Impala project.
