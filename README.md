# Query Doctor

Last reviewed: 2026-06-12

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

## Quickstart

```bash
python -m pip install query-doctor
query-doctor-analyze \
  --profile-text ./exported-impala-profile.txt \
  --out cases/cm-corpus
query-doctor-web --corpus-dir cases/cm-corpus
```

This first path needs one exported Impala text profile and no Cloudera Manager,
Kerberos, browser upload, Prometheus, or LLM. See [Pick A First Path](#pick-a-first-path)
for the demo and Cloudera Manager options.

## What It Is / Is Not

Query Doctor is:

- a local-first Impala production triage workbench;
- a deterministic evidence extractor;
- a Recent-query ranking workflow for operators and administrators;
- a safe report generator using validated facts;
- a practical tool for deciding what to inspect, change, and verify next;
- a Big Data SQL/lakehouse diagnostics wedge whose production triage engine is
  Apache Impala today, with bounded raw-free future-engine preview seams.

Query Doctor is not:

- a generic AI chatbot over raw profiles;
- a replacement for the Impala Web UI;
- a tool that executes user SQL or optimizer draft SQL;
- a tool that sends raw SQL/profile data to remote services by default;
- a root-cause oracle;
- a live multi-engine query collector today.

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
  change area when available, while report and optimizer generation remain
  separate explicit actions.
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
| Query engine | Apache Impala is the production triage engine. |
| First-value intake | One local exported Impala text profile can be staged, redacted, analyzed, and opened from Known Query ID. |
| Recent scan | Cloudera Manager is the full Recent discovery/profile/metrics/events provider for Impala workflows. |
| Direct Impala | Bounded Recent scans, Running scans, and one Known Query ID through impalad daemon endpoints; no Cloudera Manager events and no SQL execution. |
| Runtime metrics | Optional bounded Prometheus summaries for configured direct Impala workflows; no arbitrary PromQL from users. |
| Metadata | Read-only allowlisted Impala metadata statements through `impala-shell`; no user SQL execution or unbounded metadata crawl. |
| Reports and optimizer | Python-owned facts and validation. Known Query ID prepares the deterministic Python report in its explicit submit job; LLM narratives and optimizer actions remain explicit selected-case actions. |
| Trino and Spark | Bounded raw-free preview/compact surfaces only. They are not production engine support, live Recent scans, Details/trusted report output, optimizer behavior, or Query Doctor-generated SQL. |

Trino preview surfaces are offline or compact raw-free imports and checks only:
sanitized evidence packages, bounded local compact imports, explicit
source-contract checks, and bounded pruned QueryInfo paths documented in the
engine docs. They do not provide live collection, Details/trusted report
output, optimizer behavior, live metadata collection, or Query Doctor-generated
Trino SQL. Spark compact support surfaces are limited to bounded compact
History Server intake, compact evidence-package build/validation, and compact
diagnosis; there is no public Spark engine support.

Future Big Data SQL/lakehouse live collectors, broader providers, prepared
event/log sources, and Cluster Doctor workflows remain roadmap seams, not
current support. For the detailed Trino and Spark preview command catalog, use
[docs/engines/README.md](docs/engines/README.md) and
[docs/engine-support-gap-matrix.md](docs/engine-support-gap-matrix.md).

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
header from the exported profile. If the profile lacks a readable Query ID
header, add `--query-id <query-id>`; if both are present, they must match
before the local case is written.

To inspect the same staged case in the local UI, start `query-doctor-web`,
choose `One Query ID`, and enter the Query ID from that profile. Known Query ID
analysis reuses complete manual-profile staged cases instead of recollecting
them, and prepares the deterministic Python report in the same explicit submit
job. LLM narrative and optimizer actions remain explicit buttons.

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

The `0.5.0` synthetic demo pack contains eleven sanitized cases covering
workload follow-up, repeated patterns, trusted optimizer recommendations,
stats maintenance, storage/HDFS follow-up, frequent-short workloads, mixed
signals, unknown but useful limited evidence, and direct-Impala compatibility.
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
- Validated optimizer SQL drafts are the only SQL exception in the browser:
  Details shows them only for explicit selected-case optimizer actions when
  `source_visibility=owner_raw`; the default `safe` mode shows trusted
  recommendations/no-rewrite guidance instead.
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

This repository is public. Public source releases start at `v0.4.2`; `v0.7.0`
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
