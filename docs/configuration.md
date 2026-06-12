# Configuration Reference

Last reviewed: 2026-06-09

Query Doctor reads non-secret local settings from a JSON config file. Keep
passwords, tokens, keytabs, ticket contents, Authorization headers, and API keys
out of this file. Put those values in environment variables or local env files
described in [credentials.md](credentials.md).

The committed
[query-doctor-config.minimal.example.json](../query-doctor-config.minimal.example.json)
is the first-copy Cloudera Manager starter. The fuller
[query-doctor-config.example.json](../query-doctor-config.example.json) shows
CM, direct Impala, Prometheus, metadata, and LLM routing fields in one
advanced template. Add optional fields from the reference below only when you
need to override a built-in default.

## Config Location

Preferred local path:

```bash
mkdir -p ~/.qdcreds
cp query-doctor-config.minimal.example.json ~/.qdcreds/query-doctor-config.json
chmod 600 ~/.qdcreds/query-doctor-config.json
```

The file is non-secret, but it often contains hostnames, usernames, local paths,
and cluster names, so treat it as private workstation state.

Most packaged commands that support automatic local config discovery use this
order when `--config` is omitted:

1. `query-doctor-config.json` in the current working directory.
2. `~/.qdcreds/query-doctor-config.json`.
3. `query-doctor-config.json` in the repository root, when the command allows
   the repository default.
4. Legacy `.query-doctor-cm.local.json` in the current working directory.
5. Legacy `.query-doctor-cm.local.json` in the repository root, when allowed.

The local web bootstrap wrapper has a workstation-oriented order:

1. `QD_CONFIG`, when set.
2. `$QD_CREDS_DIR/query-doctor-config.json`, defaulting to
   `~/.qdcreds/query-doctor-config.json`.
3. Repository-local `query-doctor-config.json`.
4. Legacy repository-local `.query-doctor-cm.local.json`.

Explicit `--config PATH` always wins. CLI flags then override environment
variables, config values, and code defaults for the settings they control.
Credential environment variables such as `CM_PASSWORD`, `CM_TOKEN`, and
`KRB5CCNAME` remain outside the JSON config; `KRB5CCNAME` overrides configured
`krb5ccname`.

## Minimal Cloudera Manager Config

Use this shape, also available in
[`query-doctor-config.minimal.example.json`](../query-doctor-config.minimal.example.json),
for the normal Cloudera Manager workflow:

```json
{
  "clusters": [
    {
      "id": "cm-impala",
      "label": "Impala via Cloudera Manager",
      "cluster_type": "cm",
      "cm_url": "https://cm.example.com:7183/",
      "cluster": "example_cluster",
      "service": "impala"
    }
  ],
  "language": "en",
  "recent_scan_timezone": "UTC"
}
```

Provide `CM_USERNAME` plus `CM_PASSWORD` or `CM_TOKEN` through the shell
environment, for example from `~/.qdcreds/cm-ro.env`. The `username` config
field remains supported as a non-secret fallback, but keeping the CM auth user
with the CM auth secret avoids drift between files.

Add `ca_bundle` only when your Cloudera Manager endpoint uses a private CA,
and add metadata or direct-Impala fields only after the basic Recent scan path
is working.

Direct `query_doctor.cli.batch_recent` runs also read the local Cloudera
Manager env file before preflight. Discovery order is:

1. `QD_CM_ENV`, when set.
2. `$QD_CREDS_DIR/cm-ro.env`, when `QD_CREDS_DIR` is set.
3. `~/.qdcreds/cm-ro.env`.

The file is parsed as simple `KEY=value` or `export KEY=value` assignments
without shell evaluation. Only `CM_USERNAME`, `CM_USER`, `CM_PASSWORD`,
and `CM_TOKEN` are accepted from this file. Already-exported environment
variables win over file values. Kerberos cache and principal settings should
come from the shell environment, wrapper defaults, keytab inference, or JSON
config where appropriate, not from `cm-ro.env`.

## Minimal Direct Impala Config

Use this shape when Cloudera Manager is not the profile source:

```json
{
  "cluster_type": "impala",
  "impala_profile_hosts": [
    "impalad-worker-1.example.com",
    "impalad-worker-2.example.com"
  ],
  "impala_kerberos_service_name": "hive",
  "metadata_coordinator": "impala-coordinator.example.com:21000",
  "metadata_impala_shell": ".venv-impala-shell/bin/impala-shell",
  "metadata_kerberos_service_name": "hive"
}
```

Direct Impala collection reads only bounded daemon debug web endpoints for
Recent, Running, or one Known Query ID workflow. It does not execute SQL.
Metadata collection uses read-only `SHOW` statements through `impala-shell` and
stays bounded by the metadata limits below.
For Cloudera Manager Recent batches, the metadata refresh may use table
references extracted from discovery statements before profile identifier
redaction. Those identifiers are passed only to the bounded metadata subprocess;
progress, summaries, trusted reports, and pipeline plan output remain raw-free.

## Multiple Clusters

Prefer `clusters[]` when one workstation talks to more than one target. Keep
cluster-specific settings inside each cluster object. Avoid top-level
`cm_url`, `cluster`, or `service` when mixing Cloudera Manager and direct
Impala clusters; otherwise direct clusters inherit irrelevant CM defaults.

```json
{
  "clusters": [
    {
      "id": "cm-prod",
      "label": "Cloudera Manager production",
      "cluster_type": "cm",
      "cm_url": "https://cm-prod.example.com:7183/",
      "cluster": "prod_cluster",
      "service": "impala",
      "ca_bundle": "~/.qdcreds/cm-chain.pem",
      "metadata_coordinator": "impala-prod-coordinator.example.com:21000",
      "metadata_impala_shell": ".venv-impala-shell/bin/impala-shell"
    },
    {
      "id": "direct-impala",
      "label": "Direct Impala",
      "cluster_type": "impala",
      "impala_profile_hosts": ["impalad-worker-1.example.com"],
      "metadata_coordinator": "impala-coordinator.example.com:21000",
      "metadata_impala_shell": ".venv-impala-shell/bin/impala-shell"
    }
  ]
}
```

Cluster entries may define target, TLS, direct Impala, Prometheus, metadata,
privacy, redaction, and `recent_scan_timezone` fields. `language`, `no_llm`, web
`host`/`port`, Recent scan limits, and output paths are global. Cluster `id`
values must use only letters, digits, `.`, `_`, or `-`.

Direct `query_doctor.cli.batch_recent` runs can select one of these entries
with `--config-cluster <id>`. The selected cluster supplies source, metadata,
runtime-metrics, redaction, and `source_visibility` settings; explicit CLI
flags still override the selected cluster. For local web runs, omit
`source_owner_user` unless you intentionally need a fixed owner that differs
from the keytab-derived user.

## LLM Routes

Reports and Query LLM optimizer can use separate routes. For local Ollama, the
provider and models are enough; the default base URL is
`http://localhost:11434`.

```json
{
  "report_llm_provider": "ollama",
  "report_llm_model": "qwen3-coder:30b-a3b-q8_0",
  "optimizer_llm_provider": "ollama",
  "optimizer_llm_model": "deepseek-coder-v2:16b"
}
```

To switch either route to an external OpenAI-compatible API, change the provider
and add the non-secret base URL. Keep the token in `~/.qdcreds/llm-api.env`.

```json
{
  "report_llm_provider": "openai_compatible",
  "report_llm_model": "report-route-model",
  "report_llm_base_url": "https://llm-gateway.example.com",
  "optimizer_llm_provider": "openai_compatible",
  "optimizer_llm_model": "optimizer-route-model",
  "optimizer_llm_base_url": "https://llm-gateway.example.com"
}
```

## Safety And Privacy

| Field | Type | Scope | Notes |
| --- | --- | --- | --- |
| `privacy_mode` | boolean | global or cluster | Default on. Makes identifier, hostname, and metadata redaction the default behavior. |
| `no_llm` | boolean | global only | Disables LLM-backed report and optimizer generation. Reports and optimizer outcomes stay Python-owned. |
| `redact` | boolean | global | Redacts sensitive profile content for collection. Real profile collection requires redaction. |
| `redact_identifiers` | boolean | global or cluster | Redacts database, table, and SQL-like identifiers in collected/displayed safe artifacts. |
| `redact_hosts` | boolean | global or cluster | Replaces infrastructure hostnames/IPs with stable aliases. |
| `metadata_redact` | boolean | global or cluster | Redacts collected metadata context. Leave enabled unless inspecting private local artifacts only. |
| `source_visibility` | string | global or cluster | `safe` or `owner_raw`. Default `safe`. `owner_raw` enables fail-closed owner gating for Recent and Running scans; it does not expose raw browser/report fields by itself. |
| `source_owner_user` | string | global or cluster | Optional query owner user for `owner_raw`. Prefer omitting this for local web runs: Query Doctor derives a simple user from `QD_SOURCE_OWNER_USER`, `QD_KRB5_PRINCIPAL`, `KRB5_PRINCIPAL`, or simple principals in `QD_KEYTAB`. Service principals with `/` are not accepted for inference. Keytab-derived users are sorted alphabetically, and the first user becomes the default Username selection. |
| `language` | string | global | Global language mode shown in the web header. It controls Help, Details static UI, and newly generated trusted report language. Supported values: `en`, `ru`. Default: `en`. Existing reports are not regenerated automatically after changing this field. The web header points to this config key without rendering the absolute config path. |
| `report_llm_provider` | string | global | Report LLM provider: `ollama` or `openai_compatible`. |
| `report_llm_model` | string | global | Report model route name. |
| `report_llm_base_url` | string URL | global | Non-secret report provider base URL. For external providers, keep tokens in `~/.qdcreds/llm-api.env`, not JSON. |
| `report_llm_chat_path` | string | global | Optional OpenAI-compatible report chat path override. Omit unless your gateway needs a non-standard path. |
| `optimizer_llm_provider` | string | global | Query LLM optimizer provider: `ollama` or `openai_compatible`. |
| `optimizer_llm_model` | string | global | Query LLM optimizer model route name. `optimizer_model` remains a legacy alias. |
| `optimizer_llm_base_url` | string URL | global | Non-secret optimizer provider base URL. For external providers, keep tokens in `~/.qdcreds/llm-api.env`, not JSON. |
| `optimizer_llm_chat_path` | string | global | Optional OpenAI-compatible optimizer chat path override. Omit unless your gateway needs a non-standard path. |
| `out` | string path | global | Local generated output directory for collector workflows. Do not commit generated output. |

Browser-visible UI and trusted reports must remain raw-free regardless of these
settings. Disabling privacy controls is for private local artifacts only.
`source_visibility=owner_raw` is not an "unhide everything" switch. It only
narrows Cloudera Manager or direct Impala Recent and Running scans to the owner
user before any raw source-view feature is allowed to exist.
When the local web wrapper exposes `QD_KEYTAB`, Query Doctor reads simple
account names from that keytab, sorts them alphabetically, and uses the first
account as the default Username for `owner_raw`. The keytab path and full
Kerberos principals remain local process data and are not rendered in the
browser.

## Web Server

| Field | Type | Notes |
| --- | --- | --- |
| `host` | string | Web bind host. Use `127.0.0.1` for normal local operation. |
| `port` | positive integer | Web bind port. |
| `web_advanced_settings_enabled` | boolean | Shows the Diagnose Advanced settings disclosure when set to `true`. Default is hidden. |
| `web_advanced_filters` | string list | Optional editable filters inside Diagnose Advanced settings. Supported values: `user`, `pool`. When omitted and advanced settings are enabled, both filters are shown. |

Non-local binds require the explicit web CLI risk flag and are not the
supported shared-service deployment model.

## Cloudera Manager

| Field | Type | Notes |
| --- | --- | --- |
| `cm_url` | string URL | Cloudera Manager base URL. Credentials stay in environment variables. |
| `cluster` | string | Cloudera Manager cluster name. |
| `service` | string | Impala service name. |
| `username` | string | Cloudera Manager username. `cm_user` is accepted as a legacy alias. |
| `ca_bundle` | string path | PEM CA bundle for verified TLS, often `~/.qdcreds/cm-chain.pem`. |
| `insecure_skip_verify` | boolean | Disables CM TLS verification. Use only for private local diagnostics. |
| `krb5ccname` | string | Kerberos cache path, for example `FILE:/tmp/krb5cc_query_doctor`. `metadata_krb5ccname` is a legacy alias. |
| `cm_metrics_profile` | string | Cloudera Manager metric compatibility profile, such as `cm6` or `cm7`. |

## Single Query Collection

| Field | Type | Notes |
| --- | --- | --- |
| `since_hours` | positive integer | Lookback window for collector workflows. |
| `limit` | positive integer | Maximum profile count for collector workflows. |
| `min_duration_sec` | non-negative integer | Minimum duration filter. |
| `max_profile_bytes` | positive integer | Profile text byte cap. |
| `pool` | string | Optional admission pool filter. |
| `user` | string | Optional query user filter. |
| `status` | string | One of `succeeded`, `failed`, `cancelled`, or `all`. |
| `query_type` | string | Query type filter, normally `QUERY`. |
| `collect_cm_timeseries` | boolean | Collect bounded allowlisted CM time-series summaries. |
| `cm_timeseries_padding_sec` | non-negative integer | Seconds to pad before and after query time windows. |
| `max_timeseries_bytes` | positive integer | Maximum bytes per CM time-series response. |
| `max_timeseries_points` | positive integer | Maximum numeric points to summarize per query. |

## Recent And Running Scans

| Field | Type | Notes |
| --- | --- | --- |
| `recent_limit` | positive integer | Maximum query summaries to inspect. |
| `recent_select` | positive integer | Maximum candidates selected for deeper analysis. |
| `recent_window_minutes` | positive integer | Lookback window for Recent scans. |
| `recent_min_duration_sec` | non-negative number | Lower duration bound. |
| `recent_max_duration_sec` | non-negative number | Upper duration bound. |
| `recent_order` | string | One of `recent`, `duration-desc`, `duration-asc`, `recent-duration-desc`, or `status-priority`. |
| `recent_output_json` | string path | Optional sanitized recent candidate JSON output path. |
| `recent_include_failed` | boolean | Include failed queries in candidate selection. |
| `recent_include_running` | boolean | Include running queries in candidate selection. |
| `recent_user` | string | Optional recent-query user filter. |
| `recent_pool` | string | Optional recent-query pool filter. |
| `recent_scan_timezone` | string | IANA timezone used for the web Finished queries Scan date/hour selector and UTC CM bounds, for example `UTC`. Default is `UTC`; the form label shows the current UTC offset. This field can also be set per cluster. |
| `recent_parallelism` | positive integer | Overall Recent scan worker limit. |
| `recent_cm_jobs` | positive integer | CM profile/context worker limit. |
| `recent_cm_summary_limit` | positive integer | CM summary scan cap. |
| `recent_profile_analysis_limit` | positive integer | Profile analysis cap. |
| `recent_metadata_jobs` | positive integer | Metadata refresh worker limit. |
| `recent_metadata_top_limit` | non-negative integer | Maximum number of top collectable cases eligible for metadata refresh. |
| `recent_collect_cm_events` | boolean | Collect bounded CM event context when supported. |
| `recent_cm_events_max_events` | positive integer | Maximum CM events to summarize. |
| `recent_collect_cm_timeseries` | boolean | Collect bounded CM runtime metrics when supported. |
| `recent_cm_timeseries_top_limit` | non-negative integer | Number of top cases eligible for CM time-series refresh. |
| `collect_workload_history` / `recent_collect_workload_history` | boolean | Opt in to local workload fingerprint baseline history and regression labels. |
| `workload_history_path` / `recent_workload_history_path` | string path | Optional local JSONL path for workload history. Defaults to `~/.query-doctor/workload_history.jsonl`. |
| `workload_history_max_bytes` / `recent_workload_history_max_bytes` | positive integer | Rotate the local workload history file before appending when it exceeds this size. |

In the web Diagnose flow, `Minimum duration (sec)` is intentionally blank by
default even when `recent_min_duration_sec` exists in local config. An empty web
field sends no lower-duration filter so long-query and repeated-short workload
patterns remain available; enter a value in the field when you want the web scan
to narrow to longer-running queries.

Recent and Running web workflows do not auto-run LLM reports or optimizer jobs.
The default Diagnose form keeps source, scan target, time window, duration, and
required owner filters in the browser. Optional `recent_user` and `recent_pool`
filters can remain config defaults, or can be made editable by setting
`web_advanced_settings_enabled=true` and `web_advanced_filters`. Worker-count
settings such as `recent_parallelism` and `recent_metadata_jobs` are intended
as local config defaults or explicit request overrides, not normal per-scan
browser choices.

## Manual Profile Inbox

| Field | Type | Scope | Notes |
| --- | --- | --- | --- |
| `manual_profile_dir` | string path | global or cluster | Optional local directory of exported Apache Impala text profiles for Known Query ID analysis. Name each file with the Query ID slug, for example `<query-id-slug>.txt` after replacing the Query ID separator with `_`. The web UI stages matching files through the existing manual-profile analyzer path and does not upload raw profile text through the browser. If the file contains an embedded Query ID for a different query, staging fails closed before replacing any existing case. |

`manual_profile_dir` is a local-first fallback for one exported profile. It
does not enable Recent scans, Running scans, Cloudera Manager metrics/events,
direct impalad collection, metadata collection, report generation, or optimizer
actions by itself. When it is the only configured source, Known Query ID fails
closed if the matching profile file is absent instead of falling back to live
collection.

## Direct Impala Profiles

| Field | Type | Scope | Notes |
| --- | --- | --- | --- |
| `cluster_type` / `query_profile_source` | string | global or cluster | `cm` or `impala`. Prefer `cluster_type` in user configs; `query_profile_source` remains the internal/legacy name. Use `impala` for direct daemon endpoints. |
| `impala_profile_hosts` | string list | global or cluster | One or more impalad debug web hosts or host:port values. |
| `impala_profile_port` | positive integer | global or cluster | Default daemon web port for hosts without a port. |
| `impala_profile_scheme` | string | global or cluster | `http` or `https`. |
| `impala_profile_timeout_sec` | positive integer | global or cluster | Per-request timeout. |
| `impala_profile_prefer_json` | boolean | global or cluster | Optional compatibility probe. When true, direct Impala collection tries a JSON profile endpoint first and falls back to text endpoints for older Impala versions. Default is false. |
| `impala_profile_collect_docs` | boolean | global or cluster | Optional `/profile_docs/?json` counter-stability probe with `/profile_docs` HTML fallback. When true, direct Impala collection writes a safe allowlisted counter registry context when the endpoint is available as JSON-style docs or a Web UI HTML table. Missing endpoints are non-fatal. Default is false. |
| `impala_collect_admission_context` | boolean | global or cluster | Optional `/admission?json` aggregate pool-context probe. When true, direct Impala collection writes only bounded safe summaries such as queue presence, queue-time bucket, pool pressure, and freshness. Missing endpoints are non-fatal. Default is false. |
| `impala_kerberos_service_name` | string | global or cluster | Kerberos service token, such as `impala` or `hive`. |

## Prometheus Runtime Metrics

| Field | Type | Scope | Notes |
| --- | --- | --- | --- |
| `collect_prometheus_timeseries` | boolean | global or cluster | Enables bounded Prometheus runtime metric summaries for direct Impala workflows. |
| `prometheus_url` | string URL | global or cluster | Prometheus base URL. Do not include credentials, query parameters, or fragments. |
| `prometheus_metrics_profile` | string | global or cluster | Metrics compatibility profile, such as `ambari-hadoop`. |
| `prometheus_step_sec` | positive integer | global or cluster | Query step in seconds. |
| `prometheus_timeseries_padding_sec` | non-negative integer | global or cluster | Seconds to pad around query windows. |

Prometheus collection uses allowlisted PromQL and writes summarized facts only.
It does not write raw time-series responses or labels. Treat Prometheus
host-level metrics as shared runtime context when multiple Impala deployments
can run on the same hosts; Query Doctor only strengthens runtime hypotheses
when selected-query profile evidence correlates the signal.

## Metadata Collection

| Field | Type | Scope | Notes |
| --- | --- | --- | --- |
| `metadata_coordinator` | string | global or cluster | Impala coordinator `HOST:PORT`. |
| `metadata_impala_shell` | string path | global or cluster | `impala-shell` executable. |
| `metadata_auth` | string | global or cluster | Only `kerberos` is supported. |
| `metadata_protocol` | string | global or cluster | `beeswax`, `hs2`, or `hs2-http`. |
| `metadata_ssl` | boolean | global or cluster | Enables TLS for `impala-shell`. |
| `metadata_ca_cert` | string path | global or cluster | CA certificate for metadata TLS. |
| `metadata_kerberos_service_name` | string | global or cluster | Kerberos service token for metadata, such as `impala` or `hive`. |
| `metadata_timeout_sec` | positive integer | global or cluster | Optional per-command timeout override. Omit to use the built-in default. |
| `metadata_max_tables` | positive integer | global or cluster | Optional maximum tables override for each metadata run. Omit to use the workflow default. |
| `metadata_max_output_bytes` | positive integer | global or cluster | Optional metadata output byte limit override. Omit to use the built-in default. |
| `metadata_redact` | boolean | global or cluster | Redacts metadata output before artifacts are written. |

Metadata collection is read-only, allowlisted, bounded, explicit, and redacted.
Default metadata limits are intentionally omitted from the example config; add
these fields only when a local environment needs different bounds.

## Validation Rules

The config loader rejects:

- unknown fields;
- duplicate canonical aliases, such as both `username` and `cm_user`;
- secret-looking keys such as `password`, `token`, `secret`, or
  `authorization`;
- Prometheus URLs that include credentials, query parameters, or fragments;
- invalid enum values and invalid integer/boolean types.

This fail-closed behavior is intentional. A typo in local config should stop
startup instead of silently changing collection scope.
