# Pick A First Path

Last reviewed: 2026-08-11

Use the smallest path that matches the access you have. The README shows the
one-line version; this page has the full setup, options, and troubleshooting.

| Door | Use when | Starts from |
| --- | --- | --- |
| One exported profile | You can get one Impala Web UI text profile, but cannot grant live access yet. | `query-doctor-analyze --profile-text`, `query-doctor-web` upload, or `query-doctor-web` with `manual_profile_dir` |
| Synthetic demo | You want a read-only local click-through with no real data. | `query-doctor-web --public-demo` |
| Minimal CM scan | You have read-only Cloudera Manager access for an Impala service. | `query-doctor-web` or `query-doctor-batch-recent` |
| Direct Impala scan | You can reach the debug Web UI endpoints of Kubernetes Impala coordinators. | `query-doctor-batch-recent --discover-only`, then `query-doctor-web` |

## Door 1: Analyze One Exported Profile

The lowest-setup path is one exported Apache Impala text profile to one local
diagnosis. This does not contact Cloudera Manager or impalad, and does not
require Kerberos, metadata collection, Prometheus, or an LLM provider.

```bash
query-doctor-analyze \
  --profile-text ./your-profile.txt \
  --out cases/cm-corpus
```

The command stages a collector-shaped local case under `cases/cm-corpus`,
redacts users, hosts, credentials, and common secret forms by default, writes
`analysis_facts.md` plus `analysis.json`, and prints the output case directory.
Use `--redact-identifiers` when the staged local artifacts may be shared.

The manual profile intake accepts exported text profiles only; JSON, Thrift, and
profile-v2 payloads remain outside this entry path. The CLI uses the Query ID
header from the exported profile, or the downloaded Impala Web UI filename when
it has the strict `profile_<query-id-high>_<query-id-low>` shape. If neither is
readable, add `--query-id <query-id>`; when multiple Query ID sources are
present, they must match before the local case is written.

To inspect staged cases in the local UI, start `query-doctor-web --corpus-dir
cases/cm-corpus` from the same workspace. The Query Inbox page opens an Exported
Profiles results table from complete manual-profile cases in that corpus without
requiring Cloudera Manager settings, credentials, or default local config. You
can still choose `One Query ID` and enter the Query ID from a staged profile to
reopen that exact case. LLM narrative and optimizer actions remain explicit
buttons.

### Upload from a local web session

For a local or private web session, choose `One Query ID`, enter the matching
Impala Query ID in `Profile Query ID`, select one exported text profile in
`Exported profile`, and press `Upload`. The upload path is bounded by
`max_profile_bytes`, accepts exactly one multipart file, rejects JSON, Thrift,
and profile-v2 payloads in the same analyzer path, stages a server-owned case
under `corpus_dir`, and removes the temporary upload file after staging. The
public synthetic demo hides this form and blocks uploads before reading the
request body.

### Local profile inbox

Put the exported text profile in `manual_profile_dir` using the Query ID slug as
the file name (for example, replace the Query ID separator with `_` and save
`<query-id-slug>.txt`), start `query-doctor-web`, choose `One Query ID`, and
enter the original Query ID. The web path stages and analyzes the local file
through the same text-only, bounded, redacted analyzer path. If the file
contains an embedded Query ID for a different query, staging fails closed before
replacing any existing case.

For a self-contained one-profile workspace, set both paths in an ignored local
config file and keep generated cases outside the source tree:

```json
{
  "manual_profile_dir": "/path/to/profile-inbox",
  "corpus_dir": "/path/to/query-doctor-cases",
  "no_llm": true
}
```

Then start `query-doctor-web --config ./query-doctor-one-profile.json`. Relative
`corpus_dir` values in config resolve from the config file; the `--corpus-dir`
CLI flag resolves relative paths from the current directory. When neither is
set, the web UI stores generated Query ID cases under `./cases/cm-corpus` from
the directory where you started `query-doctor-web`.

### Troubleshooting

- `Profile text does not include a Query ID`: keep the original Impala Web UI
  download name when it has the strict `profile_<query-id-high>_<query-id-low>`
  shape, or pass `--query-id <query-id>`. Query Doctor also accepts a
  `Query ID:` header inside the text export. If multiple Query ID sources are
  present, they must match.
- `Parsed operators: 0`: the case is still staged and can open in the UI, but
  that text export did not include a parseable `ExecSummary`/operator table. Use
  the preserved Impala text profile export when available; JSON, Thrift, and
  profile-v2 payloads are outside this manual profile path.
- `query-doctor-web --corpus-dir cases/cm-corpus` asks for Cloudera Manager
  settings: confirm that `query-doctor-analyze` wrote a complete case under the
  same corpus directory you pass to web, and run web from the same workspace or
  use an absolute `--corpus-dir`.

## Door 2: Run The Synthetic Demo

The synthetic demo is deterministic, local-only, and contains no real SQL,
profiles, metadata, hostnames, users, or credentials.

```bash
query-doctor-web --public-demo
```

This one-command mode is documented in [demo-mode.md](demo-mode.md). It
generates the synthetic demo pack in a dedicated temp directory, forces
Python-only mode, ignores default local config, and blocks all POST actions.

To inspect or reuse the generated pack manually, use the lower-level commands:

```bash
query-doctor-demo-preflight
DEMO_PACK="${TMPDIR:-/tmp}/query-doctor-demo-pack"
query-doctor-demo --out "$DEMO_PACK" --overwrite
QUERY_DOCTOR_ACTION_OUTCOMES_PATH="$DEMO_PACK/action_outcomes.jsonl" \
  query-doctor-web --host 127.0.0.1 --port 8766 --batch-summary "$DEMO_PACK/batch_summary.json"
```

Open the localhost URL printed by `query-doctor-web`. Start with
`/?query_group=workloads#scan-context` to show the compact Scan context workload
follow-up links and local synthetic action outcomes before opening Workload
Details. When a Recent summary has repeated safe row-level workload fingerprints
but no materialized workload payload, the UI derives bounded repeated workload
details from the sanitized rows; those details have no baseline or regression
claim until local history evidence is available.

The main results table is decision-focused: attention rows show one short
deterministic classification, priority, duration, owner context, and a clear
Details path. Repeated workloads keep priority, p95, total observed impact, and
top owner in the inbox; p50, pool, bottleneck, and supporting evidence remain
available in Workload Details.

The synthetic demo pack contains eleven sanitized Impala cases covering workload
follow-up, repeated patterns, trusted optimizer recommendations, stats
maintenance, storage/HDFS follow-up, frequent-short workloads, mixed signals,
unknown but useful limited evidence, and direct-Impala compatibility. It also
includes two read-only raw-free Trino Beta demo cases rendered from static
compact diagnosis facts, without contacting a Trino coordinator or enabling
Details, reports, optimizer guidance, generated SQL, or SQL execution. See
[demo-cases.md](demo-cases.md) for the full scenario list and talk track.

## Door 3: Run A Minimal Cloudera Manager Scan

Use this when you have read-only Cloudera Manager access for an Impala service.
Keep secrets in the shell environment or a local env file, not in JSON config.
Create `~/.qdcreds/cm-ro.env` with `CM_USERNAME` plus `CM_PASSWORD` or `CM_TOKEN`
before sourcing it.

```bash
mkdir -p ~/.qdcreds
cp query-doctor-config.minimal.example.json ~/.qdcreds/query-doctor-config.json
# Edit with CM URL, cluster, service, and CA bundle if needed.
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
[configuration.md](configuration.md) and [credentials.md](credentials.md).

For repeated safe local runs, `--reuse-analyzed-profiles-from <cache-root>` can
reuse completed analyzed cases from direct child `query-doctor-*` batch outputs
when the Query ID and explicit profile reuse contract match.

## Door 4: Connect Directly To Kubernetes Impala

Use this when Cloudera Manager is not the query source and the Query Doctor
runtime can reach the debug Web UI endpoint of every Impala coordinator that
accepts user queries. Direct collection is read-only and bounded. It reads the
configured `/queries` and profile endpoints; it does not submit SQL.

First verify the installed package without contacting the cluster:

```bash
query-doctor-self-test
```

The self-test includes a synthetic direct-Impala query-list dialect with one
finished and one running query. It also writes raw-free summaries to SQLite and
opens them through a fresh store instance. This proves the installed parser and
local history restart contract, not connectivity or compatibility with a real
Impala deployment.

Save the following as `~/.qdcreds/query-doctor-config.json`, replacing only the
example coordinator host and scheme. Keep credentials outside JSON. The same
shape is committed as `query-doctor-config.direct-impala.example.json` for
checkout-based installs.

```json
{
  "clusters": [
    {
      "id": "kubernetes-impala",
      "label": "Kubernetes Impala",
      "cluster_type": "impala",
      "impala_profile_hosts": ["impalad-coordinator.example.com"],
      "impala_profile_scheme": "https"
    }
  ],
  "active_cluster_key": "kubernetes-impala",
  "language": "en",
  "source_visibility": "safe",
  "no_llm": true,
  "recent_history_backend": "sqlite",
  "recent_history_db": "./query-doctor-state/recent-history.sqlite3",
  "recent_history_summary_retention_days": 30,
  "recent_scan_timezone": "UTC",
  "recent_window_minutes": 60,
  "recent_include_running": true,
  "recent_profile_analysis_limit": 10,
  "recent_metadata_top_limit": 0
}
```

Run one bounded discovery-only acceptance. It records finished and currently
running summaries in the configured SQLite history without collecting profiles,
metadata, reports, optimizer output, or raw SQL:

```bash
query-doctor-batch-recent \
  --config ~/.qdcreds/query-doctor-config.json \
  --out "${TMPDIR:-/tmp}/query-doctor-direct-impala-readiness" \
  --overwrite \
  --discover-only \
  --include-running \
  --metadata-mode off \
  --top-reports 0
```

Review only the aggregate summary first. A successful run should report direct
Impala discovery and a non-warning Recent history status. Zero running queries
is a valid result; it means none were retained by the configured coordinators at
that moment. Query-log depth is limited by each coordinator's retention.

Start the private local UI with the same config, open Online History, then stop
and restart the process. The retained summaries should remain available after
restart:

```bash
query-doctor-web \
  --config ~/.qdcreds/query-doctor-config.json \
  --host 127.0.0.1 \
  --port 8765
```

If multiple coordinators accept queries, list each one explicitly in
`impala_profile_hosts`; a single load-balanced endpoint may not retain every
query or profile. For a shared Kubernetes deployment, use the configured Helm
mode, external Secret references, persistent storage, and a trusted auth front
door. Do not copy workstation paths or credentials into chart values.

### Troubleshooting

- `did not find a readable query list`: verify network policy, DNS, TLS, and the
  configured scheme from the Query Doctor runtime. Treat this as an environment
  failure until the endpoint is reachable.
- Recent is empty after known traffic: query retention may be too short, or the
  configured coordinator set may be incomplete. Use a fresh query and check the
  aggregate discovery warnings.
- Finished works but Running is empty: an empty Running set is valid. Validate
  again while a bounded test query is active if an operator-approved workload is
  available.
- History does not survive restart: keep `recent_history_db` on persistent
  storage and confirm the process can read and write its parent directory.
