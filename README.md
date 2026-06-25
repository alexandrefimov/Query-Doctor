# Query Doctor

Last reviewed: 2026-06-25

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
browser/report surfaces.

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

The profile-analysis path needs one exported Impala text profile and no
Cloudera Manager, Kerberos, local config, browser upload, Prometheus, or LLM. A
direct Impala Web UI download named `profile_<query-id-high>_<query-id-low>` can
be used as-is. The web UI opens staged cases from `--corpus-dir` automatically.
See [Pick A First Path](#pick-a-first-path) for the demo and Cloudera Manager
options.

## What It Is / Is Not

Query Doctor is:

- a local-first Impala production triage workbench;
- a deterministic evidence extractor;
- a Recent-query ranking workflow for operators and administrators;
- a safe report generator using validated facts;
- a practical tool for deciding what to inspect, change, and verify next;
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
  diagnosis without Cloudera Manager, Kerberos, metadata, Prometheus, browser
  upload, or an LLM provider.
- Scans completed Recent queries as the flagship production workflow, with
  Running queries and one explicit Known Query ID as focused secondary modes.
- Works with Cloudera Manager when available, or with bounded direct Impala
  daemon endpoints for non-Cloudera-Manager Impala clusters.
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
| First-value intake | One local exported Impala text profile can be staged, redacted, analyzed, and opened from Known Query ID. |
| Recent scan | Cloudera Manager is the full Recent discovery/profile/metrics/events provider for Impala workflows. |
| Direct Impala | Bounded Recent scans, Running scans, and one Known Query ID through impalad daemon endpoints; no Cloudera Manager events and no SQL execution. |
| Runtime metrics | Optional bounded Prometheus summaries for configured direct Impala workflows; no arbitrary PromQL from users. |
| Metadata | Read-only allowlisted Impala metadata statements through `impala-shell`; no user SQL execution or unbounded metadata crawl. |
| Reports and optimizer | Python-owned facts and validation. Known Query ID prepares the deterministic Python report in its explicit submit job; LLM narratives remain explicit selected-case actions, and optimizer actions are shown only for cases with safe-to-attempt rewrite support. |
| Trusted SSO/auth proxy deployment | Query Doctor supports deployment behind a trusted SSO/auth proxy via `viewer_identity_header` for shared/non-local `owner_raw` access only after the raw-free D3 support-readiness gate passes. The proxy or ingress owns authentication, MFA, session lifecycle, token handling, and inbound-header stripping; Query Doctor only enforces the normalized viewer owner header against `query.user`. |
| Trino local | Local web Trino mode can read one bounded retained pruned coordinator query list for Recent diagnosis, then bounded pruned coordinator QueryInfo payloads for selected rows or one explicit Query ID, render deterministic compact diagnosis, materialize server-owned raw-free case artifacts, open a raw-free Details view, and generate deterministic Python Report plus optimizer guidance from those materialized case facts. `trino_support_mode=beta` keeps the legacy beta label; `trino_support_mode=production` marks the same bounded raw-free local lanes as local production support and removes that label. No Running scans, query-history crawling, metadata collection, LLM report output, Query Optimizer jobs, generated Trino SQL, SQL execution, or broader/shared Trino production triage support. |
| Spark | Bounded compact support surfaces only. Spark is not production engine support, live Recent scans, Details/trusted report output, optimizer behavior, raw event-log handling, Spark job execution, or Query Doctor-generated SQL. |

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

## Pick A First Path

Use the smallest path that matches the access you have.

| Door | Use when | Starts from |
| --- | --- | --- |
| One exported profile | You can get one Impala Web UI text profile, but cannot grant live access yet. | `query-doctor-analyze --profile-text` or `query-doctor-web` with `manual_profile_dir` |
| Synthetic demo | You want a read-only local click-through with no real data. | `query-doctor-web --public-demo` |
| Minimal CM scan | You have read-only Cloudera Manager access for an Impala service. | `query-doctor-web` or `query-doctor-batch-recent` |

### Door 1: Analyze One Exported Profile

The lowest-setup path is one exported Apache Impala text profile to one local
diagnosis. This does not contact Cloudera Manager or impalad, does not require
Kerberos, metadata collection, Prometheus, or an LLM provider, and does not
upload the raw profile through the browser.

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
cases/cm-corpus` from the same workspace. The Diagnose page opens an Exported
Profiles results table from complete manual-profile cases in that corpus
without requiring Cloudera Manager settings, credentials, or default local
config. You can still choose `One Query ID` and enter the Query ID from a staged
profile to reopen that exact case. LLM narrative and optimizer actions remain
explicit buttons.

You can also configure a local profile inbox for the web UI. Put the exported
text profile in `manual_profile_dir` using the Query ID slug as the file name
(for example, replace the Query ID separator with `_` and save
`<query-id-slug>.txt`), start `query-doctor-web`, choose `One Query ID`, and
enter the original Query ID. The web path stages and analyzes the local file
through the same text-only, bounded, redacted analyzer path; it does not upload
the raw profile through the browser. If the file contains an embedded Query ID
for a different query, staging fails closed before replacing any existing case.
For a self-contained one-profile workspace, set both paths in an ignored local
config file and keep generated cases outside the source tree:

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

The local web UI starts with a bounded search form and renders synthetic
Finished Queries results for review:

![Synthetic Query Doctor demo search form](docs/assets/demo_search.png)

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

## Main Workflows

- `query-doctor-self-test --help`: local installed-package confidence check
  over synthetic data and core offline user paths.
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

This repository is public. Public source releases start at `v0.4.2`; `v0.9.0`
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
