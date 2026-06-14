# Local Smoke Workflows

Language: English | [Russian](i18n/ru/local-smoke.md)

This guide contains deterministic local validation workflows for maintainers
and operators. It uses packaged `query-doctor-*` console scripts. Root-level
compatibility launchers have been removed; when console scripts are not
installed, use `python -m query_doctor.cli.<command_module>` from the checkout.

## Preconditions

- Start from a clear repository state: `git status --short`.
- Use ignored local cases only.
- Do not stage or commit files under `cases/cm-corpus/` or
  `cases/cm-corpus-hostalias/`.
- Keep generated reports and metadata outputs under ignored case directories or
  `/tmp/query-doctor-*`.
- Do not print full profiles, raw SQL, raw metadata, credentials, hostnames, IPs
  or production identifiers in terminal output copied into docs or issues.
- Report generation may call local Ollama; analyzer-only and corpus smoke must
  not.

## Packaging Smoke

Use a fresh virtual environment so the smoke does not mutate system Python:

```bash
python3 -m venv /tmp/query-doctor-pkg-smoke-venv
/tmp/query-doctor-pkg-smoke-venv/bin/python -m pip install -e .
```

If the environment is network-restricted and editable install tries to download
PEP 517 build dependencies, use the committed legacy editable-install shim:

```bash
/tmp/query-doctor-pkg-smoke-venv/bin/python setup.py develop
```

Minimum checks:

```bash
/tmp/query-doctor-pkg-smoke-venv/bin/query-doctor-analyze --help
/tmp/query-doctor-pkg-smoke-venv/bin/query-doctor-web --help
/tmp/query-doctor-pkg-smoke-venv/bin/query-doctor-report --help
/tmp/query-doctor-pkg-smoke-venv/bin/query-doctor-optimize-query --help
/tmp/query-doctor-pkg-smoke-venv/bin/query-doctor-pipeline --help
/tmp/query-doctor-pkg-smoke-venv/bin/query-doctor-demo-preflight

/tmp/query-doctor-pkg-smoke-venv/bin/query-doctor-analyze \
  tests/fixtures/minimal_case \
  -o /tmp/query-doctor-pkg-smoke-analysis.md
```

Remove generated package metadata if an editable smoke creates it in the
checkout:

```bash
rm -rf query_doctor.egg-info
```

## Analyzer Smoke

Use existing ignored corpus cases through local aliases. Keep the alias mapping
and any real case/query IDs in local exclude-only notes or local config:

```bash
CASE="cases/cm-corpus-hostalias/<host-skew-case>"
query-doctor-analyze "$CASE"

CASE="cases/cm-corpus/<cardinality-memory-case>"
query-doctor-analyze "$CASE"
```

Review only summary and evidence lines. Do not print full profiles.

Check:

- parsed operator count;
- cardinality anomaly count;
- memory anomaly count;
- `Backend / Host Tail Evidence`, if present;
- action cards;
- `supported`, `not_observed`, and `unknown` wording.

## Report Smoke

Use the packaged pipeline entry point:

```bash
query-doctor-pipeline "$CASE" --mode admin --out diagnosis_smoke.md
```

Generated report files stay inside ignored case directories. Do not stage them.

Check:

- trusted report sections:
  - localized summary
  - localized practical recommendations
  - localized detailed findings
  - localized follow-up checks
  - localized analyzer facts appendix
- analyzer facts appendix is generated from `analysis_facts.md`, not written as
  model-style narrative;
- no raw hostnames, IPs, users, emails, cookies, tokens, passwords,
  Authorization headers or URL credentials;
- no unsupported root-cause claims;
- no cardinality underestimation claim when `Cardinality anomalies: 0`;
- no row underestimation claim when actual/estimated ratio is below `1`;
- no memory underestimation claim when memory ratio is below `1`;
- no operator/profile counter time described as query wall-clock duration;
- no write-path proven-cause claim when write-path anomaly is `unknown`;
- cautious host-tail wording when execution skew is `no` or host-tail
  candidates are `0`.

## Corpus Smoke

```bash
query-doctor-corpus-smoke cases/cm-corpus
query-doctor-corpus-smoke cases/cm-corpus-hostalias
```

Corpus smoke is local analyzer-only. It does not call Cloudera Manager and does
not run Ollama/report generation.

## Real Impala Metadata Smoke

Run this only when intentionally testing the explicit metadata collector against
a real Impala coordinator. Keep output under `/tmp` and do not commit it.

### Kerberos Preconditions

On macOS, the default Kerberos cache may be `API:...`, which is not always
visible to subprocesses. For reproducible collector/pipeline smoke, use an
explicit FILE cache:

```bash
export KRB5CCNAME=FILE:/tmp/krb5cc_query_doctor_user
kinit -c "$KRB5CCNAME" user@EXAMPLE.COM
klist -c "$KRB5CCNAME"
```

To avoid exporting `KRB5CCNAME` before every web or batch run, put the cache
reference in `~/.qdcreds/query-doctor-config.json` or an ignored
repository-local `query-doctor-config.json`:

```json
{
  "krb5ccname": "FILE:/tmp/krb5cc_query_doctor_user",
  "metadata_coordinator": "impala-coordinator.example.net:21000",
  "metadata_impala_shell": ".venv-impala-shell/bin/impala-shell",
  "metadata_auth": "kerberos",
  "metadata_protocol": "beeswax",
  "metadata_redact": true
}
```

Environment `KRB5CCNAME` wins over local config. The ticket must already exist
after `kinit`; passwords, tokens and keytabs stay environment-only and must not
enter committed templates. The alias `metadata_krb5ccname` is accepted for the
same cache reference, but do not set both names in one config file.

### Local Web Preconditions

For the web UI, the Cloudera Manager (CM) secret stays in the environment and
the Kerberos cache reference may come from ignored local config. Non-secret
`metadata_*` settings in the same config enable Full scan when the web server
is started with `--config` or automatic local config discovery; CLI
`--metadata-*` flags still override config values.

Preferred local launch:

```bash
scripts/query-doctor-web-local
```

For the same local UI with selected-case report and optimizer actions forced
into deterministic Python-only mode:

```bash
scripts/query-doctor-web-local-no-llm
```

See [credentials.md](credentials.md) for expected files and permissions, and
[configuration.md](configuration.md) for config discovery order and field
groups. Put `host` and `port` in local config for the normal local bind.

Direct server startup is useful only when CM credentials are already exported
and Kerberos is already prepared:

```bash
query-doctor-web --config ~/.qdcreds/query-doctor-config.json
```

For a vanilla Impala Known Query ID smoke without Cloudera Manager, keep the
real hosts in ignored local config and use only explicit query-id collection.
Prefer a `clusters` entry so the web UI, direct collector, metadata workflow,
and Prometheus runtime metrics are selected together:

```json
{
  "redact": true,
  "clusters": [
    {
      "id": "ambari-direct-impala",
      "label": "Ambari Direct Impala",
      "cluster_type": "impala",
      "impala_profile_hosts": [
        "impalad-1.example.com",
        "impalad-2.example.com",
        "impalad-3.example.com"
      ],
      "impala_profile_port": 25000,
      "impala_profile_scheme": "http",
      "impala_profile_timeout_sec": 15,
      "impala_kerberos_service_name": "hive",
      "collect_prometheus_timeseries": true,
      "prometheus_url": "https://prometheus.example.com/",
      "prometheus_metrics_profile": "ambari-hadoop",
      "prometheus_step_sec": 30,
      "prometheus_timeseries_padding_sec": 300,
      "metadata_coordinator": "impala-coordinator.example.com:21000",
      "metadata_impala_shell": "impala-shell",
      "metadata_auth": "kerberos",
      "metadata_protocol": "beeswax",
      "metadata_kerberos_service_name": "hive",
      "metadata_redact": true
    }
  ]
}
```

In Known Query ID mode this configuration reads bounded impalad profile
endpoints for one submitted query ID. That path does not run SQL, discover
additional queries, or collect events. The same direct Impala cluster settings
can also be used by Recent queries / Running now to read bounded daemon
query-list endpoints and then collect selected profiles. When Prometheus is
configured, direct Impala workflows can add bounded runtime metric summaries for
the selected query windows.

Before using the config, validate it:

```bash
python3 -m query_doctor.config.contract ~/.qdcreds/query-doctor-config.json
```

For Ambari deployments whose Impala shell service principal is `hive`, create a
fresh safe test query with the same Kerberos service name:

```bash
KRB5CCNAME=FILE:/tmp/krb5cc_query_doctor_user \
  impala-shell -i impala-coordinator.example.com:21000 \
  -k --kerberos_service_name=hive --protocol=beeswax \
  -q 'select 1'
```

Submit the printed Query ID in the Known Query ID UI while the Ambari Direct
Impala cluster is selected, or run a tightly bounded Recent/Running smoke from
the same cluster selector. Expected analyzer facts include `source_label:
Prometheus runtime metrics`, a non-zero runtime metrics `coverage`, and
`no_data_metrics: none` when every allowlisted metric returned data.

Expected analysis output for this mode is still richer than the collection
surface: Profile Format, Source Provenance, Profile Resource Facts, Profile
Timing Facts, and Runtime Diagnosis profile resource/timing signals should be
raw-free. Browser-visible output must not contain hostnames, raw profile text,
profile digests, local paths, or temporary artifact names.

### Current-Upstream Impala Smoke

A maintainer may keep an ignored `clusters[]` entry for a current-upstream
Apache Impala build. Treat it as a direct Impala compatibility smoke target, not
committed configuration or a public support claim. Keep the real cluster
selector, connectivity command, namespace, hostnames, query IDs, and output
identifiers in local exclude-only notes or local config only.

Start any required local connectivity according to private local notes before
Query Doctor commands. Do not copy private endpoint commands into committed
docs.

Run the direct Impala smoke wrapper first. It reads
`~/.qdcreds/query-doctor-config.json`, auto-selects the only direct-Impala
cluster when there is exactly one, prepares a Kerberos ticket from the local
keytab when available, and runs a bounded no-LLM Recent scan. If metadata
Kerberos is unavailable, the default smoke still checks discovery, profile
collection, and analyzer output while skipping metadata.

```bash
scripts/query-doctor-direct-impala-smoke
```

When multiple direct-Impala clusters exist in local config, pass the local
cluster id explicitly:

```bash
scripts/query-doctor-direct-impala-smoke --cluster <direct-impala-cluster-id>
```

Use strict metadata mode only when validating the metadata path itself:

```bash
scripts/query-doctor-direct-impala-smoke --cluster <direct-impala-cluster-id> --require-metadata
```

To validate the same direct-Impala path through the local web UI and wrapper,
use the web smoke. It starts `scripts/query-doctor-web-local --no-llm`, submits
the Finished-query scan form for the selected direct-Impala cluster, waits for
the web job, checks the retained batch summary, and opens one Details page. The
script prints only aggregate statuses such as selected case count,
collection/analyzer success count, and metadata collection count.

```bash
scripts/query-doctor-web-direct-impala-smoke --cluster <direct-impala-cluster-id>
```

The web smoke requires at least one selected table-backed query to collect
metadata by default. For a discovery/profile/analyzer-only check, use
`--allow-no-metadata` or set `--metadata-top-limit 0`.

To validate one explicit Known Query ID through the local web UI, keep the
Query ID in a local ignored file and use the Known Query smoke. It starts
`scripts/query-doctor-web-local --no-llm`, submits the normal Known Query ID
form, waits for the web job, opens the Details page, and checks the
deterministic Python report route without printing the Query ID.

```bash
scripts/query-doctor-web-known-query-smoke \
  --cluster <direct-impala-cluster-id> \
  --query-id-file <ignored-query-id-file>
```

For a table-backed query where metadata collection is expected, add
`--require-metadata`.

Use `--require-metadata` only with a fresh retained table-backed `SELECT` whose
profile exposes source tables. DDL, `SHOW` statements, CTE-only queries, and
old query IDs can still validate discovery/profile/analyzer/report routing, but
they do not prove the Known Query ID metadata path because there may be no
collectable table reference or retained profile to inspect.

Direct Impala Known Query ID collection must be able to fetch the retained
profile through the configured `impala_profile_hosts` endpoint. A single
load-balanced or ingress endpoint may not reach the daemon that coordinated a
particular query; in that case the smoke should fail safely with a collector
subprocess category while keeping captured output hidden.

Validate the summary before changing wording or behavior:

```bash
python3 scripts/audit_profile_evidence_gates.py \
  <ignored-smoke-output-dir>/batch_summary.json \
  --fail-on-issues
```

Record private per-run results in local exclude-only notes. Public docs may keep only
path-free aggregate summaries, compatibility observations, and follow-up gates
after reviewing them for support-claim drift.

For local `impala-shell`, use the isolated venv. The wrapper creates it when
`.venv-impala-shell/bin/impala-shell` is missing; manually:

```bash
scripts/bootstrap-impala-shell
```

Use one explicit scratch/test table, not a broad table list. For CDH 6 / Impala
3.2 with pip `impala-shell`, use `--protocol beeswax`; HS2/OpenSession may not
work with that stack.

### Collector Smoke

```bash
rm -rf /tmp/query-doctor-impala-collector-smoke-test-table
mkdir -p /tmp/query-doctor-impala-collector-smoke-test-table

KRB5CCNAME=FILE:/tmp/krb5cc_query_doctor_user \
query-doctor-collect-impala-context \
  --table scratch_db.query_doctor_meta_probe \
  --out /tmp/query-doctor-impala-collector-smoke-test-table \
  --impala-shell .venv-impala-shell/bin/impala-shell \
  --coordinator impala-coordinator.example.net:21000 \
  --auth kerberos \
  --protocol beeswax \
  --timeout-sec 30 \
  --max-output-bytes 200000 \
  --redact
```

Expected collector behavior:

- executes only `SHOW CREATE TABLE`, `SHOW TABLE STATS`, and
  `SHOW COLUMN STATS`;
- prints only safe progress/status lines;
- writes `impala_context.md` and `impala_context.json` under the selected
  `/tmp` output directory;
- replaces infrastructure hosts with safe aliases such as `host_01`;
- keeps useful metadata: requested table name, column names, file format,
  row/size values, and `NULL` / `-1` markers;
- stops the smoke path if collector-only smoke fails.

### Trino Kerberos Smoke

This is an operator-only development smoke for checking Kerberos/SPNEGO access
to a Trino coordinator while Query Doctor's Trino path remains limited to
sanitized offline evidence package import, bounded local event-store import,
bounded HTTP event archive import, bounded HTTP query-detail archive import,
bounded local query-detail import, bounded local query-list aggregate import,
bounded local statement-stats import, event-source contract checking, and
dry-run coordinator query-info target checking, plus bounded pruned coordinator
query-info probing.
It is not a live Trino collector, live engine selector, UI route, report
surface, optimizer path, metadata path, or live support claim.

The script executes only built-in read-only smoke statements:

- actor identity check;
- source listing check;
- optional count check for one explicit `catalog.schema.table`;
- optional one-row sample check for one explicit `catalog.schema.table`.

It does not accept arbitrary SQL. It writes only a safe
`trino_smoke_summary.json` with statuses, row counts, field counts, page counts,
safe error categories, and redaction assertions. It does not write statement
text, result values, query identifiers, actor identity values, coordinator
hostnames, object names, or raw failure details.

Prepare a Kerberos cache first. For coordinators whose HTTP service principal
is in a different realm from the client principal, use a local `KRB5_CONFIG`
that maps the coordinator host to the service realm.

```bash
KRB5_CONFIG=/tmp/query-doctor-trino-krb5.conf \
  kinit -kt /path/to/user.keytab \
  -c FILE:/tmp/query-doctor-trino-smoke-krb5cc \
  user@EXAMPLE.COM
```

Run the smoke with explicit table arguments for the table-specific checks:

```bash
rm -rf /tmp/query-doctor-trino-smoke

python3 scripts/trino_kerberos_smoke.py \
  --server https://trino-coordinator.example.net \
  --client-user user \
  --kerberos-principal user@EXAMPLE.COM \
  --service-name HTTP \
  --krb5-config /tmp/query-doctor-trino-krb5.conf \
  --krb5-ccname FILE:/tmp/query-doctor-trino-smoke-krb5cc \
  --count-table sample_catalog.sample_schema.sample_table \
  --sample-table sample_catalog.sample_schema.sample_table \
  --out /tmp/query-doctor-trino-smoke
```

Expected smoke behavior:

- uses `curl` with Kerberos/SPNEGO and the configured service name;
- sends Trino client user only in the protocol header;
- submits only the built-in allowlisted smoke statements;
- follows bounded Trino protocol pages;
- prints only per-check safe status lines;
- writes only `trino_smoke_summary.json` under the selected `/tmp` output
  directory.

### Padded `impala-shell` Output

`impala-shell` can heavily pad tabular output, especially for
`SHOW CREATE TABLE`. Query Doctor compacts only safe shell formatting before
checking the output-size limit:

- trims trailing whitespace;
- collapses repeated blank lines;
- reduces ASCII table borders and cell right-padding before closing `|`;
- preserves meaningful internal whitespace, for example
  `COMMENT 'hello   world'`.

`--max-output-bytes` and `--metadata-max-output-bytes` apply to normalized
output. `impala_context.json` records raw/normalized byte counts and
`stdout_normalized` / `stderr_normalized` flags. If the normalized body still
exceeds the limit, status remains `too_large`, the body is not saved, and the
collector stays fail-closed.

This does not expand collector SQL scope. Allowed statements remain only
`SHOW CREATE TABLE`, `SHOW TABLE STATS`, and `SHOW COLUMN STATS`; `SELECT`,
`COMPUTE STATS`, `REFRESH`, `INVALIDATE METADATA`, `MSCK REPAIR`,
`SHOW PARTITIONS`, and `DESCRIBE FORMATTED` are not executed.

### Pipeline Metadata Smoke

Use a temporary ignored copy of one real case:

```bash
SOURCE_CASE="cases/cm-corpus/<ignored_case_id>"
SMOKE_OUT="${TMPDIR:-/tmp}/query-doctor-realcase-metadata-smoke"

rm -rf "$SMOKE_OUT"
mkdir -p "$SMOKE_OUT"

cp "$SOURCE_CASE/profile_digest.md" "$SMOKE_OUT/profile_digest.md"

KRB5CCNAME=FILE:/tmp/krb5cc_query_doctor_user \
query-doctor-pipeline "$SMOKE_OUT" \
  --metadata-mode on \
  --metadata-coordinator impala-coordinator.example.net:21000 \
  --metadata-impala-shell .venv-impala-shell/bin/impala-shell \
  --metadata-protocol beeswax \
  --metadata-max-tables 1 \
  --metadata-redact
```

Fast analyzer/metadata-only variant:

```bash
KRB5CCNAME=FILE:/tmp/krb5cc_query_doctor_user \
query-doctor-pipeline "$SMOKE_OUT" \
  --metadata-mode on \
  --metadata-coordinator impala-coordinator.example.net:21000 \
  --metadata-impala-shell .venv-impala-shell/bin/impala-shell \
  --metadata-protocol beeswax \
  --metadata-max-tables 1 \
  --metadata-redact \
  --stop-after-analysis
```

`--stop-after-analysis` preserves normal metadata semantics, reruns analyzer
after successful metadata collection, and exits before report generation.
Expect `analysis_facts.md` and, if metadata was collected,
`impala_context.md/json`. Do not expect `diagnosis.md` or
`diagnosis.partial.md`. This mode does not validate LLM wording; run a full
report smoke separately on representative cases.

## Bounded Recent Query Scan Smoke

First pass without metadata or LLM:

```bash
CM_PASSWORD=... \
KRB5CCNAME=FILE:/tmp/krb5cc_query_doctor_user \
query-doctor-batch-recent \
  --out /tmp/query-doctor-recent-batch-example \
  --recent-window-minutes 1440 \
  --cm-inspect-limit 5000 \
  --triage-profile-limit 5000 \
  --min-duration-sec 10 \
  --order duration-desc \
  --metadata-mode off \
  --top-reports 0 \
  --cm-jobs 20 \
  --jobs 4 \
  --metadata-jobs 1 \
  --overwrite
```

This batch workflow is intentionally two-stage:

- run CM discovery and explicit query-id profile collection for at most
  `--triage-profile-limit` cases;
- run analyzer/metadata only for selected cases through pipeline
  `--stop-after-analysis`;
- score `analysis_facts.md` deterministically;
- run full report generation only for the worst `--top-reports` cases.

Important bounds:

- `--cm-inspect-limit` is the bounded recent-summary request/inspection cap
  after server-side CM filters such as time window and duration.
- `--triage-profile-limit` is the maximum explicit profile collection count;
  hard cap `5000`.
- `--select-limit` is a deprecated compatibility alias.
- Duration filtering is pushed into the CM request where supported and remains
  client-side as a safety backstop.
- Outputs are `batch_summary.json` and `batch_summary.md`, with truncated query
  IDs, sanitized user/pool fields, no full SQL, no raw profiles, and no secrets.
- Use a fresh dedicated `/tmp/query-doctor-*` output directory. Add
  `--overwrite` only when you intend to delete and recreate that directory.
- Do not point `--out` inside the repository, tracked `cases/`, home or system
  paths.

Parallelism:

- `--cm-jobs`: CM profile collection workers.
- `--jobs`: analyzer workers after collection.
- `--metadata-jobs`: metadata refresh workers. Default and hard cap are both
  `5`; lower it manually for conservative smoke runs.

When metadata is enabled, `--metadata-top-limit` is spent on top collectable
cases. For Cloudera Manager Recent batches, real table references may be passed
internally from discovery statements to the bounded metadata subprocess;
progress, summaries, and report-visible output stay raw-free.

High analyzer parallelism is available only behind an explicit guard and only
when LLM reports are disabled. Metadata refresh has a separate hard cap through
`--metadata-jobs`, so analyzer `--jobs` does not increase metastore/Impala
metadata concurrency:

```bash
query-doctor-batch-recent \
  --out /tmp/query-doctor-recent-batch-fast \
  --recent-window-minutes 1440 \
  --cm-inspect-limit 5000 \
  --triage-profile-limit 5000 \
  --min-duration-sec 10 \
  --order duration-desc \
  --metadata-mode off \
  --top-reports 0 \
  --cm-jobs 50 \
  --jobs 4 \
  --metadata-jobs 1 \
  --allow-high-jobs
```

Start high-concurrency collection with `--cm-jobs 20` or `--cm-jobs 50`.
`--cm-jobs 100` is allowed, but it can create many concurrent CM profile
requests. `--allow-high-jobs` is needed only when analyzer `--jobs` exceeds the
normal cap; metadata refresh remains bounded separately by `--metadata-jobs <=
5`.

Second-stage full reports should be run only for top suspicious cases from
`batch_summary.json`:

```bash
KRB5CCNAME=FILE:/tmp/krb5cc_query_doctor_user \
query-doctor-pipeline /tmp/query-doctor-recent-batch-example/cases/case-001/QUERY_ID_ALIAS \
  --metadata-coordinator impala-coordinator.example.net:21000 \
  --metadata-impala-shell .venv-impala-shell/bin/impala-shell \
  --metadata-protocol beeswax \
  --metadata-max-tables 5 \
  --metadata-max-output-bytes 2097152 \
  --metadata-redact
```

Expected healthy batch smoke behavior:

- recent discovery is bounded and duration-filtered by CM where supported;
- profile collection remains one explicit `--query-id --redact --limit 1` call
  per selected case;
- high analyzer jobs, if used, are allowed only with
  `--metadata-mode off --top-reports 0`;
- full LLM reports are escalated only for explicitly selected/top-ranked
  suspicious cases;
- real metadata collection for top cases uses only `SHOW CREATE TABLE`,
  `SHOW TABLE STATS`, and `SHOW COLUMN STATS`;
- `diagnosis.md` is written only after validation;
- `diagnosis.partial.md` is not trusted.

## Smoke Output Checks

After metadata or batch smoke:

```bash
find "$SMOKE_OUT" -maxdepth 3 -type f | sort

rg -n "Table Metadata Context|SHOW TABLE STATS status|SHOW COLUMN STATS status|table stats rows|column stats" \
  "$SMOKE_OUT/analysis_facts.md" || true
```

The safety scan should confirm the absence of `SELECT`, `COMPUTE STATS`,
`MSCK REPAIR`, `REFRESH`, `INVALIDATE METADATA`, `SHOW PARTITIONS`,
`DESCRIBE FORMATTED`, leaked coordinator hostnames, credentials, tokens,
cookies, and auth headers.

## Final Checks

```bash
pre-commit run --all-files
python3 -m pytest -q
git diff --check
git status --short
git diff --name-status
git diff --stat
```

Ignored generated files may remain under case directories. Confirm they are not
tracked:

```bash
git ls-files cases/cm-corpus cases/cm-corpus-hostalias
```
