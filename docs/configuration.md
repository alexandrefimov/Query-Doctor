# Configuration Reference

Last reviewed: 2026-05-13

Query Doctor reads non-secret local settings from a JSON config file. Keep
passwords, tokens, keytabs, ticket contents, Authorization headers, and API keys
out of this file. Put those values in environment variables or local env files
described in [credentials.md](credentials.md).

The committed [query-doctor-config.example.json](../query-doctor-config.example.json)
is the full template. Copy it locally, then remove fields you do not use.

## Config Location

Preferred local path:

```bash
mkdir -p ~/.qdcreds
cp query-doctor-config.example.json ~/.qdcreds/query-doctor-config.json
chmod 600 ~/.qdcreds/query-doctor-config.json
```

The file is non-secret, but it often contains hostnames, usernames, local paths,
and cluster names, so treat it as private workstation state.

Most packaged commands that support automatic local config discovery use this
order when `--config` is omitted:

1. `query-doctor-config.json` in the current working directory.
2. `query-doctor-config.json` in the repository root, when the command allows
   the repository default.
3. `~/.qdcreds/query-doctor-config.json`.
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

Use this shape for the normal Cloudera Manager workflow:

```json
{
  "host": "127.0.0.1",
  "port": 8765,
  "cm_url": "https://cm.example.com:7183/",
  "cluster": "example_cluster",
  "service": "impala",
  "username": "query_doctor_user",
  "ca_bundle": "~/.qdcreds/cm-chain.pem",
  "privacy_mode": true
}
```

Provide `CM_PASSWORD` or `CM_TOKEN` through the shell environment, for example
from `~/.qdcreds/cm-ro.env`.

## Minimal Direct Impala Config

Use this shape when Cloudera Manager is not the profile source:

```json
{
  "host": "127.0.0.1",
  "port": 8765,
  "query_profile_source": "impala",
  "impala_profile_hosts": [
    "impalad-worker-1.example.com",
    "impalad-worker-2.example.com"
  ],
  "impala_profile_port": 25000,
  "impala_profile_scheme": "http",
  "impala_profile_timeout_sec": 15,
  "impala_kerberos_service_name": "hive",
  "metadata_coordinator": "impala-coordinator.example.com:21000",
  "metadata_impala_shell": ".venv-impala-shell/bin/impala-shell",
  "metadata_auth": "kerberos",
  "metadata_protocol": "beeswax",
  "metadata_kerberos_service_name": "hive",
  "metadata_redact": true,
  "privacy_mode": true
}
```

Direct Impala collection reads only bounded daemon debug web endpoints for
Recent, Running, or one Known Query ID workflow. It does not execute SQL.
Metadata collection uses read-only `SHOW` statements through `impala-shell` and
stays bounded by the metadata limits below.

## Safety And Privacy

| Field | Type | Scope | Notes |
| --- | --- | --- | --- |
| `privacy_mode` | boolean | global or cluster | Default on. Makes identifier, hostname, and metadata redaction the default behavior. |
| `no_llm` | boolean | global only | Disables LLM-backed report and optimizer generation. Reports and optimizer outcomes stay Python-owned. |
| `redact` | boolean | global | Redacts sensitive profile content for collection. Real profile collection requires redaction. |
| `redact_identifiers` | boolean | global or cluster | Redacts database, table, and SQL-like identifiers in collected/displayed safe artifacts. |
| `redact_hosts` | boolean | global or cluster | Replaces infrastructure hostnames/IPs with stable aliases. |
| `metadata_redact` | boolean | global or cluster | Redacts collected metadata context. Leave enabled unless inspecting private local artifacts only. |
| `optimizer_model` | string | global | Local optimizer model route name. Ignored when `no_llm=true`. |
| `out` | string path | global | Local generated output directory for collector workflows. Do not commit generated output. |

Browser-visible UI and trusted reports must remain raw-free regardless of these
settings. Disabling privacy controls is for private local artifacts only.

## Web Server

| Field | Type | Notes |
| --- | --- | --- |
| `host` | string | Web bind host. Use `127.0.0.1` for normal local operation. |
| `port` | positive integer | Web bind port. |

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
| `recent_parallelism` | positive integer | Overall Recent scan worker limit. |
| `recent_cm_jobs` | positive integer | CM profile/context worker limit. |
| `recent_cm_summary_limit` | positive integer | CM summary scan cap. |
| `recent_profile_analysis_limit` | positive integer | Profile analysis cap. |
| `recent_metadata_jobs` | positive integer | Metadata refresh worker limit. |
| `recent_metadata_top_limit` | non-negative integer | Number of top cases eligible for metadata refresh. |
| `recent_collect_cm_events` | boolean | Collect bounded CM event context when supported. |
| `recent_cm_events_max_events` | positive integer | Maximum CM events to summarize. |
| `recent_collect_cm_timeseries` | boolean | Collect bounded CM runtime metrics when supported. |
| `recent_cm_timeseries_top_limit` | non-negative integer | Number of top cases eligible for CM time-series refresh. |

Recent and Running web workflows do not auto-run LLM reports or optimizer jobs.

## Direct Impala Profiles

| Field | Type | Scope | Notes |
| --- | --- | --- | --- |
| `query_profile_source` | string | global or cluster | `cm` or `impala`. Use `impala` for direct daemon endpoints. |
| `impala_profile_hosts` | string list | global or cluster | One or more impalad debug web hosts or host:port values. |
| `impala_profile_port` | positive integer | global or cluster | Default daemon web port for hosts without a port. |
| `impala_profile_scheme` | string | global or cluster | `http` or `https`. |
| `impala_profile_timeout_sec` | positive integer | global or cluster | Per-request timeout. |
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
It does not write raw time-series responses or labels.

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
| `metadata_timeout_sec` | positive integer | global or cluster | Per-command timeout. |
| `metadata_max_tables` | positive integer | global or cluster | Maximum tables to inspect per metadata run. |
| `metadata_max_output_bytes` | positive integer | global or cluster | Maximum metadata output bytes. |
| `metadata_redact` | boolean | global or cluster | Redacts metadata output before artifacts are written. |

Metadata collection is read-only, allowlisted, bounded, explicit, and redacted.

## Multiple Clusters

Use `clusters` when one workstation needs several configured targets:

```json
{
  "host": "127.0.0.1",
  "port": 8765,
  "privacy_mode": true,
  "clusters": [
    {
      "id": "prod",
      "label": "Production",
      "cm_url": "https://cm-prod.example.com:7183/",
      "cluster": "prod_cluster",
      "service": "impala",
      "cm_metrics_profile": "cm7",
      "metadata_coordinator": "impala-prod-coordinator.example.com:21000"
    },
    {
      "id": "direct-impala",
      "label": "Ambari Direct Impala",
      "query_profile_source": "impala",
      "impala_profile_hosts": ["impalad-worker-1.example.com"],
      "impala_kerberos_service_name": "hive",
      "metadata_coordinator": "impala-coordinator.example.com:21000",
      "metadata_auth": "kerberos",
      "metadata_protocol": "beeswax",
      "metadata_kerberos_service_name": "hive"
    }
  ]
}
```

Cluster entries may define target, TLS, direct Impala, Prometheus, metadata,
privacy, and redaction fields. `no_llm`, web `host`/`port`, Recent scan limits,
and output paths are global.

Cluster `id` values must use only letters, digits, `.`, `_`, or `-`.

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
